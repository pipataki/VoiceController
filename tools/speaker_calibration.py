#!/usr/bin/env python3
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
speaker_calibration: mide si merece la pena filtrar por voz en VoiceController.

NO forma parte de la aplicación y NO importa ni modifica nada suyo salvo
`config` (solo para leer: mismo micrófono, misma frecuencia de muestreo y
mismos modelos que usa el reconocedor de verdad). Se puede borrar entero
sin que pase nada.

QUÉ MIDE
--------
Vosk 0.3.45 sabe sacar un "x-vector" de 128 dimensiones por frase (un
resumen numérico de CÓMO suena la voz, no de lo que dice). Comparando el
x-vector de una frase con un PERFIL grabado antes se obtiene una
similitud de 0 a 1. La pregunta es dónde poner el corte:

  - demasiado alto  -> rechaza al propio usuario (falso rechazo)
  - demasiado bajo  -> deja pasar la tele/la radio/otra gente (falso positivo)

Esa frontera depende de la voz, del micrófono y de la sala, así que hay
que medirla AQUÍ, no copiarla de un artículo.

Sabemos ya, por una prueba previa con voces sintéticas, que las frases
MUY cortas (<1 s: "tab", "dictar"...) dan x-vectores inestables o
directamente ninguno. Por eso el informe separa los resultados por
duración: es el dato que decide si el filtro puede aplicarse a los
comandos o solo al dictado.

USO (todo manos libres: cuentas atrás y pitidos, sin pulsar teclas)
-------------------------------------------------------------------
    ./venv/bin/python tools/speaker_calibration.py enroll     # tu perfil de voz
    ./venv/bin/python tools/speaker_calibration.py commands   # tus comandos cortos
    ./venv/bin/python tools/speaker_calibration.py ambient    # tele/radio, tú callado
    ./venv/bin/python tools/speaker_calibration.py report     # veredicto y umbral

