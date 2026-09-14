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
Calibra la deteccion de zonas clicables PROBANDO, no adivinando.

Captura el escritorio, recorta la casilla que se le diga, y prueba muchas
combinaciones de los ajustes de config.py diciendo cuantas zonas encuentra
cada una. Con eso se elige el valor con datos delante en vez de a tientas.

    ./venv/bin/python tools/calibrar_zonas.py [casilla]
    ./venv/bin/python tools/calibrar_zonas.py [casilla] [bloque_px]

Sin bloque: la tabla de cuantas zonas da cada combinacion.

Con bloque:  aplica ese valor y saca las coordenadas de cada zona.

YA NO DIBUJA NADA SOBRE EL ESCRITORIO
-------------------------------------
Dibujaba las zonas encima del escritorio con `vc_vistas.Items`, los dos
ultimos restos del modo servicio con vcs. **Borrados el 12-sep-2026 a
peticion de pipataki**, y con razon: el programa ya no pinta sobre el escritorio
-- todo se ve en el GUI, sobre la captura --, y dejar aquello vivo solo
servia para que alguien (yo) volviera a razonar como si aquello
siguiera existiendo.

Lo que se pierde es mirar las zonas dibujadas. Lo que queda -- la tabla y
las coordenadas -- es lo que de verdad se usa para elegir el valor. Si algun
dia hace falta verlas, el sitio es el GUI, sobre `casilla.png`, como todo lo
demas.

El numero solo no basta. La tabla dice "5 zonas", pero no si esas cinco son
cinco cosas utiles o tres trozos del mismo nombre. El tope esta en 9 y no se
sube (ver ZONAS_MAX en config.py); lo que se busca es que esas nueve sean
nueve cosas DISTINTAS, y eso hay que verlo.

POR QUE HACE FALTA
------------------
El 5-sep-2026 se vio que en una casilla con dos iconos solo detectaba dos
zonas, cuando lo util son cuatro: el dibujo del icono y su nombre son cosas
DISTINTAS -- a veces se quiere pulsar el nombre, para renombrar.

El culpable suele ser `ZONAS_BLOQUE_PX`: con bloques grandes, el icono y su
etiqueta caen en bloques contiguos y el agrupado por adyacencia los funde en
una sola region.

COMO SE LEE LA TABLA
--------------------
Mas zonas NO es mejor por si mismo. Lo que se busca es el valor a partir del
cual empiezan a salir las cosas que uno quiere pulsar por separado, sin que
empiecen a salir trozos de fondo. Si al bajar el bloque el numero se dispara
a veinte y pico, se ha pasado: eso ya es textura, no elementos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

import board
import config
import zones
from paths import CASILLA_FILE

BLOQUES = (12, 10, 8, 6, 5, 4)
SIGMAS = (0.6, 0.8, 1.0, 1.3)


