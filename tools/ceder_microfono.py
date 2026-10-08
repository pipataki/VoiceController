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
ceder_microfono: arranca un programa con el micrófono pedido a
VoiceController, y se lo devuelve cuando el programa termina.

Para Pipe-Logic (o cualquier otro) sin tener que tocar su código:

    python tools/ceder_microfono.py -- pipe-logic --sus --opciones

Si VoiceController no está en marcha, el programa arranca igual. El
protocolo está en cesion_microfono.py, por si es mejor que el propio
programa pida el micrófono solo mientras graba.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from cesion_microfono import pedir_microfono  # noqa: E402


def main() -> int:
    orden = sys.argv[1:]
    if orden and orden[0] == "--":
        orden = orden[1:]
    if not orden:
        print(__doc__)
        return 2
    with pedir_microfono():
        try:
            return subprocess.call(orden)
        except KeyboardInterrupt:
            return 130


if __name__ == "__main__":
    sys.exit(main())
