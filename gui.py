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
Ventana principal de VoiceController.

- Siempre visible y "always on top" hasta que se diga "close".
- Tres campos de texto apilados (ver manual, Sección 2):
    1. Texto (arriba): texto ya CONFIRMADO ("entra"/"okey"), acumulado línea
       a línea. No se envía solo al confirmar — se queda aquí hasta que se
       diga "copiar texto" (va al portapapeles), "pegar texto" (se escribe
       por teclado en la ventana activa y se vacía) o "seleccionar texto"
       (copia + resalta visualmente este campo). "vaciar texto" lo borra
       sin enviarlo a ningún sitio.
    2. Pre-Texto (medio): lo que se está dictando AHORA MISMO (buffer +
       previsualización en vivo), tanto en modo Dictado como en modo
       Fórmula. Se sube a Texto al confirmar, o se descarta con
       "reset"/"idel".
    3. Sugerencias (abajo): aviso puntual que aparece tras una pausa
       mientras se dicta (ver config.PAUSE_SUGGESTION_MS), por ejemplo
       cuando lo dictado en modo normal "suena" a una expresión numérica y
       se podría pasar a dígitos/notación matemática ("aplica sugerencia"
       para aceptarla, "descarta sugerencia" para ignorarla). Se limpia
       sola en cuanto hay nueva actividad de voz.
- Fila de estado: LEDs de IDLE / DICT / FORMULA / VOZ, la combinación de
  idiomas activa y la última celda/subcelda visitada por voz.
- Botones "Enter"/"Reset"/"Idle"/"Close" + "Copiar"/"Pegar"/"Vaciar" (estos
  tres últimos actúan sobre el campo Texto): funcionan igual por clic que
  por voz, porque mandan las mismas acciones que router.on_final/
  manual_action ya reconocen.
- apartar_ventana() / subir_ventana(): se llaman
  desde actions.py mientras dura una acción del tablero (mover, click,
  scroll...) y se ejecutan de forma segura en el hilo de Qt vía señales,
  porque quien las llama corre en el hilo de audio/recognizer.
- run_on_main_thread(fn) / run_on_main_thread_delayed(fn, delay_ms): ejecutan
  una función en el hilo principal de Qt (la segunda, tras una pequeña
  pausa). Imprescindible para todo lo que llame a grid_vc.py, porque
  usa clases de Qt (QScreen, QPixmap...) que NO se pueden tocar de forma
  segura fuera del hilo principal — llamarlas desde el hilo de audio puede
  fallar en silencio o no hacer nada visible. El retraso da tiempo a que el
  minimizado de la ventana (animación del compositor, no instantánea en
  Wayland/KWin) se complete antes de que grid_vc capture pantalla.
- Detector de pausas (self._pause_check_timer): sondea cada
  config.PAUSE_POLL_MS si han pasado config.PAUSE_SUGGESTION_MS desde la
  última actividad de texto mientras se dicta; si es así, llama UNA vez (por
  cada episodio de pausa) al callback registrado con set_pause_callback(fn)
  — normalmente router.check_pause_suggestion — para que decida si hay algo
  que sugerir. Vive en el hilo de Qt (igual que toda la GUI), así que no
  hace falta ninguna señal para esto: solo se lee un timestamp que las
  propias señales de texto ya actualizan.
"""

import math
import subprocess
import time

import sounddevice as sd
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QIcon, QAction, QActionGroup, QPainter, QPen, QFont, QColor, QPixmap, QCursor,
)
from PySide6.QtCore import QRectF, QPointF, QSize, QPoint
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QSystemTrayIcon, QMenu, QStyle, QSizePolicy,
)
import json
import config
import board
from paths import (
    PROJECT_ROOT,
    WEBAPP_DIR,
    WEBAPP_STATIC_DIR,
    WEBAPP_UPLOADS_DIR,
    COMMANDS_FILE,
    WEBAPP_CONFIG_FILE,
    WEBAPP_CERT_FILE,
    WEBAPP_KEY_FILE,
    LABELS_FILE,
    TABLERO_FILE,
    CASILLA_FILE,
    VC_FILE,
    ZOOM_OUT_FILE,
    FOCO_FILE,
    ESTADO_VISTA_FILE,
    ICONS_DIR,
)


def _load_labels() -> dict:
    try:
        with open(LABELS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[gui] no se pudo cargar {LABELS_FILE}: {exc!r} -- uso etiquetas por defecto")
        return {
            "es": {"active_prefix": "Activo", "cell_label": "Celda", "btn_enter": "Entrar",
                   "btn_reset": "Borrar", "btn_correct": "Corregir", "btn_idle": "Escucha", "btn_close": "Cerrar",
                   "btn_copy": "Copiar", "btn_paste": "Pegar", "btn_select": "Seleccion",
                   "btn_clear": "Vaciar", "texto_label": "Texto:",
                   "board_placeholder": "(sin tablero todavia)"},
        }


class ClickableImageLabel(QLabel):
    """QLabel que informa (como fracción 0.0-1.0 de su propio tamaño) dónde
    se ha tocado/clicado -- usada para el tablero (selección de casilla
    táctil, ver manual Sección 1: "Todo el tablero GUI acepta entrada
    táctil")."""

    def __init__(self, on_tap, parent=None):
        super().__init__(parent)
        self._on_tap = on_tap

    def mousePressEvent(self, event):  # noqa N802
        if self._on_tap and self.width() > 0 and self.height() > 0:
            try:
                pos = event.position()  # Qt6: QPointF
                fx = pos.x() / self.width()
                fy = pos.y() / self.height()
            except AttributeError:
                pos = event.pos()
                fx = pos.x() / self.width()
                fy = pos.y() / self.height()
            self._on_tap(fx, fy)
        super().mousePressEvent(event)


LED_ON = "#2ecc71"
LED_OFF = "#3a3a3a"
# El LED de escucha tiene TRES estados, no dos, y por eso no le vale el
# LED_ON/LED_OFF de los demas:
#   verde    -> despierto y te ha reconocido
#   ambar    -> despierto pero la ultima voz no era la tuya (ver
#               command_router._preguntar_si_eres_tu). No es una alarma:
#               no ha pasado nada, simplemente no se ha hecho nada
#   apagado  -> en espera (standby); solo atiende al santo y sena
# Se distingue de un vistazo y SIN un solo sonido, que es justo lo que
# hacia falta: saber si te esta escuchando sin que el ordenador hable.
LED_DUDA = "#e0a030"
LED_STYLE = "border-radius: 7px; min-width: 14px; max-width: 14px; min-height: 14px; max-height: 14px;"


class CompassWidget(QWidget):
    """Compás de 8 direcciones, con los iconos de icons/ (Activado en
    verde / Desactivado en gris, ver Iconos.zip): alternativa gráfica
    al ajuste fino por voz. Solo está habilitado (iconos "Activado")
    mientras hay una casilla seleccionada -- ver gui.set_board_active().

    Los 8 pétalos se colocan por trigonometría (no en una rejilla)
    sobre un círculo perfecto de radio _RADIUS.

    "Click izquierdo"/"click derecho" (antes un par de botones justo
    debajo del círculo) se QUITARON -- por accesibilidad, para que la
    imagen central (tablero/zoom_out/casilla) pueda ocupar el máximo
    ancho posible de la ventana; con el rediseño de accesibilidad
    (puntero verde + touchpad + confirmación por voz, ver Fase 2 y
    actions.fire_zoom_out_action/fire_board_action) esos dos botones ya
    eran redundantes con decir "click"/"click derecho" por voz."""

    _DIRECTIONS = [
        ("n", "norte", 0), ("ne", "noreste", 45), ("e", "este", 90),
        ("se", "sureste", 135), ("s", "sur", 180), ("sw", "suroeste", 225),
        ("w", "oeste", 270), ("nw", "noroeste", 315),
    ]
    _ICON_SIZE = QSize(20, 20)
    _BTN_SIZE = 24
    _RADIUS = 30  # distancia del centro del círculo a cada pétalo (px)

    def __init__(self, on_direction, parent=None):
        super().__init__(parent)
        self._on_direction = on_direction
        self._active = False
        self._petal_buttons = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.setAlignment(Qt.AlignHCenter)

        # -- círculo de 8 pétalos (posicionados a mano, sin QGridLayout,
        # para que formen un círculo geométrico real y no una rejilla) --
        diameter = round(self._RADIUS * 2 + self._BTN_SIZE)
        circle = QWidget()
        circle.setFixedSize(diameter, diameter)
        cx = cy = diameter / 2
        for key, word, angle_deg in self._DIRECTIONS:
            btn = self._make_button(lambda checked=False, w=word: self._direction_clicked(w))
            btn.setParent(circle)
            angle = math.radians(angle_deg - 90)  # 0° = arriba (norte)
            bx = cx + self._RADIUS * math.cos(angle) - self._BTN_SIZE / 2
            by = cy + self._RADIUS * math.sin(angle) - self._BTN_SIZE / 2
            btn.setGeometry(round(bx), round(by), self._BTN_SIZE, self._BTN_SIZE)
            self._petal_buttons[key] = btn
        outer.addWidget(circle, alignment=Qt.AlignHCenter)

        self.set_active(False)

    def _make_button(self, slot):
        btn = QPushButton()
        btn.setFlat(True)
        btn.setIconSize(self._ICON_SIZE)
        btn.setFixedSize(self._BTN_SIZE, self._BTN_SIZE)
        btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; padding: 0px; } "
            "QPushButton:disabled { background: transparent; }"
        )
        btn.clicked.connect(slot)
        return btn

    def _icon(self, filename: str) -> QIcon:
        path = ICONS_DIR / filename
        if not path.exists():
            return QIcon()
        return QIcon(str(path))

    def _direction_clicked(self, word):
        if self._active and self._on_direction:
            self._on_direction(word)

    def set_active(self, active: bool):
        self._active = active
        suffix = "Ac" if active else "Deac"
        for key, btn in self._petal_buttons.items():
            btn.setIcon(self._icon(f"{key}{suffix}.png"))
            btn.setEnabled(active)


