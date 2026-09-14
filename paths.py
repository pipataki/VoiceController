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
paths.py: Módulo central de rutas para VoiceController.

Este módulo detecta automáticamente la ubicación del proyecto y proporciona
todas las rutas relativas como variables globales, para que funcione desde
cualquier directorio sin necesidad de hardcodear rutas.

Uso:
    from paths import PROJECT_ROOT, WEBAPP_DIR, COMMANDS_FILE, etc.

Ventajas:
    - Portable: funciona desde cualquier ubicación
    - Una fuente de verdad: todas las rutas se definen en un único lugar
    - Fácil de modificar: cambiar una variable afecta a todo el proyecto
    - Automático: no requiere configuración manual
"""

import os
import sys
from pathlib import Path

# ==============================================================================
# DETECCIÓN AUTOMÁTICA DEL ROOT_PATH
# ==============================================================================
# PROJECT_ROOT es el directorio donde está ubicado este archivo (paths.py).
# Al estar en la raíz del proyecto, todas las otras carpetas se definen
# relativamente a partir de aquí.

PROJECT_ROOT = Path(__file__).parent.absolute()

# ==============================================================================
# DIRECTORIOS DEL PROYECTO
# ==============================================================================

# Carpeta de la webapp (Flask, HTML, config)
WEBAPP_DIR = PROJECT_ROOT / "webapp"
WEBAPP_STATIC_DIR = WEBAPP_DIR / "static"

# Carpeta para uploads de la webapp
WEBAPP_UPLOADS_DIR = PROJECT_ROOT / "webapp_uploads"

# Carpeta del tablero de 100 casillas (Sección 1 del manual): "tablero.png"
# (captura completa del escritorio) y "casilla.png" (recorte de la casilla
# seleccionada), siempre sobrescritos -- solo existen estos 2 archivos ahí.
# Va DENTRO de la carpeta estática de la webapp (webapp/app.py sirve con
# static_url_path=""), así que Flask ya los sirve solo, sin streaming de
# escritorio ni rutas a medida: /board/tablero.png y /board/casilla.png.
BOARD_DIR = WEBAPP_STATIC_DIR / "board"
TABLERO_FILE = BOARD_DIR / "tablero.png"
CASILLA_FILE = BOARD_DIR / "casilla.png"
# Captura de SOLO la ventana del GUI (no del escritorio completo, ver
# TABLERO_FILE) -- se guarda en la misma carpeta que tablero.png/casilla.png
# para que Flask la sirva igual de gratis en /board/vc.png, sin ruta nueva.
# La usa la webapp para mostrar un espejo del GUI en vez del escritorio
# entero (que en móvil se ve minúsculo) -- ver gui.py:
# GUI._maybe_capture_vc_snapshot().
VC_FILE = BOARD_DIR / "vc.png"

# Recorte de UN CUARTO del escritorio (5x5 casillas, la mitad del ancho y
# la mitad del alto de la rejilla 10x10) alrededor de la casilla
# seleccionada, SIN numerar ni dibujar rejilla -- término medio de zoom
# entre tablero.png (todo el escritorio) y casilla.png (una sola
# casilla). Ver board.capture_zoom_out() y el comando de voz "menos
# zoom"/"zoom out". Misma carpeta que las demás capturas, servida igual
# de gratis por Flask en /board/zoom_out.png.
ZOOM_OUT_FILE = BOARD_DIR / "zoom_out.png"

# Vista "foco": la ventana en la que se estaba trabajando, recortada a la
# misma proporcion que el escritorio para que el touchpad del movil siga
# funcionando igual (ver board.capture_foco y el comando de voz "foco").
FOCO_FILE = BOARD_DIR / "foco.png"

# Que vista esta ensenando el GUI ahora mismo ("overview", "cell",
# "zoom_out" o "foco"). Lo escribe gui.py al cambiar de modo, y lo lee
# tools/guardar_capturas.py para guardar solo la vista que interese.
# Un fichero de una linea: hace falta que lo pueda leer OTRO proceso.
ESTADO_VISTA_FILE = BOARD_DIR / "vista_actual.txt"

# ==============================================================================
# ARCHIVOS DE CONFIGURACIÓN
# ==============================================================================

# Archivo principal de comandos de voz.
COMMANDS_FILE = PROJECT_ROOT / "commands.json"

# Nombres de ventana conocidos para el comando de voz "trae <nombre>"
# (ver command_router._try_parse_bring_window / window_names.py) --
# mapea la forma normalizada de un nombre dicho (ej. "kate") a su
# capitalización REAL de título de ventana (ej. "Kate"), para que
# `kdotool` (que compara contra el título tal cual, ver
# actions.activate_window_by_name) lo encuentre bien. Separado a
# propósito de corrections.json (ese es para el aprendizaje de
# correcciones de palabra del dictado, un sistema totalmente distinto;
# mezclar aquí lo llenaría de entradas que no tienen nada que ver).
WINDOW_NAMES_FILE = PROJECT_ROOT / "window_names.json"

# Configuración de la webapp
WEBAPP_CONFIG_FILE = PROJECT_ROOT / "webapp_config.json"

# Etiquetas de la interfaz por idioma (ES/EN), común para GUI y webapp --
# ver labels.json. Al cambiar el idioma activo en las preferencias, la
# interfaz se actualiza sola (gui.set_ui_language()).
LABELS_FILE = PROJECT_ROOT / "labels.json"

# Correcciones de palabra aprendidas ("corregir <numero> <modificador>
# [ambiguo]", ver corrections.py y command_router._correct_word):
# diccionario global {"strict": {...}, "ambiguous": {...}}, se auto-crea
# la primera vez que se aprende una corrección.
CORRECTIONS_FILE = PROJECT_ROOT / "corrections.json"

# Iconos del tablero (compás de 8 direcciones + botones izquierdo/derecho),
# cada uno con estado Activado (verde, casilla seleccionada) y Desactivado
# (gris, sin casilla seleccionada). El GUI de escritorio los lee de aquí;
# se copian también a webapp/static/icons/ para que la webapp los sirva.
ICONS_DIR = PROJECT_ROOT / "icons"
WEBAPP_ICONS_DIR = WEBAPP_STATIC_DIR / "icons"

# Archivos HTTPS autofirmados (generados en primer uso)
WEBAPP_CERT_FILE = PROJECT_ROOT / "webapp_cert.pem"
WEBAPP_KEY_FILE = PROJECT_ROOT / "webapp_key.pem"

# ==============================================================================
# MÓDULOS DEL PROYECTO
# ==============================================================================

# Ubicación de grid_vc.py (puede estar en mismo root o en subdirectorio)

# ==============================================================================
# ASEGURAR QUE LOS DIRECTORIOS EXISTEN
# ==============================================================================

def ensure_directories():
    """Crea los directorios necesarios si no existen."""
    for directory in [WEBAPP_DIR, WEBAPP_STATIC_DIR, WEBAPP_UPLOADS_DIR, BOARD_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


# ==============================================================================
# AÑADIR PROJECT_ROOT A sys.path PARA IMPORTACIONES
# ==============================================================================
# Esto permite que los módulos se importen sin necesidad de especificar rutas

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# INFORMACIÓN DE DEBUG
# ==============================================================================

def get_paths_info() -> dict:
    """Retorna un diccionario con toda la información de rutas."""
    return {
        "PROJECT_ROOT": str(PROJECT_ROOT),
        "WEBAPP_DIR": str(WEBAPP_DIR),
        "WEBAPP_STATIC_DIR": str(WEBAPP_STATIC_DIR),
        "WEBAPP_UPLOADS_DIR": str(WEBAPP_UPLOADS_DIR),
        "BOARD_DIR": str(BOARD_DIR),
        "COMMANDS_FILE": str(COMMANDS_FILE),
        "CORRECTIONS_FILE": str(CORRECTIONS_FILE),
        "WEBAPP_CONFIG_FILE": str(WEBAPP_CONFIG_FILE),
        "WEBAPP_CERT_FILE": str(WEBAPP_CERT_FILE),
        "WEBAPP_KEY_FILE": str(WEBAPP_KEY_FILE),
    }


def print_paths_info():
    """Imprime la información de rutas de forma legible."""
    print("\n" + "="*70)
    print("VoiceController - INFORMACIÓN DE RUTAS")
    print("="*70)
    info = get_paths_info()
    for key, value in info.items():
        exists = "✓" if Path(value).exists() else "✗"
        print(f"{exists} {key:25} {value}")
    print("="*70 + "\n")


# ==============================================================================
# INICIALIZACIÓN AL IMPORTAR
# ==============================================================================

# Crear directorios necesarios al importar este módulo
ensure_directories()

# DEBUG: descomentar la siguiente línea para ver las rutas al iniciar
# print_paths_info()
