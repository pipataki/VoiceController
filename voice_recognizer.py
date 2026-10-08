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
Motor de reconocimiento de voz offline (Vosk) con dos modelos (ES y EN)
alimentados con el mismo audio.

El selector del tray marca una lengua primaria; si ambas devuelven algo,
siempre gana la primaria. La secundaria solo se usa si la primaria no
reconoce nada, para evitar que las dos secciones se activen a la vez.

El listener corre en su propio hilo y nunca se detiene salvo con stop().
Emite resultados (parciales y finales) a través de callbacks thread-safe;
la GUI se encarga de despachar eso al hilo de Qt con señales.
"""

import json
import queue
import threading

import numpy as np
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel, SpkModel

import cesion_microfono
import config
import prosody
import speaker_id
import tts

SetLogLevel(-1)  # silencia el log interno de Vosk/Kaldi


def _compute_rms(data: bytes) -> float:
    """RMS (0-32767 aprox) de un bloque de audio PCM16 mono."""
    if not data:
        return 0.0
    arr = np.frombuffer(data, dtype=np.int16)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


# Se levanta cuando el microfono esta ABIERTO y entregando audio, y se baja
# al cerrarlo.
#
# Hace falta porque el programa arranca al reves de lo que parece: la ventana
# sale la primera y el microfono se abre el ultimo, despues de cargar el
# modelo de voz, que es lo que mas tarda. Entre medias se pedia el santo y
# sena -- por pantalla Y EN VOZ ALTA -- sin que hubiera nada escuchando.
#
# En un equipo rapido no se nota. En uno lento son treinta segundos hablando
# al vacio, y quien no ve la pantalla no tiene forma de saber que pasa: para
# esa persona la voz es la unica senal que hay.
MICROFONO_ABIERTO = threading.Event()


def esperar_microfono(timeout: float = 90.0) -> bool:
    """Bloquea hasta que el microfono este escuchando. False si se agota.

    Pensado para avisos que solo tienen sentido cuando alguien puede
    contestarlos. Con timeout siempre: mas vale un aviso a destiempo que un
    programa mudo esperando algo que no va a pasar.
    """
    return MICROFONO_ABIERTO.wait(timeout)


class _MotorVacio:
    """Ocupa el sitio del idioma que no está instalado.

    Cumple la parte de la interfaz de KaldiRecognizer que se usa aquí y no
    reconoce nada nunca. Así `_pick_preferred` se queda siempre con el otro
    idioma, sin que haya que comprobar en cada llamada si el motor existe.
    """

    def AcceptWaveform(self, data):  return False
    def Result(self):                return "{}"
    def PartialResult(self):         return '{"partial": ""}'
    def FinalResult(self):           return "{}"
    def SetWords(self, activado):    pass
    def SetSpkModel(self, modelo):   pass


def _devolver_memoria_al_sistema():
    """Obliga a glibc a devolver al sistema lo que ya está liberado.

    NO SOBRA, y costó verlo. Al cambiar de idioma se suelta el modelo
    grande viejo ANTES de cargar el nuevo, precisamente para que no
    coincidan los dos en memoria. Pero soltarlo en Python no basta: glibc
    se queda las páginas para reutilizarlas y no se las devuelve al núcleo
    hasta que le viene bien. Medido el 5-sep-2026 en un cambio real:

        antes del cambio (es principal) ....  3.450 MB
        PICO durante el cambio ............ 10.772 MB   <-- los dos a la vez
        después del cambio (en principal) ..  7.477 MB

    Ese pico es justo lo que se quería evitar. Con malloc_trim(0) las
    páginas vuelven en el acto:

        modelo grande cargado ....  3.414 MB
        tras soltarlo ..............  530 MB
        tras malloc_trim(0) .........  67 MB

    De paso se lleva el residuo de ~700 MB que parecía inevitable.

    Solo existe en glibc (Linux). En Windows y en cualquier otra libc no
    está y no pasa nada: se sigue como antes, con el pico alto pero
    funcionando.
    """
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass          # no es glibc: nada que hacer, y no es grave


class DualLanguageRecognizer:
    def __init__(self, on_partial, on_final, on_audio_level=None):
        """
        on_partial(text: str)  -> se llama con texto parcial (mientras se habla)
        on_final(text: str, confidence: float, language: str, sentence_type: str)
            -> se llama cuando una frase se considera cerrada. sentence_type
            es "statement" | "question" | "exclamation" | "suggestion",
            estimado por prosody.py a partir de la entonación + el propio
            texto (ver ahí las limitaciones de esa estimación).
        on_audio_level(is_silent: bool, rms: float) -> opcional. Se llama en
            cada bloque de audio procesado con el estado del detector de
            silencio (VAD ligero por energía, ver config.SILENCE_*). Sirve
            solo como señal informativa (p.ej. un LED en la GUI) y, además,
            se usa aquí para no propagar texto parcial mientras se considera
            silencio (evita que quede "colgado" texto residual entre frases).
        """
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_audio_level = on_audio_level

        # estado del VAD por energía: empieza en "silencio" hasta el primer
        # bloque con energía suficiente
        self._is_silent = True
        self._silence_hangover = 0
        # bloques descartados por cola llena (solo para avisar, ver
        # _audio_callback)
        self._overflow_blocks = 0

        # True solo mientras command_router está en estado DICTATING (lo fija
        # set_dictating(), llamado desde CommandRouter._set_state()). El
        # análisis de prosodia (y por tanto el "formato humano" del texto)
        # SOLO tiene sentido dictando texto: en estado de escucha (silencio)
        # únicamente se admiten acciones, nunca texto, así que ahí no se
        # gasta CPU clasificando entonación de algo que no se va a escribir.
        self._dictating = False

        # True mientras el router está esperando el santo y seña: la
        # verificación usa entonces su propio umbral, bastante más
        # exigente (ver speaker_id.threshold y config.VOICE_LOGIN_*). Sin
        # esto se comprobaría con el umbral de comandos (0,18), pensado
        # para no rechazarle NUNCA -- con el que cualquier voz ajena
        # entraría.
        self._awaiting_login = False

        self._audio_q: "queue.Queue[bytes]" = queue.Queue()
        self._stop_event = threading.Event()
        # Testigo de "vida" de la sesión de escucha en curso. Cada start()/
        # start_network() crea uno nuevo; el hilo de proceso solo sigue vivo
        # mientras el suyo siga siendo el actual. Sin esto, un stop() cuyo
        # join() venciera dejaba un hilo huérfano que _resucitaba_ en el
        # siguiente start() (que hace _stop_event.clear()), quedando DOS
        # hilos metiendo audio en el MISMO KaldiRecognizer -- ver stop().
        self._run_token = None
        self._stream = None
        self._thread = None
        self._state_lock = threading.Lock()
        self._running = False

        # True si el micrófono LOCAL se ha quedado sin abrir (o se ha
        # cerrado) por habérselo cedido a otra aplicación: al devolverlo hay
        # que volver a abrirlo. Si en ese rato se pasa al móvil, se olvida
        # (ver cesion_microfono y ceder_microfono()).
        self._reabrir_al_devolver = False
        self._cesion_lock = threading.Lock()

        # La lengua MATERNA manda: es la que dicta y la que cuenta.
        # Ver config.LENGUA_MATERNA.
        self.language_mode = getattr(config, "LENGUA_MATERNA", "es")
        self._cambiando_idioma = False   # ver _cambiar_de_par()

        # Cada idioma se carga por separado y SIN tumbar el programa si
        # falta. Antes se cargaban los dos a pelo: quien no tuviera el
        # modelo de inglés (el instalador de Windows solo baja el español,
        # y son 3,8 GB más) se quedaba sin NADA de reconocimiento, con un
        # "Failed to create a model" que no dice qué idioma falló.
        # Los 6 GB de los dos modelos tampoco caben en cualquier máquina.
        self._cargar_par(self.language_mode)
        if self._model_es is None and self._model_en is None:
            raise RuntimeError(
                "no hay ningún modelo de voz: descarga al menos uno en "
                f"{config.VOSK_MODELS_DIR} (los baja el instalador)")
        if self._model_en is None:
            self.language_mode = "es"
        elif self._model_es is None:
            self.language_mode = "en"

        # Reconocimiento de locutor (ver speaker_id.py): el modelo solo se
        # carga si hay perfil Y está activado -- así, sin perfil, todo
        # sigue funcionando exactamente igual que antes y no se gastan
        # 15 MB ni un segundo de arranque en algo que no se va a usar.
        # Un verificador por micrófono: cada uno con su perfil (ver
        # speaker_id.SpeakerVerifier, config.SPEAKER_PROFILE_FILE*).
        self._verifiers = {
            "device": speaker_id.SpeakerVerifier("device"),
            "network": speaker_id.SpeakerVerifier("network"),
        }
        self._verifier = self._verifiers["device"]

        # Callback de ENROLADO: mientras esté puesto, cada x-vector del
        # micrófono indicado se entrega tal cual en vez de verificarse.
        # Es como se graba el perfil del móvil sin sacar el audio de aquí
        # (ver command_router.start_mobile_enrollment).
        self._enroll_source = None
        self._enroll_cb = None
        self._spk_model = None
        # interruptor en caliente (bandeja del sistema). Arranca reflejando
        # config.SPEAKER_ID_ENABLED, pero puede apagarse sin reiniciar.
        self._speaker_filter_on = True
        if self._verifier.enabled:
            try:
                self._spk_model = SpkModel(config.SPEAKER_ID_MODEL)
                print(f"[voice_recognizer] reconocimiento de locutor ACTIVO "
                      f"(modo {config.SPEAKER_ID_MODE}) -- {self._verifier.reason}")
            except Exception as exc:
                print(f"[voice_recognizer] no se pudo cargar el modelo de locutor "
                      f"({exc!r}) -- se sigue SIN filtrar por voz")
                self._verifier.profile = None
        else:
            print(f"[voice_recognizer] reconocimiento de locutor inactivo: "
                  f"{self._verifier.reason}")

        self._rec_es = None
        self._rec_en = None

        # "device" -> micrófono local (sounddevice); "network" -> audio que
        # llega ya decodificado desde la webapp (micrófono remoto del móvil)
        self._mode = "device"

        # Último micrófono LOCAL elegido (config o bandeja del sistema).
        # Es al que se vuelve tras una sesión del móvil -- ver
        # set_input_device("original").
        self._last_local_device = config.INPUT_DEVICE

        # samplerate at which the input device actually provides audio.
        # Determined on start() and used directly by recognizers.
        self._input_samplerate = None

        # acumula el audio de la frase en curso, para poder analizar su
        # entonación (prosody.py) en cuanto Vosk marca un resultado final
        self._utterance_pcm = bytearray()

        # PICO de energía (RMS) de la frase en curso. Es la señal de "esto
        # se ha dicho CERCA del micrófono": alguien delante del ordenador
        # pica alto, una tele al fondo de la habitación no. La usa el
        # detector de intrusos del router (ver _register_intruder_strike),
        # que necesita distinguir "hay una tele puesta" de "hay alguien
        # dándole órdenes a mi ordenador". Se coge el pico y no la media
        # porque una frase corta dicha de cerca puede llevar mucho silencio
        # alrededor y la media la hundiría.
        self._utterance_peak_rms = 0.0

        # firma del callback on_final que resultó válida (ver _emit_final)
        self._final_signature = None

    def set_language_mode(self, mode: str):
        """mode: lengua primaria: 'es' o 'en'.

        SE LLAMA CONTINUAMENTE, no solo al cambiar de idioma:
        command_router._set_state() la invoca en cada cambio de estado
        (IDLE <-> DICTATING). Por eso lo primero es salir si no cambia
        nada; si no, cada vez que se entrase en dictado se recargarían los
        modelos.
        """
        assert mode in ("es", "en")
        if mode == self.language_mode:
            return
        if not self._hay_que_cambiar_de_modelos(mode):
            # Los dos grandes cargados: como siempre, una bandera.
            modelo = self._model_es if mode == "es" else self._model_en
            if modelo is None:
                print(f"[voice_recognizer] no se puede cambiar a {mode!r}: "
                      f"ese modelo no está instalado")
                return
            self.language_mode = mode
            return
        self._cambiar_de_par(mode)

    def _cambiar_de_par(self, mode: str):
        """Cambia el idioma principal RECARGANDO los modelos.

        Con el secundario pequeño, cambiar de principal ya no es una
        bandera: el idioma que entra necesita su modelo grande y el que
        sale suelta el suyo. Son unos 7 s en los que no se reconoce nada.

        EN SU PROPIO HILO, y no es un adorno. Quien pide el cambio suele
        ser el router, que corre en el hilo del reconocedor -- el mismo que
        hay que parar. Llamar a stop() desde ahí sería un join() sobre uno
        mismo. Al hacerlo aparte, stop() invalida el testigo, el hilo viejo
        termina lo que estaba haciendo y muere solo (ver stop()).

        Si el join de 2 s vence, el hilo viejo aún sostiene sus
        recognizers un rato más y la memoria tarda un poco más en volver.
        No es grave y queda dicho en el log.
        """
        if self._cambiando_idioma:
            print(f"[voice_recognizer] ya se está cambiando de idioma: "
                  f"se ignora la petición de {mode!r}")
            return
        self._cambiando_idioma = True

        def faena():
            import time as _t
            t0 = _t.time()
            try:
                estaba = self._running
                fuente = self._mode
                print(f"[voice_recognizer] cambiando idioma principal a "
                      f"{mode!r}: recargando modelos (unos segundos sin "
                      f"reconocer)")
                if estaba:
                    self.stop()
                self._cargar_par(mode)
                self.language_mode = mode
                if estaba:
                    if fuente == "network":
                        self.start_network()
                    else:
                        self.start()
                print(f"[voice_recognizer] idioma principal ya es {mode!r} "
                      f"({_t.time() - t0:.1f}s)")
            except Exception as exc:
                print(f"[voice_recognizer] falló el cambio de idioma: {exc!r}")
            finally:
                self._cambiando_idioma = False

        threading.Thread(target=faena, name="cambio-idioma",
                         daemon=True).start()

    def set_speaker_filter_enabled(self, enabled: bool):
        """Enciende/apaga el filtro por voz en caliente, desde el
        interruptor de la bandeja (ver gui._toggle_speaker_filter). No
        recarga ni descarga nada: el modelo de locutor ya está cargado (o
        no lo está y entonces no hay nada que encender), solo se deja de
        consultar el veredicto."""
        if enabled and self._spk_model is None:
            print("[voice_recognizer] no se puede activar el filtro por voz: "
                  "no hay modelo/perfil cargado (hace falta reiniciar tras crearlo)")
            return
        self._speaker_filter_on = bool(enabled)
        print(f"[voice_recognizer] filtro por voz "
              f"{'ACTIVADO' if self._speaker_filter_on else 'DESACTIVADO'}")

    def set_enrollment(self, source, callback):
        """Empieza (o para, con callback=None) el enrolado de un
        micrófono. Mientras esté activo, las frases de ESE micrófono no se
        verifican -- se entrega su x-vector al recolector, que es quien
        va montando el perfil nuevo.

        Vive aquí y no en un script aparte porque el audio del móvil llega
        por la webapp, que corre DENTRO de este mismo proceso: un script
        externo no tendría forma de verlo."""
        # El modelo de locutor se carga AQUI si hace falta.
        #
        # Normalmente solo se carga cuando ya hay un perfil, para no gastar
        # 15 MB en algo que no se va a usar. Pero eso dejaba un punto
        # muerto: al conectar el movil por primera vez se lanza su
        # enrolado, el enrolado necesita x-vectors, los x-vectors necesitan
        # este modelo... y el modelo no estaba porque aun no habia perfil.
        # El sintoma era "muestra sin x-vector: se repite" en bucle, sin
        # que se pudiera terminar nunca.
        if callback is not None and self._spk_model is None:
            self._cargar_modelo_locutor()
        self._enroll_source = source
        self._enroll_cb = callback
        print(f"[voice_recognizer] enrolado de {source!r}: "
              f"{'ACTIVO' if callback else 'terminado'}")

    def _cargar_modelo_locutor(self):
        """Carga el modelo de locutor y lo aplica a los reconocedores que ya
        estén en marcha (si no, el cambio no surtiría efecto hasta
        reiniciar)."""
        import os
        if not os.path.isdir(config.SPEAKER_ID_MODEL):
            print(f"[voice_recognizer] no está el modelo de locutor en "
                  f"{config.SPEAKER_ID_MODEL}: no se pueden sacar x-vectors")
            return False
        try:
            self._spk_model = SpkModel(config.SPEAKER_ID_MODEL)
        except Exception as exc:
            print(f"[voice_recognizer] no se pudo cargar el modelo de "
                  f"locutor ({exc!r})")
            return False
        for rec in (self._rec_es, self._rec_en):
            if rec is None:
                continue
            try:
                rec.SetSpkModel(self._spk_model)
            except Exception as exc:
                print(f"[voice_recognizer] SetSpkModel falló: {exc!r}")
        print("[voice_recognizer] modelo de locutor cargado bajo demanda")
        return True

    def reload_profiles(self):
        """Vuelve a leer los perfiles del disco. Se llama tras grabar uno
        nuevo, para que empiece a usarse sin reiniciar."""
        for src in list(self._verifiers):
            self._verifiers[src] = speaker_id.SpeakerVerifier(src)
        self._verifier = self._verifiers["device"]
        print("[voice_recognizer] perfiles de voz recargados: "
              + ", ".join(f"{k}={'sí' if v.enabled else 'no'}"
                          for k, v in self._verifiers.items()))

    def set_awaiting_login(self, awaiting: bool):
        """El router avisa de si está esperando el santo y seña, para que
        la verificación use su umbral propio. Mismo mecanismo que
        set_dictating(), y por el mismo motivo: quien conoce el estado es
        el router, pero quien tiene el x-vector es este módulo."""
        self._awaiting_login = bool(awaiting)

    def set_dictating(self, is_dictating: bool):
        """Informa al reconocedor si estamos en DICTATING (para que solo
        entonces analice prosodia). Lo llama CommandRouter en cada cambio
        de estado."""
        self._dictating = bool(is_dictating)

    def set_formuling(self, is_formuling: bool):
        """Llamado desde CommandRouter cada vez que cambia
        al estado matematico/cientifico.
        Controla si se analiza prosodia (ver _process_chunk)."""
        self._formuling = bool(is_formuling)





    def _drain_queue(self):
        """Vacía la cola de audio pendiente. Se llama al parar Y al arrancar:
        el audio que quedara encolado pertenece a la sesión ANTERIOR, y casi
        siempre a otro sample rate (48000 del micro local vs 16000 del móvil),
        así que alimentárselo al reconocedor nuevo es meterle ruido puro --
        justo lo que inflaba la retícula de Kaldi hasta el aviso de
        'Did not reach requested beam ... exceeds maximum 50000000 bytes'."""
        dropped = 0
        while True:
            try:
                self._audio_q.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        if dropped:
            print(f"[voice_recognizer] descartados {dropped} bloques de audio "
                  f"de la sesión anterior")

    @staticmethod
    def _cargar_modelo(ruta, idioma):
        """El modelo, o None si no está. No es fatal: se puede trabajar en
        un solo idioma."""
        import os
        if not os.path.isdir(ruta):
            print(f"[voice_recognizer] sin modelo de {idioma} en {ruta} -- "
                  f"ese idioma queda desactivado")
            return None
        try:
            return Model(ruta)
        except Exception as exc:
            print(f"[voice_recognizer] el modelo de {idioma} no se pudo cargar "
                  f"({exc!r}) -- ese idioma queda desactivado")
            return None

    # ------------------------------------------------------------------
    # EL PAR DE MODELOS: grande el principal, pequeño el secundario
    # ------------------------------------------------------------------
    #
    # El secundario no dicta NUNCA. Mientras se dicta, todo lo que produce
    # sale como "descartado (idioma secundario en dictado, no es comando)":
    # solo se le pregunta si lo oído es uno de los comandos de su lista,
    # que es corta y cerrada.
    #
    # Sostener un modelo grande para eso costaba 6.686 MB de RAM y la mitad
    # de la CPU (cada trozo de audio se decodifica dos veces). Ver la
    # sección de modelos en config.py, con las medidas.

    @staticmethod
    def _rutas_del_par(principal: str):
        """(ruta_es, ruta_en) según quién sea el idioma principal.

        Si el pequeño que toca no está descargado se usa el grande: esto
        no puede dejar a nadie sin idioma por una descarga que falte.
        """
        import os
        grande = {"es": config.VOSK_MODEL_ES, "en": config.VOSK_MODEL_EN}
        if not getattr(config, "SECONDARY_SMALL_MODEL", True):
            return grande["es"], grande["en"]
        pequeno = {"es": getattr(config, "VOSK_MODEL_ES_SMALL", ""),
                   "en": getattr(config, "VOSK_MODEL_EN_SMALL", "")}
        rutas = {}
        for idioma in ("es", "en"):
            if idioma == principal:
                rutas[idioma] = grande[idioma]
            elif os.path.isdir(pequeno[idioma]):
                rutas[idioma] = pequeno[idioma]
            else:
                print(f"[voice_recognizer] no está el modelo pequeño de "
                      f"{idioma} ({pequeno[idioma]}): se usa el grande")
                rutas[idioma] = grande[idioma]
        return rutas["es"], rutas["en"]

    def _cargar_par(self, principal: str):
        """Carga los dos modelos para ese principal. Suelta los de antes."""
        # Soltar ANTES de cargar, no después: si se hiciera al revés, en el
        # cambio de idioma se juntarían los dos grandes en memoria y el pico
        # sería peor que no haber tocado nada.
        self._model_es = None
        self._model_en = None
        self._rec_es = None
        self._rec_en = None
        import gc
        gc.collect()
        _devolver_memoria_al_sistema()

        import os
        ruta_es, ruta_en = self._rutas_del_par(principal)
        self._model_es = self._cargar_modelo(ruta_es, "español")
        self._model_en = self._cargar_modelo(ruta_en, "inglés")
        print(f"[voice_recognizer] modelos para principal={principal!r}: "
              f"es={os.path.basename(ruta_es)} en={os.path.basename(ruta_en)}")

    def _hay_que_cambiar_de_modelos(self, mode: str) -> bool:
        """¿Cambiar de idioma principal exige recargar modelos?

        Solo si el secundario es pequeño. Con los dos grandes cargados --
        el comportamiento antiguo -- cambiar de idioma sigue siendo gratis:
        una bandera y ya.
        """
        return self._rutas_del_par(mode) != self._rutas_del_par(
            self.language_mode)

    def _init_recognizers(self, sample_rate: int):
        # Para el idioma que no esté se pone un motor vacío en vez de None:
        # así el resto del código sigue llamando a AcceptWaveform/Result sin
        # comprobar nada, y no hay que sembrar el fichero de "if is None".
        self._rec_es = (KaldiRecognizer(self._model_es, sample_rate)
                        if self._model_es is not None else _MotorVacio())
        self._rec_en = (KaldiRecognizer(self._model_en, sample_rate)
                        if self._model_en is not None else _MotorVacio())
        # A LOS DOS: el x-vector lo trae el resultado del motor que cierre
        # la frase, y cuál sea depende del idioma que se haya oído (ver
        # _pick_preferred). Si solo se le pusiera al español, cualquier
        # frase cerrada por el inglés llegaría sin vector y se trataría
        # como no verificada. El coste medido es despreciable.
        if self._spk_model is not None:
            for rec in (self._rec_es, self._rec_en):
                try:
                    rec.SetSpkModel(self._spk_model)
                except Exception as exc:
                    print(f"[voice_recognizer] SetSpkModel falló: {exc!r}")
        for rec in (self._rec_es, self._rec_en):
            rec.SetWords(True)

    # ---------- ciclo de vida ----------

    def start(self):
        with self._state_lock:
            if self._running:
                return
            if cesion_microfono.cedido():
                # Otra aplicación tiene el micrófono pedido: se abrirá
                # cuando lo devuelva (recuperar_microfono()).
                self._reabrir_al_devolver = True
                print("[voice_recognizer] micrófono cedido a otra aplicación: "
                      "se abrirá cuando lo devuelva")
                return

            self._stop_event.clear()
            self._drain_queue()
            self._mode = "device"
            # El ordenador vuelve a hablar por su altavoz: quien escucha
            # está otra vez delante de él.
            try:
                tts.get_speaker().set_salida_solo_movil(False)
            except Exception:
                pass
            try:
                devinfo = sd.query_devices(config.INPUT_DEVICE, "input")
                self._input_samplerate = int(devinfo.get("default_samplerate", config.SAMPLE_RATE))
                dev_name = devinfo.get("name")
            except Exception:
                self._input_samplerate = config.SAMPLE_RATE
                dev_name = str(config.INPUT_DEVICE)

            print(f"[voice_recognizer] opening input device={dev_name!r} samplerate={self._input_samplerate}")
            self._init_recognizers(int(self._input_samplerate))
            self._utterance_pcm = bytearray()
            token = object()
            self._run_token = token

            self._stream = sd.RawInputStream(
                samplerate=self._input_samplerate,
                blocksize=config.AUDIO_BLOCKSIZE,
                device=config.INPUT_DEVICE,
                dtype="int16",
                channels=1,
                callback=self._audio_callback,
            )
            self._stream.start()
            MICROFONO_ABIERTO.set()
            self._thread = threading.Thread(
                target=self._process_loop,
                args=(token, self._rec_es, self._rec_en),
                daemon=True,
            )
            self._thread.start()
            self._running = True

    def start_network(self):
        """Arranca el reconocedor en modo 'micrófono de red': no abre ningún
        stream local; el audio (ya decodificado a PCM16 mono a
        config.SAMPLE_RATE Hz) llega vía feed_external_audio(), típicamente
        reenviado desde el endpoint /receive_audio de la webapp."""
        with self._state_lock:
            if self._running:
                return

            self._stop_event.clear()
            self._drain_queue()
            self._mode = "network"
            # En modo red NO hay micrófono local que abrir, pero SÍ se está
            # escuchando -- por el del móvil. Sin esto, el aviso de "ya
            # escucho" no se levantaba nunca aquí y la petición del santo y
            # seña se quedaba esperando los 90 segundos del tope, con el
            # cartel parpadeando todo ese rato.
            #
            # Lo notó él en cuanto conectó el móvil: el arreglo de ayer
            # cubría el micrófono del PC y se dejaba este caso fuera.
            MICROFONO_ABIERTO.set()
            # Con el micrófono del móvil, el ordenador se calla: la frase
            # llega por el teléfono, y sonando en los dos sitios se oye
            # dos veces y desfasada (ver TTS_SOLO_MOVIL_EN_RED).
            try:
                tts.get_speaker().set_salida_solo_movil(True)
            except Exception:
                pass
            self._input_samplerate = config.SAMPLE_RATE
            self._stream = None

            print(f"[voice_recognizer] modo red activo: esperando audio de la webapp (samplerate={self._input_samplerate})")
            self._init_recognizers(int(self._input_samplerate))
            self._utterance_pcm = bytearray()
            token = object()
            self._run_token = token

            self._thread = threading.Thread(
                target=self._process_loop,
                args=(token, self._rec_es, self._rec_en),
                daemon=True,
            )
            self._thread.start()
            self._running = True

    def feed_external_audio(self, data: bytes):
        """Encola audio PCM16 mono (a config.SAMPLE_RATE Hz) recibido desde
        una fuente externa (micrófono remoto de la webapp). Se ignora si el
        reconocedor no está corriendo en modo 'network'."""
        if self._mode != "network" or not self._running:
            return
        self._audio_q.put(data)

    def stop(self):
        with self._state_lock:
            # Un stop() explícito (salir, cambiar de micrófono, pasar al
            # móvil) anula la reapertura pendiente; quien quiera el local
            # otra vez llamará a start().
            self._reabrir_al_devolver = False
            if not self._running:
                return
            # invalidar el testigo ANTES que nada: aunque el join() de abajo
            # venza (el hilo puede estar minutos dentro de un AcceptWaveform
            # con una retícula enorme), el hilo viejo ya no podrá volver al
            # bucle -- ni siquiera después del _stop_event.clear() del
            # siguiente start()
            self._run_token = None
            self._stop_event.set()
            # Se baja SIEMPRE, no solo si habia microfono local: en modo red
            # no hay flujo que cerrar, y sin esto el aviso de "ya escucho"
            # se quedaria levantado con el reconocedor parado.
            MICROFONO_ABIERTO.clear()
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
                MICROFONO_ABIERTO.clear()
            if self._thread is not None:
                self._thread.join(2)
                if self._thread.is_alive():
                    # no es fatal (el testigo ya lo tiene condenado y sus
                    # recognizers son solo suyos), pero conviene verlo en el
                    # log: significa que el reconocimiento va por detrás del
                    # audio en tiempo real
                    print("[voice_recognizer] el hilo de reconocimiento no "
                          "terminó en 2s; se le deja morir solo (ya no "
                          "procesará audio nuevo)")
                self._thread = None
            self._drain_queue()
            self._running = False

    def set_input_device(self, device_id):
        """Cambia el micrófono en caliente.

        `device_id` admite: un índice numérico, un nombre de dispositivo,
        "default" (el que diga el sistema) o **"original"** (el que
        estuviera configurado antes de irse al micrófono de red).

        "original" existe por un fallo concreto: al terminar la sesión del
        móvil se volvía con "default", que pone config.INPUT_DEVICE = None
        -- o sea, el micrófono POR DEFECTO DEL SISTEMA, que no tiene por
        qué ser el que el usuario tenía configurado. En su máquina el suyo
        es el 5 ('acp: - (hw:3,0)') y el del sistema es otro: el
        reconocedor "volvía" a un micrófono que no era el suyo y parecía
        que no volvía nunca. Y encima config.INPUT_DEVICE se quedaba en
        None, así que el ajuste original se perdía hasta reiniciar.
        """
        if device_id in ("original", "local"):
            target = self._last_local_device
            print(f"[voice_recognizer] volviendo al micrófono de siempre: {target!r}")
        elif device_id in (None, "", "default"):
            target = None
        else:
            try:
                target = int(device_id)
            except Exception:
                target = device_id
        # Se recuerda cuál fue la última elección REAL del usuario, para
        # poder volver a ella tras usar el móvil.
        if target is not None:
            self._last_local_device = target
        config.INPUT_DEVICE = target
        print(f"[voice_recognizer] requested input switch -> {target!r}")
        self.stop()
        self.start()

    def switch_to_network(self):
        """Cambia en caliente al micrófono de red (webapp/móvil): detiene
        el micrófono local, si estaba activo, y pasa a esperar audio vía
        feed_external_audio()."""
        print("[voice_recognizer] cambiando a micrófono de red (móvil)")
        self.stop()
        self.start_network()

    def ceder_microfono(self):
        """Suelta el micrófono LOCAL porque otra aplicación lo pide (ver
        cesion_microfono). Vuelve cuando ya está cerrado. Con el micrófono
        del móvil no hay nada que soltar y se sigue escuchando por él."""
        with self._cesion_lock:
            with self._state_lock:
                local = self._running and self._mode == "device"
            if local:
                self.stop()
                self._reabrir_al_devolver = True

    def recuperar_microfono(self):
        """La otra aplicación ha soltado el micrófono: se vuelve a abrir si
        se estaba usando el local cuando se cedió (o se pidió entretanto)."""
        with self._cesion_lock:
            if self._reabrir_al_devolver and not cesion_microfono.cedido():
                self.start()

    # ---------- internos ----------

    def _audio_callback(self, indata, frames, time_info, status):
        # se ejecuta en el hilo de audio de sounddevice; solo encolamos.
        # Con TOPE: si el reconocimiento se queda atrás (dos modelos grandes
        # comiendo el mismo audio), una cola sin límite no se recupera nunca
        # -- crece sola y el retraso se acumula, así que lo reconocido llega
        # cada vez más tarde (y ya no corresponde a lo que acabas de decir).
        # Preferimos perder lo más viejo y seguir en tiempo real.
        if self._audio_q.qsize() >= config.AUDIO_QUEUE_MAX_BLOCKS:
            try:
                self._audio_q.get_nowait()
            except queue.Empty:
                pass
            self._overflow_blocks += 1
            if self._overflow_blocks % 50 == 1:
                print(f"[voice_recognizer] cola de audio llena: el "
                      f"reconocimiento va por detrás del micrófono "
                      f"({self._overflow_blocks} bloques descartados)")
        self._audio_q.put(bytes(indata))

    def _process_loop(self, token, rec_es, rec_en):
        # rec_es/rec_en se reciben por parámetro a propósito: son LOS de esta
        # sesión. Aunque este hilo tarde en morir, nunca tocará los
        # recognizers que haya creado un start() posterior -- alimentar el
        # mismo KaldiRecognizer desde dos hilos es lo que corrompía la
        # retícula y acababa en 'No final token found' + ASSERTION_FAILED en
        # TraceBackBestPath (aborto de Kaldi, imposible de capturar en Python).
        while not self._stop_event.is_set() and self._run_token is token:
            try:
                data = self._audio_q.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._run_token is not token:
                break

            try:
                self._process_chunk(data, rec_es, rec_en)
            except Exception as exc:
                # un fallo puntual de reconocimiento/parseo NUNCA debe matar
                # el hilo entero (eso te deja sin poder cerrar la app por voz)
                print(f"[voice_recognizer] error procesando audio, se ignora: {exc!r}")
                continue

    @staticmethod
    def _safe_json(raw: str, label: str) -> dict:
        """Parsea el JSON que devuelve Vosk; si falla, imprime el texto
        crudo para poder diagnosticar (en vez de solo el error genérico)."""
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"[voice_recognizer] JSON inválido de {label}: {exc!r} | contenido crudo: {raw!r}")
            return {}

    def _update_silence_state(self, data: bytes) -> float:
        """Actualiza el estado del VAD ligero a partir de la energía RMS del
        bloque y notifica al callback informativo. Devuelve el rms crudo."""
        rms = _compute_rms(data)
        if rms >= config.SILENCE_RMS_THRESHOLD:
            self._silence_hangover = 0
            self._is_silent = False
        else:
            self._silence_hangover += 1
            if self._silence_hangover >= config.SILENCE_HANGOVER_BLOCKS:
                self._is_silent = True
        if self._on_audio_level:
            try:
                self._on_audio_level(self._is_silent, rms)
            except Exception as exc:
                print(f"[voice_recognizer] error en callback de nivel de audio: {exc!r}")
        return rms

    def _process_chunk(self, data: bytes, rec_es, rec_en):
        # Mientras VoiceController está HABLANDO (ver tts.py) se tira el
        # audio sin metérselo a Vosk: si no, se transcribiría a sí mismo y
        # su propio "no te entiendo" acabaría tratándose como una orden.
        # Cubre también una pequeña cola posterior
        # (config.TTS_MIC_MUTE_TAIL_MS) porque el sonido tarda algo en
        # dejar de llegar al micrófono.
        if tts.is_speaking():
            self._utterance_pcm = bytearray()
            return

        # VAD ligero por energía: informa a la GUI (LED) y se usa abajo para
        # no mostrar texto parcial "colgado" durante silencio real
        rms = self._update_silence_state(data)
        if rms > self._utterance_peak_rms:
            self._utterance_peak_rms = rms

        # se acumula el audio crudo de la frase en curso, para poder estimar
        # su entonación (prosody.py) en cuanto se cierre con un resultado final
        self._utterance_pcm += data
        # tope de seguridad: si una "frase" no cierra en mucho tiempo (silencio
        # raro, ruido...), no dejamos crecer el buffer sin límite -- nos
        # quedamos con los últimos ~8s, que es lo que más importa para el
        # contorno de tono del final de la frase
        max_bytes = int((self._input_samplerate or config.SAMPLE_RATE) * 2 * 8)
        if len(self._utterance_pcm) > max_bytes:
            del self._utterance_pcm[:-max_bytes]

        # SIEMPRE se alimentan ambos modelos, esté seleccionado el que esté,
        # para no romper su estado interno de cara a un cambio de modo futuro
        final_es = rec_es.AcceptWaveform(data)
        final_en = rec_en.AcceptWaveform(data)

        if final_es or final_en:
            raw_es = rec_es.Result() if final_es else "{}"
            raw_en = rec_en.Result() if final_en else "{}"
            res_es = self._safe_json(raw_es, "rec_es.Result") if final_es else {}
            res_en = self._safe_json(raw_en, "rec_en.Result") if final_en else {}
            text, confidence, language = self._pick_preferred(res_es, res_en)

            # --- Filtro por voz (ver speaker_id.py) ---
            # Se comprueba AQUÍ, antes de entregar la frase al router,
            # porque este es el único sitio donde coinciden las dos cosas
            # que hacen falta: el x-vector (solo viene en el resultado
            # crudo de Vosk) y si se está dictando o no (self._dictating,
            # que fija el propio router) -- y de cuál de las dos sea
            # depende el umbral, que NO es el mismo.
            # Veredicto de TRES estados (ver speaker_id.verdict): "him",
            # "other" y "unknown". El tercero es el que faltaba: una frase
            # sin x-vector NO es "otra persona", es "no se puede saber" --
            # y les pasa continuamente a los comandos cortos suyos.
            # Tratarlos como ajenos hacía que un 'cerrar' con confianza
            # 1.00 contara como intento de intrusión.
            speaker_verdict = speaker_id.SpeakerVerifier.HIM
            # La verificación por voz solo vale para los micrófonos cuyo
            # perfil se enroló (ver config.SPEAKER_ID_SOURCES): el del
            # móvil produce x-vectores que no se parecen al perfil del
            # PC, así que verificarlo ahí solo generaría rechazos e
            # intrusos falsos. Ese canal se autentica con la contraseña
            # de la webapp, que es un secreto de verdad.
            fuentes = getattr(config, "SPEAKER_ID_SOURCES", ("device",))
            verificador = self._verifiers.get(self._mode, self._verifier)

            # ENROLADO en curso para este micrófono: el x-vector se
            # entrega al recolector y la frase NO se verifica (todavía no
            # hay perfil contra el que compararla).
            if text and self._enroll_cb and self._mode == self._enroll_source:
                spk_vector = res_es.get("spk") or res_en.get("spk")
                try:
                    self._enroll_cb(spk_vector, text)
                except Exception as exc:
                    print(f"[voice_recognizer] error recogiendo muestra de enrolado: {exc!r}")
                self._utterance_pcm = bytearray()
                self._utterance_peak_rms = 0.0
                return

            if (text and verificador.enabled and self._speaker_filter_on
                    and self._mode in fuentes):
                spk_vector = res_es.get("spk") or res_en.get("spk")
                # EL UMBRAL SE ELIGE POR LA FRASE, NO POR EL ESTADO.
                #
                # Antes bastaba con estar dictando para usar el liston de
                # 0,50, que esta calibrado sobre frases largas. Pero un
                # "entra" o un "cerrar" dicho DURANTE el dictado sigue
                # siendo una palabra suelta, y sus palabras sueltas puntuan
                # 0,292-0,577 (ver config): casi siempre por debajo de 0,50.
                #
                # Eso monto una trampa cerrada el 5-sep-2026: el liston alto
                # rechazaba el comando que habria sacado del liston alto.
                # Ver la nota de SPEAKER_ID_PALABRAS_CORTO.
                corto = len((text or "").split()) <= int(
                    getattr(config, "SPEAKER_ID_PALABRAS_CORTO", 3))
                if self._awaiting_login:
                    modo = speaker_id.SpeakerVerifier.LOGIN
                elif self._dictating and not corto:
                    modo = speaker_id.SpeakerVerifier.DICTATION
                else:
                    modo = speaker_id.SpeakerVerifier.COMMAND
                speaker_verdict, score, threshold = verificador.verdict(
                    spk_vector, modo)
                accept = (speaker_verdict == speaker_id.SpeakerVerifier.HIM
                          or not verificador.blocking)
                verificador.n_checked += 1
                if speaker_verdict != speaker_id.SpeakerVerifier.HIM:
                    verificador.n_would_reject += 1
                    if speaker_verdict == speaker_id.SpeakerVerifier.UNKNOWN:
                        verificador.n_no_vector += 1
                shown = f"{score:.3f}" if score is not None else "sin x-vector"
                if speaker_verdict != speaker_id.SpeakerVerifier.HIM:
                    etiqueta = "DESCARTADO" if not accept else "[aviso] se habría descartado"
                    print(f"[voice_recognizer] {etiqueta} por voz ajena "
                          f"({shown} < {threshold:.2f}): {text!r}  "
                          f"[{verificador.stats()}]")
                    # OJO: aunque se vaya a descartar, la frase se le pasa
                    # igualmente al router con el veredicto, y es ÉL
                    # quien no la ejecuta. Antes se cortaba aquí, y eso
                    # dejaba el detector de intrusos muerto justo en modo
                    # "block": para saber si una frase ajena es un COMANDO
                    # DE VERDAD (la condición que separa "hay una tele" de
                    # "alguien me da órdenes") hay que mirarla contra
                    # commands.json, y eso solo lo sabe el router.

            if text:
                # Solo se analiza entonación mientras se dicta texto (estado
                # DICTATING). En estado de escucha (silencio) esta frase solo
                # puede ser una acción/comando -> nunca se le da "formato
                # humano", ni tiene sentido gastar CPU calculándolo.
                sentence_type = "statement"
                if self._dictating:
                    try:
                        sentence_type, _conf = prosody.classify_utterance(
                            bytes(self._utterance_pcm), int(self._input_samplerate or config.SAMPLE_RATE), text
                        )
                    except Exception as exc:
                        print(f"[voice_recognizer] error clasificando entonación, se usa 'statement': {exc!r}")

                self._emit_final(text, confidence, language, sentence_type,
                                 speaker_verdict, self._utterance_peak_rms,
                                 self._mode)

            # frase cerrada: se limpia el buffer de audio y el pico de
            # energía para la siguiente
            self._utterance_pcm = bytearray()
            self._utterance_peak_rms = 0.0
        else:
            # parciales: mostramos lo que sea que ya tenga texto
            partial_es = self._safe_json(rec_es.PartialResult(), "rec_es.PartialResult").get("partial", "")
            partial_en = self._safe_json(rec_en.PartialResult(), "rec_en.PartialResult").get("partial", "")
            partial, language = self._pick_partial(partial_es, partial_en)
            # el LED de silencio es puramente informativo: NO se usa para
            # descartar nada aquí, para no interferir con el reconocimiento
            # (si el umbral está mal calibrado para tu micro, antes esto
            # podía ocultar texto parcial válido, incluido en español)
            if partial:
                self._emit_partial(partial, language)

    # Firmas admitidas para el callback de frase cerrada, de la más
    # completa a la más simple. Se prueban en orden y se recuerda la
    # primera que funcione: antes esto era una escalera de try/except
    # anidados que crecía un nivel cada vez que se añadía un dato (y al
    # añadir el veredicto ya eran cinco), imposible de leer.
    _FINAL_SIGNATURES = (
        lambda cb, t, c, l, s, ok, r, o: cb(t, c, l, s, ok, r, o),
        lambda cb, t, c, l, s, ok, r, o: cb(t, c, l, s, ok, r),
        lambda cb, t, c, l, s, ok, r, o: cb(t, c, l, s, ok),
        lambda cb, t, c, l, s, ok, r, o: cb(t, c, l, s),
        lambda cb, t, c, l, s, ok, r, o: cb(t, c, l),
        lambda cb, t, c, l, s, ok, r, o: cb(t, c),
        lambda cb, t, c, l, s, ok, r, o: cb(t),
    )

    def _emit_final(self, text, confidence, language, sentence_type, speaker_verdict,
                    peak_rms=0.0, source="device"):
        """Entrega la frase cerrada al router con tantos datos como su
        callback acepte. `speaker_verdict` es el veredicto del filtro
        por voz (ver speaker_id.verdict): "him", "other" o "unknown".
        `source` es de qué micrófono vino: "device" (el del PC) o
        "network" (el del móvil). El router lleva la identificación por
        SEPARADO para cada uno -- ver command_router.get_session_state."""
        # Una vez sabemos qué firma acepta, se recuerda: así no se vuelve
        # a probar en cada frase y, sobre todo, un TypeError lanzado DENTRO
        # del router no puede degradarnos en silencio a una firma más
        # corta (perdiendo datos sin que nadie se entere).
        if self._final_signature is not None:
            self._final_signature(self._on_final, text, confidence, language,
                                  sentence_type, speaker_verdict, peak_rms, source)
            return
        for call in self._FINAL_SIGNATURES:
            try:
                call(self._on_final, text, confidence, language, sentence_type,
                     speaker_verdict, peak_rms, source)
                self._final_signature = call
                return
            except TypeError:
                continue
        print("[voice_recognizer] ningún formato de callback on_final encajó")

    def _emit_partial(self, text: str, language: str):
        """Manda texto parcial al router tolerando callbacks antiguos que
        no acepten el idioma -- mismo criterio que ya se usaba con
        _on_final."""
        try:
            self._on_partial(text, language)
        except TypeError:
            self._on_partial(text)

    @staticmethod
    def _avg_confidence(result: dict) -> float:
        words = result.get("result", [])
        if not words:
            # sin info de confianza por palabra: si hay texto, damos algo de crédito
            return 0.4 if result.get("text") else 0.0
        confs = [w.get("conf", 0.0) for w in words]
        return sum(confs) / len(confs)

    def _pick_partial(self, partial_es: str, partial_en: str) -> tuple[str, str]:
        if self.language_mode == "es":
            return (partial_es, "es") if partial_es else (partial_en, "en")
        if self.language_mode == "en":
            return (partial_en, "en") if partial_en else (partial_es, "es")
        return (partial_es, "es") if partial_es else (partial_en, "en")

    def _pick_preferred(self, res_es: dict, res_en: dict) -> tuple[str, float, str]:
        text_es = (res_es.get("text") or "").strip()
        text_en = (res_en.get("text") or "").strip()

        if self.language_mode == "es":
            if text_es:
                return text_es, self._avg_confidence(res_es), "es"
            if text_en:
                return text_en, self._avg_confidence(res_en), "en"
            return "", 0.0, "es"

        if self.language_mode == "en":
            if text_en:
                return text_en, self._avg_confidence(res_en), "en"
            if text_es:
                return text_es, self._avg_confidence(res_es), "es"
            return "", 0.0, "en"

        # fallback conservador por si llega un modo desconocido
        if text_es:
            return text_es, self._avg_confidence(res_es), "es"
        if text_en:
            return text_en, self._avg_confidence(res_en), "en"
        return "", 0.0, "es"
