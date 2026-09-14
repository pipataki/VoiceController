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
prosody.py: Clasificación aproximada del "tipo de frase" (afirmación,
pregunta, exclamación, sugerencia) combinando:

  1. Contorno de tono (F0) del audio de la frase, estimado con autocorrelación
     (solo numpy, sin dependencias nuevas) -- una pregunta suele terminar en
     tono ascendente, una exclamación tiene más rango/energía.
  2. Pistas léxicas en español (partículas interrogativas, interjecciones,
     fórmulas de sugerencia) sobre el texto ya reconocido -- más fiables que
     el tono solo, porque el pitch tracker es ligero y se degrada con ruido,
     micrófonos Bluetooth, etc.

IMPORTANTE - limitaciones honestas:
  - Esto NO es un clasificador entrenado ni un sistema de NLU. Es una
    heurística combinada, pensada como señal ADICIONAL para desambiguar
    (p.ej. si el final de una frase larga coincide por casualidad con una
    palabra de control), no como reemplazo de las palabras de control
    explícitas de commands.json.
  - La detección de tono funciona peor con voces muy graves/agudas fuera del
    rango típico, audio con mucho ruido de fondo, o frases muy cortas (menos
    de ~0.3s de voz). En esos casos se degrada a "statement" con confianza baja.
