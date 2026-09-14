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
Lo mismo que numbers_es, pero en inglés: convierte números dictados como
palabras ("thirty two") a enteros, token a token.

    "thirty two"          -> 32
    "one hundred"         -> 100
    "twenty one"          -> 21

POR QUE HIZO FALTA
------------------
Hasta el 5-sep-2026 solo existía numbers_es, y TODO lo numérico pasaba por
él: las casillas del tablero, las zonas dentro de una casilla, "corrige
<nº>", "mover <casilla>". O sea que con el inglés de idioma principal la
interfaz numérica entera quedaba muerta -- que es casi toda la aplicación.

Se vio en una prueba real: "thirty two" se reconocía perfectamente
(`lang=en, conf=1.00`) y acto seguido salía `no entendido`. El número
llegaba bien y no había quien lo tradujera.

DIFERENCIAS CON EL ESPAÑOL, que no son cosméticas
--------------------------------------------------
1. **La escala.** El inglés usa la escala corta: `billion` son 10^9, no
   10^12. numbers_es usa la larga (1 billón = 10^12), que es la española.
   Traducir la tabla sin tocar esto daría números mil veces mayores.

2. **Las centenas son compuestas.** El español tiene una palabra entera
   para cada una ("doscientos"); el inglés las construye con coeficiente
   ("two hundred"), igual que hace con los millares. Por eso aquí "hundred"
   es una escala más y no un diccionario.

3. **El "and".** "one hundred and five" es corriente en inglés (y en
   español no existe ese "y" ahí). Se acepta y se ignora.

4. **"a" vale por "one"**: "a hundred", "a thousand".

Se espera texto ya normalizado (minúsculas, sin guiones) -- ver
command_router._normalize(). Por eso "twenty-one" llega como dos tokens.

La interfaz es EXACTAMENTE la de numbers_es (`parse_number_prefix(tokens,
start) -> (valor, consumidos)`), para que quien llame pueda elegir uno u
otro sin enterarse de nada más.
"""

UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3,
    "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}

# "a hundred" es 100, pero "a" A SECAS NO ES UN NUMERO, y esto importa
# mucho más de lo que parece: los dos parseadores se prueban sobre el mismo
# texto (ver command_router._parsear_numero), así que un "a" suelto valiendo
# 1 haría que decir "a" en español abriese la casilla 1. Y "a" es de las
# palabras más corrientes que hay.
#
# Por eso vale solo pegada a una escala: "a hundred", "a thousand".
_ARTICULOS = {"a", "an"}
TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

# ESCALA CORTA, la del inglés: billion = 10^9. En numbers_es es 10^12.
# "hundred" entra aquí como una escala más, y ésa es la diferencia gorda
# con el español, que tiene palabra propia para cada centena.
_SCALES = [
    ({"billion", "billions"}, 10 ** 9),
    ({"million", "millions"}, 10 ** 6),
    ({"thousand", "thousands"}, 10 ** 3),
    ({"hundred", "hundreds"}, 10 ** 2),
]

# "and" se salta donde el inglés lo mete: "one hundred and five".
_RELLENO = {"and"}


def _saltar_relleno(tokens, i):
    """Salta un 'and' suelto. Devuelve el índice siguiente."""
    if i < len(tokens) and tokens[i] in _RELLENO:
        return i + 1
    return i


def _parse_0_99(tokens, i):
    """Lee un número 0-99 (decena [+ unidad] | teens | unidad suelta) a
    partir de tokens[i]. (valor, consumidos) o (None, 0)."""
    if i >= len(tokens):
        return None, 0
    tok = tokens[i]

    if tok in TENS:
        total = TENS[tok]
        consumed = 1
        # "thirty two" -> 32. Sin "y" por medio, al revés que el español.
        if i + 1 < len(tokens) and tokens[i + 1] in UNITS:
            total += UNITS[tokens[i + 1]]
            consumed = 2
        return total, consumed

    if tok in TEENS:
        return TEENS[tok], 1

    if tok in UNITS:
        return UNITS[tok], 1

    return None, 0


def _parse_scaled(tokens, i, scale_idx):
    """Lee un número completo desde tokens[i], componiendo escalas desde
    _SCALES[scale_idx] hacia abajo (billion -> million -> thousand ->
    hundred -> 0-99).

    El coeficiente de cada escala se calcula con las escalas MENORES, que
    es lo que permite leer "two hundred thousand" (coeficiente de
    "thousand" = "two hundred" = 200) o "one million two hundred thousand
    and three". Misma recursión que numbers_es, con "hundred" añadido
    abajo del todo.
    """
    if i >= len(tokens):
        return None, 0
    if scale_idx >= len(_SCALES):
        return _parse_0_99(tokens, i)

    words, scale_value = _SCALES[scale_idx]
    start = i

    # "a hundred" / "an hour"... el artículo solo cuenta como 1 si detrás
    # viene la palabra de escala. Ver _ARTICULOS.
    if (tokens[i] in _ARTICULOS and i + 1 < len(tokens)
            and tokens[i + 1] in words):
        coeff, consumed = 1, 1
    else:
        coeff, consumed = _parse_scaled(tokens, i, scale_idx + 1)
    j = i + consumed if coeff is not None else i

    if j < len(tokens) and tokens[j] in words:
        c = coeff if coeff is not None else 1     # "hundred" a secas = 100
        total = c * scale_value
        i = _saltar_relleno(tokens, j + 1)
        rest, rest_consumed = _parse_scaled(tokens, i, scale_idx + 1)
        if rest is not None:
            total += rest
            i += rest_consumed
        return total, i - start

    # esta escala no aparece aquí: se delega tal cual en la de abajo
    return _parse_scaled(tokens, start, scale_idx + 1)


def parse_number_prefix(tokens, start):
    """Intenta leer UN número a partir de tokens[start].

    Devuelve (valor:int, tokens_consumidos:int) o (None, 0) si tokens[start]
    no empieza un número reconocible. Misma firma que
    numbers_es.parse_number_prefix.
    """
    if start >= len(tokens):
        return None, 0

    # dígitos sueltos, ej. "45"
    if tokens[start].isdigit():
        return int(tokens[start]), 1

    return _parse_scaled(tokens, start, 0)
