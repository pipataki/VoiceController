# VoiceController -- control del ordenador por voz, pensado para accesibilidad.
# Copyright (C) 2026  pipataki <pipataki@pipataki.net>
#
# Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo
# los terminos de la Licencia Publica General Reducida GNU (LGPL)
# publicada por la Free Software Foundation, en su version 3 o
# cualquier version posterior.
#
# Se distribuye con la esperanza de que sea util, pero SIN NINGUNA GARANTIA;
# ni siquiera la garantia implicita de COMERCIABILIDAD o IDONEIDAD PARA UN
# PROPOSITO PARTICULAR. Consulta la LGPL para mas detalles.
#
# Deberias haber recibido una copia de la LGPL junto a este programa. Si
# no, ver <https://www.gnu.org/licenses/>.

"""
tts: la voz del propio VoiceController (Piper, con espeak-ng de respaldo).

Para qué se usa
---------------
1. "ayuda audio" / "ayuda con audio": lee en alto la misma lista que
   muestra el pop-up de ayuda (ver command_router._show_help).
2. "No te entiendo": aviso hablado cuando VoiceController oye algo
   dirigido a él y no sabe qué hacer con ello.

Por qué Piper y no espeak
-------------------------
espeak-ng/spd-say ya estaban instalados, pero suenan a lector de
pantalla robótico y lo que se pedía era justo lo contrario: una voz
agradable de escuchar. Piper es una red neuronal que corre EN LOCAL, sin
internet ni cuentas: medido aquí, sintetiza entre 10x y 17x más rápido
que tiempo real (98 ms para "No te entiendo"), y el modelo tarda 0,78 s
en cargarse una sola vez. espeak-ng se queda como respaldo automático:
si falta Piper o su voz, se sigue hablando aunque sea peor, en vez de
quedarse mudo.

Las tres reglas que evitan que la voz moleste
---------------------------------------------
Este es el problema real de una aplicación que habla: en la prueba con
la tele puesta, el reconocedor cerró más de 150 frases ajenas en un
rato. Decir "no te entiendo" en cada una sería insufrible, y además el
micrófono se oiría a sí mismo. Por eso:

  1. **Silencio mientras habla.** `is_speaking()` está en alto desde que
     empieza a sonar hasta un poco después de terminar
     (config.TTS_MIC_MUTE_TAIL_MS), y voice_recognizer tira el audio de
     ese rato. Sin esto, VoiceController se transcribiría a sí mismo.
  2. **Un mínimo entre avisos.** Cada categoría tiene su propio
     intervalo (config.TTS_MIN_INTERVAL_S): si el aviso anterior de esa
     misma categoría es demasiado reciente, este se descarta -- no se
     encola, se tira. Encolarlos solo retrasaría la avalancha.
  3. **Nunca en mitad de un dictado.** Un aviso hablado mientras se
     dicta interrumpe la frase y encima se mete en el micrófono. La
     ayuda pedida a propósito sí puede sonar siempre: la ha pedido el
     usuario.

Todo ocurre en un hilo aparte con una cola: `say()` vuelve
inmediatamente y nunca bloquea al reconocedor.
"""

import io
import queue
import subprocess
import threading
import time
import wave

import config

# Categorías de aviso. Cada una tiene su propio mínimo entre repeticiones
# en config.TTS_MIN_INTERVAL_S -- ver las reglas de arriba.
HELP = "help"                       # pedido a propósito: sin límite
NOT_UNDERSTOOD = "not_understood"   # "no te entiendo" a quien SÍ es el usuario
NOT_UNDERSTOOD_SHORT = "not_understood_short"   # ídem, pero de una frase corta
INTRUDER = "intruder"               # voz que no es la suya y suena dirigida a la máquina



