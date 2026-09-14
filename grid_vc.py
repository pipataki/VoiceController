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

from __future__ import annotations

import sys
# import pyautogui

import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPoint, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QFont, QGuiApplication, QPixmap, QScreen
from PySide6.QtWidgets import QApplication, QWidget

from PySide6 import QtDBus

from paths import PROJECT_ROOT




# ---------------------------------------------------------------------------
# Configuracion de la rejilla
# ---------------------------------------------------------------------------

MAIN_COLS_LANDSCAPE = 15
MAIN_ROWS_LANDSCAPE = 10
MAIN_COLS_PORTRAIT = 10
MAIN_ROWS_PORTRAIT = 15
SUB_COLS = 3
SUB_ROWS = 3


# ---------------------------------------------------------------------------
# Calculo de geometria
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GridLayout:
    """Describe la rejilla principal calculada para una pantalla concreta."""

    screen_rect: QRectF
    cols: int
    rows: int

    @property
    def cell_width(self) -> float:
        return self.screen_rect.width() / self.cols

    @property
    def cell_height(self) -> float:
        return self.screen_rect.height() / self.rows




    def cell_rect(self, cell_number: int) -> QRectF:
        """Rectangulo (coordenadas globales) de la celda 1..cols*rows."""
        total = self.cols * self.rows
        if not (1 <= cell_number <= total):
            raise ValueError(
                f"cell_number debe estar entre 1 y {total}, recibido {cell_number}"
            )
        index = cell_number - 1
        col = index % self.cols
        row = index // self.cols
        x1 = self.screen_rect.x() + round(col * self.cell_width)
        y1 = self.screen_rect.y() + round(row * self.cell_height)
        x2 = self.screen_rect.x() + round((col + 1) * self.cell_width)
        y2 = self.screen_rect.y() + round((row + 1) * self.cell_height)
        return QRectF(QPoint(x1, y1), QPoint(x2 - 1, y2 - 1))

    def subcell_rect(self, cell_number: int, subcell_number: int) -> QRectF:
        """Rectangulo (coordenadas globales) de la sub-celda 1..9 dentro
        de la celda indicada."""
        total_sub = SUB_COLS * SUB_ROWS
        if not (1 <= subcell_number <= total_sub):
            raise ValueError(
                f"subcell_number debe estar entre 1 y {total_sub}, "
                f"recibido {subcell_number}"
            )
        cell = self.cell_rect(cell_number)
        sub_index = subcell_number - 1
        scol = sub_index % SUB_COLS
        srow = sub_index // SUB_COLS
        sub_w = cell.width() / SUB_COLS
        sub_h = cell.height() / SUB_ROWS
        x1 = cell.x() + round(scol * sub_w)
        y1 = cell.y() + round(srow * sub_h)
        x2 = cell.x() + round((scol + 1) * sub_w)
        y2 = cell.y() + round((srow + 1) * sub_h)
        return QRectF(QPoint(x1, y1), QPoint(x2 - 1, y2 - 1))


def build_grid_layout(screen: Optional[QScreen] = None) -> GridLayout:
    """Crea el GridLayout para la pantalla dada (o la primaria si no se
    indica), eligiendo automaticamente landscape (15x10) o portrait
    (10x15) segun sus proporciones."""
    app = QGuiApplication.instance()
    if app is None:
        raise RuntimeError(
            "Se necesita una QGuiApplication/QApplication activa antes de "
            "llamar a build_grid_layout()."
        )
    screen = screen or app.primaryScreen()
    geo = screen.geometry()
    if geo.width() >= geo.height():
        cols, rows = MAIN_COLS_LANDSCAPE, MAIN_ROWS_LANDSCAPE
    else:
        cols, rows = MAIN_COLS_PORTRAIT, MAIN_ROWS_PORTRAIT
    return GridLayout(screen_rect=geo, cols=cols, rows=rows)




def get_position(
    cell_number: int,
    subcell_number: int,
    screen: Optional[QScreen] = None,
) -> QPoint:
    """Devuelve el punto central (coordenadas globales del escritorio)
    de la sub-celda (cell_number, subcell_number).

    Requiere una QGuiApplication/QApplication activa (se crea una
    automaticamente si se usa a traves de locate())."""
    layout = build_grid_layout(screen)
    rect = layout.subcell_rect(cell_number, subcell_number)
    return rect.center()


# ---------------------------------------------------------------------------
# Mover el puntero del raton (via ydotool)
# ---------------------------------------------------------------------------
#
# En Wayland (KDE Plasma 6) no existe una API "normal" de Qt para mover el
# cursor (QCursor.setPos() no funciona por las restricciones del propio
# protocolo). ydotool se apoya en /dev/uinput a nivel de kernel, asi que
# funciona independientemente del compositor. Requiere:
#   1. El paquete "ydotool" instalado.
#   2. El daemon "ydotoold" corriendo (systemctl enable --now ydotool.service,
#      o "ydotoold &" a mano).