class GUI(QWidget):
    # alto de board_view cuando todavía no hay ninguna imagen que mostrar
    # (solo el texto de aviso) -- con imagen manda la proporción, ver
    # _fit_board_view()
    _BOARD_PLACEHOLDER_H = 140

    # señales para poder llamar estos métodos de forma segura desde otro hilo
    sig_update_pretexto = Signal(str, str)     # (buffer, preview) -- campo 2
    sig_update_texto = Signal(str)             # texto confirmado -- campo 1
    sig_highlight_texto = Signal(bool)         # resalta el campo Texto ("seleccionar texto")
    sig_update_suggestion = Signal(str, bool)  # texto de la sugerencia y si es urgente -- campo 3
    sig_update_escucha = Signal(str)          # "activo" / "duda" / "dormido" -- LED de escucha
    sig_clear_suggestion = Signal()
    sig_clear_pretexto = Signal()
    sig_quit = Signal()
    sig_minimize = Signal()
    sig_restore = Signal()
    sig_run_callable = Signal(object)          # ejecuta fn() ya en el hilo de Qt
    sig_run_callable_delayed = Signal(object, int)  # ejecuta fn() tras delay_ms
    sig_update_state = Signal(str)             # "IDLE" | "DICTATING"
    sig_update_formuling = Signal(bool)         # True = formuling (letra a letra) active
    sig_update_pretexto_formuling = Signal(str, str)  # (buffer, preview) for formuling mode
    sig_update_position = Signal(int, int)     # (celda, subcelda)
    sig_update_language_combo = Signal(str)
    sig_update_audio_level = Signal(bool, float)  # (is_silent, rms) -- VAD ligero
    sig_show_board_overview = Signal()               # tablero.png + rejilla numerada
    sig_show_board_cell = Signal(int, int, int, object)  # casilla.png + marcador (cell, offset_x, offset_y, zones)
    sig_show_zoom_out = Signal(int, int, int)        # zoom_out.png + marcador verde (cell, offset_x, offset_y)
    sig_show_foco = Signal(int, int)                 # foco.png + puntero verde (offset_x, offset_y)
    sig_set_ui_language = Signal(str)                # "es" | "en" -- refresca todas las etiquetas
    sig_set_board_active = Signal(bool)              # activa/desactiva el compás de 8 direcciones
    sig_show_help = Signal(str, object, int)         # (titulo, lineas, duracion_ms) -- ventana de ayuda
    sig_hide_help = Signal()

    # A partir de cuántas líneas la ventana de ayuda pasa a dos columnas.
    #
    # Subido de 22 a 30 el 5-sep-2026, junto con el agrupado de las acciones
    # mecánicas en command_router._GRUPOS_AYUDA: la ayuda más larga que hay
    # -- dentro de una casilla -- pasó de 66 líneas a 30, y esas 30 se leen
    # mejor seguidas que partidas en dos columnas de 15.
    #
    # El mismo número está en ayuda_popup.MAX_FILAS, que es la ventana del
    # modo servicio. SON DOS COPIAS: si se toca una, hay que tocar la otra.
    _HELP_MAX_ROWS = 30

    def __init__(self, on_manual_action, arranca_oculto: bool = False):
        """
        on_manual_action(action: str) -> callback llamado cuando se pulsa un
        botón o una opción de la bandeja. Recibe acciones internas como
        "confirm", "reset", "idle", "quit", "copy_confirmed", "paste_confirmed",
        "clear_confirmed".

        arranca_oculto=True es el MODO SERVICIO (--as-service): la misma
        ventana de siempre, con todo lo que ya funciona, pero que empieza
        escondida y se pide cuando hace falta.

        Sustituye al modo servicio anterior, que pintaba las vistas como
        vcs sobre el escritorio. Se descartó el 6-sep-2026 con
        medidas: no ahorraba memoria (consumía 220 MB MÁS que la ventana),
        el compositor tenía que componer tres superficies a pantalla
        completa todo el rato, y dio dos días de peleas con Wayland. Ver
        MANIFEST.md.

        Por defecto False: con la ventana normal, ABSOLUTAMENTE NADA
        cambia. Todo lo que este valor enciende está detrás de un `if`.
        """
        # Modo servicio: la ventana existe pero no se enseña sola. Nada
        # más de este fichero cambia si esto es False.
        self._modo_servicio = bool(arranca_oculto)

        # Origen de seleccion fijado: mientras lo haya, el puntero se pinta
        # AMARILLO en vez de verde. Ver _color_puntero().
        self._seleccion_pendiente = False
        # Origen de la seleccion EN LAS UNIDADES DE LA VISTA (los mismos
        # offset_x/offset_y que reciben los metodos de pintado), mas la
        # vista y la casilla donde se fijo. Ver _pintar_seleccion().
        self._seleccion_origen_offset = None
        self._seleccion_origen_vista = None
        self._seleccion_origen_celda = None
        # Ultimo (offset_x, offset_y) con el que se pinto la vista. Hace
        # falta para poder repintarla sin que nadie vuelva a pedirla --
        # p.ej. al fijar el origen de una seleccion, para que el recuadro
        # se vea en el acto y no en el siguiente movimiento.
        self._ultimo_offset = (0, 0)


        self._last_position = None  # (cell, subcell) o None
        self._current_state = "IDLE"
        self._last_activity_ts = 0.0
        self._pause_notified = True  # no hay nada que sugerir al arrancar
        self._pause_callback = None  # se conecta con set_pause_callback()
        self._touch_callback = None  # se conecta con set_touch_callback()
        self._labels_all = _load_labels()
        self._ui_lang = "es"
        self._board_mode = "overview"  # "overview" | "cell" | "zoom_out" | "foco"
        self._board_cell = None
        self._board_zones = []  # últimas zonas detectadas de la casilla activa, para
                                 # poder redibujar el marcador sin repasarlas cada vez
                                 # (ver _do_touch_track)

        # Seguimiento táctil del círculo verde (ver _do_touch_track): mientras
        # haya una casilla ampliada visible, el marcador verde sigue la
        # posición REAL del puntero (ratón/touchpad/táctil), sin necesitar
        # eventos de Qt (la ventana es click-through) -- se lee la posición
        # global del cursor por sondeo. self._touch_offset guarda el último
        # (offset_x, offset_y) calculado, consultable desde fuera con
        # get_touch_offset() para comandos de voz tipo "click verde".
        # self._touch_follow_enabled controla la fuente activa: True =
        # táctil (por defecto); False = "cara" -- reservado para un futuro
        # seguimiento por cámara/detección facial, TODAVÍA NO IMPLEMENTADO
        # (ver command_router._try_parse_input_mode) -- con False, no se seguirá
        # nada por ahora hasta que se implemente esa fuente.
        self._touch_follow_enabled = True
        self._touch_offset = None
        # Ventana flotante de ayuda ("ayuda"/"help", scope any) -- se
        # crea perezosamente la primera vez que se pide (ver
        # _do_show_help) y se reutiliza después.
        self._help_popup = None
        self._help_title = None
        self._help_body = None
        self._help_body_2 = None
        self._help_timer = None
        self._board_canvas_size = None  # (ancho, alto) del último canvas dibujado
        self._board_scale = None        # (sx, sy) del último canvas dibujado

        super().__init__()
        self._on_manual_action = on_manual_action
        self._build_ui()
        self._wire_signals()
        self._do_update_state("IDLE")  # estado inicial (ya en el hilo de Qt, construcción)

        self._pause_check_timer = QTimer(self)
        self._pause_check_timer.setInterval(config.PAUSE_POLL_MS)
        self._pause_check_timer.timeout.connect(self._check_pause)
        self._pause_check_timer.start()

        # Captura periódica de la ventana del GUI a vc.png (ver docstring
        # del módulo y config.VC_SNAPSHOT_POLL_MS) -- solo escribe a disco
        # si el contenido visual cambió de verdad desde la última captura,
        # para no generar escrituras/parpadeos innecesarios en la webapp.
        self._last_vc_image = None
        self._vc_snapshot_timer = QTimer(self)
        self._vc_snapshot_timer.setInterval(config.VC_SNAPSHOT_POLL_MS)
        self._vc_snapshot_timer.timeout.connect(self._maybe_capture_vc_snapshot)
        self._vc_snapshot_timer.start()

        # Sondeo de la posición REAL del puntero (QCursor.pos(), global,
        # no depende de eventos Qt -- la ventana es click-through) para
        # que el círculo verde de la casilla ampliada siga cualquier
        # movimiento de ratón/touchpad/táctil (ver _do_touch_track,
        # get_touch_offset(), config.TOUCH_TRACK_POLL_MS). Solo hace algo
        # mientras self._board_mode == "cell" y self._touch_follow_enabled.
        self._touch_track_timer = QTimer(self)
        self._touch_track_timer.setInterval(config.TOUCH_TRACK_POLL_MS)
        self._touch_track_timer.timeout.connect(self._do_touch_track)
        self._touch_track_timer.start()

        # Ventana común y corriente: sin passthrough, sin transparencia
        # forzada, sin onTop ni ningún flag especial de ventana -- el
        # control de foco/orden de apilamiento se hace explícitamente
        # con bring_to_front()/send_to_back() en vez de con flags
        # permanentes de Qt (ver command_router y actions.fire_board_action).
        #
        # EXCEPCIÓN NECESARIA: WA_ShowWithoutActivating NO es un flag de
        # "ventana especial" (no es passthrough/transparencia/onTop) --
        # es lo que evita que un simple self.show() le robe el foco a lo
        # que esté abierto (p.ej. un menú recién abierto por la propia
        # acción de tablero). Sin él, el ciclo hide()/show() que hace
        # apartar_ventana()/send_to_back() en cada clic vuelve
        # a activar la ventana al reaparecer y cierra el menú -- por eso
        # se mantiene, aunque el resto de flags especiales se hayan
        # quitado.
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.resize(356, 200)
        # Título explícito y fijo: necesario para poder activar esta
        # MISMA ventana por nombre con `kdotool` (ver
        # bring_to_front() -- kdotool activa a través de KWin
        # directamente, mucho más fiable que self.activateWindow() de
        # Qt cuando otra ventana está maximizada/ocupando el escritorio
        # bajo Wayland).
        self.setWindowTitle("VoiceController")
        # EN EL CENTRO DESDE EL PRIMER ARRANQUE. Sin esto sale donde quiera
        # el gestor de ventanas, que no es lo mismo en KDE, en Windows ni en
        # una VM recien hecha. Se repite en el primer showEvent porque hasta
        # que no se muestra, el tamano definitivo no esta decidido.
        self.centrar_en_pantalla()
        self._ya_centrada = False
        # Provide a system tray for emergency/interactivity controls
        self._setup_tray()

    def resizeEvent(self, evento):
        """Si al cambiar de tamano se sale de la pantalla, se vuelve a meter.

        POR QUE HACE FALTA: la ventana se coloca con el tamano que tiene EN
        ESE MOMENTO -- al arrancar, o en reposition_for_board --, y despues
        CRECE: al mostrar el tablero, _fit_board_view le da a la imagen su
        alto, y la ventana pasa de 491 a 712 px con una captura 16:10. Nadie
        la recolocaba. En la VM de pruebas (2560x1600 al 175%, escritorio
        logico de 1463x914) acababa unos 30 px por debajo del borde. Lo vio
        pipataki el 12-sep-2026.

        Solo se mueve si hace falta, y solo lo justo: si ya cabe, no se toca
        -- que el usuario la haya puesto donde quiere es sagrado.
        """
        super().resizeEvent(evento)
        if not self.isVisible():
            return
        x, y = self.x(), self.y()
        nx, ny = self._dentro_de_pantalla(x, y, self.width(), self.height())
        if (nx, ny) != (x, y):
            self.move(nx, ny)

    def showEvent(self, evento):
        """La primera vez que se ve, se recentra con el tamano de verdad."""
        super().showEvent(evento)
        if not getattr(self, "_ya_centrada", False):
            self._ya_centrada = True
            self.centrar_en_pantalla()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Fila 1: estado (LEDs, idioma activo, celda) + compás ---
        status_row = QHBoxLayout()
        self.led_idle = QLabel()
        self.led_idle.setStyleSheet(LED_STYLE)
        self.led_dictating = QLabel()
        self.led_dictating.setStyleSheet(LED_STYLE)
        self.led_formuling = QLabel()
        self.led_formuling.setStyleSheet(LED_STYLE)
        self.led_audio = QLabel()
        self.led_audio.setStyleSheet(f"background: {LED_OFF}; {LED_STYLE}")
        self.led_escucha = QLabel()
        self.led_escucha.setStyleSheet(f"background: {LED_ON}; {LED_STYLE}")
        self.led_escucha.setToolTip("Despierto y te reconozco")
        status_row.addWidget(QLabel("ESCUCHA"))
        status_row.addWidget(self.led_escucha)
        status_row.addSpacing(12)
        status_row.addWidget(QLabel("IDLE"))
        status_row.addWidget(self.led_idle)
        status_row.addSpacing(12)
        status_row.addWidget(QLabel("DICT"))
        status_row.addWidget(self.led_dictating)
        status_row.addSpacing(8)
        status_row.addWidget(QLabel("FORMULA"))
        status_row.addWidget(self.led_formuling)
        status_row.addSpacing(8)
        status_row.addWidget(QLabel("VOZ"))
        status_row.addWidget(self.led_audio)
        status_row.addStretch()
        self.language_combo_label = QLabel("Activo: ES > EN")
        status_row.addWidget(self.language_combo_label)
        status_row.addSpacing(12)
        self.position_label = QLabel("Celda: —")
        status_row.addWidget(self.position_label)
        status_row.addSpacing(10)

        layout.addLayout(status_row)

        # --- Fila 2: edición del campo Texto (copiar/pegar/seleccionar/
        # vaciar) -- junto a los LEDs de estado, NO abajo del todo (ver
        # boceto del manual: la fila inferior es solo para Entrar/Borrar/
        # Escucha/Cerrar). Sin icono dedicado (Iconos.zip no trae uno para
        # esto), así que llevan un acabado a juego con el verde del compás.
        texto_btn_style = (
            "QPushButton { background: #1a1a1a; color: #a8f0c0; border: 1px solid #2ecc71; "
            "border-radius: 4px; padding: 3px 8px; font-size: 12px; } "
            "QPushButton:hover { background: #163a24; } "
            "QPushButton:pressed { background: #2ecc71; color: #0a0a0a; }"
        )
        texto_btn_row = QHBoxLayout()
        self.texto_row_label = QLabel("Texto:")
        self.btn_copy_texto = QPushButton("📋 Copiar")
        self.btn_paste_texto = QPushButton("📤 Pegar")
        self.btn_select_texto = QPushButton("🖱 Seleccion")
        self.btn_clear_texto = QPushButton("🗑 Vaciar")
        for _b in (self.btn_copy_texto, self.btn_paste_texto, self.btn_select_texto, self.btn_clear_texto):
            _b.setStyleSheet(texto_btn_style)
        self.btn_copy_texto.clicked.connect(lambda: self._on_manual_action("copy_confirmed"))
        self.btn_paste_texto.clicked.connect(lambda: self._on_manual_action("paste_confirmed"))
        self.btn_select_texto.clicked.connect(lambda: self._on_manual_action("select_confirmed"))
        self.btn_clear_texto.clicked.connect(lambda: self._on_manual_action("clear_confirmed"))
        texto_btn_row.addWidget(self.texto_row_label)
        texto_btn_row.addWidget(self.btn_copy_texto)
        texto_btn_row.addWidget(self.btn_paste_texto)
        texto_btn_row.addWidget(self.btn_select_texto)
        texto_btn_row.addWidget(self.btn_clear_texto)
        texto_btn_row.addStretch()

        self.compass = CompassWidget(self._on_compass_direction)
        texto_btn_row.addWidget(self.compass)

        layout.addLayout(texto_btn_row)

        # --- Tablero de 100 casillas (Sección 1 del manual) ---
        # Vista general (tablero.png + rejilla numerada) o, con una casilla
        # seleccionada, el recorte ampliado (casilla.png + marcador de
        # ajuste fino). Acepta toque/clic (selección de casilla en la vista
        # general), igual que por voz.
        #
        # ANCHO: el que dé la ventana (accesibilidad -- la imagen debe
        # llegar de lado a lado). ALTO: NO se fija aquí; lo calcula
        # _fit_board_view() a partir de la proporción de la imagen que
        # toque mostrar, así que la ventana crece o mengua un poco de alto
        # según se muestre tablero (16:9), zoom_out o casilla. Antes era
        # setFixedSize(356, 200) y las tres funciones de dibujo escalaban
        # con un tope de 170px de ALTO: para una captura 16:9 ese tope
        # mandaba (302x170), así que sobraban ~27px muertos a cada lado y
        # la imagen nunca llegaba al ancho de la ventana.
        self.board_view = ClickableImageLabel(self._on_board_tap)
        self.board_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.board_view.setMinimumHeight(self._BOARD_PLACEHOLDER_H)
        self.board_view.setStyleSheet("background: #101010; border: 1px solid #2a2a2a;")
        self.board_view.setAlignment(Qt.AlignCenter)
        self.board_view.setText(self._labels_all["es"]["board_placeholder"])
        self.board_view.setStyleSheet(
            self.board_view.styleSheet() + " color: #666; font-size: 11px;"
        )
        board_row = QHBoxLayout()
        board_row.setContentsMargins(0, 0, 0, 0)
        board_row.addWidget(self.board_view)
        layout.addLayout(board_row)

        # --- Botones de confirmación, JUSTO debajo de la imagen ---
        # Mismo esquema que el touchpad del móvil (ver NuevoGUI.pdf): se
        # arrastra el puntero verde sobre la imagen y se confirma aquí,
        # como en un touchpad físico. No mandan una acción propia: inyectan
        # "click verde"/"click derecho verde" por el MISMO camino que la
        # voz y el compás (handle_touch -> on_final), así que actúan sobre
        # la posición en vivo del puntero verde, no sobre el ajuste del
        # compás -- ver command_router._try_parse_board_action_green.
        # Van debajo del tablero a propósito, no al lado: ahí no le quitan
        # ancho a la imagen, que es lo que importa para la accesibilidad.
        touchpad_btn_style = (
            "QPushButton { background: #1a1a1a; color: #a8f0c0; border: 1px solid #2ecc71; "
            "border-radius: 4px; padding: 6px 8px; font-size: 12px; } "
            "QPushButton:hover { background: #163a24; } "
            "QPushButton:pressed { background: #2ecc71; color: #0a0a0a; } "
            "QPushButton:disabled { color: #5a5a5a; border: 1px solid #3a3a3a; }"
        )
        self.btn_tp_left = QPushButton("Izquierdo")
        self.btn_tp_right = QPushButton("Derecho")
        touchpad_btn_row = QHBoxLayout()
        touchpad_btn_row.setContentsMargins(0, 0, 0, 0)
        for _b, _cmd in ((self.btn_tp_left, "click verde"),
                         (self.btn_tp_right, "click derecho verde")):
            _b.setStyleSheet(touchpad_btn_style)
            _b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            _b.setEnabled(False)  # solo con casilla/zoom_out activo
            _b.clicked.connect(lambda _checked=False, cmd=_cmd: self._on_touchpad_button(cmd))
            touchpad_btn_row.addWidget(_b)
        layout.addLayout(touchpad_btn_row)


        # --- Campo 1: Texto (confirmado) ---
        self.texto_label = QLabel("")
        self.texto_label.setWordWrap(True)
        self._texto_style_normal = (
            "font-size: 16px; padding: 10px; background: #1e1e1e; color: #f0f0f0; "
            "border: 1px solid #1e1e1e;"
        )
        self._texto_style_highlight = (
            "font-size: 16px; padding: 10px; background: #1e1e1e; color: #f0f0f0; "
            "border: 1px solid #2ecc71;"
        )
        self.texto_label.setStyleSheet(self._texto_style_normal)
        self.texto_label.setMinimumHeight(90)
        self.texto_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.texto_label)

        # --- Campo 2: Pre-Texto (en vivo) ---
        self.pretexto_label = QLabel("")
        self.pretexto_label.setWordWrap(True)
        self.pretexto_label.setStyleSheet(
            "font-size: 13px; padding: 8px; background: #141414; color: #d8d8d8;"
        )
        self.pretexto_label.setMinimumHeight(46)
        self.pretexto_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.pretexto_label)

        # --- Campo 3: Sugerencias ---
        self.suggestion_label = QLabel("")
        self.suggestion_label.setWordWrap(True)
        self._estilo_sugerencia = (
            "font-size: 12px; font-style: italic; padding: 6px 10px; "
            "background: #241d0a; color: #e0b84a; border-left: 3px solid #e0b84a;"
        )
        # Urgente: en negrita, sin cursiva y con el fondo invertido. A 24px
        # se comía la ventana -- lo que llama la atención es el contraste y
        # el parpadeo, no el tamaño.
        self._estilo_sugerencia_urgente = (
            "font-size: 15px; font-weight: bold; padding: 8px 10px; "
            "background: #e0b84a; color: #1a1400; border-left: 5px solid #ffffff;"
        )
        self._estilo_sugerencia_urgente_apagado = (
            "font-size: 15px; font-weight: bold; padding: 8px 10px; "
            "background: #7a6420; color: #1a1400; border-left: 5px solid #7a6420;"
        )
        self.suggestion_label.setStyleSheet(self._estilo_sugerencia)

        # El parpadeo se crea AQUI, con la etiqueta, y no mas abajo con los
        # demas temporizadores: el GUI llama a _do_clear_suggestion durante
        # su propia construccion, antes de llegar a esa parte, y se caia con
        # un AttributeError nada mas arrancar.
        self._parpadeo_timer = QTimer(self)
        self._parpadeo_timer.setInterval(600)
        self._parpadeo_timer.timeout.connect(self._parpadear_sugerencia)
        self._parpadeo_encendido = True

        # El micrófono se abre AL FINAL del arranque, después de cargar el
        # modelo de voz, que es lo que más tarda. Hasta entonces la ventana
        # ya está en pantalla y ya puede estar pidiendo el santo y seña --
        # pero no hay nada escuchando, así que hablar no sirve de nada.
        #
        # En un equipo rápido el hueco casi no se nota. En uno lento es de
        # medio minuto largo, y quien lo estrena habla al vacío sin
        # entender por qué no pasa nada. Salió instalando de cero en una
        # máquina virtual, que hizo de ordenador lento sin querer.
        #
        # Que llegue nivel de audio ES la prueba de que el dispositivo está
        # abierto: esa señal no se emite antes.
        self._micro_listo = False
        self._aviso_urgente_pendiente = None
        self.suggestion_label.setMinimumHeight(24)
        self.suggestion_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.suggestion_label.hide()  # solo visible cuando hay una sugerencia activa
        layout.addWidget(self.suggestion_label)

        layout.addStretch()

        # --- Fila inferior: SOLO los 5 básicos para manejar el dictado
        # (ver boceto del manual) -- Entrar / Borrar / Corregir / Escucha /
        # Cerrar. Nada más aquí; la edición del Texto (copiar/pegar/...)
        # está arriba, junto al estado.
        btn_row = QHBoxLayout()
        self.btn_enter = QPushButton("📥 Entrar")
        self.btn_reset = QPushButton("🗑 Borrar")
        self.btn_correct = QPushButton("🩹 Corregir")
        self.btn_idle = QPushButton("🎧 Escucha")
        self.btn_close = QPushButton("✕ Cerrar")
        self.btn_enter.clicked.connect(lambda: self._on_manual_action("confirm"))
        self.btn_reset.clicked.connect(lambda: self._on_manual_action("reset"))
        self.btn_correct.clicked.connect(lambda: self._on_manual_action("correct_last_word"))
        self.btn_idle.clicked.connect(lambda: self._on_manual_action("idle"))
        self.btn_close.clicked.connect(self.quit_app)
        btn_row.addWidget(self.btn_enter)
        btn_row.addWidget(self.btn_reset)
        btn_row.addWidget(self.btn_correct)
        btn_row.addWidget(self.btn_idle)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self._apply_labels()  # aplica labels.json["es"] (idioma inicial) a todo lo anterior

    def keyPressEvent(self, event):
        # vía de escape sin voz ni ratón, por si el reconocedor falla
        if event.key() == Qt.Key_Escape:
            self.quit_app()
        else:
            super().keyPressEvent(event)

    def _wire_signals(self):
        self.sig_update_pretexto.connect(self._do_update_pretexto)
        self.sig_update_pretexto_formuling.connect(self._do_update_pretexto_formuling)
        self.sig_update_texto.connect(self._do_update_texto)
        self.sig_highlight_texto.connect(self._do_highlight_texto)
        self.sig_update_suggestion.connect(self._do_update_suggestion)
        self.sig_update_escucha.connect(self._do_update_escucha)
        self.sig_clear_suggestion.connect(self._do_clear_suggestion)
        self.sig_clear_pretexto.connect(self._do_clear_pretexto)
        self.sig_show_board_overview.connect(self._do_show_board_overview)
        self.sig_show_board_cell.connect(self._do_show_board_cell)
        self.sig_show_zoom_out.connect(self._do_show_zoom_out)
        self.sig_show_foco.connect(self._do_show_foco)
        self.sig_set_ui_language.connect(self._do_set_ui_language)
        self.sig_set_board_active.connect(self.compass.set_active)
        self.sig_set_board_active.connect(self._do_set_board_active)
        self.sig_quit.connect(self._do_quit)
        self.sig_minimize.connect(self._do_minimize)
        self.sig_restore.connect(self._do_restore)
        self.sig_run_callable.connect(self._do_run_callable)
        self.sig_run_callable_delayed.connect(self._do_run_callable_delayed)
        self.sig_update_state.connect(self._do_update_state)
        self.sig_update_formuling.connect(self._do_update_formuling)
        self.sig_update_position.connect(self._do_update_position)
        self.sig_update_language_combo.connect(self._do_update_language_combo)
        self.sig_update_audio_level.connect(self._do_update_audio_level)
        self.sig_show_help.connect(self._do_show_help)
        self.sig_hide_help.connect(self._do_hide_help)

    # ---------- API pública thread-safe (llamada desde command_router / actions) ----------

    def update_live_text(self, buffer: str, preview: str = ""):
        self.update_pretexto(buffer, preview)

    def update_live_formuling(self, buffer: str, preview: str = ""):
        """Emit live update specifically for formuling mode (no spaces)."""
        self.update_pretexto_formuling(buffer, preview)

    def update_pretexto(self, buffer: str, preview: str = ""):
        self.sig_update_pretexto.emit(buffer, preview)

    def update_pretexto_formuling(self, buffer: str, preview: str = ""):
        self.sig_update_pretexto_formuling.emit(buffer, preview)

    def update_texto(self, text: str):
        """Actualiza el campo Texto (confirmado). Se llama con el
        acumulado completo (router.confirmed_text), no con un delta."""
        self.sig_update_texto.emit(text)

    def highlight_texto(self, enabled: bool):
        """Resalta (o quita el resalte de) el campo Texto -- usado por
        "seleccionar texto" para marcar visualmente que su contenido
        se acaba de copiar/preparar."""
        self.sig_highlight_texto.emit(enabled)

    def update_escucha(self, estado: str):
        """LED de escucha: "activo", "duda" o "dormido".

        Existe porque hacia falta saber si el programa esta despierto SIN
        que diga nada. Hasta ahora la unica forma de enterarse era que
        hablara ("te escucho"), y eso no sirve cuando no quieres que suene
        -- de noche, con gente delante, o grabando.
        """
        self.sig_update_escucha.emit(str(estado))

    def update_suggestion(self, text: str, urgente: bool = False):
        """`urgente=True` para cuando el programa ESPERA que el usuario
        hable ahora.

        Instalando de cero en una máquina sin altavoces se vio el problema:
        el programa pedía el santo y seña hablando, y por pantalla solo lo
        decía esta línea, en 12 píxeles y en cursiva. El aviso estaba, pero
        no se veía; se acabó adivinando por el LED de voz, que indica que
        pasa algo pero no dice qué hacer.

        No es un caso raro de una máquina virtual: le pasa igual a quien
        tenga el volumen bajado, a quien no oiga bien, y a cualquier
        ordenador sin altavoces. Cuando el programa espera que hables tiene
        que notarse SIN oír nada."""
        self.sig_update_suggestion.emit(text, bool(urgente))

    def clear_suggestion(self):
        self.sig_clear_suggestion.emit()

    def clear_pretexto(self):
        self.sig_clear_pretexto.emit()

    # -- ventana de ayuda ("ayuda"/"help", ver command_router._show_help) --

    def show_help(self, title: str, lines, duration_ms: int = 8000):
        """Muestra una ventana flotante con la lista de comandos
        disponibles AHORA (la lista la arma el router a partir de
        commands.json, así que refleja los aliases personalizados) y la
        cierra sola pasados `duration_ms`. Thread-safe: se llama desde
        el hilo de audio/reconocedor."""
        self.sig_show_help.emit(title, list(lines), int(duration_ms))

    def hide_help(self):
        self.sig_hide_help.emit()

    # -- tablero de 100 casillas --

    def show_board_overview(self):
        self.sig_show_board_overview.emit()

    def show_board_cell(self, cell: int, offset_x: int = 0, offset_y: int = 0, zones=None):
        """zones: lista opcional de (dx, dy) -- offsets físicos (mismo
        sistema que offset_x/offset_y) de las zonas clicables detectadas
        por board.detect_zones(); se dibujan numeradas 1..N encima de
        casilla.png (ver _do_show_board_cell)."""
        self.sig_show_board_cell.emit(cell, offset_x, offset_y, list(zones) if zones else [])

    def show_foco(self, offset_x: int = 0, offset_y: int = 0):
        """Muestra foco.png -- la ventana en la que se estaba trabajando,
        recortada a la proporcion del escritorio (ver board.capture_foco) --
        CON el puntero verde en (offset_x, offset_y) respecto al centro.

        Interactiva igual que zoom_out: sin puntero la vista solo servia
        para mirar, y la gracia es poder trabajar dentro de la ventana."""
        self.sig_show_foco.emit(int(offset_x), int(offset_y))

    def show_zoom_out(self, cell: int, offset_x: int = 0, offset_y: int = 0):
        """Muestra zoom_out.png (cuarto de escritorio, 5x5 casillas, sin
        numerar -- ver board.capture_zoom_out) en el panel de tablero,
        CON el puntero verde dibujado en (offset_x, offset_y) respecto
        al centro de esa región -- Fase 2 del rediseño de accesibilidad:
        ya no es una vista pasiva, se puede posicionar el puntero verde
        aquí igual que en la casilla ampliada (ver _do_touch_track, que
        ahora también sigue el ratón/táctil en este modo)."""
        self.sig_show_zoom_out.emit(cell, offset_x, offset_y)

    def get_touch_offset(self):
        """Último (offset_x, offset_y) calculado por el seguimiento
        táctil del círculo verde (ver _do_touch_track), en el mismo
        sistema de coordenadas que board_offset_x/y (píxeles físicos
        respecto al centro de la casilla seleccionada) -- o None si no
        hay casilla ampliada visible ahora mismo, el seguimiento está
        desactivado (modo "cara", sin implementar), o el puntero está
        fuera del área rastreable. Usado por comandos de voz tipo "click
        verde"/"mueve verde" (ver command_router._try_parse_board_action_green)
        para actuar en la posición real del puntero en vez del ajuste
        fino acumulado por voz/compás."""
        return self._touch_offset

    def set_touch_follow_enabled(self, enabled: bool):
        """Activa/desactiva el seguimiento táctil del círculo verde --
        comando de voz "táctil"/"touch" (True) vs "cara"/"face" (False,
        reservado para un futuro seguimiento por cámara/detección facial,
        TODAVÍA NO IMPLEMENTADO). Con False, get_touch_offset() siempre
        devuelve None hasta que se vuelva a activar."""
        self._touch_follow_enabled = enabled
        if not enabled:
            self._touch_offset = None

    def set_touch_callback(self, fn):
        """Registra fn(text: str) -- normalmente router.handle_touch --
        para las selecciones de casilla por toque/clic sobre la vista
        general del tablero (ver manual: "todo el tablero GUI acepta
        entrada táctil"), y también para el compás de 8 direcciones y
        los botones de click izquierdo/derecho."""
        self._touch_callback = fn

    def set_board_active(self, active: bool):
        """Habilita/deshabilita (iconos verdes "Activado" / grises
        "Desactivado") el compás de 8 direcciones -- activo mientras hay
        una casilla seleccionada. Lo llama command_router al seleccionar/
        deseleccionar."""
        self.sig_set_board_active.emit(active)

    def _on_compass_direction(self, word: str):
        if self._touch_callback:
            self._touch_callback(word)

    def _on_touchpad_button(self, command: str):
        """Botones Izquierdo/Derecho de debajo del tablero. Inyectan el
        mismo texto que diría la voz ("click verde"/"click derecho
        verde"), para no duplicar nada de la lógica de acciones."""
        if self._touch_callback:
            self._touch_callback(command)

    def _do_set_board_active(self, active: bool):
        """Los botones de confirmación solo tienen sentido con una casilla
        o un zoom_out activo -- fuera de ahí no hay puntero verde sobre el
        que actuar. Mismo criterio que los pétalos del compás."""
        self.btn_tp_left.setEnabled(bool(active))
        self.btn_tp_right.setEnabled(bool(active))

    def _board_target_width(self) -> int:
        """Ancho ÚTIL de board_view (descontado el borde de 1px de su hoja
        de estilo): a este ancho se escala la imagen, para que llegue de
        verdad de lado a lado."""
        return max(self.board_view.contentsRect().width(), 120)

    def _fit_board_view(self, canvas: QPixmap):
        """Coloca la imagen ya escalada y ajusta el ALTO del widget al
        suyo, para que el QLabel calce exactamente con ella. Sin esto
        quedaría un margen muerto arriba y abajo (AlignCenter), que además
        obligaba a _do_touch_track a compensarlo (pad_y) y descuadraba la
        fracción que reporta ClickableImageLabel al tocar."""
        chrome = self.board_view.height() - self.board_view.contentsRect().height()
        target_h = canvas.height() + max(chrome, 0)
        if self.board_view.minimumHeight() != target_h or self.board_view.maximumHeight() != target_h:
            self.board_view.setFixedHeight(target_h)
        self.board_view.setText("")
        self.board_view.setPixmap(canvas)

    def _reset_board_view_height(self):
        """Vuelve al alto suelto (sin imagen: placeholder)."""
        self.board_view.setMinimumHeight(self._BOARD_PLACEHOLDER_H)
        self.board_view.setMaximumHeight(16777215)

    def _dentro_de_pantalla(self, x: int, y: int, w: int, h: int):
        """Recorta (x, y) para que la ventana no se salga de la pantalla.

        Sin esto, un cálculo pensado para un monitor grande deja la ventana
        medio fuera en una pantalla pequeña: `reposition_for_board` la pone
        al 52% de la altura, y con 768 píxeles de alto una ventana de 700
        se va por debajo del borde. Aparece en cuanto se sale del monitor
        de siempre -- una VM, una Raspberry Pi, un portátil."""
        # La pantalla DONDE ESTA la ventana, no siempre la principal: con
        # dos monitores, recortar contra el principal la empujaba al otro.
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return x, y
        geo = screen.availableGeometry()
        # EL MARCO CUENTA. w y h son del CONTENIDO, pero lo que ocupa la
        # ventana en pantalla incluye la barra de titulo y los bordes que
        # pone el sistema. Sin sumarlos, la ventana "recortada" seguia
        # asomando por abajo lo que mide esa barra -- en Windows al 175%,
        # unos 30 px. Antes de mostrarse el marco aun no existe y la
        # diferencia es 0, que es lo correcto.
        extra_w = max(0, self.frameGeometry().width() - self.width())
        extra_h = max(0, self.frameGeometry().height() - self.height())
        w, h = w + extra_w, h + extra_h
        x = max(geo.x(), min(x, geo.x() + geo.width() - w))
        y = max(geo.y(), min(y, geo.y() + geo.height() - h))
        return x, y

    def centrar_en_pantalla(self):
        """Deja la ventana en el centro del escritorio.

        POR QUE HACE FALTA
        ------------------
        Sin esto la ventana aparece donde quiera el gestor de ventanas, que
        no es lo mismo en KDE, en Windows ni en una maquina virtual recien
        instalada -- y en algunas sale pegada a una esquina o a medias fuera.
        Quien usa esto por accesibilidad no tiene por que empezar arrastrando
        una ventana con el raton.

        AQUI NO HAY CONVERSION DE COORDENADAS, Y ES A PROPOSITO
        ------------------------------------------------------
        Todo el lio de hoy (captura en fisicos, ydotool en logicos) no toca
        en este sitio: `availableGeometry()` y `move()` hablan las dos el
        MISMO idioma, el logico de Qt. Asi que centrar sale bien en
        cualquier resolucion y con cualquier escalado sin dividir por nada,
        y vale igual en Linux y en Windows.

        Se usa `availableGeometry` y no `geometry`: la primera descuenta el
        panel de KDE o la barra de tareas de Windows, asi que "centrado" es
        centrado en el sitio utilizable, no debajo de la barra.
        """
        pantalla = self.screen() or QApplication.primaryScreen()
        if pantalla is None:
            return
        geo = pantalla.availableGeometry()
        self.adjustSize()
        w, h = self.width(), self.height()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + (geo.height() - h) // 2
        self.move(*self._dentro_de_pantalla(x, y, w, h))

    def reposition_for_board(self, col: int):
        """Reposiciona la ventana al lado simétrico opuesto a la columna
        (unidad) de la casilla seleccionada -- ver manual, Sección 1 Paso
        3: unidad 1-5 -> ventana a la derecha; unidad 6-10 -> a la
        izquierda; siempre un poco por debajo del centro."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.adjustSize()
        w, h = max(self.width(), 420), max(self.height(), 260)
        y = geo.y() + int(geo.height() * 0.52)
        if col <= 5:
            x = geo.x() + geo.width() - w - 24
        else:
            x = geo.x() + 24
        self.move(*self._dentro_de_pantalla(x, y, w, h))

    # -- idioma de la interfaz (i18n, labels.json) --

    def set_ui_language(self, lang: str):
        self.sig_set_ui_language.emit(lang)

    # -- alias retrocompatibles (por si algún módulo externo aún los usa) --
    def clear_text(self):
        self.clear_pretexto()

    def quit_app(self):
        self.sig_quit.emit()

    def apartar_ventana(self):
        self.sig_minimize.emit()

    def subir_ventana(self):
        self.sig_restore.emit()

    def _pintar_seleccion(self, painter, canvas, sx, sy, mx, my):
        """Dibuja el recuadro de lo que se va a seleccionar.

        POR QUE HACE FALTA, y lo dijo pipataki: sin esto se elige a ciegas. Las
        dos coordenadas se guardan y no pasa nada en el sistema hasta el
        final -- que es lo correcto -- pero entonces no hay forma de ver
        QUE se va a seleccionar hasta que ya esta hecho.

        Es el mismo criterio que el punto verde: lo que se ve es una marca
        sobre la CAPTURA, no sobre el escritorio real. No tiene que ser
        exacta; tiene que dejar claro que trozo abarca.

        Vive en un solo metodo porque las tres vistas (casilla, cuarto de
        pantalla y foco) pintan igual -- `centro + offset * escala` -- y
        tres copias se habrian separado a la primera.
        """
        if self._seleccion_origen_offset is None:
            return
        # Solo si el origen es de ESTA vista: un recuadro dibujado con las
        # coordenadas de otra vista senalaria un trozo que no es.
        if self._seleccion_origen_vista != self._board_mode:
            return
        if (self._board_mode in ("cell", "zoom_out")
                and self._seleccion_origen_celda != self._board_cell):
            return
        ox, oy = self._seleccion_origen_offset
        x1 = canvas.width() / 2 + ox * sx
        y1 = canvas.height() / 2 + oy * sy
        rect = QRectF(min(x1, mx), min(y1, my), abs(mx - x1), abs(my - y1))
        painter.fillRect(rect, QColor(241, 196, 15, 60))
        pluma = QPen(QColor(241, 196, 15), 2, Qt.DashLine)
        painter.setPen(pluma)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(rect)
        # y una marca en el origen, para saber por donde se empezo
        painter.setBrush(QColor(241, 196, 15))
        painter.setPen(QPen(QColor(80, 60, 0), 1))
        painter.drawEllipse(QPointF(x1, y1), 5, 5)

    def set_seleccion_origen(self, offset, vista, celda):
        """Apunta el origen para dibujarlo. offset=None lo borra.

        Por el hilo principal, como todo lo que acaba repintando: quien
        llama es el router, que corre en el hilo del reconocedor.
        """
        def _do():
            self._seleccion_origen_offset = offset
            self._seleccion_origen_vista = vista
            self._seleccion_origen_celda = celda
            self._repintar_vista()
        self.run_on_main_thread(_do)

    def _repintar_vista(self):
        """Vuelve a pintar la vista actual, para que se vea el recuadro."""
        try:
            if self._board_mode == "cell" and self._board_cell:
                self._do_show_board_cell(self._board_cell,
                                         self._ultimo_offset[0],
                                         self._ultimo_offset[1],
                                         self._board_zones)
            elif self._board_mode == "foco":
                self._do_show_foco(*self._ultimo_offset)
            elif self._board_mode == "zoom_out" and self._board_cell:
                self._do_show_zoom_out(self._board_cell, *self._ultimo_offset)
        except Exception as exc:
            print(f"[gui] no se pudo repintar la vista: {exc!r}")

    def _color_puntero(self):
        """Verde de siempre, AMARILLO mientras hay una seleccion a medias.

        El color es la unica senal de que hay un origen fijado esperando su
        final. Sin ella, quien fije un origen y se distraiga no tiene forma
        de saber que el programa esta esperando algo -- y un estado
        invisible que espera es de las cosas que dejan colgado.

        Vive en un solo metodo porque el punto se pinta en TRES sitios
        (casilla, cuarto de pantalla y foco): tres copias del color se
        habrian separado a la primera.
        """
        if self._seleccion_pendiente:
            return QColor(241, 196, 15)      # amarillo
        return QColor(46, 204, 113)          # el verde de siempre

    def set_seleccion_pendiente(self, pendiente: bool):
        """Enciende o apaga el amarillo. Lo llama el router.

        Por el hilo principal: quien llama es el router, que corre en el
        hilo del reconocedor, y repintar desde ahi es corrupcion de memoria
        -- ya nos costo un segfault el 5-sep.
        """
        def _do():
            self._seleccion_pendiente = bool(pendiente)
            self.update()
        self.run_on_main_thread(_do)

    def alternar_monitor(self):
        """Muestra u oculta la ventana. Es el comando de voz "monitor".

        SOLO EN MODO SERVICIO. Con la ventana normal no hace nada, que es
        lo que hacía hasta ahora: este método no existía en gui.GUI y el
        router lo llama con getattr(..., None). Si actuara siempre, decir
        "monitor" escondería la ventana a quien no ha pedido nada de eso.
        """
        if not self._modo_servicio:
            return
        # POR EL HILO PRINCIPAL, Y NO ES OPCIONAL.
        #
        # A esto lo llama el router, que corre en el hilo del RECONOCEDOR.
        # Hacer show()/hide()/raise_() desde ahi es tocar widgets fuera del
        # hilo de Qt: colgo el programa el 6-sep-2026 y hubo que matarlo.
        # En el log se ve clavado -- "final reconocido: 'monitor'" y despues
        # nada, ni "panel mostrado" ni "panel oculto".
        #
        # Asi es como lo hace "subir" (raise_gui -> sig_restore.emit), que
        # lleva funcionando desde siempre.
        self.run_on_main_thread(self._do_alternar_monitor)

    def _do_alternar_monitor(self):
        if self.isVisible():
            self.ocultar_panel()
        else:
            self.mostrar_panel()

    def _pedir_encima_a_kwin(self, encima: bool):
        """Le pide a KWin que deje (o quite) la ventana por encima.

        EN SU PROPIO HILO: son dos llamadas a kdotool, que habla con KWin
        por D-Bus y puede tardar o atascarse. Hacerlas en el hilo de la
        interfaz la dejaria congelada mientras tanto -- y si kdotool no
        contesta, congelada hasta que venza el plazo.

        No toca ningun widget, solo manda ordenes a KWin, asi que puede
        correr fuera del hilo de Qt sin problema.
        """
        titulo = self.windowTitle() or "VoiceController"

        def _faena():
            try:
                import actions as _actions
                _actions.poner_ventana_encima(titulo, encima)
            except Exception as exc:
                print(f"[gui] no se pudo hablar con KWin: {exc!r}")

        try:
            import threading
            threading.Thread(target=_faena, name="kwin-encima",
                             daemon=True).start()
        except Exception as exc:
            print(f"[gui] no se pudo lanzar la peticion a KWin: {exc!r}")

    def _empujon_arriba(self):
        """Sube la ventana delante de todo SIN dejarla clavada encima.

        "Encima" y "quitar encima", EN ESE ORDEN Y EN EL MISMO HILO. Antes
        eran dos llamadas a _pedir_encima_a_kwin, cada una en su hilo,
        lanzadas una detras de otra: nada garantizaba que llegaran en orden,
        y si el "quitar" se adelantaba, la ventana se quedaba "siempre
        encima" para siempre. Vale para KWin y para Windows (ver
        actions.poner_ventana_encima).
        """
        titulo = self.windowTitle() or "VoiceController"

        def _faena():
            try:
                import actions as _actions
                _actions.poner_ventana_encima(titulo, True)
                _actions.poner_ventana_encima(titulo, False)
            except Exception as exc:
                print(f"[gui] no se pudo subir la ventana: {exc!r}")

        try:
            import threading
            threading.Thread(target=_faena, name="empujon-arriba",
                             daemon=True).start()
        except Exception as exc:
            print(f"[gui] no se pudo lanzar el empujon: {exc!r}")

    def mostrar_panel(self):
        """Ensena la ventana ENCIMA de lo que haya, sin tocar nada mas.

        NO se usa bring_to_front(), y esa es la correccion del 6-sep-2026.
        Aquel MINIMIZA la ventana activa para colarse encima -- que en el
        modo con ventana tiene sentido ("subir" es una peticion de ver el
        GUI), pero en modo servicio hace desaparecer del escritorio la
        ventana en la que estabas trabajando. Lo conto pipataki: pedir el panel
        no puede llevarse por delante lo que tienes abierto.

        Tampoco se activa la ventana: activateWindow() se lleva el FOCO DEL
        TECLADO, y con eso decir "guardar" mandaria el ctrl+s a
        VoiceController en vez de a tu programa (ya paso una vez, ver
        traer_al_frente_suave).

        Asi que: mostrar, subir en el orden de apilamiento, y pedirle a KWin
        que la deje encima mientras este visible -- porque bajo Wayland
        raise_() solo no basta contra una ventana maximizada. La marca se
        quita al ocultarla, para no dejar el panel volando por encima de
        todo el resto de la sesion.
        """
        try:
            self.show()
            self.raise_()
        except Exception as exc:
            print(f"[gui] error mostrando el panel: {exc!r}")
        self._pedir_encima_a_kwin(True)
        print("[gui] panel mostrado, encima y sin tocar tus ventanas")

    def ocultar_panel(self):
        """Esconde la ventana y le quita la marca de "siempre encima"."""
        self._pedir_encima_a_kwin(False)
        try:
            self.hide()
        except Exception as exc:
            print(f"[gui] error ocultando el panel: {exc!r}")
        print("[gui] panel oculto")

    def ocultar_para_captura(self):
        """Salir de la foto antes de una captura. AQUÍ NO HACE FALTA NADA.

        En modo ventana, quien llama ya ha hecho send_to_back() y la
        ventana queda por debajo: no sale en la captura. Existe para que
        el modo servicio pueda hacer lo suyo -- allí no hay ventana que
        bajar, pero SÍ hay vcs encima del escritorio, y esos sí
        salían en la foto (ver servicio.ocultar_para_captura).

        No se reutilizó send_to_back() para esto porque significa otra
        cosa: "apártate pero sigue visible", y se usa también antes de
        cada clic. Convertirlo en "escóndete" haría desaparecer los
        vcs en cada clic, y nadie los devolvería.
        """
        pass

    def restaurar_tras_captura(self):
        """La pareja de ocultar_para_captura(). Aquí tampoco hace falta."""
        pass

    def run_on_main_thread(self, fn):
        """Ejecuta fn() en el hilo principal de Qt (asíncrono: no bloquea
        a quien llama). Usar para CUALQUIER cosa que toque grid_vc."""
        self.sig_run_callable.emit(fn)

    def run_on_main_thread_delayed(self, fn, delay_ms: int = 300):
        """Como run_on_main_thread(), pero espera delay_ms antes de
        ejecutar fn(), para dar tiempo a que termine una animación previa
        (p.ej. el minimizado de esta ventana) antes de que grid_vc
        capture pantalla."""
        self.sig_run_callable_delayed.emit(fn, delay_ms)

    def update_state_indicator(self, state: str):
        """state: 'IDLE' o 'DICTATING'."""
        self.sig_update_state.emit(state)

    def set_idle_standby_callback(self, fn):
        """fn() -- normalmente router.check_idle_standby, llamada desde el
        temporizador de pausas."""
        self._idle_standby_check = fn

    def set_pause_callback(self, fn):
        """Registra fn() -- normalmente router.check_pause_suggestion --
        para que se llame UNA vez por cada pausa detectada mientras se
        dicta (ver config.PAUSE_SUGGESTION_MS). fn() se ejecuta ya en el
        hilo de Qt (el mismo que corre este temporizador)."""
        self._pause_callback = fn

    def update_position_label(self, cell: int, subcell: int):
        self.last_cell = cell
        self.last_subcell = subcell
        self.sig_update_position.emit(cell, subcell)
        # NUEVO: guardar como última posición
        self._last_position = (cell, subcell)


    def set_last_position(self, cell: int, subcell: int):
        """Guarda la última posición visitada."""
        self._last_position = (cell, subcell)

    def get_last_position(self) -> tuple | None:
        """Retorna la última posición visitada, o None si no hay."""
        return self._last_position

    def update_language_combo_label(self, combo_label: str):
        self.sig_update_language_combo.emit(combo_label)

    def update_audio_level(self, is_silent: bool, rms: float):
        """state del VAD ligero: is_silent True cuando no se detecta voz
        (LED apagado); False mientras hay energía suficiente (LED verde)."""
        self.sig_update_audio_level.emit(is_silent, rms)

    def set_manual_action_callback(self, fn):
        """Conecta los botones Enter/Reset/Idle y el menú de la bandeja a
        un callback real (normalmente router.manual_action). Sin esto los
        botones no hacen nada (on_manual_action se pasa como None al crear
        la GUI, antes de que exista el router)."""
        self._on_manual_action = fn

    # ---------- slots reales, ejecutados en el hilo de Qt ----------

    def _register_activity(self):
        """Marca que acaba de haber actividad de texto: reinicia el reloj
        de pausa y permite que se vuelva a evaluar una sugerencia la
        próxima vez que haya un hueco de silencio."""
        self._last_activity_ts = time.monotonic()
        self._pause_notified = False

    def _do_update_pretexto(self, buffer: str, preview: str):
        shown = (buffer + " " + preview).strip() if preview else buffer
        self.pretexto_label.setText(shown)
        self._register_activity()

    def _do_update_pretexto_formuling(self, buffer: str, preview: str):
        # concat without inserting extra space: formuling mode shows letters together
        shown = (buffer + preview).replace(" ", " ")
        self.pretexto_label.setText(shown)
        self._register_activity()

    def _do_update_texto(self, text: str):
        self.texto_label.setText(text)
        self.texto_label.setStyleSheet(self._texto_style_normal)

    def _do_highlight_texto(self, enabled: bool):
        self.texto_label.setStyleSheet(
            self._texto_style_highlight if enabled else self._texto_style_normal
        )

    def _do_update_escucha(self, estado: str):
        color, texto = {
            "dormido": (LED_OFF,  "En espera: solo atiendo al santo y seña"),
            "duda":    (LED_DUDA, "Despierto, pero la última voz no era la tuya"),
        }.get(estado, (LED_ON, "Despierto y te reconozco"))
        self.led_escucha.setStyleSheet(f"background: {color}; {LED_STYLE}")
        self.led_escucha.setToolTip(texto)

    def _do_update_suggestion(self, text: str, urgente: bool = False):
        self.suggestion_label.setText(text)
        self.suggestion_label.setVisible(bool(text))
        if urgente and text:
            if not self._micro_listo:
                # Todavía no escucha: se guarda el aviso y se dice la verdad.
                self._aviso_urgente_pendiente = text
                self.suggestion_label.setText("⏳ Espera, estoy arrancando...")
            self._parpadeo_encendido = True
            self.suggestion_label.setStyleSheet(self._estilo_sugerencia_urgente)
            self._parpadeo_timer.start()
        else:
            self._parpadeo_timer.stop()
            self.suggestion_label.setStyleSheet(self._estilo_sugerencia)

    def _parpadear_sugerencia(self):
        self._parpadeo_encendido = not self._parpadeo_encendido
        self.suggestion_label.setStyleSheet(
            self._estilo_sugerencia_urgente if self._parpadeo_encendido
            else self._estilo_sugerencia_urgente_apagado
        )

    def _do_clear_suggestion(self):
        self._aviso_urgente_pendiente = None
        self._parpadeo_timer.stop()
        self.suggestion_label.setStyleSheet(self._estilo_sugerencia)
        self.suggestion_label.setText("")
        self.suggestion_label.hide()

    def _do_clear_pretexto(self):
        self.pretexto_label.setText("")

    # -- tablero: dibujado --

    def _on_board_tap(self, fx: float, fy: float):
        """Toque/clic sobre self.board_view. Solo activo en la vista
        general (seleccionar casilla); en la vista de casilla ampliada no
        hace nada por ahora (usa voz/botones para el ajuste fino)."""
        if self._board_mode != "overview" or not self._touch_callback:
            return
        cell = board.cell_from_fraction(fx, fy)
        self._touch_callback(str(cell))

    def _do_show_help(self, title: str, lines, duration_ms: int):
        """Ventana de ayuda: se crea la primera vez y se reutiliza
        después. Es una ventana APARTE (Qt.Tool + FramelessWindowHint)
        en vez de un campo más del GUI porque la lista puede ser larga y
        no debe descolocar la ventana principal ni tapar el tablero de
        forma permanente. Con WA_ShowWithoutActivating, igual que la
        ventana principal, para no robarle el foco a la aplicación en la
        que se esté trabajando (ver __init__)."""
        if self._help_popup is None:
            popup = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
            popup.setWindowTitle("VoiceController — ayuda")
            lay = QVBoxLayout(popup)
            lay.setContentsMargins(14, 12, 14, 12)
            lay.setSpacing(6)
            self._help_title = QLabel("")
            self._help_title.setStyleSheet("font-weight: bold; font-size: 13px;")
            # Dos columnas: con ~40 comandos en idle, una sola columna se
            # sale por abajo de una pantalla de portátil. La segunda se
            # oculta cuando la lista es corta (ver más abajo).
            body_row = QHBoxLayout()
            body_row.setSpacing(18)
            self._help_body = QLabel("")
            self._help_body_2 = QLabel("")
            for lbl in (self._help_body, self._help_body_2):
                lbl.setTextFormat(Qt.PlainText)
                lbl.setStyleSheet("border: none;")
                lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
                body_row.addWidget(lbl)
            lay.addWidget(self._help_title)
            lay.addLayout(body_row)
            popup.setStyleSheet(
                "QWidget { background: #1e1e1e; color: #f0f0f0;"
                " border: 2px solid #4c9aff; border-radius: 8px; }"
            )
            self._help_popup = popup
            self._help_timer = QTimer(popup)
            self._help_timer.setSingleShot(True)
            self._help_timer.timeout.connect(self._do_hide_help)

        self._help_title.setText(title)
        lines = list(lines)
        if len(lines) > self._HELP_MAX_ROWS:
            half = (len(lines) + 1) // 2
            self._help_body.setText("\n".join(lines[:half]))
            self._help_body_2.setText("\n".join(lines[half:]))
            self._help_body_2.show()
        else:
            self._help_body.setText("\n".join(lines) if lines else "(sin comandos que mostrar)")
            self._help_body_2.hide()
        # activate() fuerza a recalcular el layout ANTES de medir: sin
        # esto, al reutilizar la ventana para una lista más corta (p.ej.
        # dictado tras idle) se quedaba con el alto/ancho de la anterior.
        self._help_popup.layout().activate()
        self._help_popup.resize(self._help_popup.sizeHint())
        # Centrada sobre la ventana principal, sin salirse de la pantalla
        try:
            geo = self.frameGeometry()
            size = self._help_popup.sizeHint()
            x = geo.center().x() - size.width() // 2
            y = geo.center().y() - size.height() // 2
            screen = self.screen().availableGeometry() if self.screen() else None
            if screen is not None:
                x = min(max(x, screen.left() + 8), screen.right() - size.width() - 8)
                y = min(max(y, screen.top() + 8), screen.bottom() - size.height() - 8)
            self._help_popup.move(x, y)
        except Exception as exc:
            print(f"[gui] no se pudo colocar la ventana de ayuda: {exc!r}")
        self._help_popup.show()
        self._help_popup.raise_()
        self._help_timer.start(max(1000, int(duration_ms)))

    def _do_hide_help(self):
        if self._help_popup is not None:
            self._help_popup.hide()

    def _do_show_board_overview(self):
        self._board_mode = "overview"
        self._anotar_vista("overview")
        self._board_cell = None
        self._board_canvas_size = None
        self._board_scale = None
        self._touch_offset = None
        if not TABLERO_FILE.exists():
            self.board_view.setPixmap(QPixmap())
            self.board_view.setText(self._labels_all[self._ui_lang]["board_placeholder"])
            self._reset_board_view_height()
            return
        base = QPixmap(str(TABLERO_FILE))
        if base.isNull():
            return
        canvas = base.scaledToWidth(self._board_target_width(), Qt.SmoothTransformation)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = canvas.width(), canvas.height()
        cell_w, cell_h = w / board.COLS, h / board.ROWS
        pen = QPen(QColor(0, 220, 255, 170))
        pen.setWidth(1)
        painter.setPen(pen)
        font = QFont("Sans Serif", max(6, int(min(cell_w, cell_h) * 0.32)))
        painter.setFont(font)
        for row in range(1, board.ROWS + 1):
            for col in range(1, board.COLS + 1):
                rect = QRectF((col - 1) * cell_w, (row - 1) * cell_h, cell_w, cell_h)
                painter.drawRect(rect)
                painter.setPen(QColor(180, 240, 255, 220))
                painter.drawText(rect, Qt.AlignCenter, str(board.cell_from_row_col(row, col)))
                painter.setPen(pen)
        painter.end()
        self._fit_board_view(canvas)

    def _do_show_board_cell(self, cell: int, offset_x: int, offset_y: int, zones=None):
        self._ultimo_offset = (offset_x, offset_y)
        self._board_mode = "cell"
        self._anotar_vista("cell")
        self._board_cell = cell
        self._board_zones = list(zones) if zones else []
        if not CASILLA_FILE.exists():
            return
        orig = QPixmap(str(CASILLA_FILE))
        if orig.isNull() or orig.width() == 0 or orig.height() == 0:
            return
        canvas = orig.scaledToWidth(self._board_target_width(), Qt.SmoothTransformation)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        sx = canvas.width() / orig.width()
        sy = canvas.height() / orig.height()
        # se guardan para poder invertir la conversión en _do_touch_track
        # (posición del puntero DENTRO de esta imagen -> offset_x/offset_y
        # en las mismas unidades que recibe este método) sin tener que
        # recargar/reescalar casilla.png en cada sondeo del temporizador
        self._board_canvas_size = (canvas.width(), canvas.height())
        self._board_scale = (sx, sy)

        # zonas clicables autodetectadas (board.detect_zones): numeradas
        # 1..N, para poder decir "click 1", "mover 2"... ver manual y
        # command_router._try_parse_board_zone_action.
        if zones:
            zone_font = QFont("Sans Serif", 9, QFont.Bold)
            painter.setFont(zone_font)
            for idx, (zx, zy) in enumerate(zones, start=1):
                px = canvas.width() / 2 + zx * sx
                py = canvas.height() / 2 + zy * sy
                painter.setBrush(QColor(255, 165, 0, 220))
                painter.setPen(QPen(QColor(60, 30, 0), 1))
                painter.drawEllipse(QPointF(px, py), 9, 9)
                painter.setPen(QColor(20, 10, 0))
                painter.drawText(QRectF(px - 9, py - 9, 18, 18), Qt.AlignCenter, str(idx))

        mx = canvas.width() / 2 + offset_x * sx
        my = canvas.height() / 2 + offset_y * sy
        self._pintar_seleccion(painter, canvas, sx, sy, mx, my)
        painter.setBrush(self._color_puntero())
        painter.setPen(QPen(QColor(10, 40, 20), 1))
        painter.drawEllipse(QPointF(mx, my), 7, 7)
        painter.end()
        self._fit_board_view(canvas)

    def _anotar_vista(self, modo: str) -> None:
        """Deja escrito que vista se esta ensenando, para que otro proceso
        pueda saberlo (ver tools/guardar_capturas.py).

        Un fichero de texto y no una variable porque quien lo lee es un
        programa aparte. Si falla no pasa nada: es informativo."""
        try:
            ESTADO_VISTA_FILE.parent.mkdir(parents=True, exist_ok=True)
            ESTADO_VISTA_FILE.write_text(modo + "\n", encoding="utf-8")
        except Exception:
            pass

    def _do_show_foco(self, offset_x: int = 0, offset_y: int = 0):
        self._ultimo_offset = (offset_x, offset_y)
        self._board_mode = "foco"
        self._anotar_vista("foco")
        self._board_cell = None
        self._touch_offset = (offset_x, offset_y)
        if not FOCO_FILE.exists():
            self.board_view.setPixmap(QPixmap())
            self.board_view.setText(
                self._labels_all[self._ui_lang].get("board_placeholder", ""))
            self._board_canvas_size = None
            self._board_scale = None
            self._reset_board_view_height()
            return
        orig = QPixmap(str(FOCO_FILE))
        if orig.isNull() or orig.width() == 0 or orig.height() == 0:
            return
        canvas = orig.scaledToWidth(self._board_target_width(), Qt.SmoothTransformation)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        sx = canvas.width() / orig.width()
        sy = canvas.height() / orig.height()
        self._board_canvas_size = (canvas.width(), canvas.height())
        self._board_scale = (sx, sy)

        mx = canvas.width() / 2 + offset_x * sx
        my = canvas.height() / 2 + offset_y * sy
        self._pintar_seleccion(painter, canvas, sx, sy, mx, my)
        painter.setBrush(self._color_puntero())
        painter.setPen(QPen(QColor(10, 40, 20), 1))
        painter.drawEllipse(QPointF(mx, my), 7, 7)
        painter.end()
        self.board_view.setText("")
        self._fit_board_view(canvas)

    def _do_show_zoom_out(self, cell: int, offset_x: int, offset_y: int):
        self._ultimo_offset = (offset_x, offset_y)
        """Muestra zoom_out.png (cuarto de escritorio, ver
        board.capture_zoom_out) SIN numerar ni dibujar rejilla -- solo
        la imagen escalada -- pero SÍ con el puntero verde en
        (offset_x, offset_y) respecto al centro de esa región (Fase 2:
        interactivo, igual que la casilla ampliada). Guarda
        _board_canvas_size/_board_scale igual que _do_show_board_cell,
        para que _do_touch_track pueda invertir la conversión."""
        self._board_mode = "zoom_out"
        self._anotar_vista("zoom_out")
        self._board_cell = cell
        self._touch_offset = (offset_x, offset_y)
        if not ZOOM_OUT_FILE.exists():
            self.board_view.setPixmap(QPixmap())
            self.board_view.setText(self._labels_all[self._ui_lang].get("board_placeholder", ""))
            self._board_canvas_size = None
            self._board_scale = None
            self._reset_board_view_height()
            return
        orig = QPixmap(str(ZOOM_OUT_FILE))
        if orig.isNull() or orig.width() == 0 or orig.height() == 0:
            return
        canvas = orig.scaledToWidth(self._board_target_width(), Qt.SmoothTransformation)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        sx = canvas.width() / orig.width()
        sy = canvas.height() / orig.height()
        self._board_canvas_size = (canvas.width(), canvas.height())
        self._board_scale = (sx, sy)

        mx = canvas.width() / 2 + offset_x * sx
        my = canvas.height() / 2 + offset_y * sy
        self._pintar_seleccion(painter, canvas, sx, sy, mx, my)
        painter.setBrush(self._color_puntero())
        painter.setPen(QPen(QColor(10, 40, 20), 1))
        painter.drawEllipse(QPointF(mx, my), 7, 7)
        painter.end()
        self._fit_board_view(canvas)

    def _do_touch_track(self):
        """Llamado cada config.TOUCH_TRACK_POLL_MS por
        self._touch_track_timer. El círculo verde debe seguir al puntero
        SOLO cuando el puntero está DENTRO de la imagen que el propio
        GUI está mostrando en board_view (la casilla ampliada) -- NO
        cuando está sobre la región correspondiente del escritorio real.
        La interacción es enteramente sobre la miniatura que ves en la
        ventana de VoiceController: mueves el ratón/dedo encima de esa
        imagen, y el círculo verde se coloca ahí -- el movimiento es
        relativo A ESA IMAGEN, no al escritorio. Si el puntero está
        fuera de esa imagen, NO se actualiza nada (se mantiene el último
        offset calculado, no se pierde ni se "improvisa" un valor fuera
        de contexto).

        Para saber si el puntero está dentro, se compara su posición
        GLOBAL (QCursor.pos(), coordenadas lógicas de Qt) contra el
        rectángulo GLOBAL que ocupa de verdad el canvas dibujado dentro
        de board_view (que puede ser más pequeño que el QLabel en sí,
        centrado por AlignCenter) -- ambos valores están en el MISMO
        sistema de coordenadas (lógicas de Qt), así que aquí NO hace
        falta ninguna conversión física/lógica (a diferencia de
        fire_board_action, que si acaba tocando el escritorio real, sí
        la necesita más adelante vía board.cell_absolute_position).

        Una vez dentro, se invierte exactamente la misma fórmula que usa
        _do_show_board_cell/_do_show_zoom_out para dibujar el marcador
        (mx = canvas_w/2 + offset_x*sx), despejando offset_x/offset_y --
        así el resultado queda en las mismas unidades (píxeles reales)
        que espera fire_board_action/board_offset_x/y (modo "cell") o
        actions.fire_zoom_out_action (modo "zoom_out", Fase 2 del
        rediseño de accesibilidad -- mismo patrón, aplicado también a
        la vista de cuarto de escritorio, no solo a la casilla)."""
        # "foco" no tiene casilla asociada -- su region es la de la ventana,
        # no la de la rejilla -- asi que se exige _board_cell solo a los
        # otros dos modos.
        if self._board_mode not in ("cell", "zoom_out", "foco"):
            return
        if self._board_mode != "foco" and self._board_cell is None:
            return
        if not self._touch_follow_enabled:
            return
        if self._board_canvas_size is None or self._board_scale is None:
            return
        try:
            canvas_w, canvas_h = self._board_canvas_size
            sx, sy = self._board_scale
            if sx <= 0 or sy <= 0 or canvas_w <= 0 or canvas_h <= 0:
                return
            label_topleft = self.board_view.mapToGlobal(QPoint(0, 0))
            # el canvas se centra dentro del QLabel (AlignCenter) -- si es
            # más pequeño que el QLabel, hay un margen a cada lado que
            # hay que tener en cuenta para saber dónde empieza de verdad
            pad_x = (self.board_view.width() - canvas_w) / 2
            pad_y = (self.board_view.height() - canvas_h) / 2
            canvas_left = label_topleft.x() + pad_x
            canvas_top = label_topleft.y() + pad_y
            pos = QCursor.pos()
            local_x = pos.x() - canvas_left
            local_y = pos.y() - canvas_top
            if not (0 <= local_x <= canvas_w and 0 <= local_y <= canvas_h):
                return  # puntero fuera de la imagen mostrada -- no se toca nada
            raw_x = (local_x - canvas_w / 2) / sx
            raw_y = (local_y - canvas_h / 2) / sy
            if self._board_mode == "foco":
                ox, oy = board.foco_clamp_offset(raw_x, raw_y)
            elif self._board_mode == "zoom_out":
                ox, oy = board.zoom_out_clamp_offset(self._board_cell, raw_x, raw_y)
            else:
                ox, oy = board.clamp_offset(self._board_cell, round(raw_x), round(raw_y))
        except Exception as exc:
            print(f"[gui] error en seguimiento táctil: {exc!r}")
            return
        if self._touch_offset == (ox, oy):
            return  # sin cambios, no repintar de más
        self._touch_offset = (ox, oy)
        if self._board_mode == "foco":
            self._do_show_foco(ox, oy)
        elif self._board_mode == "zoom_out":
            self._do_show_zoom_out(self._board_cell, ox, oy)
        else:
            self._do_show_board_cell(self._board_cell, ox, oy, self._board_zones)

    # -- idioma de la interfaz --

    def _apply_labels(self):
        L = self._labels_all.get(self._ui_lang, self._labels_all.get("es", {}))
        get = lambda k, default: L.get(k, default)
        self.btn_enter.setText(f"📥 {get('btn_enter', 'Entrar')}")
        self.btn_reset.setText(f"🗑 {get('btn_reset', 'Borrar')}")
        self.btn_correct.setText(f"🩹 {get('btn_correct', 'Corregir')}")
        self.btn_idle.setText(f"🎧 {get('btn_idle', 'Escucha')}")
        self.btn_close.setText(f"✕ {get('btn_close', 'Cerrar')}")
        self.btn_copy_texto.setText(f"📋 {get('btn_copy', 'Copiar')}")
        self.btn_paste_texto.setText(f"📤 {get('btn_paste', 'Pegar')}")
        self.btn_select_texto.setText(f"🖱 {get('btn_select', 'Seleccion')}")
        self.btn_clear_texto.setText(f"🗑 {get('btn_clear', 'Vaciar')}")
        self.texto_row_label.setText(get("texto_label", "Texto:"))
        if self._board_mode == "overview" and (self.board_view.pixmap() is None or self.board_view.pixmap().isNull()):
            self.board_view.setText(get("board_placeholder", ""))

    def _do_set_ui_language(self, lang: str):
        if lang not in self._labels_all:
            lang = "es"
        self._ui_lang = lang
        self._apply_labels()

    def _check_pause(self):
        # Standby por inactividad (ver command_router.check_idle_standby).
        # Se cuelga del temporizador de pausas que YA existía en vez de
        # crear otro: corre en el hilo de Qt y se dispara cada
        # config.PAUSE_POLL_MS, que es de sobra para algo que mide
        # minutos.
        fn = getattr(self, "_idle_standby_check", None)
        if fn is not None:
            try:
                fn()
            except Exception as exc:
                print(f"[gui] error comprobando el standby por inactividad: {exc!r}")

        """Llamado cada config.PAUSE_POLL_MS por self._pause_check_timer."""
        if self._current_state != "DICTATING" or self._pause_notified:
            return
        if not self._pause_callback:
            return
        elapsed_ms = (time.monotonic() - self._last_activity_ts) * 1000
        if elapsed_ms >= config.PAUSE_SUGGESTION_MS:
            self._pause_notified = True
            try:
                self._pause_callback()
            except Exception as exc:
                print(f"[gui] error en pause_callback: {exc!r}")

    def _maybe_capture_vc_snapshot(self):
        """Llamado cada config.VC_SNAPSHOT_POLL_MS por
        self._vc_snapshot_timer. Captura la ventana del GUI TAL COMO SE VE
        (self.grab(), no el escritorio completo -- para eso está
        board.capture_tablero()) y la guarda en VC_FILE (vc.png) SOLO si el
        contenido cambió desde la última captura, comparando la imagen
        completa (QImage.__eq__ es una comparación de píxeles) -- así no se
        reescribe el archivo (ni se le cambia la fecha de modificación, que
        es lo que usa la webapp para saber cuándo hay novedad) si la
        ventana lleva un rato sin cambiar visualmente.

        Si la ventana está oculta (apartar_ventana(), o el
        propio grab() devuelve una imagen vacía por estar minimizada en
        algún compositor) se salta la captura sin más -- la webapp se
        queda con la última imagen válida hasta que la ventana vuelva a
        estar visible y cambie de nuevo."""
        # EN MODO SERVICIO SE CAPTURA AUNQUE ESTÉ OCULTA.
        #
        # self.grab() funciona con la ventana escondida y devuelve
        # exactamente la misma imagen -- comprobado el 6-sep-2026. Sin
        # esto, en modo servicio (donde la ventana vive oculta casi
        # siempre) el móvil se quedaría con una foto congelada, que es
        # justo el fallo que tuvo el modo que pintaba sobre el escritorio.
        #
        # Con la ventana normal el comportamiento es el de siempre: si
        # está oculta (apartar_ventana) no se recaptura.
        if not self.isVisible() and not self._modo_servicio:
            return
        try:
            pixmap = self.grab()
        except Exception as exc:
            print(f"[gui] error capturando snapshot del GUI: {exc!r}")
            return
        if pixmap.isNull() or pixmap.width() <= 0 or pixmap.height() <= 0:
            return
        image = pixmap.toImage()
        if self._last_vc_image is not None and image == self._last_vc_image:
            return  # sin cambios visuales desde la última captura
        try:
            ok = image.save(str(VC_FILE), "PNG")
        except Exception as exc:
            print(f"[gui] error guardando {VC_FILE}: {exc!r}")
            return
        if ok:
            self._last_vc_image = image

    def _do_quit(self):
        QApplication.quit()

    def bring_to_front(self):
        """Restaura visibilidad y trae la ventana al frente
        (self.show() + self.raise_() + self.activateWindow()) -- pensado
        para que el GUI vuelva a verse si quedó detrás de otra ventana o
        se ocultó, p.ej. al pulsar "🎧 Escucha" (ver
        command_router.manual_action, acción "idle").

        A diferencia de send_to_back()/_do_restore() (pensados para NO
        robar el foco tras una acción automática de tablero o de
        pegado), esta función SÍ activa la ventana: es una petición
        explícita del usuario de traer el GUI al frente, y bajo KWin
        self.raise_() solo (sin activar) a veces no basta para
        colocarse por encima de una ventana maximizada u ocupando el
        escritorio -- de ahí el activateWindow() añadido.

        REFUERZO vía kdotool (KWin/D-Bus, más fiable que Qt bajo
        Wayland cuando otra ventana ocupa todo el escritorio): además
        de lo anterior, se intenta (1) minimizar la ventana que esté
        actualmente activa (actions.minimize_active_window()) y (2)
        activar esta MISMA ventana por su título fijo "VoiceController"
        (actions.activate_window_by_name(), ver setWindowTitle() en
        __init__). Ninguno de los dos pasos es indispensable -- si
        kdotool no está instalado, se avisa por consola y se sigue solo
        con lo que Qt pueda conseguir."""
        try:
            import actions as _actions
            _actions.minimize_active_window()
            _actions.activate_window_by_name("VoiceController",
                                             permitir_propia=True)
        except Exception as exc:
            print(f"[gui] error usando kdotool en bring_to_front: {exc!r}")
        try:
            self.show()
            self.raise_()
            self.activateWindow()
        except Exception as exc:
            print(f"[gui] error trayendo la ventana al frente: {exc!r}")
        # En Windows activateWindow y SetForegroundWindow los bloquea el
        # sistema (bloqueo del primer plano): parpadea la barra de tareas y
        # nada mas. El empujon de orden de apilamiento si funciona.
        self._empujon_arriba()

    def traer_al_frente_suave(self):
        """Sube la ventana SIN llevarse el foco del teclado.

        Dos cosas que hay que evitar aqui, y cada una costo un fallo:

        1. bring_to_front() MINIMIZA la ventana activa para colarse encima.
           Despues de la vista "foco" eso minimizaria justo la ventana que
           se acaba de capturar, y la siguiente vez ya no estaria.

        2. activateWindow() -- y activate_window_by_name -- se llevan el
           FOCO DEL TECLADO. Con eso, decir "guardar" mandaba el ctrl+s a
           VoiceController en vez de a Kate: el registro decia "tecla
           especial save: OK" y no pasaba nada. Lo encontro el probando la
           habilidad de Kate desde la vista foco.

        Asi que solo se sube en el orden de apilamiento: se ve encima, y las
        teclas siguen yendo a la ventana en la que se esta trabajando.
        """
        try:
            self.show()
            self.raise_()
        except Exception as exc:
            print(f"[gui] error subiendo la ventana: {exc!r}")
        # RAISE_() NO BASTA BAJO WAYLAND. El compositor decide el orden de
        # apilamiento y a un cliente que se sube solo le hace caso... o no,
        # y contra una ventana maximizada normalmente no. Se refuerza
        # pidiendoselo a KWin, que es quien manda -- en su propio hilo,
        # porque kdotool habla por D-Bus y puede tardar.
        #
        # Se pide "encima" y se quita acto seguido: lo que hace falta es el
        # EMPUJON, no dejarla clavada por encima de todo para siempre.
        self._empujon_arriba()

    def send_to_back(self):
        """Muestra la ventana (sigue visible -- el usuario la sigue viendo
        y vc.png/el seguimiento táctil siguen funcionando) pero SIN
        traerla al frente: self.lower() la manda al fondo del orden de
        apilamiento del escritorio. Es lo contrario de bring_to_front()/
        subir_ventana().

        Se usa tras CADA acción de tablero/táctil (ver
        actions.fire_board_action) para que VoiceController nunca quede
        por encima de un menú, la barra de tareas o el menú de inicio
        que la propia acción acabe de abrir -- antes, al traer el GUI de
        vuelta al frente justo después de cada clic (subir_ventana,
        que sí hace raise_()), esos menús se cerraban solos nada más
        abrirse porque VoiceController se colocaba por encima. Para
        volver a ver/usar el GUI en primer plano explícitamente, usar
        bring_to_front() (botón/acción "🎧 Escucha", comando de voz
        "subir")."""
        try:
            # show() SOLO SI HACE FALTA. Sobre una ventana que ya se ve, un
            # show() de mas puede ACTIVARLA -- y entonces el foco de teclado
            # se viene aqui aunque lower() la deje al fondo. Eso rompia lo
            # que venia detras: tras seleccionar en Kate, el "copiar" se lo
            # comia VoiceController. (10-sep-2026.)
            if not self.isVisible():
                self.show()
            self.lower()
        except Exception as exc:
            print(f"[gui] error mandando la ventana a un nivel inferior: {exc!r}")

    def _do_minimize(self):
        # Hide instead of minimizing to avoid compositor animation bugs
        self.hide()

    def _do_restore(self):
        # Show without stealing focus; do not call activateWindow()
        self.show()
        self.raise_()
        # keep the window non-activating to avoid focus issues

    def _do_run_callable(self, fn):
        try:
            fn()
        except Exception as exc:
            print(f"[gui] error ejecutando acción en el hilo principal: {exc!r}")

    def _do_run_callable_delayed(self, fn, delay_ms: int):
        QTimer.singleShot(delay_ms, lambda: self._do_run_callable(fn))

    def _do_update_state(self, state: str):
        self._current_state = state
        self._pause_notified = state != "DICTATING"  # no sugerir nada en IDLE
        if state == "DICTATING":
            self._last_activity_ts = time.monotonic()
        else:
            self._do_clear_suggestion()
        self.led_idle.setStyleSheet(f"background: {LED_ON if state == 'IDLE' else LED_OFF}; {LED_STYLE}")
        self.led_dictating.setStyleSheet(f"background: {LED_ON if state == 'DICTATING' else LED_OFF}; {LED_STYLE}")

    def _do_update_formuling(self, enabled: bool):
        self.led_formuling.setStyleSheet(f"background: {LED_ON if enabled else LED_OFF}; {LED_STYLE}")

    def _do_update_position(self, cell: int, subcell: int):
        label = self._labels_all.get(self._ui_lang, {}).get("cell_label", "Celda")
        if self._last_position:
            last_cell, last_subcell = self._last_position
            self.position_label.setText(f"{label}: {cell}  [{last_cell}]")
        else:
            self.position_label.setText(f"{label}: {cell}")

    def _do_update_language_combo(self, combo_label: str):
        prefix = self._labels_all.get(self._ui_lang, {}).get("active_prefix", "Activo")
        self.language_combo_label.setText(f"{prefix}: {combo_label}")

    def _do_update_audio_level(self, is_silent: bool, rms: float):
        # Primera vez que llega audio: el micrófono está abierto de verdad.
        # Si había un aviso esperando ("di tu santo y seña"), ahora sí tiene
        # sentido enseñarlo.
        if not self._micro_listo:
            self._micro_listo = True
            if self._aviso_urgente_pendiente:
                self.suggestion_label.setText(self._aviso_urgente_pendiente)
                self._aviso_urgente_pendiente = None

        # LED encendido = se está detectando voz; apagado = silencio.
        color = LED_OFF if is_silent else LED_ON
        self.led_audio.setStyleSheet(f"background: {color}; {LED_STYLE}")
        self.led_audio.setToolTip(f"nivel: {rms:.0f} (umbral: {config.SILENCE_RMS_THRESHOLD})")

    def update_formuling_indicator(self, enabled: bool):
        """Public API to toggle the formuling LED from other threads/logic."""
        self.sig_update_formuling.emit(enabled)

    def _setup_tray(self):
        """Create a system tray icon with emergency controls (show interactive,
        show passive, send Enter/Reset/Idle, quit) and an audio-input selector.
        This allows controlling the app even when the GUI is click-through."""
        try:
            tray_icon = QSystemTrayIcon(self)
            # Prefer a security-themed icon if the icon theme provides one.
            security_names = (
                "emblem-security",
                "security-high",
                "system-lock-screen",
                "dialog-password",
                "emblem-readonly",
                "security",
            )
            icon = QIcon()
            for name in security_names:
                _ic = QIcon.fromTheme(name)
                if not _ic.isNull():
                    icon = _ic
                    break
            if icon.isNull():
                # fallback to a generic editor icon then to a warning/computer icon
                icon = QIcon.fromTheme("accessories-text-editor")
            if icon.isNull():
                icon = QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning)

            tray_icon.setIcon(icon)
            tray_icon.setToolTip("VoiceController — seguridad")

            menu = QMenu()
            show_action = QAction("Mostrar", self)
            show_action.triggered.connect(self.bring_to_front)
            menu.addAction(show_action)

            # En modo servicio la ventana vive escondida, así que hace
            # falta la pareja de "Mostrar". En modo normal no se pone: la
            # ventana se cierra o se minimiza como cualquier otra.
            if self._modo_servicio:
                # Por el mismo camino que el comando de voz: mostrar el
                # panel no debe minimizar la ventana en la que se trabaja.
                show_action.triggered.disconnect()
                show_action.triggered.connect(self.mostrar_panel)
                hide_action = QAction("Ocultar", self)
                hide_action.triggered.connect(self.ocultar_panel)
                menu.addAction(hide_action)

            menu.addSeparator()

            # Language priority selector submenu
            lang_menu = QMenu("Lengua materna")
            lang_group = QActionGroup(self)
            lang_group.setExclusive(True)
            self._language_combo_actions = []
            combos = (
                ("es", "en", "Español (inglés como segunda)"),
                ("en", "es", "English (Spanish as second)"),
            )
            for primary, secondary, label in combos:
                act = QAction(label, self)
                act.setCheckable(True)
                lang_group.addAction(act)
                act.triggered.connect(
                    lambda checked, p=primary, s=secondary, lbl=label: self._select_language_combo(p, s, lbl)
                )
                lang_menu.addAction(act)
                self._language_combo_actions.append((primary, secondary, act, label))
            menu.addMenu(lang_menu)

            # Audio input selector submenu
            input_menu = QMenu("Entrada audio")
            inputs = self._get_audio_inputs()
            self._audio_input_actions = []
            self._audio_input_group = QActionGroup(self)
            self._audio_input_group.setExclusive(True)
            default_selected = None
            for dev_id, label in inputs:
                act = QAction(label, self)
                act.setCheckable(True)
                self._audio_input_group.addAction(act)
                act.triggered.connect(lambda checked, did=dev_id, lbl=label: self._select_audio_input(did, lbl))
                input_menu.addAction(act)
                self._audio_input_actions.append((dev_id, act))
                if default_selected is None:
                    default_selected = dev_id
            menu.addMenu(input_menu)

            menu.addSeparator()

            send_enter = QAction("Enviar Enter", self)
            send_enter.triggered.connect(lambda: self._on_manual_action("confirm"))
            menu.addAction(send_enter)

            send_reset = QAction("Enviar Reset", self)
            send_reset.triggered.connect(lambda: self._on_manual_action("reset"))
            menu.addAction(send_reset)

            send_correct = QAction("Corregir última palabra", self)
            send_correct.triggered.connect(lambda: self._on_manual_action("correct_last_word"))
            menu.addAction(send_correct)

            send_idle = QAction("Enviar Idle", self)
            send_idle.triggered.connect(lambda: self._on_manual_action("idle"))
            menu.addAction(send_idle)

            # --- Filtro por voz: SALIDA DE EMERGENCIA ---
            # Tiene que estar aquí, en la bandeja, y no solo como comando
            # de voz: si el filtro se calibra mal y empieza a rechazar al
            # propio usuario, por voz ya no se le podría decir que pare.
            # Ver speaker_id.py y config.SPEAKER_ID_*.
            try:
                import speaker_id as _speaker_id
                import config as _config
                self._speaker_filter_action = QAction("Filtrar por mi voz", self)
                self._speaker_filter_action.setCheckable(True)
                self._speaker_filter_action.setChecked(
                    bool(getattr(_config, "SPEAKER_ID_ENABLED", False)))
                verifier = _speaker_id.SpeakerVerifier()
                if not verifier.enabled and getattr(_config, "SPEAKER_ID_ENABLED", False):
                    # activado en config pero sin perfil utilizable
                    self._speaker_filter_action.setEnabled(False)
                    self._speaker_filter_action.setToolTip(verifier.reason)
                self._speaker_filter_action.triggered.connect(self._toggle_speaker_filter)
                menu.addAction(self._speaker_filter_action)

                # Desbloqueo tras un aborto por intrusión. Va aquí, en la
                # bandeja, porque mientras está bloqueado NO se obedece
                # ninguna orden de voz: si la única salida fuera hablada y
                # el filtro se hubiera calibrado mal, no habría forma de
                # recuperar el control. Ver
                # command_router._try_intruder_unlock.
                self._intruder_unlock_action = QAction("Desbloquear (intruso)", self)
                self._intruder_unlock_action.triggered.connect(self._unlock_intruder)
                menu.addAction(self._intruder_unlock_action)

                # Salir de standby sin usar la voz. Despierta, pero NO
                # identifica: sigue pidiendo el santo y seña después.
                self._wake_action = QAction("Despertar (standby)", self)
                self._wake_action.triggered.connect(self._leave_standby)
                menu.addAction(self._wake_action)
                menu.addSeparator()
            except Exception as exc:
                print(f"[gui] no se pudo añadir el interruptor del filtro por voz: {exc!r}")

            menu.addSeparator()
            quit_action = QAction("Salir", self)
            quit_action.triggered.connect(self.quit_app)
            menu.addAction(quit_action)

            tray_icon.setContextMenu(menu)
            tray_icon.show()
            self._tray_icon = tray_icon
            # set initial selection
            self._selected_primary_language = "es"
            self._selected_secondary_language = "en"
            self._selected_language_combo_label = "Español > English"
            self._set_language_combo_check("es", "en")
            self._do_update_language_combo(self._selected_language_combo_label)
            self._update_tray_tooltip()
            if default_selected is not None:
                self._select_audio_input(default_selected, None)
        except Exception as exc:
            print(f"[gui] no se pudo crear tray icon: {exc!r}")

    def _toggle_speaker_filter(self, checked: bool):
        """Enciende/apaga el filtro por voz EN CALIENTE, sin reiniciar.

        Cambia config.SPEAKER_ID_ENABLED en memoria y avisa al
        reconocedor por el callback registrado con
        set_speaker_filter_callback() -- si no hay ninguno registrado, el
        cambio se queda en config y tendrá efecto en el siguiente
        arranque, que sigue siendo mejor que nada."""
        try:
            import config as _config
            _config.SPEAKER_ID_ENABLED = bool(checked)
            print(f"[gui] filtro por voz {'ACTIVADO' if checked else 'DESACTIVADO'} "
                  "desde la bandeja")
        except Exception as exc:
            print(f"[gui] no se pudo cambiar el filtro por voz: {exc!r}")
            return
        fn = getattr(self, "_speaker_filter_callback", None)
        if fn is not None:
            try:
                fn(bool(checked))
            except Exception as exc:
                print(f"[gui] el callback del filtro por voz falló: {exc!r}")

    def _unlock_intruder(self):
        """Levanta el bloqueo por intrusión desde la bandeja."""
        fn = getattr(self, "_intruder_unlock_callback", None)
        if fn is None:
            print("[gui] no hay nada conectado al desbloqueo por intrusión")
            return
        try:
            fn()
            print("[gui] bloqueo por intrusión levantado desde la bandeja")
        except Exception as exc:
            print(f"[gui] no se pudo desbloquear: {exc!r}")

    def _leave_standby(self):
        fn = getattr(self, "_standby_callback", None)
        if fn is None:
            print("[gui] no hay nada conectado al despertar de standby")
            return
        try:
            fn()
            print("[gui] despertado desde la bandeja (pedirá el santo y seña)")
        except Exception as exc:
            print(f"[gui] no se pudo despertar: {exc!r}")

    def set_standby_callback(self, fn):
        """fn() -- normalmente router.leave_standby."""
        self._standby_callback = fn

    def set_intruder_unlock_callback(self, fn):
        """fn() -- normalmente router.clear_intruder_lock."""
        self._intruder_unlock_callback = fn

    def set_speaker_filter_callback(self, fn):
        """fn(enabled: bool) -- normalmente
        recognizer.set_speaker_filter_enabled, para que el interruptor de
        la bandeja tenga efecto inmediato."""
        self._speaker_filter_callback = fn

    def set_audio_input_callback(self, fn):
        """Register a callback fn(device_id: str) called when the user selects an audio input from the tray."""
        self._audio_input_callback = fn
        current = getattr(self, "_selected_audio_input", None)
        if current is not None:
            try:
                fn(current)
            except Exception as exc:
                print(f"[gui] audio input callback raised: {exc!r}")

    def set_dictation_language_callback(self, fn):
        """Register a callback fn(language: str) called when the user selects the primary language."""
        self._dictation_language_callback = fn
        current = getattr(self, "_selected_primary_language", "es")
        try:
            fn(current)
        except Exception as exc:
            print(f"[gui] dictation language callback raised: {exc!r}")

    def _set_language_combo_check(self, primary: str, secondary: str):
        try:
            for p, s, act, _label in getattr(self, "_language_combo_actions", []):
                act.setChecked(p == primary and s == secondary)
        except Exception:
            pass
        self._selected_primary_language = primary
        self._selected_secondary_language = secondary

    def _update_tray_tooltip(self):
        try:
            combo_label = getattr(self, "_selected_language_combo_label", "Español > English")
            input_label = getattr(self, "_selected_audio_input_label", None)
            suffix = f" | micro: {input_label}" if input_label else ""
            if hasattr(self, "_tray_icon"):
                self._tray_icon.setToolTip(f"VoiceController — {combo_label}{suffix}")
        except Exception:
            pass

    def _select_language_combo(self, primary: str, secondary: str, label: str | None):
        self._set_language_combo_check(primary, secondary)
        self._selected_language_combo_label = label or f"{primary.upper()} > {secondary.upper()}"
        self._do_update_language_combo(self._selected_language_combo_label)
        self._update_tray_tooltip()
        cb = getattr(self, "_dictation_language_callback", None)
        if cb:
            try:
                cb(primary)
            except Exception as exc:
                print(f"[gui] dictation language callback raised: {exc!r}")

    def _select_audio_input(self, device_id: str, label: str | None):
        # Uncheck all actions, check the chosen one
        try:
            for did, act in getattr(self, "_audio_input_actions", []):
                act.setChecked(did == device_id)
        except Exception:
            pass
        self._selected_audio_input = device_id
        self._selected_audio_input_label = label or device_id
        self._update_tray_tooltip()
        # call callback if provided
        cb = getattr(self, "_audio_input_callback", None)
        if cb:
            try:
                cb(device_id)
            except Exception as exc:
                print(f"[gui] audio input callback raised: {exc!r}")

    def _get_audio_inputs(self) -> list:
        """Return list of (device_id, label) available on the system, más
        la entrada especial "Red (móvil)" al final (audio que llega de la
        webapp, en vez de un micrófono local)."""
        return self._get_local_audio_inputs() + [("network", "Red (móvil)")]

    def _get_local_audio_inputs(self) -> list:
        """Return list of (device_id, label) available on the system.

        Tries sounddevice first (real PortAudio input list), then QtMultimedia,
        then pulse (pactl), then arecord.
        If nothing found, returns a single fallback entry.
        """
        # Prefer sounddevice list to match what the recognizer can open.
        try:
            devs = sd.query_devices()
            res = [("default", "Default input")]
            for idx, d in enumerate(devs):
                try:
                    if int(d.get("max_input_channels", 0)) <= 0:
                        continue
                    label = f"{d.get('name', 'input')} (#{idx})"
                    res.append((str(idx), label))
                except Exception:
                    continue
            if len(res) > 1:
                return res
        except Exception:
            pass

        # Try QtMultimedia if available
        try:
            from PySide6.QtMultimedia import QMediaDevices
            devs = QMediaDevices.audioInputs()
            res = []
            for d in devs:
                try:
                    id_ = d.id()
                except Exception:
                    id_ = str(d)
                label = d.description() if hasattr(d, "description") else str(d)
                res.append((id_, label))
            if res:
                return res
        except Exception:
            pass

        # Try pactl
        try:
            out = subprocess.check_output(["pactl", "list", "short", "sources"], text=True)
            res = []
            for line in out.splitlines():
                parts = line.split('\t')
                if len(parts) >= 2:
                    idx = parts[0].strip()
                    name = parts[1].strip()
                    # make label nicer
                    res.append((name, name))
            if res:
                return res
        except Exception:
            pass

        # Try arecord -l
        try:
            out = subprocess.check_output(["arecord", "-l"], text=True, stderr=subprocess.DEVNULL)
            res = []
            for line in out.splitlines():
                if line.strip().startswith("card"):
                    # example: card 0: PCH [HDA Intel PCH], device 0: ALC233 Analog
                    label = line.strip()
                    dev_id = label
                    res.append((dev_id, label))
            if res:
                return res
        except Exception:
            pass

        # Fallback
        return [("default", "Default input")]