"""

import unicodedata

import json
import pathlib

import numpy as np

# --- rango de F0 humano típico (Hz) ---
F0_MIN = 75
F0_MAX = 400

FRAME_MS = 30
HOP_MS = 10

# --- pistas léxicas (texto ya normalizado: minúsculas, sin acentos) ---
QUESTION_STARTERS = {
    "que", "quien", "quienes", "como", "cuando", "donde", "adonde",
    "cual", "cuales", "cuanto", "cuanta", "cuantos", "cuantas", "por que",
    "acaso", "es", "esta", "estas", "son", "puedes", "podrias", "sabes",
    "tienes", "hay",
}
QUESTION_TAGS = {"verdad", "no", "vale", "cierto"}  # al final: "..., verdad?"

EXCLAMATION_WORDS = {
    "vaya", "genial", "increible", "wow", "guau", "ojala", "cuidado",
    "socorro", "bravo", "estupendo", "fantastico", "excelente", "menudo",
    "menuda", "que barbaridad",
}

SUGGESTION_CUES = {
    "deberias", "deberiamos", "podrias", "podriamos", "seria mejor",
    "que tal si", "por que no", "sugiero", "propongo", "y si",
    "tal vez podriamos", "convendria",
}

# --- las listas de verdad vienen de prosody.json --------------------------
#
# Las de arriba se quedan como RESPALDO: si el fichero falta o esta roto, el
# programa sigue funcionando con lo minimo en vez de quedarse sin prosodia.
#
# Se saco a un JSON para poder ampliarlo sin tocar codigo, igual que
# commands.json. Añadir una exclamacion no deberia exigir editar un modulo.

# El tuyo primero; si no existe, el que vino en el paquete. Mismo patron que
# commands.json / commands.default.json: lo que personalices sobrevive a las
# actualizaciones, y lo nuevo llega al fusionar (tools/merge_prosody.py).
_RAIZ = pathlib.Path(__file__).resolve().parent
_RUTA_JSON = _RAIZ / "prosody.json"
_RUTA_DEFECTO = _RAIZ / "prosody.default.json"


def _plano(seccion) -> set:
    """Junta los idiomas de una seccion en un solo conjunto, ya normalizado."""
    salida = set()
    if not isinstance(seccion, dict):
        return salida
    for idioma, entradas in seccion.items():
        if idioma.startswith("_") or not isinstance(entradas, list):
            continue
        for e in entradas:
            n = _normalize(str(e))
            if n:
                salida.add(n)
    return salida


def _cargar_listas():
    """Lee prosody.json. Si falla, se usan las listas de respaldo de arriba.

    No se avisa por voz ni se aborta nada: quedarse sin signos de
    exclamacion es un incordio, no un motivo para no arrancar.
    """
    datos = {}
    for ruta in (_RUTA_JSON, _RUTA_DEFECTO):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                datos = json.load(f)
            break
        except FileNotFoundError:
            continue
        except Exception as exc:
            print(f"[prosody] no se pudo leer {ruta.name}: {exc!r} "
                  f"-- se prueba el siguiente")

    # Lo que el usuario ha dicho que NO quiere, venga de donde venga.
    quitadas = _plano(datos.get("quitadas"))

    def _sin_quitadas(conjunto):
        return {x for x in conjunto if x not in quitadas}

    return {
        # Al principio de la frase, ganan a todo lo demas.
        "exc_inicio": _sin_quitadas(_plano(datos.get("exclamaciones_inicio"))),
        # Solo cuentan completas, en cualquier parte de la frase.
        "exc_frase": _sin_quitadas(_plano(datos.get("exclamaciones_frase"))),
        "exc_sueltas": _sin_quitadas(_plano(datos.get("exclamaciones_sueltas")) or EXCLAMATION_WORDS),
        "preg_inicio": _sin_quitadas(_plano(datos.get("preguntas_inicio")) or QUESTION_STARTERS),
        "preg_final": _sin_quitadas(_plano(datos.get("preguntas_final")) or QUESTION_TAGS),
        "sugerencias": _sin_quitadas(_plano(datos.get("sugerencias")) or SUGGESTION_CUES),
    }



def _normalize(text: str) -> str:
    text = text.strip().lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


# Se carga AQUI y no arriba: _cargar_listas() usa _normalize(), asi que tiene
# que estar definida antes. Se intento poner junto a las listas de respaldo y
# petaba al importar el modulo.
LISTAS = _cargar_listas()


def _estimate_f0_contour(pcm: np.ndarray, samplerate: int) -> np.ndarray:
    """Estima F0 por ventanas (autocorrelación), devuelve array de Hz
    (0.0 en ventanas no sonoras / silencio)."""
    frame_len = max(1, int(samplerate * FRAME_MS / 1000))
    hop_len = max(1, int(samplerate * HOP_MS / 1000))
    lag_min = max(1, int(samplerate / F0_MAX))
    lag_max = min(frame_len - 1, int(samplerate / F0_MIN))

    if len(pcm) < frame_len or lag_min >= lag_max:
        return np.array([])

    n_frames = 1 + (len(pcm) - frame_len) // hop_len
    window = np.hanning(frame_len)
    f0s = []

    for i in range(n_frames):
        start = i * hop_len
        frame = pcm[start:start + frame_len].astype(np.float64)
        frame = frame - frame.mean()
        if np.max(np.abs(frame)) < 200:  # silencio / ruido de fondo, umbral en escala int16
            f0s.append(0.0)
            continue
        frame = frame * window
        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(corr) // 2:]
        if corr[0] <= 0:
            f0s.append(0.0)
            continue
        segment = corr[lag_min:lag_max]
        if segment.size == 0:
            f0s.append(0.0)
            continue
        peak_idx = int(np.argmax(segment)) + lag_min
        peak_val = corr[peak_idx]
        # umbral de "voz sonora": el pico debe ser una fracción decente de la energía total
        if peak_val < 0.3 * corr[0]:
            f0s.append(0.0)
            continue
        f0s.append(samplerate / peak_idx)

    return np.array(f0s)


def _prosodic_signal(pcm_bytes: bytes, samplerate: int) -> dict:
    """Devuelve {'final_slope', 'range', 'voiced_ratio'} a partir del audio
    crudo (PCM16 mono). Todos 0.0 si no hay suficiente señal sonora."""
    if not pcm_bytes:
        return {"final_slope": 0.0, "range": 0.0, "voiced_ratio": 0.0}

    pcm = np.frombuffer(pcm_bytes, dtype=np.int16)
    contour = _estimate_f0_contour(pcm, samplerate)
    voiced = contour[contour > 0]

    if voiced.size < 4:
        return {"final_slope": 0.0, "range": 0.0, "voiced_ratio": 0.0}

    voiced_idx = np.nonzero(contour > 0)[0]
    third = max(1, len(voiced_idx) // 3)
    first_third = contour[voiced_idx[:third]]
    last_third = contour[voiced_idx[-third:]]

    final_slope = float(last_third.mean() - first_third.mean())
    pitch_range = float(voiced.max() - voiced.min())
    voiced_ratio = float(len(voiced) / max(1, len(contour)))

    return {"final_slope": final_slope, "range": pitch_range, "voiced_ratio": voiced_ratio}


def classify_utterance(pcm_bytes: bytes, samplerate: int, text: str) -> tuple[str, float]:
    """Clasifica una frase ya transcrita + su audio en:
    "question" | "exclamation" | "suggestion" | "statement"

    Devuelve (tipo, confianza 0-1). confianza baja (<0.4) significa que la
    señal de audio era débil/corta y se decidió sobre todo por texto (o,
    si tampoco había pistas de texto, por defecto a "statement").
    """
    norm = _normalize(text)
    tokens = norm.split()

    # --- pistas léxicas (más fiables que el tono con este pitch tracker ligero) ---
    if tokens:
        # 1) Exclamaciones que NO dejan lugar a duda al principio de la frase.
        #
        # Van las primeras a proposito. "que barbaridad" empieza por "que",
        # que tambien abre preguntas, y sin esto se clasificaba como
        # pregunta: salia "¿Que barbaridad?" en vez de "¡Que barbaridad!".
        # Quien dice "ay" o "ojala" no esta preguntando nada.
        primera = tokens[0]
        dos = " ".join(tokens[:2]) if len(tokens) > 1 else ""
        tres = " ".join(tokens[:3]) if len(tokens) > 2 else ""
        if (primera in LISTAS["exc_inicio"] or dos in LISTAS["exc_inicio"]
                or tres in LISTAS["exc_inicio"]):
            return "exclamation", 0.8

        # 2) Frases que solo cuentan COMPLETAS.
        #
        # En ingles esto es imprescindible: "god" o "hell" sueltos aparecen
        # en preguntas y en frases normales sin ninguna entonacion especial.
        #
        # Y hay un caso mas fino, que el aviso: "what the hell" es una
        # exclamacion, pero "what the hell IS THIS" es una pregunta. La frase
        # hecha esta en las dos. Asi que solo cuenta si la oracion se acaba
        # ahi o poco despues -- si sigue y ademas empezaba por una palabra de
        # pregunta, manda la pregunta.
        for f in LISTAS["exc_frase"]:
            if f not in norm:
                continue
            resto = norm.split(f, 1)[1].strip()
            empieza_pregunta = (primera in LISTAS["preg_inicio"]
                                or dos in LISTAS["preg_inicio"])
            if resto and empieza_pregunta:
                break        # "what the hell is this" -> que decida la pregunta
            return "exclamation", 0.8

        # 3) A partir de aqui, como siempre.
        if primera in LISTAS["preg_inicio"] or dos in LISTAS["preg_inicio"]:
            return "question", 0.75
        if tokens[-1] in LISTAS["preg_final"] and len(tokens) > 1:
            return "question", 0.65
        if any(w in norm for w in LISTAS["exc_sueltas"]):
            return "exclamation", 0.7
        if any(cue in norm for cue in LISTAS["sugerencias"]):
            return "suggestion", 0.65

    # --- señal prosódica (respaldo cuando no hay pistas léxicas claras) ---
    sig = _prosodic_signal(pcm_bytes, samplerate)
    if sig["voiced_ratio"] < 0.15:
        return "statement", 0.2  # muy poca señal sonora útil, valor por defecto

    if sig["final_slope"] > 25:  # sube el tono al final -> pregunta
        return "question", min(0.6, 0.3 + sig["voiced_ratio"])
    if sig["range"] > 120:  # mucho rango de tono -> exclamación
        return "exclamation", min(0.6, 0.3 + sig["voiced_ratio"])

    return "statement", min(0.55, 0.25 + sig["voiced_ratio"])
