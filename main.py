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
main.py: Punto de entrada principal de VoiceController (REFACTORIZADO).

✓ Threading Qt correcto (patrón Worker)
✓ Inicialización limpia del micrófono
✓ Manejo robusto de errores
✓ Rutas portables (paths.py)
"""

import sys
import json
import locale
import threading
from pathlib import Path

# --- CONFIGURACIÓN Y RUTAS ---
import config

# El desdoble de la salida a disco va ANTES que cualquier otro import del
# proyecto, porque varios modulos ya imprimen cosas al importarse (rutas,
# modelos que se cargan, avisos de dependencias) y esas lineas son las
# primeras que hacen falta cuando algo no arranca.
import runlog
runlog.empezar()

import tts
import board
from paths import (
    PROJECT_ROOT,
    COMMANDS_FILE,
    WEBAPP_CONFIG_FILE,
    print_paths_info,
)

# Asegurar que grid_vc se puede importar

# --- IMPORTS QT ---
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QThread, QTimer

# --- IMPORTS DEL PROYECTO ---
from command_router import CommandRouter
from recognizer_worker import RecognizerWorker
import gui as gui_module
from microphone_manager import MicrophoneManager
import cesion_microfono
from webapp.app import start_background_server, stop_background_server


def load_config() -> dict:
    """Carga la configuración desde commands.json."""
    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[main] ERROR: No se encontró {COMMANDS_FILE}")
        return {}
    except json.JSONDecodeError as e:
        print(f"[main] ERROR parseando {COMMANDS_FILE}: {e}")
        return {}


# --- La bandera --as-service -------------------------------------------------
# Se lee aqui arriba y no dentro de main() porque hay modulos que miran el
# modo al importarse. Se quita de sys.argv para que QApplication no la vea
# como suya y se queje.
MODO_SERVICIO = "--as-service" in sys.argv
if MODO_SERVICIO:
    sys.argv = [a for a in sys.argv if a != "--as-service"]


def main():
    """Punto de entrada principal."""

    if config.DEBUG:
        print_paths_info()
        print("[main] Modo DEBUG activo")

    # --- CREAR APLICACIÓN QT PRIMERO ---
    # (Debe ir antes que setlocale porque QApplication lo resetea)
    app = QApplication(sys.argv)

    # --- CONFIGURACIÓN LOCALE DESPUÉS ---
    # CRÍTICO: PySide6 cambia el locale numérico al crear QApplication.
    # Por eso debe venir DESPUÉS de crear la app.
    locale.setlocale(locale.LC_NUMERIC, "C")

    # --- MOSTRAR DISPOSITIVOS DISPONIBLES ---
    if config.DEBUG:
        MicrophoneManager.print_devices()

    # --- CARGAR CONFIGURACIÓN ---
    commands_config = load_config()
    if not commands_config:
        print("[main] ADVERTENCIA: Configuración vacía o faltante")

    # --- ARRANCAR WEBAPP (micrófono remoto / streaming) ---
    if config.ENABLE_WEBAPP:
        try:
            start_background_server()
        except Exception as e:
            print(f"[main] ERROR arrancando webapp: {e}")

    # --- CREAR LA INTERFAZ: ventana, o modo servicio ---
    #
    # Los dos modos son EXCLUYENTES y se eligen en la llamada:
    #
    #     python main.py                 con ventana (por defecto)
    #     python main.py --as-service    la MISMA ventana, pero escondida
    #
    # LOS DOS MODOS SON LA MISMA CLASE, y eso es el cambio del 6-sep-2026.
    #
    # Antes el modo servicio era otra implementacion entera (servicio.py)
    # que pintaba las vistas directamente sobre el escritorio. Se descarto
    # con medidas: consumia 220 MB MAS que la ventana, obligaba al
    # compositor a componer tres superficies a pantalla completa todo el
    # rato -- CPU que le hace falta al reconocedor -- y costo dos dias de
    # peleas con Wayland (no poder subirse solos, el passthrough, la
    # opacidad que no existe, las capturas que salian sucias cuatro veces).
    #
    # Lo que queda es mas simple y ya estaba probado: el GUI de siempre,
    # arrancado oculto. Se muestra diciendo "monitor" o desde la bandeja.
    # Con la ventana escondida las capturas y las acciones siguen
    # funcionando -- de hecho el GUI YA se esconde antes de cada captura
    # (apartar_ventana es un hide()).
    if MODO_SERVICIO:
        window = gui_module.GUI(on_manual_action=None, arranca_oculto=True)
        print("[main] MODO SERVICIO: la ventana arranca oculta. "
              "Di 'monitor' o usa la bandeja para verla.")
    else:
        window = gui_module.GUI(on_manual_action=None)
        window.show()

    # --- CREAR ROUTER DE COMANDOS ---
    router = CommandRouter(commands_config, window)

    # --- CONECTAR BOTONES/TRAY/WEBAPP DE LA GUI AL ROUTER ---
    # (antes se pasaba on_manual_action=None y nunca se rewireaba: los
    # botones Enter/Reset/Idle y el menú de la bandeja lanzaban un error
    # silencioso al pulsarlos. Necesario también para los botones equivalentes
    # de la webapp.)
    window.set_manual_action_callback(router.manual_action)

    # Sugerencias en pausa (campo "Sugerencias", ver Sección 2 del manual)
    window.set_pause_callback(router.check_pause_suggestion)

    # Tablero de 100 casillas: toques/clics sobre el tablero del GUI de
    # escritorio, y comandos táctiles equivalentes desde la webapp (mismo
    # bridge, mismo texto que reconocería la voz -- ver command_router.
    # handle_touch y webapp/app.py set_command_bridge)
    window.set_touch_callback(router.handle_touch)
    try:
        from webapp import app as webapp_app
        webapp_app.set_command_bridge(router.handle_touch)
        # Tras un clic del touchpad (ver webapp/app.py board_touchpad(),
        # actions.touchpad_click) hace falta refrescar tablero.png Y la
        # vista del GUI para que la imagen que ve la webapp (vc.png)
        # refleje el resultado -- sin esto, el touchpad movía el cursor
        # de verdad pero la webapp se quedaba con la imagen antigua
        # hasta pulsar "Actualizar" a mano.
        webapp_app.set_refresh_bridge(lambda: (board.capture_tablero(), window.show_board_overview()))
        # Fase 3 del rediseño de accesibilidad (PDF NuevoGUI, puntero
        # rojo de la webapp): qué imagen mostrar de fondo en el
        # touchpad virtual (get_board_state, expuesto en /board/info) y
        # el disparo de la acción atómica cuando se confirma un clic/
        # clic derecho/doble clic/scroll (fire_virtual_action_from_webapp,
        # ruta POST /board/virtual_action).
        webapp_app.set_board_state_bridge(router.get_board_state)
        # Estado de la sesión: sin esto la webapp serviría capturas del
        # escritorio aunque el PC no esté identificado (ver
        # webapp.board_image y command_router.get_session_state).
        webapp_app.set_session_state_bridge(router.get_session_state)
        # Primera conexión del móvil -> grabar el perfil de voz de ESE
        # micrófono (ver command_router.start_mobile_enrollment): el
        # perfil del PC no sirve ahí.
        webapp_app.set_network_connected_bridge(router.on_network_connected)
        webapp_app.set_virtual_action_bridge(router.fire_virtual_action_from_webapp)
        # Un móvil sin emparejar avisa de que está conectándose -> el
        # ordenador dice su código en voz alta para poder compararlo con el
        # que enseña el teléfono. Sin esto habría que acordarse del comando
        # "código de emparejamiento", y quien estrena la app no lo sabe.
        webapp_app.set_pairing_bridge(router._decir_codigo_emparejamiento)
        # Donde tiene el movil su punto rojo: sin esto no se puede decir
        # "pulsa rojo", que es lo unico que sirve en modo cara.
        webapp_app.set_pointer_bridge(router.actualizar_puntero_rojo)
    except Exception as e:
        print(f"[main] no se pudo conectar el bridge de la webapp: {e}")

    # Habilidades: lo especifico de cada programa (ver habilidades/).
    # Hoy la lista sale vacia y no cambia nada; el sitio esta hecho para que
    # anadir una sea escribir un fichero en esa carpeta.
    try:
        import habilidades
        habilidades.cargar()
    except Exception as e:
        print(f"[main] no se pudieron cargar las habilidades: {e}")

    # Una captura al arrancar, para que el tablero no salga vacío.
    #
    # Antes no se capturaba hasta el primer comando de casilla, y en una
    # instalación recién hecha eso deja un hueco con "(sin captura de
    # tablero todavía)" que parece que la aplicación no funciona. Quien ya
    # la usa no lo ve nunca, porque su tablero.png lleva ahí desde siempre.
    #
    # Si la captura falla no se aborta nada: show_board_overview() ya sabe
    # enseñar el marcador de posición, que es exactamente lo de antes.
    try:
        board.capture_tablero()
    except Exception as exc:
        print(f"[main] no se pudo capturar el tablero al arrancar: {exc!r}")
    window.show_board_overview()

    # --- CREAR WORKER DE RECONOCIMIENTO (QObject) ---
    recognizer_worker = RecognizerWorker()

    # Micrófono remoto del móvil (webapp) -> reconocedor: el pipeline en sí
    # (network_audio_chunk/switch_to_network_requested) ya existía en
    # RecognizerWorker, pero nada lo conectaba con /receive_audio -- el
    # audio subido por el móvil se guardaba en disco y ahí se quedaba, sin
    # que nadie lo decodificase ni se lo entregara al reconocedor. Estas
    # dos líneas son la conexión que faltaba (ver webapp/app.py
    # set_audio_bridge()/set_network_switch_bridge() para el porqué).
    try:
        from webapp import app as webapp_app
        webapp_app.set_audio_bridge(recognizer_worker.network_audio_chunk.emit)
        webapp_app.set_network_switch_bridge(recognizer_worker.switch_to_network_requested.emit)
        # "original" y no "default": hay que volver al micrófono que el
        # usuario tenía configurado, no al que diga el sistema (ver
        # voice_recognizer.set_input_device).
        webapp_app.set_local_switch_bridge(
            lambda: recognizer_worker.switch_to_device_requested.emit("original"))
    except Exception as e:
        print(f"[main] no se pudo conectar el bridge de audio de la webapp: {e}")

    # --- CREAR THREAD PARA EL WORKER ---
    recognizer_thread = QThread()
    recognizer_worker.moveToThread(recognizer_thread)

    # --- CONECTAR SEÑALES (PATRÓN Qt CORRECTO) ---

    # Cuando inicia el thread, comenzar el reconocimiento
    recognizer_thread.started.connect(recognizer_worker.start_recognition)

    # Conectar resultados del reconocedor al router
    recognizer_worker.partial_result.connect(router.on_partial)
    recognizer_worker.final_result.connect(router.on_final)

    # Conectar errores del reconocedor a ventana
    def on_recognizer_error(msg: str):
        print(f"[main] ERROR de reconocimiento: {msg}")
        # Mostrar diálogo al usuario
        QMessageBox.critical(window, "Error de Micrófono", msg)

    recognizer_worker.error_occurred.connect(on_recognizer_error)

    # Conectar el nivel de audio / detector de silencio (LED informativo)
    recognizer_worker.audio_level.connect(window.update_audio_level)

    # Conectar cambio de idioma
    router.set_language_mode_callback(recognizer_worker.set_language_mode)

    # Conectar estado dictating (para que solo ahí se analice prosodia, y
    # para que la voz de la aplicación NO hable en mitad de un dictado --
    # ver tts.Speaker.say)
    def _on_dictating(is_dictating: bool):
        recognizer_worker.set_dictating(is_dictating)
        try:
            tts.get_speaker().set_dictating(is_dictating)
        except Exception as exc:
            print(f"[main] no se pudo avisar a la voz del cambio de estado: {exc}")

    router.set_dictating_callback(_on_dictating)

    # Interruptor "Filtrar por mi voz" de la bandeja -> reconocedor, para
    # que encender/apagar el filtro por voz tenga efecto inmediato sin
    # reiniciar (ver speaker_id.py: es la salida de emergencia que NO
    # depende de la voz).
    # EL SELECTOR DE IDIOMA, que hasta el 5-sep-2026 no estaba conectado.
    #
    # gui.set_dictation_language_callback() existia desde siempre y NADIE la
    # llamaba: elegir "English > Español" en el menu cambiaba la etiqueta y
    # nada mas -- el reconocedor seguia en español. Un fallo mudo, de los
    # que solo se ven si uno va a comprobar el efecto en vez de la interfaz.
    window.set_dictation_language_callback(router.set_dictation_language)
    window.set_speaker_filter_callback(recognizer_worker.set_speaker_filter_enabled)

    # Desbloqueo tras un aborto por intrusión, desde la bandeja del
    # sistema -- la única salida que NO pasa por la voz (ver
    # command_router._try_intruder_unlock).
    window.set_intruder_unlock_callback(router.clear_intruder_lock)

    # Santo y seña: se pide en cuanto está todo montado (ver
    # command_router.start_voice_login). Con un pequeño retraso para que
    # el reconocedor ya esté escuchando cuando suene la pregunta -- si no,
    # la respuesta caería en el vacío.
    router.set_awaiting_login_callback(recognizer_worker.set_awaiting_login)

    # --- El santo y seña se pide cuando el audio YA está entrando --------
    # Antes era un temporizador fijo de 2,5 s: una suposición. Si el
    # micrófono tardaba más en abrirse, la aplicación preguntaba al vacío y
    # la respuesta se perdía; y si tardaba menos, se esperaba de más.
    #
    # `audio_level` se emite en CADA bloque de audio procesado, así que su
    # primera emisión es la prueba de que el micrófono está abierto y los
    # bloques están llegando al reconocedor. Ahí es cuando tiene sentido
    # preguntar, ni antes ni después.
    _login_pedido = {"hecho": False}

    def _pedir_santo_y_sena_si_hay_audio(_is_silent=None, _rms=None):
        if _login_pedido["hecho"]:
            return
        _login_pedido["hecho"] = True
        # Pequeño margen tras el primer bloque: que llegue uno no significa
        # que el flujo esté ya estable, y la frase de respuesta es larga.
        QTimer.singleShot(400, router.start_voice_login)

    recognizer_worker.audio_level.connect(_pedir_santo_y_sena_si_hay_audio)

    # Red de seguridad: si el audio NO llega nunca (micrófono ocupado por
    # otra aplicación, permisos, dispositivo equivocado), se pide de todas
    # formas pasados unos segundos. Mejor preguntar y que no funcione --
    # con su mensaje en pantalla -- que quedarse callado sin explicar nada.
    QTimer.singleShot(8000, _pedir_santo_y_sena_si_hay_audio)
    router.set_enrollment_callback(recognizer_worker.set_enrollment)
    router.set_reload_profiles_callback(recognizer_worker.reload_profiles)
    window.set_standby_callback(router.leave_standby)
    window.set_idle_standby_callback(router.check_idle_standby)


    # Comando de voz "micrófono local"/"mic local" -- vuelve a escuchar el
    # micrófono físico del escritorio tras haber usado el del móvil (ver
    # command_router._try_parse_switch_to_local_mic). switch_to_device_requested
    # ya existía en RecognizerWorker sin ningún emisor conectado.
    router.set_switch_to_local_mic_callback(
        lambda: recognizer_worker.switch_to_device_requested.emit("original")
    )

    # Pipe-Logic tiene preferencia sobre el micrófono: si lo pide, se le
    # cede hasta que lo suelte (ver cesion_microfono.py).
    if cesion_microfono.arrancar_servidor():
        # Y también a mano: botón "Pipe-Logic Mic" (y su entrada en la
        # bandeja) para cederlo o recuperarlo, comando "micro lógico" para
        # cederlo. El aviso de cambio llega desde otro hilo:
        # set_pipe_logic_mic va por señal. Sin servidor (Windows) no se
        # conecta nada: el botón no sale, porque Pipe-Logic no podría
        # devolver el micro y VoiceController se quedaría sordo.
        window.set_pipe_logic_mic_callback(cesion_microfono.alternar_manual)
        router.set_ceder_micro_pipe_logic_callback(
            lambda: threading.Thread(target=cesion_microfono.ceder_manual,
                                     daemon=True, name="cesion_manual").start()
        )
        cesion_microfono.al_cambiar(window.set_pipe_logic_mic)

    # --- LIMPIEZA AL CERRAR ---
    def cleanup():
        """Detener reconocimiento y limpiar threads."""
        print("[main] Limpiando recursos...")
        recognizer_worker.stop_recognition()
        recognizer_thread.quit()
        recognizer_thread.wait(2000)
        if config.ENABLE_WEBAPP:
            stop_background_server()

    app.aboutToQuit.connect(cleanup)

    # --- INICIAR EL THREAD ---
    recognizer_thread.start()

    if config.DEBUG:
        print("[main] VoiceController iniciado correctamente")
        print(f"[main] PROJECT_ROOT: {PROJECT_ROOT}")
        print(f"[main] COMMANDS_FILE: {COMMANDS_FILE}")
        print(f"[main] LC_NUMERIC: {locale.getlocale(locale.LC_NUMERIC)}")  # Verificar locale

    # --- EJECUTAR ---
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
