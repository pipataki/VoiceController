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
zones.py: Detección de "zonas clicables" dentro del recorte de una
casilla (casilla.png) -- ajuste fino asistido del tablero de 100
casillas (Sección 1 del manual).

En vez de moverse a pulso con las direcciones del compás, el usuario
puede pedir que se detecten automáticamente los elementos con más
"contraste" dentro de la casilla ya seleccionada (botones, iconos,
texto...); se numeran en orden de lectura y luego basta con decir
"<acción> <número>" (ej. "click 1", "mover 2", "doble click 3") para
actuar justo ahí -- ver board.detect_zones() y
command_router._try_parse_board_zone_action().

Algoritmo, deliberadamente ligero (sin dependencias nuevas: solo
PySide6 + numpy, ya presentes en el proyecto -- nada de OpenCV/scipy):
  1. Se lee casilla.png en escala de grises.
  2. Se divide en un grid de bloques pequeños (BLOCK_PX aprox.) y se
     mide la "energía de borde" de cada bloque (gradiente de
     intensidad: cuanto más cambia el brillo dentro de un bloque, más
     probable que ahí haya un icono/botón/texto y no fondo liso).
  3. Los bloques por encima del umbral (media + una desviación) se
     consideran "activos"; se agrupan por adyacencia (flood fill
     4-conectado) en regiones.
  4. Se descartan regiones demasiado pequeñas (ruido de una sola
     celda) y se recorta a como mucho `max_zones` regiones (si sobran,
     se priorizan las de mayor energía).
  5. Se devuelven en orden de lectura (arriba-abajo, izquierda-derecha)
     como bounding boxes fraccionarios (0.0-1.0) del ancho/alto de la
     imagen -- board.detect_zones() los convierte a offsets físicos
     (mismo sistema que el ajuste fino por voz/compás).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

# Estos cuatro valores viven en config.py (seccion "ZONAS CLICABLES"), para
# poder ajustarlos por maquina en config_local.py sin tocar el codigo. Aqui
# quedan los de respaldo, por si config no estuviera disponible.
_BLOCK_PX_DEFECTO = 10
_MIN_BLOQUES_DEFECTO = 2
_MAX_ZONAS_DEFECTO = 9
_SIGMA_DEFECTO = 1.0


def _ajuste(nombre, defecto):
    """Lee un ajuste de config.py, o devuelve el de respaldo.

    Se lee EN CADA LLAMADA y no al importar: asi se puede cambiar el valor
    en config_local.py y ver el efecto sin reiniciar el programa entero,
    que es justo lo que hace falta mientras se calibra."""
    try:
        import config
        valor = getattr(config, nombre, None)
        return defecto if valor is None else valor
    except Exception:
        return defecto


BLOCK_PX = _BLOCK_PX_DEFECTO             # se conservan por compatibilidad
MIN_BLOCKS_PER_ZONE = _MIN_BLOQUES_DEFECTO
DEFAULT_MAX_ZONES = _MAX_ZONAS_DEFECTO


def _grayscale_array(path: str):
    """Devuelve la imagen en `path` como array 2D (float32) en escala
    de grises, o None si no se pudo leer."""
    image = QImage(str(path))
    if image.isNull():
        return None
    image = image.convertToFormat(QImage.Format_Grayscale8)
    w, h = image.width(), image.height()
    if w == 0 or h == 0:
        return None
    stride = image.bytesPerLine()
    buf = bytes(image.constBits())
    arr = np.frombuffer(buf, dtype=np.uint8, count=stride * h).reshape(h, stride)
    return arr[:, :w].astype(np.float32)


def _edge_energy(arr) -> "np.ndarray":
    """Magnitud de gradiente simple (diferencias horizontales +
    verticales) -- suficiente para distinguir "fondo liso" de "hay algo
    dibujado aquí" sin necesitar un Sobel completo."""
    gx = np.zeros_like(arr)
    gy = np.zeros_like(arr)
    gx[:, :-1] = np.abs(np.diff(arr, axis=1))
    gy[:-1, :] = np.abs(np.diff(arr, axis=0))
    return gx + gy


