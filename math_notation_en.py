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
math_notation_en: el vocabulario INGLÉS del modo fórmula.

Solo tablas. El algoritmo está en math_notation.py, compartido con el
español, para que no haya dos copias de la misma lógica.

DIFERENCIAS CON EL ESPAÑOL, que no son de traducción
-----------------------------------------------------
1. **Las letras.** En español las letras habladas ("efe", "erre", "uvedoble")
   casi no aparecen en prosa normal. En inglés los NOMBRES de las letras SON
   palabras corrientes: "see" (c), "why" (y), "are" (r), "you" (u), "bee"
   (b), "in" no, pero "an" sí. Eso podría destrozar una frase dictada.

   No es tan grave como parece, y por una razón concreta: estas tablas solo
   se aplican DESPUÉS de que looks_like_math() haya dicho que sí, y esa
   comprobación pide densidad alta de señales. Aun así, aquí se han dejado
   fuera los homógrafos más peligrosos y se prefieren las formas
   deletreadas -- "double u" antes que "w".

2. **"times" y "over".** El español multiplica con "por", que es una
   preposición corrientísima; el inglés usa "times", mucho más específico.
   Ahí el inglés lo tiene más fácil.

3. **Los símbolos de salida son los mismos.** El pseudocódigo que produce
   ("THEN", "WHILE", "P>>") ya estaba en inglés en el módulo español, así
   que la salida no cambia de idioma: cambia lo que se DICE para llegar a
   ella.
