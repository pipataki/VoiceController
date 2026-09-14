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
Convierte números dictados en español (como palabras: "cuarenta y cinco")
a enteros, token a token, para poder parsear frases tipo:

    "vc cuarenta y cinco tres move"
    "vc ciento cincuenta nueve scroll arriba"

También acepta dígitos sueltos ("45"), por si algún modelo/config de Vosk
llegase a transcribir números como cifras en vez de palabras.

Cubre 0 - 999.999.999.999.999 (hasta miles de billones), compuesto de
forma recursiva: [<coef> billon(es)] [<coef> millon(es)] [<coef> mil] [resto]
donde cada <coef> es a su vez un número 0-999 (o, para "mil"/"millon"/
"billon", puede incluir escalas menores, ej. "dos mil millones").

Se usa la escala larga española (1 billón = 10^12), no la americana.
Se espera texto ya normalizado (minúsculas, sin acentos) — ver
command_router._normalize().
"""

UNITS = {
    "cero": 0, "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}
TEENS = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19,
}
TWENTIES = {
    "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}
HUNDREDS = {
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600, "setecientos": 700,
    "ochocientos": 800, "novecientos": 900,
}



# palabras de escala, de mayor a menor magnitud. Cada entrada es
# (conjunto_de_palabras_que_la_representan, valor). "mil" no pluraliza
# ("dos mil", nunca "dos miles"); "millar"/"millon"/"billon" sí lo hacen.
_SCALES = [
    ({"billon", "billones"}, 10 ** 12),
    ({"millon", "millones"}, 10 ** 6),
    ({"mil", "millar", "millares"}, 10 ** 3),
]



def _parse_0_99(tokens, i):
    """Lee un número 0-99 (decenas [+ 'y' + unidad] | veintitantos | teens
    | unidad suelta) a partir de tokens[i]. (valor, consumidos) o (None, 0)."""
    if i >= len(tokens):
        return None, 0
    tok = tokens[i]

    if tok in TENS:
        total = TENS[tok]
        consumed = 1
        if i + 2 < len(tokens) and tokens[i + 1] == "y" and tokens[i + 2] in UNITS:
            total += UNITS[tokens[i + 2]]
            consumed = 3
        return total, consumed

    if tok in TWENTIES:
        return TWENTIES[tok], 1

    if tok in TEENS:
        return TEENS[tok], 1

    if tok in UNITS:
        return UNITS[tok], 1

    return None, 0


def _parse_0_999(tokens, i):
    """Lee un número 0-999 (centena opcional + resto 0-99) a partir de
    tokens[i]. (valor, consumidos) o (None, 0)."""
    if i >= len(tokens):
        return None, 0
    start = i
    tok = tokens[i]

    if tok in HUNDREDS:
        total = HUNDREDS[tok]
        i += 1
        rest, consumed = _parse_0_99(tokens, i)
        if rest is not None:
            total += rest
            i += consumed
        return total, i - start

    return _parse_0_99(tokens, i)


def _parse_scaled(tokens, i, scale_idx):
    """Lee un número completo a partir de tokens[i], componiendo escalas
    desde _SCALES[scale_idx] hacia abajo (billones -> millones -> mil ->
    0-999). El coeficiente de cada escala se calcula recursivamente con
    las escalas MENORES, para poder leer cosas como "dos mil millones"
    (coeficiente de "millones" = "dos mil" = 2000) o "un millon
    doscientos mil tres" (1 200 003). (valor, consumidos) o (None, 0)."""
    if scale_idx >= len(_SCALES):
        return _parse_0_999(tokens, i)

    words, scale_value = _SCALES[scale_idx]
    start = i

    coeff, consumed = _parse_scaled(tokens, i, scale_idx + 1)
    j = i + consumed if coeff is not None else i

    if j < len(tokens) and tokens[j] in words:
        c = coeff if coeff is not None else 1
        total = c * scale_value
        i = j + 1
        rest, rest_consumed = _parse_scaled(tokens, i, scale_idx + 1)
        if rest is not None:
            total += rest
            i += rest_consumed
        return total, i - start

    # esta escala no aparece aquí: delega tal cual en la escala inferior
    return _parse_scaled(tokens, start, scale_idx + 1)


def parse_number_prefix(tokens, start):
    """Intenta leer UN número a partir de tokens[start].

    Devuelve (valor:int, tokens_consumidos:int) o (None, 0) si tokens[start]
    no es el inicio de un número reconocible.
    """
    if start >= len(tokens):
        return None, 0

    # dígitos sueltos, ej. "45"
    if tokens[start].isdigit():
        return int(tokens[start]), 1

    return _parse_scaled(tokens, start, 0)
