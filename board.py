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
board.py: Tablero de 100 casillas (Sección 1 del manual) -- geometría
10x10, captura de escritorio ("tablero.png") y recorte por casilla
("casilla.png").

Numeración: cada casilla N (1-100) se interpreta literalmente por sus dos
dígitos decimales -- decena y unidad:

    decena = N // 10   (0 para N=1..9)
    unidad = N % 10    (0 para N=10,20,...,100)

Ejemplo del manual: casilla "57" -> unidad=7, decena=5. La región que
ocupa en el escritorio es:
    x: [(unidad-1) * W/10,  unidad * W/10]
    y: [(decena-1) * H/10,  decena * H/10]

Caso especial: los números de una sola cifra (1-9) tienen decena=0, que
no es una fila válida en una rejilla de filas 1-10 -- se agrupan en la
fila 10, junto con la casilla 100 (cuya unidad es igualmente 0 -> columna
10). Así se completa una rejilla 10x10 sin huecos ni solapes:
    fila 10 = {1, 2, 3, 4, 5, 6, 7, 8, 9, 100}
    fila r (1-9) = {10r, 10r+1, ..., 10r+9}   (10r+0 -> columna 10)

Todo el cálculo de regiones se hace sobre el TAMAÑO REAL de tablero.png
(los píxeles físicos de la propia captura), no sobre la resolución
"lógica" de Qt -- así el recorte de casilla.png es exacto, sin
conversiones de escala, y el punto de acción final se puede mover con
grid_vc.move_pointer_physical() sin más ajustes.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from PySide6.QtGui import QImage

import zones as _zones
from paths import BOARD_DIR, TABLERO_FILE, CASILLA_FILE, ZOOM_OUT_FILE, FOCO_FILE

ROWS = 10
COLS = 10
TOTAL_CELLS = ROWS * COLS

# Segundos máximos de espera a que `spectacle` termine una captura antes
# de darla por fallida. 1.5s es de sobra para una captura de pantalla
# normal -- si spectacle tarda más que eso, algo va mal (ventana de
# diálogo bloqueada, compositor colgado...) y es mejor fallar rápido que
# quedarse esperando.
SPECTACLE_TIMEOUT_S = 1.5


# ---------------------------------------------------------------------------
# Geometría: casilla <-> (fila, columna) <-> región en píxeles
# ---------------------------------------------------------------------------

