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
corrections.py: Aprendizaje de correcciones de palabra para VoiceController.

Cuando el usuario corrige una palabra concreta del Pre-Texto con
"corregir <numero> <modificador> [ambiguo]" (ver command_router._correct_word),
esa corrección se recuerda en corrections.json para aplicarse la próxima vez
que se dicte la misma palabra -- así no hay que repetir "corregir 4
mayuscula" cada vez que se dicta "Sevilla".

Dos niveles de confianza, elegidos por el usuario al corregir:

  - STRICT (por defecto, sin decir "ambiguo"): UN solo modificador que se
    auto-aplica en cuanto la palabra vuelve a aparecer en el texto
    dictado, sin avisar -- pensado para palabras sin otro significado
    razonable en el contexto del usuario (ej. "sevilla" -> "Sevilla",
    "juan" -> "Juán").

  - AMBIGUOUS (diciendo "ambiguo" al corregir): la palabra puede resolverse
    de VARIAS formas distintas según el contexto (ej. "once" puede ser el
    número 11, el acrónimo "ONCE", o simplemente la palabra "once" tal
    cual). Cada vez que se enseña una corrección ambigua para la misma
    palabra, el modificador se AÑADE a la lista de opciones de esa
    palabra (no sustituye a las anteriores). Nunca se auto-aplica sola;
    en vez de eso, la próxima vez que la palabra aparezca se pregunta en
    el panel de sugerencias, enumerando todas las opciones aprendidas
    hasta ahora (ej. '¿"once" como "siglas", "cifras" o "letras"?'), y el
    usuario resuelve diciendo directamente el nombre de la opción elegida
    (ver command_router._try_resolve_ambiguous_choice) -- no hace falta
    ningún comando adicional tipo "vale".

Una palabra no puede estar aprendida como estricta Y ambigua a la vez: la
corrección más reciente gana, y sustituye por completo lo que hubiera en
el otro nivel (si pasa de ambigua a estricta, se pierden las opciones
ambiguas acumuladas; si pasa de estricta a ambigua, empieza una lista
ambigua nueva con esa única opción).

El diccionario es GLOBAL (no separado por idioma ni por proyecto/sesión):
si hay coincidencia de palabras entre distintos contextos (ej. dos
organizaciones con el mismo acrónimo), el usuario ha aceptado que da
igual -- la corrección aprendida es la misma para cualquier aparición de
esa palabra.

Cada entrada solo guarda el/los MODIFICADOR/ES (ver
command_router._WORD_MODIFIERS / _apply_word_modifier: "mayuscula",
"minuscula", "siglas", "cifras", "letras"), no el resultado literal ya
aplicado -- así, aplicar la corrección es siempre
_apply_word_modifier(palabra_tal_como_aparece, modificador), y respeta
igual que la corrección manual cualquier puntuación pegada a la palabra.
"""

import json

import paths

# Estructura de corrections.json:
# {
#   "strict":    {"<palabra_normalizada>": "<modificador>", ...},
#   "ambiguous": {"<palabra_normalizada>": ["<modificador>", ...], ...}
# }
# (nota: "ambiguous" guarda una LISTA de opciones por palabra, no un único
# modificador -- ver load(), que migra sola el formato antiguo de versiones
# previas de este módulo, donde "ambiguous" guardaba un string suelto).


def load() -> dict:
    """Carga corrections.json. Si no existe o está corrupto, empieza en
    blanco (nunca revienta el arranque de VoiceController por esto)."""
    try:
        with open(paths.CORRECTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"strict": {}, "ambiguous": {}}
    data.setdefault("strict", {})
    data.setdefault("ambiguous", {})
    # migración desde el formato anterior (una única corrección ambigua por
    # palabra, guardada como string suelto en vez de lista de opciones)
    for word, value in list(data["ambiguous"].items()):
        if isinstance(value, str):
            data["ambiguous"][word] = [value]
    return data


def save(data: dict):
    """Persiste corrections.json. Si falla (permisos, disco...), no
    interrumpe el flujo de dictado -- se pierde solo el aprendizaje de
    esta corrección, no la corrección puntual que ya se aplicó en el
    Pre-Texto."""
    try:
        with open(paths.CORRECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError:
        pass


def learn(data: dict, word_norm: str, modifier: str, ambiguous: bool):
    """Registra el aprendizaje de `word_norm` -> `modifier`.

    - Si `ambiguous` es True: añade `modifier` a la LISTA de opciones
      ambiguas de `word_norm` (sin duplicar si ya estaba), y borra
      cualquier corrección estricta previa de esa palabra.
    - Si `ambiguous` es False: fija `modifier` como la única corrección
      ESTRICTA de `word_norm`, y borra cualquier lista de opciones
      ambiguas previa de esa palabra (una palabra no puede estar en
      ambos niveles a la vez).

    No guarda en disco por sí sola: llamar a save() aparte."""
    if not word_norm:
        return
    if ambiguous:
        data["strict"].pop(word_norm, None)
        options = data["ambiguous"].setdefault(word_norm, [])
        if modifier not in options:
            options.append(modifier)
    else:
        data["ambiguous"].pop(word_norm, None)
        data["strict"][word_norm] = modifier


def find_strict(data: dict, word_norm: str):
    """Devuelve el modificador aprendido como ESTRICTO para `word_norm`, o
    None si no hay ninguno."""
    return data.get("strict", {}).get(word_norm)


def find_ambiguous(data: dict, word_norm: str):
    """Devuelve la LISTA de modificadores aprendidos como opciones
    AMBIGUAS para `word_norm` (lista vacía si no hay ninguno), en el
    orden en que se fueron enseñando."""
    return data.get("ambiguous", {}).get(word_norm, [])