YDOTOOL_BIN = "ydotool"

class YdotoolError(RuntimeError):
    """Error al invocar ydotool (binario ausente, daemon no disponible, etc.)."""


def _timeout_ydotool() -> float:
    """Limite de espera (config.YDOTOOL_TIMEOUT_S). Ver el comentario de
    esa opcion: sin limite, un demonio mudo cuelga el hilo para siempre."""
    try:
        import config
        return float(getattr(config, "YDOTOOL_TIMEOUT_S", 5.0) or 5.0)
    except Exception:
        return 5.0


def _run_ydotool(args: list[str]) -> None:
    try:
        subprocess.run(
            [YDOTOOL_BIN, *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=_timeout_ydotool(),
        )
    except subprocess.TimeoutExpired as exc:
        raise YdotoolError(
            f"ydotool no respondio en {_timeout_ydotool():.0f}s. "
            "Comprueba que ydotoold esta vivo y que es el TUYO "
            "(systemctl --user status ydotool.service)."
        ) from exc
    except FileNotFoundError as exc:
        raise YdotoolError(
            "No se encontro el binario 'ydotool'. Instalalo con tu gestor "
            "de paquetes (p.ej. 'sudo pacman -S ydotool')."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise YdotoolError(
            f"ydotool fallo (codigo {exc.returncode}): {exc.stderr.strip()}\n"
            "Comprueba que el daemon ydotoold esta corriendo "
            "('sudo systemctl enable --now ydotool.service' o 'sudo ydotoold &')."
        ) from exc


# ydotool en modo --absolute NO usa pixeles reales: usa un rango
# normalizado 0-32767 (como una tableta grafica), independiente de la
# resolucion real de la pantalla, y ademas en este sistema el modo
# absoluto falla directamente (no todos los compositores/versiones de
# ydotool lo soportan sin calibrar el dispositivo virtual). Por eso se
# usa movimiento RELATIVO, con dos correcciones sobre el intento
# anterior:
#   1. Escala: MEDIDO el 11-sep-2026, ydotool mueve en pixeles LOGICOS,
#      uno a uno -- no en fisicos, como se creia aqui. Lo que hay que
#      convertir es al reves: las coordenadas de la CAPTURA (fisicas) a
#      logicas antes de mover. Ver _escala_a_logico().
#   2. Aceleracion: el compositor/libinput acelera los eventos relativos
#      grandes, asi que el movimiento se trocea en pasos pequenos.



# CAPTURAR EL ESCRITORIO YA NO SE HACE AQUI
# -----------------------------------------
# Habia tres funciones -- capture_desktop(), _capture_desktop_pixmap() y
# _get_real_desktop_resolution() -- que llamaban a spectacle para fotografiar
# el escritorio y medirlo. La ultima la usaba move_pointer() para saber la
# resolucion real, lo que suponia UNA CAPTURA DE PANTALLA POR CADA MOVIMIENTO
# DEL RATON.
#
# Se quedaron sin usuarios el 11-sep-2026, al descubrir que ydotool mueve en
# pixeles logicos y esa conversion sobraba. Borradas el 12-sep.
#
# Quien necesite una captura del escritorio: board.capture_tablero(), que es
# la que usa todo el programa y ademas aparta la ventana antes.


def _escala_a_logico():
    """Cuantos pixeles LOGICOS hay por cada pixel de la CAPTURA, por eje.

    MEDIDO EL 10-sep-2026, NO SUPUESTO:

        kdotool getmouselocation      x:1049
        ydotool mousemove -- 200 0
        kdotool getmouselocation      x:1249      <- sube 200, no 111

    **ydotool mueve en pixeles LOGICOS**, uno a uno -- son las coordenadas
    del compositor, no las del monitor. Y tablero.png esta en FISICOS
    (3840x2160 con la pantalla logica en 2133x1200, escala 1,8).

    Asi que pedir "el pixel 1900 de la captura" movia el cursor a 1900
    logicos = 3420 fisicos: todo caia abajo y a la derecha, y el error
    crecia con la distancia al origen. A 1920x1080 sin escalado los dos
    numeros eran el mismo y esto no podia verse -- por eso ha aguantado
    hasta que pipataki cambio el escalado.

    Se divide el ancho logico entre el de la captura, y por eje: la
    proporcion no hace falta saberla (ver board.escala_captura, que hace
    justo lo contrario para recortar la imagen).
    """
    try:
        import board
        m = board.medidas()
        if m is not None:
            return m.a_logico
    except Exception as exc:
        print(f"[grid_vc] no se pudo saber la escala del puntero: {exc!r}")
    # Sin captura todavia, o sin Qt: se supone que coinciden, que es
    # lo que pasa siempre con la pantalla sin escalar.
    return 1.0, 1.0


# Reinicio: salto relativo enorme hacia arriba-izquierda. El compositor
# lo recorta al llegar a (0,0), asi que el cursor queda "clavado" ahi sin
# importar desde donde partiera. El posible overshoot por aceleracion no
# importa aqui porque de todas formas se recorta en el borde.
_RESET_OFFSET = 32767

# Tamano maximo (en pixeles logicos) de cada paso al mover hacia el
# objetivo, para no activar la curva de aceleracion del puntero.
_STEP = 15


def _move_relative_stepped(dx: int, dy: int) -> None:
    """Mueve el cursor (dx, dy) pixeles fisicos, partiendo el movimiento
    en pasos de como maximo _STEP pixeles para evitar la aceleracion del
    puntero."""
    remaining_x, remaining_y = dx, dy
    while remaining_x != 0 or remaining_y != 0:
        step_x = max(-_STEP, min(_STEP, remaining_x))
        step_y = max(-_STEP, min(_STEP, remaining_y))
        _run_ydotool(["mousemove", "--", str(step_x), str(step_y)])
        remaining_x -= step_x
        remaining_y -= step_y


def move_pointer(
    x: int,
    y: int,
    screen: Optional[QScreen] = None,
) -> None:
    """Mueve el puntero del raton a la posicion (x, y) en pixeles
    logicos del escritorio, con movimiento relativo troceado.

    NO se convierte nada: ydotool mueve en logicos, que es justo lo que
    entra aqui. Ver _escala_a_logico() para el caso contrario.

    Lanza YdotoolError si ydotool no esta instalado o el comando falla.
    """
    app = QGuiApplication.instance()
    if app is None:
        raise RuntimeError(
            "move_pointer() necesita una QGuiApplication/QApplication "
            "activa para conocer el origen y la resolucion logica de "
            "la pantalla."
        )
    screen = screen or app.primaryScreen()
    geo = screen.geometry()
    logical_width, logical_height = geo.width(), geo.height()

    # NO SE CONVIERTE NADA: la entrada ya viene en logicas y ydotool mueve
    # en logicas (medido, ver _escala_a_logico). Antes se multiplicaba por
    # la resolucion real -- lo que mandaba el cursor 1,8 veces demasiado
    # lejos en una pantalla escalada -- y ademas obligaba a CAPTURAR EL
    # ESCRITORIO ENTERO con spectacle en cada llamada solo para saber esa
    # resolucion.
    del logical_width, logical_height          # ya no hacen falta

    # Paso 1: clavar el cursor en (0,0).
    _run_ydotool(
        ["mousemove", "--", f"-{_RESET_OFFSET}", f"-{_RESET_OFFSET}"]
    )
    # Paso 2: desde (0,0), avanzar hasta el objetivo, troceado para evitar
    # la aceleracion.
    _move_relative_stepped(round(x - geo.x()), round(y - geo.y()))


def move_to(
    cell_number: int,
    subcell_number: int,
    screen: Optional[QScreen] = None,
) -> QPoint:
    """Calcula la posicion de (cell_number, subcell_number) y mueve el
    puntero del raton hasta ahi con ydotool.

    Requiere una QGuiApplication/QApplication activa (igual que
    get_position()). Devuelve el punto al que se ha movido el cursor.

    NOTA: esto es del sistema de rejilla ANTIGUO (15x10 + sub-celda 3x3),
    que se conservaba para la rejilla antigua, ya retirada (la
    previsualización a pantalla completa). El tablero de 100 casillas
    (board.py) usa move_pointer_physical(), no esta funcion.
    """
    app = QGuiApplication.instance()
    screen = screen or app.primaryScreen()
    position = get_position(cell_number, subcell_number, screen)
    move_pointer(position.toPoint().x(), position.toPoint().y(), screen)
    return position


def move_pointer_physical(phys_x: int, phys_y: int) -> None:
    """Mueve el puntero a una posición dada en píxeles FÍSICOS reales --
    los mismos que usan tablero.png/casilla.png (board.py). Pensado para
    el tablero de 100 casillas, cuyas coordenadas se calculan sobre la
    imagen capturada. Aqui SI se convierte -- de pixeles de la captura a
    logicos, que es lo que entiende ydotool -- porque los dos espacios
    solo coinciden cuando la pantalla no tiene escalado.

    Lanza YdotoolError si ydotool no esta instalado o el comando falla.
    """
    fx, fy = _escala_a_logico()
    destino_x, destino_y = round(phys_x * fx), round(phys_y * fy)
    _run_ydotool(["mousemove", "--", f"-{_RESET_OFFSET}", f"-{_RESET_OFFSET}"])
    _move_relative_stepped(destino_x, destino_y)
    _comprobar_donde_cayo(phys_x, phys_y, destino_x, destino_y)


def _comprobar_donde_cayo(pedido_x, pedido_y, destino_x, destino_y):
    """Apunta en el log donde se pidio y donde acabo de verdad el raton.

    APAGADO POR DEFECTO: cuesta un proceso (kdotool) por cada movimiento.
    Se enciende en config_local.py con

        DEPURAR_PUNTERO = True

    Existe porque "el clic cae un poco desplazado" no se puede arreglar: hay
    que saber CUANTO y si crece con la distancia. Mirandolo a ojo se tarda
    una tarde; con dos numeros en el log se ve a la primera.
    """
    try:
        import config
        if not getattr(config, "DEPURAR_PUNTERO", False):
            return
        import keyboard_keys
        k = keyboard_keys.find_kdotool()
        if not k:
            return
        r = subprocess.run([k, "getmouselocation"], capture_output=True,
                           text=True, timeout=2)
        salida = (r.stdout or "").strip()
        real_x = real_y = None
        for trozo in salida.split():
            if trozo.startswith("x:"):
                real_x = int(trozo[2:])
            elif trozo.startswith("y:"):
                real_y = int(trozo[2:])
        if real_x is None or real_y is None:
            return
        print(f"[grid_vc] puntero: captura ({pedido_x},{pedido_y}) -> "
              f"pedido logico ({destino_x},{destino_y}) -> real ({real_x},{real_y}) "
              f"| desvio ({real_x - destino_x:+d},{real_y - destino_y:+d})")
    except Exception as exc:
        print(f"[grid_vc] no se pudo comprobar el puntero: {exc!r}")


def move_pointer_relative(dx: int, dy: int) -> None:
    """Mueve el puntero (dx, dy) píxeles físicos DESDE SU POSICIÓN
    ACTUAL -- a diferencia de move_pointer_physical()/move_pointer(),
    que van a una posición ABSOLUTA (casilla+ajuste fino), esta función
    NO resetea a ninguna esquina primero: es movimiento puro estilo
    touchpad, pensado para arrastrar el dedo por la pantalla táctil del
    móvil (ver webapp/static/index.html, zona "touchpad", y
    webapp/app.py, ruta /board/touchpad) y que el cursor real siga el
    gesto en tiempo real, igual que el touchpad físico de un teclado.

    Reutiliza _move_relative_stepped() (mismo trocreado en pasos
    pequeños que ya usan move_pointer_physical/move_pointer, para no
    activar la curva de aceleración del puntero/libinput).

    Lanza YdotoolError si ydotool no esta instalado o el comando falla.
    """
    fx, fy = _escala_a_logico()
    _move_relative_stepped(round(dx * fx), round(dy * fy))


# ---------------------------------------------------------------------------
# Lo que YA NO esta aqui
# ---------------------------------------------------------------------------

# Rejilla principal (1-150): cian
COLOR_GRID_MAIN = QColor(0, 200, 255, 50)
COLOR_TEXT_MAIN = QColor(150, 235, 255, 50)

# Sub-rejillas (1-9): naranja, para diferenciarlas claramente de la principal
COLOR_GRID_SUB = QColor(255, 170, 0, 50)
COLOR_TEXT_SUB = QColor(255, 210, 120, 50)

COLOR_HIGHLIGHT_CELL = QColor(255, 60, 60, 50)
COLOR_HIGHLIGHT_SUB = QColor(255, 60, 60, 50)






# ---------------------------------------------------------------------------
# API de alto nivel
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Ejecucion como script
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lo que YA NO esta aqui, y por que
# ---------------------------------------------------------------------------
#
# Este modulo tenia ademas una rejilla a PANTALLA COMPLETA -- la clase
# GridVc, show_vc() y locate() -- que era como se elegian las
# posiciones ANTES de que existiera el tablero de 100 casillas.
#
# Se quito el 4-sep-2026, a peticion suya: ya no se usaba para nada y solo
# servia para confundir. Lo que se ve ahora es la vista del GUI, que dibuja
# la rejilla numerada dentro de la ventana (ver gui._do_show_board_overview
# y el comando "tablero").
#
# Lo que SI se queda, y es la razon de que el modulo siga existiendo: mover
# el puntero y pulsar. move_pointer_physical(), move_to(), click_at(),
# right_click_at(), double_click_at() y scroll() son la capa que toca el
# raton de verdad, y medio programa pasa por aqui.
#
# Si alguien vuelve a necesitar una rejilla a pantalla completa, esta en el
# historial: git show <commit anterior>:grid_vc.py