def cell_row_col(n: int) -> tuple[int, int]:
    """(fila, columna), ambas 1-10, para la casilla n (1-100)."""
    if not (1 <= n <= TOTAL_CELLS):
        raise ValueError(f"la casilla debe estar entre 1 y {TOTAL_CELLS}, recibido {n}")
    # decade = ( n + 10 ) // 10
    # unit = n % 10

    #if n < 10 :
    #    row = 1
    #    col = n
    #elif n % 10 == 0 :
    #    row = n // 10
    #    col = 10
    #else :
    if n == 100 :
        decade = 10
        unit = 10
    elif n < 10 :
        decade = 1
        unit = n
    elif n % 10 == 0 and n >= 10 :
        decade = n // 10
        unit = 10
    else:
        decade = ( n // 10 ) + 1
        unit = n % 10
    row = decade if decade != 0 else ROWS
    col = unit if unit != 0 else COLS
    return row, col


def cell_from_row_col(row: int, col: int) -> int:
    """Inverso de cell_row_col(): casilla (1-100) para fila/columna 1-10
    (usado al interpretar un toque táctil sobre tablero.png)."""
    """
    row = min(max(row, 1), ROWS)
    col = min(max(col, 1), COLS)
    if row == ROWS:
        return 100 if col == COLS else col
    return row * 10 +  (0 if col == COLS else col)
    """
    return (row - 1 ) * 10 + col


def cell_region(n: int, width: int, height: int) -> tuple[int, int, int, int]:
    """(x1, y1, x2, y2) en píxeles: región de la casilla n sobre una
    imagen/escritorio de `width` x `height` píxeles reales."""
    row, col = cell_row_col(n)
    x1 = round((col - 1) * width / COLS)
    x2 = round(col * width / COLS)
    y1 = round((row - 1) * height / ROWS)
    y2 = round(row * height / ROWS)
    return x1, y1, x2, y2


def cell_from_fraction(fx: float, fy: float) -> int:
    """Casilla (1-100) correspondiente a un punto tocado en tablero.png,
    dado como fracción (0.0-1.0) de su ancho/alto -- usado por la webapp
    y por los toques sobre el tablero en el GUI de escritorio."""
    fx = min(max(fx, 0.0), float(1))
    fy = min(max(fy, 0.0), float(1))
    # tope DESPUÉS de calcular col/row (no antes, con 0.999999 como se
    # hacía) -- con fx/fy exactamente en 1.0, int(fx*COLS)+1 daría
    # COLS+1 (11), fuera de rango; así se recorta a COLS/ROWS de verdad
    # en vez de acercarse por debajo con un valor artificial que
    # introducía el desajuste "un pelín desplazado" que viste en el GUI.
    col = min(int(fx * COLS) + 1, COLS)
    row = min(int(fy * ROWS) + 1, ROWS)
    return cell_from_row_col(row, col)


def unit_of(n: int) -> int:
    """La "unidad" (columna, 1-10) de la casilla n -- usada por la GUI
    para decidir en qué lado del escritorio colocarse (ver manual,
    Sección 1 Paso 3): unidad 1-5 -> GUI a la derecha; 6-10 -> GUI a la
    izquierda (la unidad 0/10 de las decenas exactas y de la 100 cae en
    este segundo grupo)."""
    return cell_row_col(n)[1]


# ---------------------------------------------------------------------------
# Captura de escritorio y recorte de la casilla seleccionada
# ---------------------------------------------------------------------------

def capture_tablero() -> bool:
    """Captura el escritorio completo con spectacle y lo guarda como
    tablero.png (sobrescribiendo el anterior). Devuelve True si tuvo
    éxito. Es la imagen que refleja la situación "actual" del escritorio
    (ver manual, Sección 1 Paso 1)."""
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    # En Windows no hay spectacle: la captura la hace la capa de plataforma
    # (mss) y deja el fichero en el mismo sitio, que es lo que espera el
    # resto del programa.
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        return backends.get().screenshot(TABLERO_FILE)
    try:
        subprocess.run(
            ["spectacle", "-b", "-n", "-s", "-e", "-S", "-o", str(TABLERO_FILE)],
            check=True, timeout=SPECTACLE_TIMEOUT_S,
        )
        return TABLERO_FILE.exists()
    except FileNotFoundError:
        print("[board] 'spectacle' no encontrado; instala KDE Spectacle.")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"[board] error capturando tablero.png: {exc}")
        return False
    except subprocess.TimeoutExpired:
        print("[board] timeout capturando tablero.png")
        return False


