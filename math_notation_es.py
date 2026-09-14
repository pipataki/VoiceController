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
math_notation_es.py: Detecta cuándo una frase dictada "suena" a notación
matemática o pseudocódigo (sumas, igualdades, comparaciones, estructuras
tipo "si...entonces...") y la convierte a su forma simbólica.

NO valida si la expresión resultante es matemática o sintácticamente
correcta -- solo traduce palabra dictada -> símbolo/token, de forma literal.

Se espera texto ya normalizado (minúsculas, sin acentos) -- ver
command_router._normalize(). Reutiliza numbers_es para los números.

Deliberadamente NO se aplica a cualquier frase que contenga "por", "menos",
"entre", etc. (son palabras muy comunes en español normal: "por si acaso",
"entre semana"...). Solo se activa cuando looks_like_math() da positivo,
es decir, cuando la frase en conjunto tiene una proporción alta de
números/operadores/palabras clave de pseudocódigo.
"""

import math_notation
from numbers_es import parse_number_prefix

# frases de más de una palabra -> símbolo (se prueban primero, más largas primero)

CODIGO = False


PHRASES = [
    (["mayor", "o", "igual", "que"], ">= "),
    (["menor", "o", "igual", "que"], "<= "),
    (["distinto", "de"], "!= "),
    (["distinto", "a"], "!= "),
    (["no", "es"], "!= "),
    (["es", "igual", "a"], "== "),
    (["igual", "a"], "= "),
    (["mayor", "que"], "> "),
    (["menor", "que"], "< "),
    (["elevado", "a"], "^ "),
    (["al", "cuadrado"], "^2 "),
    (["al", "cubo"], "^3 "),
    (["raiz", "cuadrada", "de"], "sqrt( "),
    (["abre", "parentesis"], "( "),
    (["cierra", "parentesis"], ") "),
    (["abre", "corchetes"], "[ "),
    (["cierra", "corchetes"], "] "),
    (["abre", "llaves"], "{ "),
    (["cierra", "llaves"], "} "),
    (["por", "ciento"], "% "),
    (["y","griega"],"y "),
    (["i","griega"],"y "),
    (["si","y","solo","si"],"<--> "),
    (["si","solo","si"],"<--> "),
    (["imprime","salto","de","linea"],"P/n>> "),
]

# palabra suelta -> símbolo
SINGLE = {
    # "menos" estuvo escrito como "menos " (con un espacio) y no coincidia
    # nunca: "dos menos tres" salia "2 3". Visto al generar COMANDOS.md, 13-sep-2026.
    "mas": "+ ", "menos": "- ", "por": "* ", "entre": "/ ", "dividido": "/ ",
    "igual": "= ", "modulo": "% ", "coma": ", ","vale": "= ",
    "mayor":"> ", "menor":"< ",
    "cuadrado": "^2 ",
    "cubo": "^3 ",
    "elevado": "^ ",
    "corchetes": "[ ",
    "llaves": "{ ",
    "parentesis": "( ",
    "cierto": "True ",
    "no": "! ",
    "verdadero": "True ",
    "falso": "False ",
}

# letras habladas -> variable de una letra (solo se usan dentro de una
# frase ya detectada como matemática/pseudocódigo, así que no interfieren
# con el dictado normal)
VARIABLES = {
    "mas": "+ ",
    "equis": "x ",
    "zeta": "z ",
    "ceta": "z ",
    "ka": "k ",
    "ca": "k ",
    "ene": "n ",
    "eme": "m ",
    "jota": "j ",
    "i": "i ",
    "a": "a ","ah": "a ",
    "e": "e ","eh": "e ",
    "o": "o ","oh": "o ",
    "u": "u ","uh": "u ",


    "be": "b ",
    "ce": "c ",
    "de": "d ",
    "efe": "f ",
    "ge": "g ",
    "ache": "h ","hache": "h ",
    "jota": "j ",
    "ca": "k ","ka": "k ",
    "ele": "l ",
    "eme": "m ",
    "ene": "n ",
    "pe": "p ",
    "cu": "q ", "ku": "q ",
    "erre": "r ", "ere": "r ",
    "ese": "s ",
    "te": "t ",
    "uve": "v ", "ube": "v ", "ue": "v ",
    "uvedoble": "w ","ubedoble": "w ", "uedoble": "w ",
    "igriega": "y ",
    "ygriega": "y ",
    "ekis": "x ",


}

# palabras clave de pseudocódigo: se dejan tal cual (no se traducen a
# símbolo), pero cuentan como señal fuerte de "esto es código, no prosa"
PSEUDOCODE_KEYWORDS = {

    "<--> ": "<--> ",
    "si": "--> ",
    "entonces": "THEN ",
    "sino": "! --> ",
    "mientras": "WHILE ",
    "para": "FOR ",
    "funcion": "F# ",
    "resultado": "F<< ",
    "retorna": ">>> ",
    "devuelve": ">>> ",
    "recibe": "<<< ",
    "imprime": "P>> ",
    "P/n>> ": "P/n>> ",
    "variable": "VAR ",
    "hacer": "DO ",
    "repetir": "2X ",
    "entero": "INT ",
    "flotante": "FLOAT ",
    "booleano": "BOOL ",
    "binario": "BOOL ",
    "and": "AND ",
    "or": "OR ",
    "corchetes": "[ ",
    "llaves": "{ ",
    "parentesis": "( ",
    "cierto": "True ",
    "no": "! ",
    "verdadero": "True ",
    "falso": "False ",

}


# El algoritmo NO vive aquí: está en math_notation.py, una sola vez, y
# recibe estas tablas. Ver allí el porqué -- en corto, para que no haya dos
# copias de la misma lógica esperando a que alguien arregle solo una.
_VOC = math_notation.Vocabulario(
    phrases=PHRASES,
    single=SINGLE,
    variables=VARIABLES,
    pseudocode=PSEUDOCODE_KEYWORDS,
    # Palabras que cuentan como señal aunque solas no traduzcan nada:
    # forman parte de frases compuestas ("mayor que", "al cuadrado").
    extra_senales={"mayor", "menor", "distinto", "diferente", "cuadrado",
                   "cubo", "raiz", "parentesis", "corchetes", "llaves",
                   "elevado", "ciento"},
    parse_number_prefix=parse_number_prefix,
)


def looks_like_math(tokens: list) -> bool:
    """¿Suena a matemáticas o pseudocódigo? Ver math_notation."""
    return math_notation.looks_like_math(tokens, _VOC)


def to_symbolic(text_normalized: str) -> str:
    """A notación simbólica. Ver math_notation."""
    return math_notation.to_symbolic(text_normalized, _VOC)
