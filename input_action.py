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
input_action: Módulo parametrizable para acciones de entrada (teclado + posición).

Modos:
  1. Posición + Acción (usa última posición si no se especifica):
     {"action_type": "move" | "click" | "right_click" | "double_click", "position": (45, 3)}
     {"action_type": "scroll_up" | "scroll_down", "position": (45, 3)}

  2. Tecla / combinación:
     {"action_type": "key", "key": "ctrl+c"} 
     {"action_type": "key", "key": "Return"}

  3. Escribir texto:
     {"action_type": "type_text", "text": "Hello world"}

NOTA: Este módulo se importa en actions.py y se llama desde command_router.py
      con parámetros extraídos de commands.json.
"""

import subprocess
import sys
import os

import keyboard_keys


try:
    import grid_vc
except ImportError:
    grid_vc = None


def input_action(action_type: str, last_position=None, **kwargs) -> bool:
    """
    Acciones parametrizables de entrada.

    Args:
        action_type (str): "move", "click", "right_click", "double_click",
                          "scroll_up", "scroll_down", "key", "type_text"
        last_position (tuple): (cell, subcell) — última posición guardada en GUI
        **kwargs: parámetros adicionales según action_type
                 - position: (cell, subcell) para acciones de vc
                 - key: "ctrl+c", "Return", etc para "key"
                 - text: "texto a escribir" para "type_text"

    Returns:
        bool: True si se ejecutó exitosamente, False en caso de error
    """

    if not action_type:
        print("[input_action] Error: action_type no especificado")
        return False

    action_type = action_type.lower().strip()

    # --- ACCIONES DE POSICIÓN (grid_vc) ---
    if action_type in ["move", "click", "right_click", "double_click", "scroll_up", "scroll_down"]:
        return _position_action(action_type, last_position, **kwargs)

    # --- ACCIONES DE TECLADO ---
    elif action_type == "key":
        return _key_action(**kwargs)

    # --- ESCRIBIR TEXTO ---
    elif action_type == "type_text":
        # Delegar a actions.py (type_text), pero lo llamamos con subprocess
        return _type_text_action(**kwargs)

    else:
        print(f"[input_action] Error: action_type '{action_type}' no reconocido")
        return False


def _position_action(action_type: str, last_position: tuple, **kwargs) -> bool:
    """
    Ejecuta acciones en una posición de la rejilla.
    Usa última_posición si no viene position en kwargs.
    """

    # Obtener posición
    position = kwargs.get("position") or last_position
    if not position:
        print("[input_action] Error: No hay posición (falta position en params o última_posición)")
        return False

    if not grid_vc:
        print("[input_action] Error: grid_vc no disponible")
        return False

    try:
        cell, subcell = position
        cell, subcell = int(cell), int(subcell)
    except (TypeError, ValueError):
        print(f"[input_action] Error: Posición inválida: {position}")
        return False

    try:
        if action_type == "move":
            grid_vc.move_to(cell, subcell)
            print(f"[input_action] Movido a {cell}-{subcell}")
            return True

        elif action_type == "click":
            grid_vc.move_to(cell, subcell)
            grid_vc.click_at(cell, subcell)
            print(f"[input_action] Click en {cell}-{subcell}")
            return True

        elif action_type == "right_click":
            grid_vc.move_to(cell, subcell)
            grid_vc.right_click_at(cell, subcell)
            print(f"[input_action] Click derecho en {cell}-{subcell}")
            return True

        elif action_type == "double_click":
            grid_vc.move_to(cell, subcell)
            grid_vc.double_click_at(cell, subcell)
            print(f"[input_action] Doble click en {cell}-{subcell}")
            return True

        elif action_type == "scroll_up":
            grid_vc.move_to(cell, subcell)
            grid_vc.scroll(cell, subcell, "up")
            print(f"[input_action] Scroll arriba en {cell}-{subcell}")
            return True

        elif action_type == "scroll_down":
            grid_vc.move_to(cell, subcell)
            grid_vc.scroll(cell, subcell, "down")
            print(f"[input_action] Scroll abajo en {cell}-{subcell}")
            return True

        else:
            print(f"[input_action] Error: action_type de posición no reconocido: {action_type}")
            return False

    except Exception as e:
        print(f"[input_action] Error en acción de posición '{action_type}': {e}")
        return False


def _key_action(**kwargs) -> bool:
    """
    Envía combinaciones de teclas por NOMBRE, vía keyboard_keys.send_key.

    Soporta:
    - "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+a"
    - "shift+Tab"
    - "Return", "Escape", "Delete", "BackSpace", "Tab", "space"
    - "Left", "Right", "Up", "Down", "Page_Up", "Page_Down"
    - Teclas individuales: "a", "1", etc

    `repeat` (opcional, por defecto 1) repite la pulsación sin soltar
    los modificadores -- lo usan las acciones de scroll, que son varias
    pulsaciones seguidas de la misma flecha.

    NOTA: antes esto llamaba a `ydotool key ctrl+c` directamente, pero
    ydotool NO acepta nombres de tecla, solo códigos evdev con estado
    ("29:1 46:1 46:0 29:0") -- así que ninguna de estas acciones
    llegaba a ejecutarse nunca. La traducción vive ahora en
    keyboard_keys.py, compartida con actions.py.
    """

    key = str(kwargs.get("key", "")).strip()
    if not key:
        print("[input_action] Error: key no especificada")
        return False

    repeat = kwargs.get("repeat", 1)
    ok = keyboard_keys.send_key(key, repeat=repeat)
    if ok:
        print(f"[input_action] Tecla(s): {key}" + (f" x{repeat}" if repeat and int(repeat) > 1 else ""))
    return ok


def _type_text_action(**kwargs) -> bool:
    """
    Escribe texto usando ydotool type.
    Requiere que ydotoold esté corriendo.
    """

    text = kwargs.get("text", "")
    if not text:
        print("[input_action] Error: text no especificado")
        return False

    try:
        # Por la capa de plataforma, no por ydotool directamente: así esto
        # funciona igual en Windows.
        import backends
        if not backends.type_text(text):
            print("[input_action] Error: no se pudo escribir el texto")
            return False
        print(f"[input_action] Texto escrito: {text[:50]}{'...' if len(text) > 50 else ''}")
        return True
    except FileNotFoundError:
        print("[input_action] Error: no hay con qué escribir en esta plataforma")
        return False
    except subprocess.CalledProcessError as e:
        print(f"[input_action] Error al escribir texto: {e}")
        return False


# --- DICCIONARIO DE ACCIONES PREDEFINIDAS ---
# Para usarlo en commands.json sin tener que escribir todo el JSON:
# En lugar de {"action_type": "key", "key": "ctrl+c"},
# solo {"action": "copy"} si está en este diccionario

# Cuántas pulsaciones de flecha manda un "scroll <dirección>" por
# teclado (ver más abajo). 5 es lo que se siente como "una rueda de
# ratón" en la mayoría de apps sin llegar a saltar de página.
SCROLL_KEY_REPEAT = 5

PREDEFINED_ACTIONS = {
    "copy": {"action_type": "key", "key": "ctrl+c"},
    "paste": {"action_type": "key", "key": "ctrl+v"},
    "cut": {"action_type": "key", "key": "ctrl+x"},
    "select_all": {"action_type": "key", "key": "ctrl+a"},
    "undo": {"action_type": "key", "key": "ctrl+z"},
    "redo": {"action_type": "key", "key": "ctrl+shift+z"},

    "save": {"action_type": "key", "key": "ctrl+s"},
    "open": {"action_type": "key", "key": "ctrl+o"},
    "close": {"action_type": "key", "key": "ctrl+w"},
    "quit": {"action_type": "key", "key": "alt+F4"},

    "find": {"action_type": "key", "key": "ctrl+f"},
    "replace": {"action_type": "key", "key": "ctrl+h"},

    "delete": {"action_type": "key", "key": "Delete"},
    "backspace": {"action_type": "key", "key": "BackSpace"},
    "tab": {"action_type": "key", "key": "Tab"},
    "enter": {"action_type": "key", "key": "Return"},
    "escape": {"action_type": "key", "key": "Escape"},

    "home": {"action_type": "key", "key": "Home"},
    "end": {"action_type": "key", "key": "End"},
    "page_up": {"action_type": "key", "key": "Page_Up"},
    "page_down": {"action_type": "key", "key": "Page_Down"},

    "up": {"action_type": "key", "key": "Up"},
    "down": {"action_type": "key", "key": "Down"},
    "left": {"action_type": "key", "key": "Left"},
    "right": {"action_type": "key", "key": "Right"},

    "space": {"action_type": "key", "key": "space"},
    "insert": {"action_type": "key", "key": "Insert"},
    "shift_tab": {"action_type": "key", "key": "shift+Tab"},

    # Scroll por teclado: MISMA técnica que ya usaba el tablero para sus
    # "scroll arriba/abajo/izquierda/derecha" (ver actions._scroll_key,
    # que manda las flechas 103/108/105/106) -- ydotool no expone la
    # rueda del ratón, así que "scroll" siempre ha sido flechas aquí.
    # La diferencia con "arriba"/"abajo" sueltas es el `repeat`: varias
    # pulsaciones seguidas, para que se note como un desplazamiento y no
    # como mover el cursor una línea.
    # --- archivos, sobre la aplicación que tenga el foco ---
    "save_as": {"action_type": "key", "key": "ctrl+shift+s"},
    "new_file": {"action_type": "key", "key": "ctrl+n"},
    "print": {"action_type": "key", "key": "ctrl+p"},
    "select_none": {"action_type": "key", "key": "ctrl+shift+a"},
    "duplicate": {"action_type": "key", "key": "ctrl+d"},
    "refresh": {"action_type": "key", "key": "F5"},
    "rename": {"action_type": "key", "key": "F2"},
    "next_tab": {"action_type": "key", "key": "ctrl+Tab"},
    "prev_tab": {"action_type": "key", "key": "ctrl+shift+Tab"},
    "switch_window": {"action_type": "key", "key": "alt+Tab"},

    "scroll_up": {"action_type": "key", "key": "Up", "repeat": SCROLL_KEY_REPEAT},
    "scroll_down": {"action_type": "key", "key": "Down", "repeat": SCROLL_KEY_REPEAT},
    "scroll_left": {"action_type": "key", "key": "Left", "repeat": SCROLL_KEY_REPEAT},
    "scroll_right": {"action_type": "key", "key": "Right", "repeat": SCROLL_KEY_REPEAT},
}