def _voz_del_idioma() -> str:
    """La voz de Piper que toca para la lengua materna.

    Si el programa te habla en inglés tiene que sonar en inglés: Piper
    pronuncia con la fonética de SU idioma, así que la voz española leyendo
    inglés dice "te uindou" en vez de "the window". Ininteligible, y en
    accesibilidad eso equivale a no tener voz.

    Si el idioma no tiene voz descargada se usa la de siempre: quedarse
    mudo sería peor que sonar con acento.
    """
    import os
    idioma = getattr(config, "LENGUA_MATERNA", "es")
    voces = getattr(config, "TTS_PIPER_VOICES", None) or {}
    ruta = voces.get(idioma)
    if ruta and os.path.isfile(ruta):
        return ruta
    if ruta:
        print(f"[tts] no está la voz de {idioma!r} en {ruta}: "
              f"se usa la de por defecto")
    return config.TTS_PIPER_VOICE


class Speaker:
    """Cola de habla en un hilo aparte. Se construye siempre; si no hay
    ningún motor utilizable, `available` es False y say() no hace nada
    (no revienta ni bloquea)."""

    def __init__(self):
        self._voice = None          # modelo Piper ya cargado
        self._syn_config = None     # hablante + velocidad (ver _build_syn_config)
        self._engine = None         # "piper" | "espeak" | None
        self._queue = queue.Queue()
        self._thread = None
        self._speaking_until = 0.0
        self._last_said = {}        # categoría -> monotonic del último aviso
        self._lock = threading.Lock()
        self._dictating = False
        self._load_error = ""
        # Última frase dicha, en WAV, para que la webapp (móvil) pueda
        # reproducirla también -- ver _publish_for_mobile(). Se guarda una
        # sola, no una cola: si llegan dos seguidas, lo que interesa oír
        # en el móvil es la última, no ponerse al día con las viejas.
        self._mobile_id = 0
        self._mobile_wav = None

        if not getattr(config, "TTS_ENABLED", False):
            self._load_error = "desactivado en config.TTS_ENABLED"
            return
        self._engine = self._pick_engine()
        if self._engine:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    # ---------- selección de motor ----------

    def _pick_engine(self):
        preferido = getattr(config, "TTS_ENGINE", "piper")
        if preferido == "piper" and self._try_load_piper():
            return "piper"
        if preferido == "piper":
            print(f"[tts] Piper no disponible ({self._load_error}) -- "
                  "se usa espeak-ng, que suena peor pero funciona")
        if _has_binary("espeak-ng") or _has_binary("espeak"):
            return "espeak"
        self._load_error = "ni Piper ni espeak-ng disponibles"
        print(f"[tts] sin voz: {self._load_error}")
        return None

    def _try_load_piper(self) -> bool:
        """Carga el modelo YA, en el arranque, no en el primer aviso: son
        0,78 s que no deben caer justo cuando el usuario pide ayuda."""
        try:
            from piper import PiperVoice
        except ImportError as exc:
            self._load_error = f"falta el paquete piper-tts ({exc})"
            return False
        ruta = _voz_del_idioma()
        try:
            self._voice = PiperVoice.load(ruta)
        except Exception as exc:
            self._load_error = f"no se pudo cargar {ruta!r}: {exc!r}"
            return False
        self._voz_cargada = ruta
        self._syn_config = self._build_syn_config()
        nombre = ruta.rsplit("/", 1)[-1]
        print(f"[tts] voz Piper cargada: {nombre} "
              f"(voz {config.TTS_VOICE_GENDER}, velocidad {config.TTS_SPEED}x)")
        return True

    def _build_syn_config(self):
        """Traduce las preferencias de config a lo que entiende Piper:
        qué hablante usar y a qué velocidad.

        El sexo de la voz solo se puede elegir en modelos de VARIOS
        hablantes. `es_ES-sharvard-medium` trae los dos en el mismo
        fichero (`speaker_id_map = {"M": 0, "F": 1}`), así que cambiar de
        voz masculina a femenina no descarga nada ni recarga nada. En un
        modelo de un solo hablante (las de calidad `high` lo son) el sexo
        viene dado por el propio modelo y aquí solo se avisa."""
        from piper import SynthesisConfig

        speaker_id = None
        mapa = getattr(self._voice.config, "speaker_id_map", None) or {}
        num = getattr(self._voice.config, "num_speakers", 1) or 1
        if num > 1:
            quiere_f = str(getattr(config, "TTS_VOICE_GENDER", "femenina")).lower().startswith("f")
            clave = "F" if quiere_f else "M"
            if clave in mapa:
                speaker_id = mapa[clave]
            else:
                print(f"[tts] este modelo no distingue {clave!r} entre sus hablantes "
                      f"({list(mapa)}) -- se usa el primero")
        elif getattr(config, "TTS_VOICE_GENDER", None):
            print(f"[tts] {config.TTS_PIPER_VOICE.rsplit('/', 1)[-1]} tiene un solo "
                  "hablante: TTS_VOICE_GENDER no se aplica (el sexo lo fija el modelo)")

        # config.TTS_SPEED es VELOCIDAD (menos de 1 = más despacio), que es
        # como lo lee cualquiera. Piper quiere `length_scale`, que es
        # DURACIÓN y va justo al revés -- de ahí la inversión. Exponer
        # length_scale directamente era una trampa: bajar algo llamado
        # "SPEED" aceleraba la voz.
        velocidad = float(getattr(config, "TTS_SPEED", 1.0) or 1.0)
        if velocidad <= 0:
            print(f"[tts] TTS_SPEED={velocidad!r} no es válido -- se usa 1.0")
            velocidad = 1.0
        return SynthesisConfig(speaker_id=speaker_id, length_scale=1.0 / velocidad)

    # ---------- estado ----------

    @property
    def available(self) -> bool:
        return self._engine is not None

    def is_speaking(self) -> bool:
        """True mientras suena la voz Y durante la cola de seguridad
        posterior. Lo consulta voice_recognizer para tirar ese audio y no
        transcribirse a sí mismo."""
        return time.monotonic() < self._speaking_until

    def set_dictating(self, is_dictating: bool):
        self._dictating = bool(is_dictating)

    # ---------- API ----------

    def set_salida_solo_movil(self, activo: bool) -> None:
        """Mientras el micrófono del móvil esté en uso, callar el altavoz
        del PC y hablar solo por el teléfono.

        Con los dos sonando se oye la misma frase dos veces y la del móvil
        llega detrás, porque el audio tiene que subir, decodificarse y
        bajar. Pidiendo el santo y seña eso despista: oyes el principio en
        el ordenador y el final en el teléfono.

        Solo se nota estando DELANTE del ordenador; de lejos se oye una
        sola. Pero delante lía, y arreglarlo no cuesta nada."""
        with self._lock:
            self._solo_movil = bool(activo)

    def _callar_altavoz_local(self) -> bool:
        """¿Toca callarse aquí? Solo si está pedido, permitido, y el móvil
        va a recibir la frase de verdad: quedarse callado en los dos sitios
        sería mucho peor que oírlo dos veces."""
        if not getattr(config, "TTS_SOLO_MOVIL_EN_RED", True):
            return False
        if not getattr(config, "TTS_SEND_TO_MOBILE", False):
            return False
        with self._lock:
            return getattr(self, "_solo_movil", False)

    def _quizas_cambiar_de_voz(self):
        """Si ha cambiado la lengua materna, se recarga la voz.

        La lengua se puede cambiar en caliente desde el menú de la bandeja,
        y sin esto el programa se pondría a hablar inglés CON LA VOZ
        ESPAÑOLA -- que es peor que no cambiar nada, porque Piper pronuncia
        con la fonética de su idioma y no se entiende una palabra.

        Comparar dos rutas en cada aviso no cuesta nada; recargar solo pasa
        cuando de verdad cambia, y son menos de un segundo.
        """
        if self._engine != "piper":
            return
        try:
            toca = _voz_del_idioma()
            if toca == getattr(self, "_voz_cargada", None):
                return
            from piper import PiperVoice
            self._voice = PiperVoice.load(toca)
            self._voz_cargada = toca
            self._syn_config = self._build_syn_config()
            print(f"[tts] voz cambiada a {toca.rsplit('/', 1)[-1]}")
        except Exception as exc:
            print(f"[tts] no se pudo cambiar de voz ({exc!r}): "
                  f"se sigue con la que había")

    def say(self, text: str, category: str = HELP) -> bool:
        """Encola `text`. Devuelve True si se ha aceptado, False si se ha
        descartado (motor no disponible, demasiado pronto para esa
        categoría, o dictando). NUNCA bloquea."""
        if not self.available or not text:
            return False

        self._quizas_cambiar_de_voz()

        if category != HELP:
            if self._dictating:
                # un aviso hablado en mitad de una frase dictada la
                # interrumpe y encima se cuela por el micrófono
                return False
            min_interval = config.TTS_MIN_INTERVAL_S.get(category, 0)
            if min_interval is None:
                return False    # esta categoría está silenciada del todo
            with self._lock:
                last = self._last_said.get(category, 0.0)
                now = time.monotonic()
                if now - last < min_interval:
                    return False   # se DESCARTA, no se encola: encolarlo
                                   # solo retrasaría la avalancha
                self._last_said[category] = now
        self._queue.put(text)
        return True

    # ---------- hilo ----------

    def _run(self):
        while True:
            text = self._queue.get()
            try:
                self._speak_blocking(text)
            except Exception as exc:
                print(f"[tts] error hablando: {exc!r}")

    def _publish_for_mobile(self, pcm: bytes, rate: int):
        """Deja la frase disponible en WAV para que el móvil la reproduzca.

        Se envuelve en WAV (y no se manda el PCM crudo) porque así el
        navegador la reproduce con un <audio> normal, sin Web Audio ni
        decodificación a mano.

        El móvil la recoge en el HUECO ENTRE TROZOS de grabación, que es
        cuando su micrófono está parado (ver stopBtn.onclick en
        index.html): si sonara con el micrófono abierto, el propio móvil
        se grabaría a sí mismo y mandaría la voz de VoiceController de
        vuelta al PC como si fuera una orden."""
        if not getattr(config, "TTS_SEND_TO_MOBILE", False):
            return
        try:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(pcm)
            with self._lock:
                self._mobile_id += 1
                self._mobile_wav = buf.getvalue()
        except Exception as exc:
            print(f"[tts] no se pudo preparar el audio para el móvil: {exc!r}")

    def mobile_pending(self):
        """(id, wav_bytes) de lo último dicho, o (0, None) si no hay nada.
        Lo consulta webapp/app.py."""
        with self._lock:
            return self._mobile_id, self._mobile_wav

    def _speak_blocking(self, text: str):
        if self._engine == "piper":
            self._speak_piper(text)
        else:
            self._speak_espeak(text)

    def _speak_piper(self, text: str):
        chunks = list(self._voice.synthesize(text, syn_config=self._syn_config))
        if not chunks:
            return
        rate = chunks[0].sample_rate           # Piper entrega a 22050 Hz
        pcm = b"".join(c.audio_int16_bytes for c in chunks)
        seconds = len(pcm) / (2 * rate)

        # La marca se pone ANTES de empezar a sonar y cubre todo el audio
        # más la cola de seguridad: si se pusiera después, el principio de
        # la frase ya se habría colado por el micrófono.
        self._speaking_until = (time.monotonic() + seconds
                                + config.TTS_MIC_MUTE_TAIL_MS / 1000.0)

        self._publish_for_mobile(pcm, rate)

        # La frase ya está lista para el móvil. Si el micrófono en uso es el
        # suyo, aquí se acaba: sonaría dos veces y desfasada.
        if self._callar_altavoz_local():
            return

        # En Windows no hay paplay: se reproduce por la capa de plataforma
        # (winsound, que viene con Python). Se hace antes de todo lo demás
        # para no tocar la ruta de Linux, que tiene su propio respaldo.
        import sys as _sys
        if _sys.platform.startswith("win"):
            import backends
            if backends.play_wav(pcm, rate):
                return
            print("[tts] no se pudo reproducir en Windows")
            return

        # paplay primero: la tarjeta de salida de esta máquina NO acepta
        # los 22050 Hz de Piper (`Invalid sample rate` de PortAudio), y
        # PulseAudio/PipeWire remuestrea solo y además mezcla con lo que
        # ya esté sonando en vez de pelearse por el dispositivo. Se le
        # pasa el PCM crudo por la entrada estándar: sin ficheros
        # temporales.
        if _has_binary("paplay"):
            try:
                subprocess.run(
                    ["paplay", "--raw", f"--rate={rate}", "--channels=1",
                     "--format=s16le"],
                    input=pcm, check=True, capture_output=True,
                    timeout=max(10.0, seconds * 3),
                )
                return
            except Exception as exc:
                print(f"[tts] paplay falló ({exc!r}) -- se intenta con sounddevice")

        # Respaldo: sounddevice, remuestreando a mano a la frecuencia
        # nativa del dispositivo de salida (interpolación lineal, de
        # sobra para voz).
        import numpy as np
        import sounddevice as sd

        audio = np.frombuffer(pcm, dtype=np.int16)
        try:
            dev_rate = int(sd.query_devices(kind="output")["default_samplerate"])
        except Exception:
            dev_rate = rate
        if dev_rate != rate:
            n = int(len(audio) * dev_rate / rate)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, n),
                np.arange(len(audio)),
                audio.astype(np.float32),
            ).astype(np.int16)
        sd.play(audio, dev_rate)
        sd.wait()

    def _speak_espeak(self, text: str):
        binario = "espeak-ng" if _has_binary("espeak-ng") else "espeak"
        # espeak no dice de antemano cuánto durará: se estima por el
        # número de palabras y la velocidad configurada, con margen de
        # sobra -- vale para la cola de silencio del micrófono.
        estimado = max(1.0, len(text.split()) / 2.5)
        self._speaking_until = (time.monotonic() + estimado
                                + config.TTS_MIC_MUTE_TAIL_MS / 1000.0)
        # --stdout devuelve el WAV en vez de reproducirlo: así el respaldo
        # también puede mandarse al móvil, igual que Piper.
        res = subprocess.run([binario, "-v", "es", "-s", "150", "--stdout", text],
                             check=False, capture_output=True,
                             timeout=_timeout_audio())
        if res.returncode == 0 and res.stdout:
            try:
                with wave.open(io.BytesIO(res.stdout), "rb") as w:
                    self._publish_for_mobile(w.readframes(w.getnframes()),
                                             w.getframerate())
            except Exception:
                pass
            if self._callar_altavoz_local():
                return
            # res.stdout ya es un WAV completo (con cabecera), así que
            # play_wav no necesita `rate`.
            import sys as _sys
            if _sys.platform.startswith("win"):
                import backends
                if backends.play_wav(res.stdout):
                    return
            elif _has_binary("paplay"):
                subprocess.run(["paplay"], input=res.stdout,
                               check=False, capture_output=True,
                               timeout=_timeout_audio())
                return
        if not self._callar_altavoz_local():
            subprocess.run([binario, "-v", "es", "-s", "150", text],
                           check=False, capture_output=True,
                           timeout=_timeout_audio())
        self._speaking_until = time.monotonic() + config.TTS_MIC_MUTE_TAIL_MS / 1000.0


def _timeout_audio() -> float:
    """Limite de espera para espeak y para el reproductor.

    Es una red de seguridad, no un recorte: reproducir dura lo que dura
    el audio, y una ayuda larga puede durar bastante. Por eso el valor
    por defecto (config.AUDIO_TIMEOUT_S) es deliberadamente holgado --
    solo debe saltar si el proceso se ha quedado colgado de verdad, y
    nunca cortar una frase por la mitad."""
    try:
        return float(getattr(config, "AUDIO_TIMEOUT_S", 120.0) or 120.0)
    except Exception:
        return 120.0


def _has_binary(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


# Instancia única, creada por main.py y compartida con el router y el
# reconocedor (que solo necesita is_speaking()).
_speaker = None


def get_speaker() -> Speaker:
    global _speaker
    if _speaker is None:
        _speaker = Speaker()
    return _speaker


def is_speaking() -> bool:
    """Atajo sin efectos secundarios para voice_recognizer: si nadie ha
    creado todavía el Speaker, nadie está hablando."""
    return _speaker is not None and _speaker.is_speaking()