def main():
    casilla = 1
    bloque_pedido = None
    if len(sys.argv) > 1:
        try:
            pedida = int(sys.argv[1])
            if 1 <= pedida <= board.TOTAL_CELLS:
                casilla = pedida
        except ValueError:
            pass
    if len(sys.argv) > 2:
        try:
            bloque_pedido = max(4, int(sys.argv[2]))
        except ValueError:
            pass

    app = QApplication(sys.argv)          # QImage necesita una QApplication

    print(f"  Capturando el escritorio y recortando la casilla {casilla}...")
    if not board.capture_tablero():
        print("  [!] no se pudo capturar el escritorio")
        return 1
    if not board.crop_casilla(casilla):
        print("  [!] no se pudo recortar la casilla")
        return 1

    from PySide6.QtGui import QImage
    img = QImage(str(CASILLA_FILE))
    print(f"  Recorte: {img.width()}x{img.height()} px\n")

    print(f"  Ahora mismo en config: ZONAS_BLOQUE_PX={config.ZONAS_BLOQUE_PX}  "
          f"ZONAS_MIN_BLOQUES={config.ZONAS_MIN_BLOQUES}  "
          f"ZONAS_UMBRAL_SIGMA={config.ZONAS_UMBRAL_SIGMA}  "
          f"ZONAS_MAX={config.ZONAS_MAX}\n")

    # Se prueba con un tope alto para ver cuantas SE DETECTAN de verdad; el
    # tope de config solo recorta al final y taparia el efecto del ajuste.
    tope = 60
    guardado = (config.ZONAS_BLOQUE_PX, config.ZONAS_UMBRAL_SIGMA)

    print("  zonas detectadas (tope alto, para ver el efecto real)")
    print("  bloque \\ sigma  " + "".join(f"{s:>8}" for s in SIGMAS))
    print("  " + "-" * (16 + 8 * len(SIGMAS)))
    for bloque in BLOQUES:
        fila = f"  {bloque:>6} px      "
        for sigma in SIGMAS:
            config.ZONAS_BLOQUE_PX = bloque
            config.ZONAS_UMBRAL_SIGMA = sigma
            n = len(zones.detect_zones(str(CASILLA_FILE), max_zones=tope) or [])
            fila += f"{n:>8}"
        print(fila)

    config.ZONAS_BLOQUE_PX, config.ZONAS_UMBRAL_SIGMA = guardado

    if bloque_pedido is not None:
        return _mirarlas(app, casilla, bloque_pedido)

    print()
    print("  Para el detalle de las zonas con un ajuste concreto:")
    print(f"      ./venv/bin/python tools/calibrar_zonas.py {casilla} 6")
    print()
    print("  Para fijar el que te guste, en config_local.py:")
    print("      ZONAS_BLOQUE_PX = 6")
    print("      ZONAS_UMBRAL_SIGMA = 1.0")
    print()
    print("  ZONAS_MAX se queda en 9 y NO se sube: 1-9 son los digitos que se")
    print("  dicen de un tiron, y subirlo hace que un mismo 'click 12' actue en")
    print("  la zona 12 o salte a la casilla 12 segun lo que se haya detectado.")
    print("  Lo que se busca no es tener mas, es que esas nueve sean nueve cosas")
    print("  DISTINTAS.")
    return 0


def _mirarlas(app, casilla, bloque):
    """Aplica ese tamano de bloque y saca las zonas que salen, con sus
    coordenadas dentro de la casilla.

    Antes las dibujaba sobre el escritorio. Ya no: ver la nota de arriba.
    """
    config.ZONAS_BLOQUE_PX = bloque
    cajas = zones.detect_zones(str(CASILLA_FILE), max_zones=config.ZONAS_MAX) or []
    print(f"\n  Con ZONAS_BLOQUE_PX={bloque} y tope {config.ZONAS_MAX}: "
          f"{len(cajas)} zonas en la casilla {casilla}")
    # detect_zones devuelve FRACCIONES de la casilla (0..1), no pixeles: asi
    # valen en cualquier resolucion. Aqui se pasan a pixeles para poder
    # juzgarlas, que es de lo que va esta herramienta.
    ancho = alto = None
    try:
        import struct
        d = open(str(CASILLA_FILE), "rb").read(33)
        ancho, alto = struct.unpack(">II", d[16:24])
    except Exception:
        pass
    if ancho:
        print(f"  (casilla.png mide {ancho}x{alto} px)")
    for i, caja in enumerate(cajas, 1):
        try:
            fx1, fy1, fx2, fy2 = caja[:4]
            if ancho:
                x1, y1 = round(fx1 * ancho), round(fy1 * alto)
                x2, y2 = round(fx2 * ancho), round(fy2 * alto)
                print(f"    {i:>2}.  ({x1:>4},{y1:>4}) - ({x2:>4},{y2:>4})   "
                      f"{x2 - x1:>3} x {y2 - y1:<3} px")
            else:
                print(f"    {i:>2}.  ({fx1:.3f},{fy1:.3f}) - ({fx2:.3f},{fy2:.3f})")
        except Exception:
            print(f"    {i:>2}.  {caja!r}")
    print("\n  Si te convence, en config_local.py:")
    print(f"      ZONAS_BLOQUE_PX = {bloque}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