def _block_energy(energy, block_px: int):
    """Reduce la matriz de energía por bloques de block_px x block_px
    (el último bloque de cada fila/columna puede quedar más grande, por
    si el tamaño no es múltiplo exacto)."""
    h, w = energy.shape
    rows = max(1, h // block_px)
    cols = max(1, w // block_px)
    out = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        y1 = r * block_px
        y2 = h if r == rows - 1 else (r + 1) * block_px
        for c in range(cols):
            x1 = c * block_px
            x2 = w if c == cols - 1 else (c + 1) * block_px
            out[r, c] = energy[y1:y2, x1:x2].mean()
    return out


def _connected_regions(active) -> list:
    """Flood fill 4-conectado sobre una matriz booleana de bloques
    activos. Devuelve una lista de regiones, cada una como lista de
    coordenadas (fila, columna) de bloque."""
    rows, cols = active.shape
    seen = np.zeros_like(active, dtype=bool)
    regions = []
    for r0 in range(rows):
        for c0 in range(cols):
            if not active[r0, c0] or seen[r0, c0]:
                continue
            stack = [(r0, c0)]
            seen[r0, c0] = True
            region = []
            while stack:
                r, c = stack.pop()
                region.append((r, c))
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and active[nr, nc] and not seen[nr, nc]:
                        seen[nr, nc] = True
                        stack.append((nr, nc))
            regions.append(region)
    return regions


def detect_zones(image_path: str, max_zones: int = None):
    """Detecta zonas "clicables" (regiones de alto contraste/borde) en
    la imagen `image_path` (normalmente casilla.png, ya recortado).
    Devuelve una lista de hasta `max_zones` bounding boxes, cada una
    como (fx1, fy1, fx2, fy2) -- fracciones 0.0-1.0 del ancho/alto de
    la imagen -- ordenadas en orden de lectura (arriba-abajo,
    izquierda-derecha). Lista vacía si no hay imagen legible o no se
    detecta nada suficientemente marcado."""
    # None = el de config. No se pone config.ZONAS_MAX como valor por defecto
    # del parametro porque eso se evalua UNA VEZ al importar: cambiarlo en
    # config_local.py no tendria ningun efecto hasta reiniciar, y este es
    # justo un numero que se toca mientras se calibra.
    if max_zones is None:
        max_zones = int(_ajuste("ZONAS_MAX", _MAX_ZONAS_DEFECTO))

    arr = _grayscale_array(image_path)
    if arr is None:
        return []
    h, w = arr.shape
    bloque = _ajuste("ZONAS_BLOQUE_PX", None)
    if bloque is None:
        # Automatico: relativo al tamano del recorte, no en pixeles fijos.
        # El valor bueno depende de la resolucion -- ver la explicacion en
        # config.py, seccion ZONAS CLICABLES.
        divisor = float(_ajuste("ZONAS_BLOQUE_DIVISOR", 32) or 32)
        bloque = max(4, int(round(w / divisor)))
    bloque = int(bloque)
    min_bloques = int(_ajuste("ZONAS_MIN_BLOQUES", _MIN_BLOQUES_DEFECTO))
    sigma = float(_ajuste("ZONAS_UMBRAL_SIGMA", _SIGMA_DEFECTO))
    # El suelo de 4 px no es negociable: por debajo, cualquier textura del
    # fondo empieza a contar como elemento.
    block_px = max(4, min(bloque, (h // 3) or 1, (w // 3) or 1))
    energy = _edge_energy(arr)
    blocks = _block_energy(energy, block_px)
    if blocks.size == 0:
        return []

    threshold = blocks.mean() + sigma * blocks.std()
    active = blocks > max(threshold, 1e-6)
    regions = _connected_regions(active)
    regions = [reg for reg in regions if len(reg) >= min_bloques]
    if not regions:
        return []

    def _region_energy(reg):
        return sum(blocks[r, c] for r, c in reg)

    if len(regions) > max_zones:
        regions.sort(key=_region_energy, reverse=True)
        regions = regions[:max_zones]

    boxes = []
    for reg in regions:
        rmin = min(r for r, _ in reg)
        rmax = max(r for r, _ in reg)
        cmin = min(c for _, c in reg)
        cmax = max(c for _, c in reg)
        fx1 = (cmin * block_px) / w
        fx2 = min(1.0, ((cmax + 1) * block_px) / w)
        fy1 = (rmin * block_px) / h
        fy2 = min(1.0, ((rmax + 1) * block_px) / h)
        boxes.append((fx1, fy1, fx2, fy2))

    # orden de lectura: arriba-abajo (centro Y), luego izquierda-derecha
    boxes.sort(key=lambda b: (round((b[1] + b[3]) / 2, 2), (b[0] + b[2]) / 2))
    return boxes
