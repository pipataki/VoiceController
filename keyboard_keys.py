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
keyboard_keys: envío de teclas y combinaciones por nombre, vía ydotool.

Por qué existe este módulo aparte:
  `ydotool key` NO acepta nombres de tecla ("Return", "ctrl+c"): solo
  acepta CÓDIGOS evdev con su estado, en la forma `28:1 28:0` (pulsar
  y soltar KEY_ENTER). El resto del proyecto ya lo hacía bien a mano
  donde hacía falta (actions.press_enter -> "28:1 28:0",
  actions._scroll_key -> "103"/"108"/...), pero input_action._key_action
  llamaba a `ydotool key ctrl+c`, que ydotool rechaza -- de ahí que las
  teclas especiales declaradas en commands.json ("tab", "intro",
  "escape"...) nunca llegaran a hacer nada (además de que nadie las
  despachaba todavía, ver command_router).

Aquí se centraliza:
  - KEY_CODES: nombre legible -> código evdev
    (linux/input-event-codes.h).
  - parse_key_spec("ctrl+shift+z") -> [29, 42, 44] (modificadores
    primero, tecla final la última).
  - send_key("ctrl+c", repeat=1): construye la secuencia completa
    pulsar-modificadores / pulsar-tecla / soltar-tecla /
    soltar-modificadores y la manda en UNA sola llamada a ydotool.
  - find_ydotool(): misma búsqueda tolerante que ya hacía actions.py
    (PATH + rutas habituales), para no depender de que el PATH heredado
    por el proceso incluya dónde vive el binario.