`enroll` primero; los otros tres en cualquier orden. Todo se guarda en
tools/speaker_calibration_data.json, así que se puede repetir una fase
sola (p.ej. `ambient` otro día, con otro ruido) sin perder el resto.
"""

import argparse
import json
import queue
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config  # noqa: E402  -- solo lectura: micrófono, sample rate, rutas de modelos

from vosk import KaldiRecognizer, Model, SpkModel, SetLogLevel  # noqa: E402

SPK_MODEL_DIR = PROJECT_ROOT / "vosk_models" / "vosk-model-spk-0.4"
DATA_FILE = Path(__file__).resolve().parent / "speaker_calibration_data.json"

# Frases de enrolado: largas a propósito (los x-vectores necesitan varios
# segundos de habla) y fonéticamente variadas, para que el perfil no se
# quede pegado a unos pocos sonidos.
ENROLL_PHRASES = [
    "Hola, soy yo, y esta es mi voz para el controlador por voz.",
    "El tablero tiene cien casillas numeradas de izquierda a derecha.",
    "Quiero dictar un texto largo y confirmarlo cuando esté terminado.",
    "La rejilla se muestra unos segundos y después desaparece sola.",
    "Prefiero que el ordenador escuche solamente lo que yo le digo.",
    "Cinco, catorce, veintitrés, treinta y ocho, cuarenta y siete.",
]

# Comandos cortos reales de la aplicación -- son el caso difícil.
TEST_COMMANDS = [
    "tab", "espacio", "intro", "escape", "arriba", "abajo",
    "dictar", "escucha", "entra", "borra",
    "scroll derecha", "doble click", "click derecho", "micrófono local",
    # LOS NUMEROS, anadidos el 5-sep-2026. Que no estuvieran era un agujero
    # de los gordos: son los comandos MAS FRECUENTES del programa entero --
    # se dice uno para cada casilla (1-100) y para cada zona (1-9).
    #
    # O sea que la calibracion medida el conjunto menos representativo del
    # caso mas habitual. Por eso el peor comando "conocido" era 'ayudas'
    # (0,248) y el umbral se puso en 0,18 tan tranquilo. En uso real, "uno"
    # saca 0,173 -- por debajo -- y nadie podia saberlo porque nunca se
    # midio.
    #
    # POR QUE NO ESTAN LOS CIEN, que seria lo exhaustivo: porque el
    # problema es la DURACION del audio, no el numero. "Cuarenta y cinco"
    # dura tres veces mas que "dos" y puntua como una frase. Los cien
    # tardarian unos nueve minutos de decir numeros seguidos, y al final se
    # habla distinto por cansancio: la medida saldria PEOR, no mejor.
    #
    # Asi que van los diez cortos completos -- que son los de riesgo, y de
    # paso cubren los items 1-9 -- y una muestra de compuestos que sirve de
    # CONTROL. Si los compuestos puntuan alto y los cortos bajo, ese
    # contraste demuestra que la duracion es la causa y que no hacen falta
    # los cien. Si algun compuesto puntuara bajo, la hipotesis seria falsa y
    # habria que medir mas.
    "uno", "dos", "tres", "cuatro", "cinco",
    "seis", "siete", "ocho", "nueve", "diez",
    "veinte", "veintiuno", "cuarenta y cinco", "setenta y siete",
    "noventa y nueve", "cien",
]

ENROLL_SECONDS = 6.0
AMBIENT_SECONDS = 90.0


# --------------------------------------------------------------------------
# audio
# --------------------------------------------------------------------------

def _beep(freq=880.0, dur=0.18, volume=0.25):
    """Pitido corto para marcar principio y fin de cada grabación -- la
    herramienta es manos libres, así que el usuario necesita oír cuándo
    se está grabando sin mirar la pantalla.

    Un pitido NUNCA puede parar la calibración. Si la salida de sonido no
    avanza (pasó el 14-sep-2026 en una VM cuya salida no llegaba a ningún
    sitio), tanto sd.wait() como sd.stop() esperan a que se vacíe, y eso no
    pasa nunca: se quedaba colgada en el primer pitido sin decir nada. Por
    eso se corta con abort(), que no espera, y todo va en un hilo aparte
    con tiempo máximo: si aun así se atasca, se sigue sin él."""
    import threading

    def _sonar():
        try:
            rate = 44100
            t = np.linspace(0, dur, int(rate * dur), endpoint=False)
            # envolvente suave, para que no chasquee
            env = np.minimum(1.0, np.minimum(t, dur - t) / 0.02)
            sd.play((volume * env * np.sin(2 * np.pi * freq * t)).astype(np.float32), rate)
            time.sleep(dur + 0.3)
            sd.get_stream().abort(ignore_errors=True)
        except Exception:
            pass  # sin altavoz tampoco pasa nada: los avisos también van por pantalla

    hilo = threading.Thread(target=_sonar, daemon=True)
    hilo.start()
    hilo.join(dur + 1.0)


def _countdown(seconds=3):
    for n in range(seconds, 0, -1):
        print(f"    {n}...", flush=True)
        time.sleep(1.0)


def _modelo_de_idioma() -> str:
    """El modelo de idioma que acompaña al de locutor: el PEQUEÑO si lo hay.

    Aquí el modelo de idioma solo hace de acompañante: la voz la resume el
    modelo de locutor. Y el grande costaba caro: 4.270 MB de pico, y en una
    Debian limpia de 6 GB con KDE el sistema mató la calibración a media
    instalación (14-sep-2026).

    Medido ese día con cinco voces sintéticas y 55 frases: el perfil hecho con
    el pequeño y con el grande sale IDÉNTICO (coseno 1,000), y ese perfil,
    usado luego con el grande de la aplicación, puntúa como mucho 0,004
    distinto. Puntuar frases sueltas con el pequeño se desvía algo más (unas
    centésimas), lo que mueve un poco el umbral que se propone.

    Orden: el pequeño de la lengua materna, el grande de la materna, y solo
    si no hay ninguno de los dos, los de la otra lengua -- nunca quedarse sin
    calibrar por eso. La otra lengua va al final a propósito: con el pequeño
    de inglés, lo que "oía" la calibración salía en inglés (14-sep-2026, la
    VM no tenía el pequeño de español), y el perfil se habría hecho con un
    modelo que no se ha medido.
    """
    import os
    materna = getattr(config, "LENGUA_MATERNA", "es")
    otra = "en" if materna == "es" else "es"
    pequeno = {"es": getattr(config, "VOSK_MODEL_ES_SMALL", ""),
               "en": getattr(config, "VOSK_MODEL_EN_SMALL", "")}
    grande = {"es": config.VOSK_MODEL_ES, "en": config.VOSK_MODEL_EN}
    for ruta in (pequeno[materna], grande[materna], pequeno[otra], grande[otra]):
        if ruta and os.path.isdir(ruta):
            return ruta
    sys.exit("No hay ningún modelo de idioma en vosk_models/: pasa el instalador.")


class Listener:
    """Micrófono + Vosk con modelo de locutor, con la MISMA configuración
    que usa la aplicación (config.INPUT_DEVICE y la frecuencia nativa del
    dispositivo) -- si se calibrara con otra entrada, el umbral medido no
    valdría para el uso real. `device` permite forzar otra entrada solo
    para esta prueba (ver --device / --list-devices)."""

    def __init__(self, device=None):
        SetLogLevel(-1)
        if not SPK_MODEL_DIR.is_dir():
            sys.exit(f"Falta el modelo de locutor en {SPK_MODEL_DIR}\n"
                     "Descárgalo de https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip "
                     "y descomprímelo ahí.")
        print("Cargando modelos (tarda unos segundos)...", flush=True)
        self.model = Model(_modelo_de_idioma())
        self.spk = SpkModel(str(SPK_MODEL_DIR))
        self.device = config.INPUT_DEVICE if device is None else device
        try:
            devinfo = sd.query_devices(self.device, "input")
            self.rate = int(devinfo.get("default_samplerate", config.SAMPLE_RATE))
            self.dev_name = devinfo.get("name")
        except Exception as exc:
            sys.exit(f"No se puede abrir la entrada de audio {self.device!r}: {exc}\n"
                     "Prueba `--list-devices` y elige otra con `--device N`.")
        print(f"Micrófono: {self.dev_name!r} (dispositivo {self.device}) a {self.rate} Hz")
        print("Si VoiceController está abierto, ciérralo antes: los dos se pelearían "
              "por el micrófono.\n", flush=True)
        self.q = queue.Queue()

    def _callback(self, indata, frames, time_info, status):
        self.q.put(bytes(indata))

    def _new_recognizer(self):
        rec = KaldiRecognizer(self.model, self.rate)
        rec.SetSpkModel(self.spk)
        return rec

    def record_fixed(self, seconds: float):
        """Graba `seconds` segundos y devuelve (x_vector, texto). Ventana
        fija: es lo que hace falta para el enrolado, donde la frase la
        marca la herramienta, no el detector de silencios."""
        rec = self._new_recognizer()
        vecs, words = [], []
        with sd.RawInputStream(samplerate=self.rate, blocksize=config.AUDIO_BLOCKSIZE,
                               device=self.device, dtype="int16", channels=1,
                               callback=self._callback):
            while not self.q.empty():
                self.q.get_nowait()
            t_end = time.monotonic() + seconds
            while time.monotonic() < t_end:
                try:
                    data = self.q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result())
                    if r.get("spk"):
                        vecs.append(r["spk"])
                    if r.get("text"):
                        words.append(r["text"])
        r = json.loads(rec.FinalResult())
        if r.get("spk"):
            vecs.append(r["spk"])
        if r.get("text"):
            words.append(r["text"])
        return _normalize(np.mean(np.array(vecs), axis=0)) if vecs else None, " ".join(words)

    def record_utterances(self, seconds: float, on_utterance):
        """Graba `seconds` en continuo y llama a on_utterance(vector,
        texto, duracion) por cada frase que CIERRE Vosk -- misma
        segmentación que usa la aplicación de verdad, que es lo que
        interesa medir."""
        rec = self._new_recognizer()
        with sd.RawInputStream(samplerate=self.rate, blocksize=config.AUDIO_BLOCKSIZE,
                               device=self.device, dtype="int16", channels=1,
                               callback=self._callback):
            while not self.q.empty():
                self.q.get_nowait()
            t_end = time.monotonic() + seconds
            n_bytes = 0
            while time.monotonic() < t_end:
                try:
                    data = self.q.get(timeout=0.5)
                except queue.Empty:
                    continue
                n_bytes += len(data)
                if rec.AcceptWaveform(data):
                    r = json.loads(rec.Result())
                    dur = n_bytes / (2 * self.rate)
                    n_bytes = 0
                    if r.get("text"):
                        on_utterance(_normalize(np.array(r["spk"])) if r.get("spk") else None,
                                     r["text"], dur)
        r = json.loads(rec.FinalResult())
        if r.get("text"):
            on_utterance(_normalize(np.array(r["spk"])) if r.get("spk") else None,
                         r["text"], n_bytes / (2 * self.rate))


# --------------------------------------------------------------------------
# vectores
# --------------------------------------------------------------------------

def _normalize(v):
    v = np.asarray(v, dtype=float)
    n = np.linalg.norm(v)
    return (v / n) if n else None


def _similarity(profile, vector):
    """Coseno entre dos vectores YA normalizados: 1.0 = idénticos."""
    return float(np.dot(profile, vector))


def _load():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"profile": None, "enroll": [], "commands": [], "ambient": []}


def _save(data):
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\nGuardado en {DATA_FILE}")


# --------------------------------------------------------------------------
# fases
# --------------------------------------------------------------------------

def cmd_enroll(args):
    data = _load()
    listener = Listener(args.device)
    print("=" * 68)
    print("FASE 1 -- PERFIL DE TU VOZ")
    print("=" * 68)
    print(f"Vas a leer {len(ENROLL_PHRASES)} frases. Cada una se graba durante "
          f"{ENROLL_SECONDS:.0f} segundos.")
    print("Habla como hablas normalmente al ordenador: misma distancia al")
    print("micrófono y mismo tono que cuando lo usas de verdad.")
    print("Un pitido marca el principio y otro el final. No hay que pulsar nada.\n")
    time.sleep(2)

    vectors = []
    for i, phrase in enumerate(ENROLL_PHRASES, 1):
        print(f"\n[{i}/{len(ENROLL_PHRASES)}] Lee en voz alta:")
        print(f'    "{phrase}"')
        _countdown(3)
        _beep(880)
        print("    GRABANDO...", flush=True)
        vec, heard = listener.record_fixed(ENROLL_SECONDS)
        _beep(440)
        if vec is None:
            print("    ⚠ no se ha capturado voz -- se repetirá al final")
            continue
        vectors.append(vec.tolist())
        print(f"    ✓ capturado (se oyó: {heard[:60]!r})")

    if len(vectors) < 3:
        sys.exit("\nMuy pocas frases capturadas. Comprueba el micrófono y repite `enroll`.")

    profile = _normalize(np.mean(np.array(vectors), axis=0))
    data["profile"] = profile.tolist()
    data["enroll"] = vectors

    # coherencia interna: cuánto se parece cada frase al perfil que forman
    # entre todas. Si esto ya sale bajo, el micrófono o la sala están
    # metiendo demasiada variación y el filtro no va a funcionar.
    sims = [_similarity(profile, np.array(v)) for v in vectors]
    print(f"\nPerfil creado con {len(vectors)} frases.")
    print(f"Coherencia interna: media {np.mean(sims):.3f}, mínimo {min(sims):.3f}")
    if min(sims) < 0.75:
        print("⚠ Coherencia baja: tu propia voz varía mucho entre frases.")
        print("  Repite el enrolado en un sitio más silencioso antes de seguir.")
    _save(data)
    print("\nSiguiente: `commands` (tus comandos cortos) y `ambient` (la tele).")


def cmd_commands(args):
    data = _load()
    if not data.get("profile"):
        sys.exit("Primero hay que hacer `enroll`.")
    profile = np.array(data["profile"])
    listener = Listener(args.device)

    print("=" * 68)
    print("FASE 2 -- TUS COMANDOS CORTOS (mide los FALSOS RECHAZOS)")
    print("=" * 68)
    print("Vas a decir comandos reales de la aplicación, uno por uno, con TU voz.")
    print("Todo lo que salga por debajo del umbral serían comandos tuyos que la")
    print("aplicación te rechazaría por error. Es la medida que decide si el")
    print("filtro puede aplicarse a los comandos o solo al dictado.\n")
    time.sleep(2)

    results = []
    for i, word in enumerate(TEST_COMMANDS, 1):
        print(f"\n[{i}/{len(TEST_COMMANDS)}] Di: \"{word}\"")
        _countdown(2)
        _beep(880)
        print("    GRABANDO...", flush=True)
        vec, heard = listener.record_fixed(2.5)
        _beep(440)
        entry = {"esperado": word, "oido": heard,
                 "similitud": _similarity(profile, vec) if vec is not None else None,
                 # el VECTOR, no solo su similitud: sin él no se puede
                 # construir después un perfil de duración equivalente
                 # (ver _short_profile_analysis en el informe), que es
                 # justo la pregunta que decide si el filtro sirve para
                 # los comandos cortos
                 "vector": vec.tolist() if vec is not None else None}
        results.append(entry)
        if vec is None:
            print("    ✗ SIN x-vector (frase demasiado corta para identificar la voz)")
        else:
            print(f"    similitud {entry['similitud']:.3f}   (se oyó: {heard!r})")

    data["commands"] = results
    _save(data)
    print("\nSiguiente: `ambient` (con la tele o la radio puesta, tú callado).")


def cmd_ambient(args):
    data = _load()
    if not data.get("profile"):
        sys.exit("Primero hay que hacer `enroll`.")
    profile = np.array(data["profile"])
    listener = Listener(args.device)

    seconds = args.seconds or AMBIENT_SECONDS
    print("=" * 68)
    print("FASE 3 -- RUIDO DE VOCES AJENAS (mide los FALSOS POSITIVOS)")
    print("=" * 68)
    print(f"Pon la tele, la radio o una conversación de fondo, al volumen al que")
    print(f"te molesta de verdad, y QUÉDATE CALLADO durante {seconds:.0f} segundos.")
    print("Todo lo que salga por ENCIMA del umbral serían voces ajenas que la")
    print("aplicación aceptaría como tuyas.\n")
    _countdown(5)
    _beep(880)
    print(f"GRABANDO {seconds:.0f} segundos -- no hables.\n", flush=True)

    results = []
    t0 = time.monotonic()

    def on_utt(vec, text, dur):
        sim = _similarity(profile, vec) if vec is not None else None
        results.append({"texto": text, "duracion": round(dur, 2), "similitud": sim,
                        "vector": vec.tolist() if vec is not None else None})
        left = max(0, seconds - (time.monotonic() - t0))
        shown = f"{sim:.3f}" if sim is not None else " sin x-vector"
        print(f"  [{left:5.0f}s restantes] {shown}  ({dur:.1f}s) {text[:44]!r}")

    listener.record_utterances(seconds, on_utt)
    _beep(440)
    data["ambient"] = results
    _save(data)
    print(f"\n{len(results)} frases ajenas capturadas. Ahora: `report`.")


# --------------------------------------------------------------------------
# informe
# --------------------------------------------------------------------------

def _rates(own, others, threshold):
    """(falsos rechazos, falsos positivos) al umbral dado. Las frases sin
    x-vector cuentan como rechazadas: si no se puede identificar la voz,
    un filtro estricto no tiene más remedio que descartarlas."""
    fr = sum(1 for s in own if s is None or s < threshold)
    fa = sum(1 for s in others if s is not None and s >= threshold)
    return fr, fa


def _short_profile_analysis(data):
    """¿Y si el perfil se construyera con palabras CORTAS en vez de con
    frases largas?

    Los x-vectores son sensibles a la duración: comparar una palabra de
    medio segundo contra un perfil hecho de frases de seis segundos
    penaliza aunque la voz sea la misma. Aquí se construye un perfil
    "corto" con los propios comandos y se valida DEJANDO UNO FUERA (cada
    comando se puntúa contra el perfil formado por los otros trece, nunca
    contra uno que lo incluya -- si no, el resultado saldría inflado y no
    significaría nada).

    Si con este perfil los comandos propios se separan de las voces
    ajenas cortas, el filtro sí es aplicable a los comandos y solo hacía
    falta enrolar con palabras del mismo tamaño."""
    cmds = [c for c in data.get("commands", []) if c.get("vector")]
    if len(cmds) < 5:
        print("\n(Sin vectores de comandos guardados: vuelve a ejecutar `commands` "
              "para poder analizar el perfil de duración equivalente.)")
        return

    vecs = [np.array(c["vector"]) for c in cmds]
    propios = []
    for i in range(len(vecs)):
        resto = [v for j, v in enumerate(vecs) if j != i]
        perfil = _normalize(np.mean(np.array(resto), axis=0))
        propios.append(_similarity(perfil, vecs[i]))

    perfil_corto = _normalize(np.mean(np.array(vecs), axis=0))
    largo = data.get("profile")
    antes = [c["similitud"] for c in cmds if c["similitud"] is not None]

    print("\nPERFIL DE DURACIÓN EQUIVALENTE (comandos cortos como referencia)")
    print(f"  tus comandos contra el perfil LARGO  : media {np.mean(antes):.3f} "
          f"(mín {min(antes):.3f})")
    print(f"  tus comandos contra el perfil CORTO  : media {np.mean(propios):.3f} "
          f"(mín {min(propios):.3f})   [dejando uno fuera]")
    mejora = np.mean(propios) - np.mean(antes)
    print(f"  mejora: {mejora:+.3f}")

    ambient_cortas = [np.array(a["vector"]) for a in data.get("ambient", [])
                      if a.get("vector") and a.get("duracion", 9) < 2.0]
    if not ambient_cortas:
        print("  (falta `ambient` para saber qué puntúan las voces ajenas cortas)")
        return
    ajenas = [_similarity(perfil_corto, v) for v in ambient_cortas]
    print(f"  voces ajenas cortas contra el perfil CORTO: media {np.mean(ajenas):.3f} "
          f"(máx {max(ajenas):.3f})")
    margen = min(propios) - max(ajenas)
    print(f"\n  MARGEN: tu peor comando {min(propios):.3f} vs la peor ajena "
          f"{max(ajenas):.3f}  ->  {margen:+.3f}")
    if margen > 0.05:
        print("  ✓ SEPARABLE: el filtro también sirve para los comandos cortos,")
        print("    enrolando con palabras cortas en vez de con frases largas.")
    else:
        print("  ✗ SE SOLAPAN: los comandos cortos no son verificables por voz")
        print("    ni con un perfil de su misma duración. Solo dictado.")


def cmd_report(args):
    data = _load()
    if not data.get("profile"):
        sys.exit("No hay perfil todavía: empieza por `enroll`.")

    own_all = data.get("commands", [])
    ambient = data.get("ambient", [])
    if not own_all and not ambient:
        sys.exit("No hay medidas todavía: ejecuta `commands` y `ambient`.")

    print("=" * 68)
    print("INFORME DE CALIBRACIÓN")
    print("=" * 68)

    enroll_sims = [_similarity(np.array(data["profile"]), np.array(v))
                   for v in data.get("enroll", [])]
    if enroll_sims:
        print(f"\nPerfil: {len(enroll_sims)} frases, coherencia media "
              f"{np.mean(enroll_sims):.3f} (mín {min(enroll_sims):.3f})")

    own = [c["similitud"] for c in own_all]
    sin_vector = [c for c in own_all if c["similitud"] is None]
    con_vector = [s for s in own if s is not None]

    if own_all:
        print(f"\nTUS COMANDOS ({len(own_all)} probados)")
        if sin_vector:
            print(f"  ✗ {len(sin_vector)} sin x-vector -- imposibles de verificar por voz:")
            print("     " + ", ".join(repr(c["esperado"]) for c in sin_vector))
        if con_vector:
            print(f"  similitud: mín {min(con_vector):.3f} | mediana "
                  f"{np.median(con_vector):.3f} | máx {max(con_vector):.3f}")
            peores = sorted((c for c in own_all if c["similitud"] is not None),
                            key=lambda c: c["similitud"])[:5]
            print("  los 5 peores: " + ", ".join(
                f"{c['esperado']}={c['similitud']:.2f}" for c in peores))

    amb = [a["similitud"] for a in ambient]
    amb_ok = [s for s in amb if s is not None]
    if ambient:
        print(f"\nVOCES AJENAS ({len(ambient)} frases capturadas)")
        if amb_ok:
            print(f"  similitud: mín {min(amb_ok):.3f} | mediana "
                  f"{np.median(amb_ok):.3f} | máx {max(amb_ok):.3f}")
            print(f"  la peor (la que más se te parece): {max(amb_ok):.3f}")

    if not con_vector or not amb_ok:
        print("\nFaltan datos de una de las dos partes: no se puede recomendar umbral.")
        return

    # Barrido dirigido por los datos, no por un rango fijo: el rango útil
    # depende del micrófono y de la sala, y uno fijo puede quedarse entero
    # por encima (todo rechazado) o por debajo (todo aceptado) sin mostrar
    # ni una sola fila informativa.
    lo = max(0.0, min(min(con_vector), min(amb_ok)) - 0.05)
    hi = min(1.0, max(max(con_vector), max(amb_ok)) + 0.05)
    paso = max(0.02, (hi - lo) / 14)
    print("\nUMBRALES POSIBLES")
    print(f"  {'umbral':>7} {'te rechaza':>12} {'cuela ajenas':>14}")
    best = None
    for thr in np.arange(lo, hi + paso / 2, paso):
        fr, fa = _rates(own, amb_ok, thr)
        frp, fap = 100 * fr / len(own), 100 * fa / len(amb_ok)
        marca = ""
        # criterio: primero no estorbar al usuario (<=10% de rechazos),
        # y dentro de eso, el que menos voces ajenas cuele
        if frp <= 10 and (best is None or fap < best[2]):
            best = (thr, frp, fap)
            marca = "  <-- candidato"
        print(f"  {thr:7.2f} {frp:11.0f}% {fap:13.0f}%{marca}")

    print("\nVEREDICTO")
    if best is None:
        print("  ✗ NO hay umbral que te deje trabajar sin rechazarte constantemente.")
        print("    El filtro por voz no es aplicable con este micrófono/sala.")
    else:
        thr, frp, fap = best
        print(f"  Umbral recomendado: {thr:.2f}")
        print(f"    te rechazaría el {frp:.0f}% de tus comandos")
        print(f"    dejaría pasar el {fap:.0f}% de las voces ajenas")
        if fap > 25:
            print("  ⚠ Filtra poco: no compensa aplicarlo a los comandos.")

    _short_profile_analysis(data)

    # el dato que de verdad decide: ¿cambia la cosa con frases largas?
    largas = [a["similitud"] for a in ambient
              if a["similitud"] is not None and a.get("duracion", 0) >= 2.0]
    if largas and enroll_sims:
        thr_dict = min(enroll_sims) - 0.05
        colarian = sum(1 for s in largas if s >= thr_dict)
        print(f"\n  SOLO PARA DICTADO (frases de 2 s o más)")
        print(f"    con umbral {thr_dict:.2f} (tu peor frase de enrolado menos un margen):")
        print(f"    colarían {colarian} de {len(largas)} frases ajenas largas "
              f"({100*colarian/len(largas):.0f}%)")

    print("\nPásame este informe y decidimos dónde aplicarlo.")


def cmd_login(args):
    """Mide qué puntúa TU santo y seña, y propone el umbral.

    Este paso existe porque el umbral NO se puede heredar del de dictado:
    la puntuación baja con la duración de la frase, y el santo y seña
    (unos 2,5 s) es bastante más corto que las frases de enrolado (6 s).
    Medido en su máquina, su comando más largo (1,5 s) puntuaba 0,547
    frente a 0,68-0,81 de las frases largas -- suponer aquí sería
    exactamente el error que ya se cometió dos veces antes."""
    data = _load()
    if not data.get("profile"):
        sys.exit("Primero hay que hacer `enroll`.")
    profile = np.array(data["profile"])
    listener = Listener(args.device)

    frase = args.frase or config.VOICE_LOGIN_HINT
    veces = args.veces
    print("=" * 68)
    print("SANTO Y SEÑA -- medir su umbral")
    print("=" * 68)
    print(f'Vas a decir {veces} veces: "{frase}"')
    print("Dilo como lo dirías al arrancar el programa, sin vocalizar de más.")
    print("Se comprueba SOLO tu voz, no lo que digas: la frase está para")
    print("que haya audio suficiente.\n")
    time.sleep(2)

    puntuaciones = []
    for i in range(1, veces + 1):
        print(f"\n[{i}/{veces}] Di: \"{frase}\"")
        _countdown(3)
        _beep(880)
        print("    GRABANDO...", flush=True)
        vec, oido = listener.record_fixed(4.0)
        _beep(440)
        if vec is None:
            print("    ✗ sin x-vector: la frase ha salido demasiado corta")
            continue
        sim = _similarity(profile, vec)
        puntuaciones.append(sim)
        print(f"    similitud {sim:.3f}   (se oyó: {oido[:52]!r})")

    if len(puntuaciones) < 3:
        sys.exit("\nMuy pocas medidas válidas. Prueba con una frase más larga.")

    data["login"] = puntuaciones
    _save(data)

    peor = min(puntuaciones)
    ajenas = [a["similitud"] for a in data.get("ambient", [])
              if a.get("similitud") is not None]
    print(f"\nTu santo y seña: mín {peor:.3f} | media {np.mean(puntuaciones):.3f} "
          f"| máx {max(puntuaciones):.3f}")

    # Umbral por debajo de tu PEOR intento, con margen: fallarte a ti es
    # mucho peor que dejar pasar a alguien, porque te deja fuera de tu
    # propia herramienta.
    propuesto = round(max(0.05, peor - 0.08), 2)
    print(f"\nUMBRAL PROPUESTO: {propuesto:.2f}")
    print(f"  (tu peor intento {peor:.3f} menos 0,08 de margen)")
    if ajenas:
        colarian = sum(1 for a in ajenas if a >= propuesto)
        print(f"  de las {len(ajenas)} voces ajenas medidas, colarían "
              f"{colarian} ({100*colarian/len(ajenas):.0f}%)")
        if colarian:
            print("  ⚠ Alguna voz ajena lo pasaría: sube el umbral o alarga la frase.")
    # config_local.py, NO config.py: este ultimo se sobrescribe al
    # actualizar y el umbral se perderia sin que nadie se entere -- el santo
    # y sena volveria a su valor de fabrica y fallaria mas de la cuenta.
    print(f"\nCopia esta linea a config_local.py (NO a config.py, que se "
          f"sobrescribe al actualizar):\n    VOICE_LOGIN_THRESHOLD = {propuesto:.2f}")


def cmd_export(args):
    """Escribe el perfil en el sitio donde lo busca la aplicación
    (config.SPEAKER_PROFILE_FILE). Se hace en un paso APARTE del
    enrolado a propósito: enrolar y volver a enrolar es barato y sin
    consecuencias, mientras que exportar cambia lo que la aplicación va
    a usar de verdad, y conviene que sea una decisión explícita."""
    data = _load()
    if not data.get("profile"):
        sys.exit("No hay perfil todavía: ejecuta `enroll` primero.")

    destino = Path(config.SPEAKER_PROFILE_FILE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and not args.force:
        sys.exit(f"Ya existe {destino}.\nSi quieres reemplazarlo, repite con --force.")

    cmds = [c["similitud"] for c in data.get("commands", []) if c.get("similitud") is not None]
    amb = [a["similitud"] for a in data.get("ambient", []) if a.get("similitud") is not None]
    meta = {
        "frases_enrolado": len(data.get("enroll", [])),
        "comandos_medidos": len(cmds),
        "ajenas_medidas": len(amb),
        "tu_peor_comando": round(min(cmds), 3) if cmds else None,
        "peor_ajena": round(max(amb), 3) if amb else None,
        "umbral_dictado": config.SPEAKER_ID_THRESHOLD_DICTATION,
        "umbral_comandos": config.SPEAKER_ID_THRESHOLD_COMMAND,
    }
    contenido = json.dumps({"profile": data["profile"], "meta": meta},
                           ensure_ascii=False, indent=2)
    destino.write_text(contenido, encoding="utf-8")
    # Copia fechada: un perfil cuesta varios minutos de grabación guiada y
    # es lo único que no se puede regenerar solo. Ya se perdió uno.
    try:
        import time as _time
        copias = PROJECT_ROOT / ".backups" / "profiles"
        copias.mkdir(parents=True, exist_ok=True)
        marca = _time.strftime("%Y%m%d_%H%M%S")
        (copias / f"{destino.stem}_{marca}.json").write_text(contenido, encoding="utf-8")
        print(f"Copia de seguridad en {copias}")
    except Exception as exc:
        print(f"No se pudo guardar la copia: {exc!r}")
    print(f"Perfil escrito en {destino}")
    print(f"  {meta['frases_enrolado']} frases de enrolado")
    if meta["tu_peor_comando"] is not None and meta["peor_ajena"] is not None:
        print(f"  tu peor comando {meta['tu_peor_comando']} | peor voz ajena {meta['peor_ajena']}")
        if meta["tu_peor_comando"] <= config.SPEAKER_ID_THRESHOLD_COMMAND:
            print(f"  ⚠ tu peor comando NO supera el umbral de comandos "
                  f"({config.SPEAKER_ID_THRESHOLD_COMMAND}): bájalo antes de pasar a modo 'block'.")
    print(f"\nLa aplicación arrancará en modo {config.SPEAKER_ID_MODE!r} "
          f"(config.SPEAKER_ID_MODE).")


def cmd_list_devices(args):
    print("Entradas de audio disponibles:\n")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            marca = "  <-- config.INPUT_DEVICE" if i == config.INPUT_DEVICE else ""
            print(f"  {i:3}  {d['name'][:52]:<54} {int(d['default_samplerate'])} Hz{marca}")
    print("\nUsa `--device N` para forzar una distinta solo en esta prueba.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("enroll", "graba tu perfil de voz (hazlo primero)"),
                           ("commands", "mide falsos rechazos con tus comandos cortos"),
                           ("ambient", "mide falsos positivos con la tele de fondo")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--device", type=int, default=None,
                       help="entrada de audio a usar (por defecto config.INPUT_DEVICE)")
        if name == "ambient":
            p.add_argument("--seconds", type=float, default=None)
    sub.add_parser("report", help="veredicto y umbral recomendado")
    log = sub.add_parser("login", help="mide el umbral de tu santo y seña")
    log.add_argument("--device", type=int, default=None)
    log.add_argument("--veces", type=int, default=5)
    log.add_argument("--frase", default=None)
    exp = sub.add_parser("export", help="instala el perfil para que lo use la aplicación")
    exp.add_argument("--force", action="store_true", help="sobrescribe un perfil ya instalado")
    sub.add_parser("list-devices", help="lista las entradas de audio y sale")
    args = ap.parse_args()
    {"enroll": cmd_enroll, "commands": cmd_commands, "ambient": cmd_ambient,
     "report": cmd_report, "export": cmd_export, "login": cmd_login,
     "list-devices": cmd_list_devices}[args.cmd](args)


if __name__ == "__main__":
    main()