def crop_casilla(n: int) -> bool:
    """Recorta la región de la casilla n desde tablero.png y la guarda
    como casilla.png (sobrescribiendo la anterior). Requiere que
    tablero.png ya exista (ver capture_tablero()). Devuelve True si tuvo
    éxito. Debe llamarse desde el hilo principal de Qt (usa QImage, igual
    que grid_vc.py con QPixmap)."""
    if not TABLERO_FILE.exists():
        print("[board] no hay tablero.png -- llama a capture_tablero() antes")
        return False
    image = QImage(str(TABLERO_FILE))
    if image.isNull():
        print(f"[board] no se pudo leer {TABLERO_FILE}")
        return False
    x1, y1, x2, y2 = cell_region(n, image.width(), image.height())
    cropped = image.copy(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    return cropped.save(str(CASILLA_FILE))


def tablero_size() -> Optional[tuple[int, int]]:
    """(ancho, alto) reales de la última captura de tablero.png, o None
    si todavía no existe/no se pudo leer."""
    if not TABLERO_FILE.exists():
        return None
    image = QImage(str(TABLERO_FILE))
    if image.isNull():
        return None
    return image.width(), image.height()


def _zoom_out_region(n: int, width: int, height: int) -> tuple[int, int, int, int]:
    """(x1, y1, x2, y2) en píxeles: región del CUARTO de escritorio (5x5
    casillas) donde cae la casilla n, sobre una imagen/escritorio de
    `width` x `height` píxeles reales -- misma partición que usa
    capture_zoom_out() (factorizada aquí para no duplicar la cuenta del
    cuadrante y poder reutilizarla también en sentido inverso, ver
    virtual_pointer_to_real_position())."""
    row, col = cell_row_col(n)
    quad_row = 1 if row <= ROWS // 2 else 2
    quad_col = 1 if col <= COLS // 2 else 2
    x1 = 0 if quad_col == 1 else width // 2
    x2 = width // 2 if quad_col == 1 else width
    y1 = 0 if quad_row == 1 else height // 2
    y2 = height // 2 if quad_row == 1 else height
    return x1, y1, x2, y2


def capture_zoom_out(n: int) -> bool:
    """Recorta, desde tablero.png ya capturado, el CUARTO del escritorio
    (5x5 casillas -- la mitad del ancho y la mitad del alto de la
    rejilla 10x10) donde cae la casilla n, y lo guarda como
    zoom_out.png -- SIN numerar ni dibujar rejilla encima (a diferencia
    de la vista general del tablero en gui.py). Pensado como término
    medio de zoom entre "todo el escritorio" (tablero.png) y "solo una
    casilla" (casilla.png) -- ver comando de voz "menos zoom"/"zoom
    out". Requiere que tablero.png ya exista (llama a capture_tablero()
    antes si hace falta). Devuelve True si tuvo éxito."""
    if not TABLERO_FILE.exists():
        print("[board] no hay tablero.png -- llama a capture_tablero() antes")
        return False
    image = QImage(str(TABLERO_FILE))
    if image.isNull():
        print(f"[board] no se pudo leer {TABLERO_FILE}")
        return False
    width, height = image.width(), image.height()
    x1, y1, x2, y2 = _zoom_out_region(n, width, height)
    cropped = image.copy(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    return cropped.save(str(ZOOM_OUT_FILE))


# ---------------------------------------------------------------------------
# Vista "foco": la ventana en la que se estaba trabajando
# ---------------------------------------------------------------------------
#
# Termino medio distinto al de zoom_out. zoom_out ensena un CUARTO del
# escritorio, elegido por la casilla; "foco" ensena LA VENTANA, que es lo que
# de verdad importa cuando se esta usando un programa: el navegador, el
# editor, lo que sea.
#
# Se recorta sobre tablero.png, igual que zoom_out, y por el mismo motivo:
# conociendo el rectangulo exacto en pixeles de escritorio, un toque en el
# movil se traduce a su punto real sin perder ni un pixel. Capturar la
# ventana por separado obligaria a medir dos veces y a cuadrar los bordes.
#
# LA PROPORCION se toma de tablero.png, no se escribe 16:9 a mano: asi la
# imagen encaja en el mismo hueco del GUI y en el mismo touchpad del movil
# que las demas vistas, y sigue cuadrando en un monitor que no sea 16:9.
#
# QUE PARTE DE LA VENTANA. Se coge desde ARRIBA, incluyendo el marco y la
# barra de titulo, porque ahi estan los menus, las pestanas y los botones,
# que es donde hace falta precision. En una ventana mas alta que la
# proporcion del escritorio eso deja fuera la parte de abajo.
FOCO_DESDE_ARRIBA = True

_foco_rect = None      # (x1, y1, x2, y2) en pixeles de escritorio
_foco_recordada = False   # True si no era la ventana activa sino la ultima conocida


def _foco_region(width: int, height: int):
    """El rectangulo de la ultima captura de foco, recortado al tamano de
    la imagen. None si todavia no se ha usado la vista."""
    if _foco_rect is None:
        return None
    x1, y1, x2, y2 = _foco_rect
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(x1 + 1, min(x2, width))
    y2 = max(y1 + 1, min(y2, height))
    return x1, y1, x2, y2


# ---------------------------------------------------------------------------
# LAS MEDIDAS, CALCULADAS UNA VEZ
# ---------------------------------------------------------------------------
#
# Idea de pipataki (10-sep-2026), y es la buena: todo lo que depende del tamano
# se saca de dos numeros -- lo que mide la captura y lo que mide la pantalla
# logica -- y de ahi sale lo demas sin volver a pensarlo:
#
#     la casilla es SIEMPRE un decimo del ancho por un decimo del alto,
#     este donde este.
#
# Se calcula una vez y se guarda. Si alguna de las dos medidas cambia -- el
# usuario cambia de resolucion o de escalado -- se recalcula solo, porque la
# clave del cache son esas dos medidas. Eso es lo que evita el fallo de hoy:
# no hay ningun numero escrito a mano que se quede viejo.
_MEDIDAS = None


class Medidas:
    """Los dos espacios de coordenadas y como se pasa de uno a otro.

        captura    lo que mide tablero.png, en pixeles FISICOS
        logica     lo que mide la pantalla para el compositor
        a_logico   multiplica una coordenada de la captura -> logica
                   (para MOVER el raton: ydotool habla en logicas)
        a_captura  al reves (para RECORTAR sobre la imagen: kdotool da
                   la geometria de las ventanas en logicas)
        casilla    lo que mide una casilla en la captura: captura/10
    """

    __slots__ = ("captura", "logica", "a_logico", "a_captura", "casilla")

    def __init__(self, captura, logica):
        self.captura = captura
        self.logica = logica
        cw, ch = captura
        lw, lh = logica
        self.a_logico = (lw / cw, lh / ch) if cw and ch else (1.0, 1.0)
        self.a_captura = (cw / lw, ch / lh) if lw and lh else (1.0, 1.0)
        self.casilla = (cw / COLS, ch / ROWS)

    def __repr__(self):
        return (f"<Medidas captura={self.captura} logica={self.logica} "
                f"a_logico=({self.a_logico[0]:.5f},{self.a_logico[1]:.5f}) "
                f"casilla=({self.casilla[0]:.1f},{self.casilla[1]:.1f})>")


def _tamano_logico():
    """Lo que mide el escritorio para el compositor, o None."""
    try:
        from PySide6.QtGui import QGuiApplication
        if QGuiApplication.instance() is not None:
            p = QGuiApplication.primaryScreen()
            if p is not None:
                # virtualGeometry: TODO el escritorio, que es lo que se
                # fotografia, y no solo el monitor principal.
                g = p.virtualGeometry()
                if g.width() > 0 and g.height() > 0:
                    return g.width(), g.height()
    except Exception as exc:
        print(f"[board] no se pudo saber el tamano logico: {exc!r}")
    return None


def medidas():
    """Las medidas de ahora, calculadas una vez y recalculadas solas si
    cambia la resolucion o el escalado. None si aun no hay captura."""
    global _MEDIDAS
    captura = tablero_size()
    if captura is None:
        return None
    logica = _tamano_logico() or captura      # sin Qt: se supone que coinciden
    if (_MEDIDAS is None or _MEDIDAS.captura != captura
            or _MEDIDAS.logica != logica):
        _MEDIDAS = Medidas(captura, logica)
        print(f"[board] medidas: {_MEDIDAS}")
    return _MEDIDAS


def escala_captura(ancho_img, alto_img):
    """Cuantos pixeles de la CAPTURA hay por cada pixel LOGICO, por eje.

    POR QUE HACE FALTA
    ------------------
    La captura sale en pixeles FISICOS (aqui 3840x2160) y kdotool da la
    geometria de las ventanas en pixeles LOGICOS (2133x1200): son espacios
    distintos en cuanto la pantalla tiene escalado. Recortar la ventana con
    las coordenadas logicas sobre la imagen fisica daba un trozo 1,8 veces
    mas pequeno y corrido hacia arriba a la izquierda. Es lo que pipataki vio
    como "no carga la imagen igual que antes" (10-sep-2026).

    POR QUE SE DIVIDE Y NO SE USA LA PROPORCION
    -------------------------------------------
    pipataki propuso deducirlo de la proporcion 16:9 -- con el ancho real, el
    alto es 9/16 --, y funciona; pero exige SABER la proporcion, y por eso
    el mismo planteaba tener que autodetectar 4:3. Aqui se tienen las dos
    medidas, asi que se dividen las dos y la proporcion deja de importar:
    esto vale igual en 16:9, en 4:3, en 16:10, en ultrapanoramico y con dos
    monitores pegados, sin que nadie tenga que acertar nada.

    Ademas los dos factores NO son iguales: 3840/2133 = 1,80028 y
    2160/1200 = 1,8, porque el ancho logico es el redondeo de 3840/1,8 =
    2133,33. Con un solo factor deducido de la proporcion, ese error se
    arrastra a los dos ejes.

    Y NO se usa `devicePixelRatio()`, que seria lo obvio: en esta maquina
    devuelve 2.0 con una escala real de 1,8. Medido, no supuesto.
    """
    m = medidas()
    if m is None or m.captura != (ancho_img, alto_img):
        # Piden la escala de una imagen que no es el tablero de
        # ahora: se calcula suelta, sin tocar el cache.
        logica = _tamano_logico()
        if not logica:
            return 1.0, 1.0
        return ancho_img / logica[0], alto_img / logica[1]
    return m.a_captura


def capture_foco(nombre: str = "") -> bool:
    """Recorta de tablero.png una ventana y la guarda como foco.png.

    Con `nombre`, la ventana cuyo titulo lo contenga ("foco kate"). Sin el,
    la que estaba activa. Devuelve True si tuvo exito.

    Requiere tablero.png recien capturado: si esta viejo, se vera la
    ventana como estaba entonces. Quien llame debe capturar antes.
    """
    global _foco_rect, _foco_recordada

    import backends
    try:
        if nombre:
            geo = backends.window_geometry_by_name(nombre)
        else:
            geo = backends.focused_window_geometry()
    except Exception as exc:
        print(f"[board] no se pudo saber cual es la ventana: {exc!r}")
        return False
    if not geo:
        if nombre:
            print(f"[board] no hay ninguna ventana que sea {nombre!r}")
        else:
            print("[board] no hay ninguna ventana de la que hacer foco")
        return False

    if not TABLERO_FILE.exists():
        print("[board] no hay tablero.png -- llama a capture_tablero() antes")
        return False
    image = QImage(str(TABLERO_FILE))
    if image.isNull():
        print(f"[board] no se pudo leer {TABLERO_FILE}")
        return False
    width, height = image.width(), image.height()

    vx, vy, vw, vh, titulo, recordada = geo

    # De pixeles logicos (los que da kdotool) a pixeles de la captura. Todo
    # lo de abajo -- y todo lo que use despues _foco_rect -- trabaja ya en
    # pixeles de tablero.png, igual que la rejilla y las casillas.
    # ¿Hay que convertir? Lo dice el backend, no lo suponemos: kdotool
    # entrega logicas y GetWindowRect (Windows) entrega fisicas. Aplicar la
    # conversion en el segundo caso descuadraria el recorte por el otro
    # lado, y ademas en silencio.
    logicas = bool(getattr(backends, "GEOMETRIA_LOGICA", True))
    ex, ey = escala_captura(width, height) if logicas else (1.0, 1.0)
    if (ex, ey) != (1.0, 1.0):
        vx, vy = round(vx * ex), round(vy * ey)
        vw, vh = round(vw * ex), round(vh * ey)

    # La ventana puede sobresalir del escritorio (movida a medias fuera de
    # pantalla). Se recorta a lo que existe: lo de fuera no se ha capturado.
    x1 = max(0, min(vx, width - 1))
    y1 = max(0, min(vy, height - 1))
    x2 = max(x1 + 1, min(vx + vw, width))
    y2 = max(y1 + 1, min(vy + vh, height))

    # Alto que le toca a ese ancho para conservar la proporcion del
    # escritorio.
    ancho = x2 - x1
    alto_proporcional = max(1, round(ancho * height / width))

    if (y2 - y1) > alto_proporcional:
        # Ventana mas alta de lo que cabe: se coge desde arriba.
        if FOCO_DESDE_ARRIBA:
            y2 = y1 + alto_proporcional
        else:
            sobra = (y2 - y1) - alto_proporcional
            y1 += sobra // 2
            y2 = y1 + alto_proporcional
    elif (y2 - y1) < alto_proporcional:
        # Ventana mas baja: se anade escritorio por abajo hasta completar,
        # sin salirse. Asi no hacen falta bandas negras y lo que se ve de
        # mas sigue siendo real y clicable.
        y2 = min(height, y1 + alto_proporcional)
        if (y2 - y1) < alto_proporcional:
            y1 = max(0, y2 - alto_proporcional)

    cropped = image.copy(x1, y1, max(1, x2 - x1), max(1, y2 - y1))
    BOARD_DIR.mkdir(parents=True, exist_ok=True)
    if not cropped.save(str(FOCO_FILE)):
        print(f"[board] no se pudo guardar {FOCO_FILE}")
        return False

    _foco_rect = (x1, y1, x2, y2)
    _foco_recordada = bool(recordada)
    print(f"[board] foco: {titulo!r} -> region ({x1},{y1})-({x2},{y2})"
          + ("  (recordada, no era la activa)" if recordada else ""))
    return True


def foco_rect():
    """El rectangulo de la ultima captura de foco, o None."""
    return _foco_rect


def foco_clamp_offset(offset_x: float, offset_y: float) -> tuple[int, int]:
    """Recorta (offset_x, offset_y) -- desplazamiento respecto al CENTRO de
    la region de foco -- para que el puntero verde no pueda salirse de la
    ventana que se esta ensenando. Analogo a zoom_out_clamp_offset()."""
    size = tablero_size()
    if size is None:
        return round(offset_x), round(offset_y)
    region = _foco_region(*size)
    if region is None:
        return round(offset_x), round(offset_y)
    x1, y1, x2, y2 = region
    half_w = max(0, (x2 - x1) / 2 - 1)
    half_h = max(0, (y2 - y1) / 2 - 1)
    ox = min(max(offset_x, -half_w), half_w)
    oy = min(max(offset_y, -half_h), half_h)
    return round(ox), round(oy)


def foco_absolute_position(offset_x: int = 0, offset_y: int = 0):
    """Posicion absoluta en el escritorio del centro de la region de foco,
    desplazado (offset_x, offset_y). None si no hay vista de foco todavia."""
    size = tablero_size()
    if size is None:
        return None
    region = _foco_region(*size)
    if region is None:
        return None
    x1, y1, x2, y2 = region
    return round((x1 + x2) / 2 + offset_x), round((y1 + y2) / 2 + offset_y)


def absolute_to_foco_offset(abs_x: float, abs_y: float) -> tuple[int, int]:
    """Inverso de foco_absolute_position(): de un punto del escritorio al
    offset respecto al centro de la region de foco, ya recortado. Sirve para
    que el puntero verde aparezca donde estaba el raton al entrar."""
    size = tablero_size()
    if size is None:
        return 0, 0
    region = _foco_region(*size)
    if region is None:
        return 0, 0
    x1, y1, x2, y2 = region
    return foco_clamp_offset(abs_x - (x1 + x2) / 2, abs_y - (y1 + y2) / 2)


def foco_recordada() -> bool:
    """True si la ultima vista de foco NO era la ventana activa sino la
    ultima conocida -- el comando de voz lo avisa."""
    return _foco_recordada


# ---------------------------------------------------------------------------
# Puntero virtual (verde/rojo) -- GUI nuevo por accesibilidad
# ---------------------------------------------------------------------------
#
# El puntero real del ratón NUNCA se mueve mientras se posiciona el
# puntero virtual (arrastre en el touchpad local o del móvil): eso es
# puro dibujo, sobre una imagen YA capturada (tablero.png en la
# "pantalla inicial", zoom_out.png o casilla.png tras seleccionar una
# casilla) -- cero llamadas a spectacle/ydotool durante ese proceso.
# Solo al confirmar una acción (clic, clic derecho, doble clic, scroll,
# tecla especial) se traduce la posición del puntero virtual a una
# posición REAL de escritorio, y el cursor salta y actúa en un único
# paso atómico. Esta es la traducción -- la usan tanto el GUI (puntero
# verde) como la webapp vía una ruta nueva (puntero rojo, ver
# webapp/app.py), para que ambos lados calculen exactamente lo mismo.

def virtual_pointer_to_real_position(view: str, cell: int, fx: float, fy: float) -> Optional[tuple[int, int]]:
    """Posición REAL de escritorio (píxeles físicos, los mismos que
    tablero.png) correspondiente a un punto del puntero virtual dado
    como fracción (fx, fy, 0.0-1.0) de la imagen que se esté mostrando.

    `view` -- cuál de las tres imágenes se está mostrando ahora mismo:
      - "tablero": pantalla inicial, todo el escritorio. `cell` se
        ignora (puede ser cualquier valor, p.ej. la última casilla
        conocida -- no afecta al cálculo).
      - "foco": la ventana en la que se estaba trabajando -- misma
        región que la última capture_foco(). `cell` se ignora.
      - "zoom_out": el cuarto de escritorio (5x5 casillas) donde cae
        `cell` -- misma región que capture_zoom_out(cell).
      - "casilla": la propia casilla `cell`, magnified -- misma región
        que crop_casilla(cell).

    Devuelve None si tablero.png todavía no se ha capturado nunca (no
    hay tamaño de referencia) o si `view` no es ninguno de los tres
    valores anteriores.

    fx/fy se recortan a [0.0, 1.0] igual que cell_from_fraction() --
    un arrastre que se va fuera del borde de la imagen se queda pegado
    al borde, no se extrapola fuera de la región mostrada."""
    size = tablero_size()
    if size is None:
        return None
    width, height = size
    fx = min(max(fx, 0.0), 1.0)
    fy = min(max(fy, 0.0), 1.0)

    if view == "tablero":
        x1, y1, x2, y2 = 0, 0, width, height
    elif view == "foco":
        # La ventana en la que se estaba trabajando. El rectangulo lo dejo
        # guardado capture_foco(); sin el no hay forma de traducir nada, asi
        # que se devuelve None en vez de adivinar.
        region = _foco_region(width, height)
        if region is None:
            return None
        x1, y1, x2, y2 = region
    elif view == "zoom_out":
        x1, y1, x2, y2 = _zoom_out_region(cell, width, height)
    elif view == "casilla":
        x1, y1, x2, y2 = cell_region(cell, width, height)
    else:
        print(f"[board] virtual_pointer_to_real_position: view desconocido {view!r}")
        return None

    real_x = x1 + fx * (x2 - x1)
    real_y = y1 + fy * (y2 - y1)
    return round(real_x), round(real_y)


# ---------------------------------------------------------------------------
# Puntero verde en modo "zoom_out" (Fase 2 del rediseño de accesibilidad) --
# mismo patrón offset-desde-el-centro que clamp_offset()/cell_absolute_position()
# (para "casilla"), aplicado a la región de zoom_out en vez de a una sola
# casilla. Se mantienen AMBOS sistemas (offset en píxeles para casilla/zoom_out,
# fracción 0-1 para virtual_pointer_to_real_position) porque el de casilla ya
# funciona probado en producción -- no merece la pena tocarlo.
# ---------------------------------------------------------------------------

def zoom_out_clamp_offset(n: int, offset_x: float, offset_y: float) -> tuple[int, int]:
    """Como clamp_offset(), pero para el CUARTO de escritorio (zoom_out)
    donde cae la casilla n, en vez de para la propia casilla -- recorta
    (offset_x, offset_y), desplazamiento respecto al CENTRO de ese
    cuarto, para que el puntero verde no pueda salir de esa región."""
    size = tablero_size()
    if size is None:
        return round(offset_x), round(offset_y)
    width, height = size
    x1, y1, x2, y2 = _zoom_out_region(n, width, height)
    half_w = max(0, (x2 - x1) / 2 - 1)
    half_h = max(0, (y2 - y1) / 2 - 1)
    ox = min(max(offset_x, -half_w), half_w)
    oy = min(max(offset_y, -half_h), half_h)
    return round(ox), round(oy)


def zoom_out_absolute_position(n: int, offset_x: int = 0, offset_y: int = 0) -> Optional[tuple[int, int]]:
    """Posición absoluta (píxeles físicos reales, los mismos que
    tablero.png) del CENTRO del cuarto de escritorio (zoom_out) donde
    cae la casilla n, desplazado (offset_x, offset_y) -- análogo a
    cell_absolute_position() pero para la región de zoom_out en vez de
    la propia casilla. None si tablero.png no se ha capturado nunca."""
    size = tablero_size()
    if size is None:
        return None
    width, height = size
    x1, y1, x2, y2 = _zoom_out_region(n, width, height)
    cx = (x1 + x2) / 2 + offset_x
    cy = (y1 + y2) / 2 + offset_y
    return round(cx), round(cy)


def absolute_to_zoom_out_offset(n: int, abs_x: float, abs_y: float) -> tuple[int, int]:
    """Inverso de zoom_out_absolute_position(): dado un punto absoluto
    (píxeles físicos reales) del escritorio, calcula el offset respecto
    al centro del cuarto de escritorio (zoom_out) de la casilla n, YA
    recortado a sus límites (zoom_out_clamp_offset). Se usa para
    "extrapolar" dónde debe aparecer el puntero verde al entrar en modo
    zoom_out interactivo, a partir de la última posición real conocida
    (ver command_router._enter_zoom_out_interactive) -- nunca se mueve
    el cursor real para calcular esto, es pura aritmética sobre la
    última posición que YA sabíamos."""
    size = tablero_size()
    if size is None:
        return 0, 0
    width, height = size
    x1, y1, x2, y2 = _zoom_out_region(n, width, height)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    return zoom_out_clamp_offset(n, abs_x - cx, abs_y - cy)


def cell_from_absolute_position(x: float, y: float) -> Optional[int]:
    """Inverso de cell_absolute_position(): casilla (1-100) a la que
    pertenece un punto absoluto (píxeles físicos reales) del
    escritorio -- usado para saber en qué casilla queda el puntero
    verde tras ejecutar una acción en modo zoom_out, y así fijar la
    etiqueta "Celda" correspondiente sin numerar nada (más barato
    calcularlo por la numeración del tablero que de otro modo). None
    si tablero.png no se ha capturado nunca."""
    size = tablero_size()
    if size is None:
        return None
    width, height = size
    fx = x / width if width else 0.0
    fy = y / height if height else 0.0
    return cell_from_fraction(fx, fy)


# ---------------------------------------------------------------------------
# Posición de acción dentro de una casilla (ajuste fino)
# ---------------------------------------------------------------------------

def clamp_offset(n: int, offset_x: float, offset_y: float) -> tuple[int, int]:
    """Recorta (offset_x, offset_y) -- desplazamiento en píxeles respecto
    al centro de la casilla n -- para que el punto de acción no pueda
    salir de los límites de esa casilla (ver manual: "no se van a
    sobrepasar los límites de la región... no podrá atravesar la
    casilla")."""
    size = tablero_size()
    if size is None:
        return round(offset_x), round(offset_y)
    width, height = size
    x1, y1, x2, y2 = cell_region(n, width, height)
    half_w = max(0, (x2 - x1) / 2 - 1)
    half_h = max(0, (y2 - y1) / 2 - 1)
    ox = min(max(offset_x, -half_w), half_w)
    oy = min(max(offset_y, -half_h), half_h)
    return round(ox), round(oy)


# ---------------------------------------------------------------------------
# Zonas clicables autodetectadas dentro de la casilla (ajuste fino asistido)
# ---------------------------------------------------------------------------

def detect_zones(n: int, max_zones: int = None) -> list[tuple[int, int]]:
    """Detecta zonas clicables dentro de la casilla n (usa casilla.png,
    ya recortado por crop_casilla -- llamar DESPUÉS de esa función) y
    devuelve sus centros como offsets físicos (dx, dy) respecto al
    centro de la casilla -- mismo sistema de coordenadas que
    clamp_offset()/cell_absolute_position(), ya recortados a los
    límites de la casilla -- listos para usarse directamente como
    ajuste fino ("click 1", "mover 2"...). Numeradas en el orden en que
    aparecen en la lista devuelta (índice 0 -> zona "1"). Lista vacía
    si no hay casilla.png legible o no se detecta ninguna zona."""
    if not CASILLA_FILE.exists():
        return []
    image = QImage(str(CASILLA_FILE))
    if image.isNull() or image.width() == 0 or image.height() == 0:
        return []
    boxes = _zones.detect_zones(str(CASILLA_FILE), max_zones=max_zones)
    if not boxes:
        return []
    cell_w, cell_h = image.width(), image.height()
    offsets = []
    for fx1, fy1, fx2, fy2 in boxes:
        cx_frac = (fx1 + fx2) / 2
        cy_frac = (fy1 + fy2) / 2
        dx = (cx_frac - 0.5) * cell_w
        dy = (cy_frac - 0.5) * cell_h
        offsets.append(clamp_offset(n, dx, dy))
    return offsets


def cell_absolute_position(n: int, offset_x: int = 0, offset_y: int = 0) -> tuple[int, int]:
    """Posición absoluta (píxeles físicos reales, los mismos que
    tablero.png) del punto de acción dentro de la casilla n: su centro,
    desplazado (offset_x, offset_y) por el ajuste fino."""
    size = tablero_size()
    if size is None:
        raise RuntimeError("no hay tablero.png capturado todavía")
    width, height = size
    x1, y1, x2, y2 = cell_region(n, width, height)
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    ox, oy = clamp_offset(n, offset_x, offset_y)
    return round(cx + ox), round(cy + oy)
