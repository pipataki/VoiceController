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
math_notation: el ALGORITMO de la notación matemática, sin idioma.

POR QUE ESTA SEPARADO DEL VOCABULARIO
-------------------------------------
Al traducir el programa al inglés hacía falta un `math_notation_en`. Lo
fácil era copiar `math_notation_es` entero y cambiar las tablas -- y eso
habría dejado DOS COPIAS del mismo algoritmo, que es exactamente lo que
este proyecto lleva días pagando: dos sitios con el umbral del locutor, dos
listas de comandos en la calibración, dos ventanas de ayuda.

Dos copias no se estropean el día que se escriben. Se estropean el día que
alguien arregla una y no sabe que existe la otra.

Así que el algoritmo vive aquí una sola vez y recibe las tablas del idioma
que toque. `math_notation_es` y `math_notation_en` son solo vocabulario.

QUE HACE, EN CORTO
------------------
`looks_like_math()` decide si una frase dictada SUENA a matemáticas o
pseudocódigo. `to_symbolic()` la traduce a símbolos. La segunda da por
hecho que la primera dijo que sí.

La heurística prioriza NO dispararse en dictado normal: en español "por",
"menos" y "entre" son palabras corrientísimas ("por si acaso", "entre
semana"), y romper una frase normal es mucho peor que no detectar una
fórmula. Por eso pide densidad alta de señales, no una sola.
"""


class Vocabulario:
    """Las tablas de un idioma. Ver math_notation_es / math_notation_en.

    - `phrases`: lista de (lista_de_palabras, símbolo). Se prueban ANTES que
      las palabras sueltas, y en el orden dado: las más largas primero, o
      "mayor o igual que" se comería primero el "mayor" suelto.
    - `single`: palabra suelta -> símbolo.
    - `variables`: letra hablada -> variable de una letra.
    - `pseudocode`: palabras clave que además son señal fuerte de "esto es
      código, no prosa".
    - `extra_senales`: palabras que cuentan como señal aunque no traduzcan
      a nada por sí solas (las que forman parte de una frase compuesta).
    - `parse_number_prefix`: el lector de números del idioma
      (numbers_es / numbers_en).
    """

    def __init__(self, phrases, single, variables, pseudocode,
                 extra_senales, parse_number_prefix, no_senales=()):
        self.phrases = phrases
        self.single = single
        self.variables = variables
        self.pseudocode = pseudocode
        self.parse_number_prefix = parse_number_prefix
        # PALABRAS QUE TRADUCEN PERO NO DELATAN.
        #
        # En español casi todo el vocabulario matemático es específico. En
        # inglés no: "and", "or", "for", "do", "not", "true", "over" son
        # palabras de todos los días. Si contaran como señal, "i have three
        # dogs and two cats" saldría como expresión matemática -- medido.
        #
        # Así que siguen traduciéndose cuando la frase YA es matemática,
        # pero no sirven para decidir que lo sea. Vacío por defecto: el
        # español no necesita ninguna.
        self.senales = ((set(single) | set(variables) | set(pseudocode)
                         | set(extra_senales)) - set(no_senales))


def looks_like_math(tokens: list, voc: Vocabulario) -> bool:
    """¿Esta frase (tokens ya normalizados) parece notación matemática o
    pseudocódigo en vez de una frase normal?

    No es infalible a propósito: prefiere el falso negativo (no detectar
    una fórmula) al falso positivo (romper una frase corriente).
    """
    if not tokens:
        return False

    # Empezar por una palabra clave de código ya es señal suficiente:
    # "si...", "mientras...", "función..." no abren frases corrientes.
    if tokens[0] in voc.pseudocode:
        return True

    signal = 0
    numeric = 0
    i = 0
    while i < len(tokens):
        val, consumed = voc.parse_number_prefix(tokens, i)
        if val is not None and consumed:
            numeric += 1
            i += consumed
            continue
        if tokens[i] in voc.senales:
            signal += 1
        i += 1

    if signal == 0:
        # Sin ninguna señal de operador, variable o palabra clave, ni con
        # varios números sueltos: podría ser "tengo tres perros y dos gatos".
        return False

    density = (signal + numeric) / len(tokens)
    return density >= 0.4


def to_symbolic(text_normalized: str, voc: Vocabulario) -> str:
    """Convierte una frase ya detectada como matemática a su forma
    simbólica. No vuelve a comprobar looks_like_math().

    Lo que no reconoce se cae: se añade "" en su sitio. Es deliberado --
    en modo fórmula lo que no es notación suele ser ruido del
    reconocedor, y colarlo dentro de una expresión la estropea más que
    perderlo.

    Salvo una LETRA SUELTA, que en una fórmula es una variable, no ruido. El
    reconocedor a veces da la letra tal cual ("p") y no su nombre ("pe"), y
    se perdía: "a más tres igual a p" salía "a + 3 =" (15-sep-2026). Se
    mira después de las tablas, así que la "y" de "i griega" o de
    "treinta y cinco" sigue siendo lo que era.
    """
    tokens = text_normalized.split()
    out = []
    i = 0
    n = len(tokens)

    while i < n:
        matched = False
        for words, symbol in voc.phrases:
            length = len(words)
            if tokens[i:i + length] == words:
                out.append(symbol)
                i += length
                matched = True
                break
        if matched:
            continue

        val, consumed = voc.parse_number_prefix(tokens, i)
        if val is not None and consumed:
            out.append(str(val))
            i += consumed
            continue

        tok = tokens[i]
        if tok in voc.pseudocode:
            out.append(voc.pseudocode[tok])
        elif tok in voc.single:
            out.append(voc.single[tok])
        elif tok in voc.variables:
            out.append(voc.variables[tok])
        elif len(tok) == 1 and "a" <= tok <= "z":
            out.append(tok + " ")
        else:
            out.append("")
        i += 1

    return " ".join(out)