"""

import os
import shutil
import subprocess

# Rutas absolutas donde puede vivir el binario ydotool si NO aparece en
# el PATH del proceso de VoiceController -- esto pasa a menudo cuando la
# app se arranca desde un acceso directo/autoarranque/icono en vez de
# desde una terminal interactiva, ya que esos lanzadores no siempre
# heredan el PATH ampliado que tiene tu shell (.bashrc/.zshrc). Se
# comprueban en orden, la primera que exista y sea ejecutable gana.
_YDOTOOL_FALLBACK_PATHS = [
    "/usr/bin/ydotool",
    "/usr/local/bin/ydotool",
    os.path.expanduser("~/.local/bin/ydotool"),
    os.path.expanduser("~/.cargo/bin/ydotool"),
]


def find_ydotool() -> str | None:
    """Ruta al binario `ydotool`: primero el PATH actual (se recalcula
    en cada llamada por si el entorno cambia), luego
    _YDOTOOL_FALLBACK_PATHS. None si no aparece en ningún sitio."""
    found = shutil.which("ydotool")
    if found:
        return found
    for candidate in _YDOTOOL_FALLBACK_PATHS:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


# Códigos evdev (linux/input-event-codes.h). Las claves se comparan en
# minúsculas (ver parse_key_spec), así que da igual escribir "Return",
# "return" o "RETURN" en commands.json.
KEY_CODES = {
    # modificadores
    "ctrl": 29, "control": 29, "leftctrl": 29, "rightctrl": 97,
    "shift": 42, "leftshift": 42, "rightshift": 54,
    "alt": 56, "leftalt": 56, "altgr": 100, "rightalt": 100,
    "meta": 125, "super": 125, "win": 125,

    # teclas especiales
    "esc": 1, "escape": 1,
    "backspace": 14, "bksp": 14,
    "tab": 15,
    "enter": 28, "return": 28, "intro": 28,
    "kpenter": 96,
    "space": 57, "spacebar": 57,
    "capslock": 58,
    "insert": 110,
    "delete": 111, "del": 111,
    "home": 102, "end": 107,
    "pageup": 104, "page_up": 104, "prior": 104,
    "pagedown": 109, "page_down": 109, "next": 109,
    "up": 103, "down": 108, "left": 105, "right": 106,
    "printscreen": 99, "sysrq": 99,
    "menu": 127, "compose": 127,

    # símbolos de la fila principal
    "minus": 12, "equal": 13,
    "leftbrace": 26, "rightbrace": 27,
    "semicolon": 39, "apostrophe": 40, "grave": 41,
    "backslash": 43, "comma": 51, "dot": 52, "period": 52, "slash": 53,

    # F1..F12
    "f1": 59, "f2": 60, "f3": 61, "f4": 62, "f5": 63, "f6": 64,
    "f7": 65, "f8": 66, "f9": 67, "f10": 68, "f11": 87, "f12": 88,
}

# letras y dígitos (posición física en un teclado QWERTY)
KEY_CODES.update({
    "a": 30, "b": 48, "c": 46, "d": 32, "e": 18, "f": 33, "g": 34,
    "h": 35, "i": 23, "j": 36, "k": 37, "l": 38, "m": 50, "n": 49,
    "o": 24, "p": 25, "q": 16, "r": 19, "s": 31, "t": 20, "u": 22,
    "v": 47, "w": 17, "x": 45, "y": 21, "z": 44,
    "1": 2, "2": 3, "3": 4, "4": 5, "5": 6, "6": 7, "7": 8, "8": 9,
    "9": 10, "0": 11,
})

# Cuáles de los códigos anteriores son modificadores -- se pulsan ANTES
# y se sueltan DESPUÉS de la tecla final (ver send_key).
_MODIFIER_CODES = frozenset({29, 97, 42, 54, 56, 100, 125, 126})


def soltar_modificadores() -> bool:
    """Suelta ctrl, alt, shift y meta por si alguno se quedo pulsado.

    Hace falta porque una combinacion se manda como una secuencia:
    baja el modificador, pulsa la tecla, sube el modificador. Si ydotool
    muere o se cuelga a mitad, la bajada ya llego al kernel y la subida
    no llega nunca. A partir de ahi el teclado virtual mantiene ese
    modificador pulsado ETERNAMENTE, y el escritorio entero se comporta
    como si tuvieras el dedo clavado en Ctrl: los clics seleccionan en
    vez de pulsar, las letras disparan atajos, nada responde como debe.
    Todo sigue vivo -- el sistema, el escritorio, el programa -- y aun
    asi no puedes hacer nada. Es el fallo perfecto para volverte loco
    buscandolo donde no esta.

    Solo manda subidas (codigo:0). Soltar una tecla que ya estaba
    suelta no hace absolutamente nada, asi que se pueden mandar todas
    sin mirar cual quedo colgada.
    """
    ydotool_bin = find_ydotool()
    if not ydotool_bin:
        return False
    args = [f"{c}:0" for c in sorted(_MODIFIER_CODES)]
    try:
        subprocess.run(
            [ydotool_bin, "key"] + args,
            check=False,
            capture_output=True,
            text=True,
            timeout=_timeout(),
        )
        print("[keyboard_keys] modificadores soltados por precaucion")
        return True
    except Exception as e:
        # Si esto tambien falla, el demonio esta para el arrastre. No se
        # insiste: lo unico que se puede hacer es dejar constancia.
        print(f"[keyboard_keys] no se pudieron soltar los modificadores: {e!r}")
        return False


def _timeout() -> float:
    """Limite de espera para ydotool (config.YDOTOOL_TIMEOUT_S)."""
    try:
        import config
        return float(getattr(config, "YDOTOOL_TIMEOUT_S", 5.0) or 5.0)
    except Exception:
        return 5.0


def parse_key_spec(spec: str) -> list[int] | None:
    """"ctrl+shift+z" -> [29, 42, 44]. Devuelve None si alguna de las
    partes no está en KEY_CODES (mejor no mandar nada que mandar una
    combinación a medias)."""
    if not spec:
        return None
    codes = []
    for part in str(spec).split("+"):
        part = part.strip().lower()
        if not part:
            continue
        code = KEY_CODES.get(part)
        if code is None:
            print(f"[keyboard_keys] tecla desconocida en {spec!r}: {part!r}")
            return None
        codes.append(code)
    return codes or None


def send_key(spec: str, repeat: int = 1) -> bool:
    """Manda la tecla/combinación `spec` (ej. "ctrl+c", "Tab", "Down").

    Este es el punto por el que sale CADA tecla del programa, así que es
    también donde se elige la plataforma: fuera de Linux se delega en el
    backend correspondiente (ver backends/). En Linux sigue el mismo
    camino de siempre -- ydotool con códigos evdev -- sin cambio ninguno.

    Los modificadores se mantienen pulsados durante todas las
    repeticiones y se sueltan al final -- que es justo lo que hace un
    teclado real si dejas el dedo en Ctrl y pulsas la tecla varias
    veces."""
    # Fuera de Linux, la tecla la manda el backend de esa plataforma: los
    # códigos evdev de abajo son del kernel Linux y no significan nada en
    # otro sitio.
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        return backends.get().send_key(spec, repeat)

    codes = parse_key_spec(spec)
    if not codes:
        return False

    modifiers = [c for c in codes if c in _MODIFIER_CODES]
    main = [c for c in codes if c not in _MODIFIER_CODES]
    if not main:
        # solo modificadores ("ctrl" a secas): se pulsa y se suelta tal cual
        main, modifiers = modifiers, []

    ydotool_bin = find_ydotool()
    if not ydotool_bin:
        print("[keyboard_keys] ydotool no encontrado (ni en PATH ni en rutas habituales) -- "
              "comprueba `which ydotool` en la MISMA sesión donde arrancas VoiceController")
        return False

    args = [f"{c}:1" for c in modifiers]
    for _ in range(max(1, int(repeat))):
        args += [f"{c}:1" for c in main]
        args += [f"{c}:0" for c in reversed(main)]
    args += [f"{c}:0" for c in reversed(modifiers)]

    try:
        subprocess.run(
            [ydotool_bin, "key"] + args,
            check=True,
            capture_output=True,
            text=True,
            timeout=_timeout(),
        )
        return True
    except subprocess.TimeoutExpired:
        # subprocess ya ha matado a ydotool al expirar el plazo, asi que
        # la secuencia se ha quedado a medias: es EXACTAMENTE el caso en
        # que un modificador puede haberse quedado pulsado. Se sueltan
        # todos antes de devolver el fallo (ver soltar_modificadores).
        print(f"[keyboard_keys] ydotool no respondió en {_timeout():.0f}s enviando {spec!r} "
              f"-- ¿está vivo ydotoold? (systemctl --user status ydotool.service)")
        if modifiers:
            soltar_modificadores()
        return False
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[keyboard_keys] ydotool falló enviando {spec!r}{': ' + stderr if stderr else ''}")
        return False
    except Exception as e:
        print(f"[keyboard_keys] error inesperado enviando {spec!r}: {e!r}")
        return False