"""

import math_notation
from numbers_en import parse_number_prefix

# Frases de más de una palabra -> símbolo. Se prueban antes que las
# palabras sueltas y EN ESTE ORDEN: las largas primero, o "greater than or
# equal to" se comería primero el "greater than".
PHRASES = [
    (["greater", "than", "or", "equal", "to"], ">= "),
    (["less", "than", "or", "equal", "to"], "<= "),
    (["greater", "or", "equal", "than"], ">= "),
    (["less", "or", "equal", "than"], "<= "),
    (["is", "not", "equal", "to"], "!= "),
    (["not", "equal", "to"], "!= "),
    (["different", "from"], "!= "),
    (["is", "not"], "!= "),
    (["is", "equal", "to"], "== "),
    (["equal", "to"], "= "),
    (["equals", "to"], "= "),
    (["greater", "than"], "> "),
    (["less", "than"], "< "),
    (["to", "the", "power", "of"], "^ "),
    (["raised", "to"], "^ "),
    (["to", "the", "power"], "^ "),
    (["square", "root", "of"], "sqrt( "),
    (["open", "parenthesis"], "( "),
    (["close", "parenthesis"], ") "),
    (["open", "bracket"], "( "),
    (["close", "bracket"], ") "),
    (["open", "square", "bracket"], "[ "),
    (["close", "square", "bracket"], "] "),
    (["open", "brackets"], "[ "),
    (["close", "brackets"], "] "),
    (["open", "curly", "brace"], "{ "),
    (["close", "curly", "brace"], "} "),
    (["open", "brace"], "{ "),
    (["close", "brace"], "} "),
    (["per", "cent"], "% "),
    (["if", "and", "only", "if"], "<--> "),
    (["double", "u"], "w "),
    (["print", "new", "line"], "P/n>> "),
    (["new", "line"], "P/n>> "),
]

# Palabra suelta -> símbolo.
SINGLE = {
    "plus": "+ ", "minus": "- ", "times": "* ", "over": "/ ",
    "divided": "/ ", "equals": "= ", "equal": "= ", "modulo": "% ",
    "mod": "% ", "comma": ", ",
    "greater": "> ", "less": "< ",
    "squared": "^2 ",
    "cubed": "^3 ",
    "power": "^ ",
    "percent": "% ",
    "brackets": "[ ",
    "braces": "{ ",
    "parenthesis": "( ",
    "true": "True ",
    "false": "False ",
    "not": "! ",
}

# Letras habladas -> variable de una letra. Ver la nota 1 de la cabecera:
# se prefieren las formas deletreadas y se evitan los homógrafos peores
# ("see", "why", "are", "you"), que en inglés son palabras de uso diario.
VARIABLES = {
    "ex": "x ", "eks": "x ",
    "zed": "z ", "zee": "z ",
    "kay": "k ",
    "en": "n ",
    "em": "m ",
    "jay": "j ",
    "aitch": "h ",
    "cue": "q ", "queue": "q ",
    "ar": "r ",
    "ess": "s ",
    "tee": "t ",
    "vee": "v ",
    "dee": "d ",
    "ef": "f ",
    "gee": "g ",
    "el": "l ",
    "pee": "p ",
    "bee": "b ",
    "a": "a ", "i": "i ", "o": "o ", "e": "e ", "u": "u ",
    # Y las letras tal cual las suele escribir Vosk cuando se dicen
    # sueltas. Sin esto, "x to the power of two" perdía la x y salía
    # "^ 2" -- medido.
    "x": "x ", "y": "y ", "z": "z ", "b": "b ", "c": "c ", "d": "d ",
    "f": "f ", "g": "g ", "h": "h ", "j": "j ", "k": "k ", "l": "l ",
    "m": "m ", "n": "n ", "p": "p ", "q": "q ", "r": "r ", "s": "s ",
    "t": "t ", "v": "v ", "w": "w ",
}

# Palabras clave de pseudocódigo. Además de traducirse, son señal fuerte de
# "esto es código, no prosa": si la frase EMPIEZA por una de ellas, ya se
# considera matemática.
PSEUDOCODE_KEYWORDS = {
    "<--> ": "<--> ",
    "if": "--> ",
    "then": "THEN ",
    "else": "! --> ",
    "otherwise": "! --> ",
    "while": "WHILE ",
    "for": "FOR ",
    "function": "F# ",
    "result": "F<< ",
    "return": ">>> ",
    "returns": ">>> ",
    "receives": "<<< ",
    "takes": "<<< ",
    "print": "P>> ",
    "P/n>> ": "P/n>> ",
    "variable": "VAR ",
    "do": "DO ",
    "repeat": "2X ",
    "integer": "INT ",
    "float": "FLOAT ",
    "boolean": "BOOL ",
    "binary": "BOOL ",
    "and": "AND ",
    "or": "OR ",
    "brackets": "[ ",
    "braces": "{ ",
    "parenthesis": "( ",
    "true": "True ",
    "false": "False ",
    "not": "! ",
}

_VOC = math_notation.Vocabulario(
    phrases=PHRASES,
    single=SINGLE,
    variables=VARIABLES,
    pseudocode=PSEUDOCODE_KEYWORDS,
    # Cuentan como señal aunque solas no traduzcan: forman parte de frases
    # compuestas ("greater than", "square root of").
    extra_senales={"than", "root", "square", "raised", "close", "open",
                   "cent", "only", "curly", "brace", "power"},
    # Traducen, pero no delatan: son palabras corrientes en inglés. Ver
    # math_notation.Vocabulario. Las vocales sueltas entran aquí por lo
    # mismo ("a", "i" son palabras).
    # Solo las que de verdad son de uso diario. "root", "cent", "curly",
    # "brace", "raised" y "receives" NO lo son, y quitarlas de aquí es lo
    # que hace que "square root of sixteen" y "fifty per cent" se detecten:
    # sin ellas, esas frases se quedaban a cero señales.
    no_senales={"a", "i", "o", "e", "u", "and", "or", "for", "do", "not",
                "true", "false", "over", "result", "takes", "open", "close",
                "square", "only", "than", "power"},
    parse_number_prefix=parse_number_prefix,
)


def looks_like_math(tokens: list) -> bool:
    """¿Suena a matemáticas o pseudocódigo? Ver math_notation."""
    return math_notation.looks_like_math(tokens, _VOC)


def to_symbolic(text_normalized: str) -> str:
    """A notación simbólica. Ver math_notation."""
    return math_notation.to_symbolic(text_normalized, _VOC)
