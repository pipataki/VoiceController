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
actions: Acciones ejecutables desde comandos (voz, directos, táctiles...).

Módulos:
  - board: geometría/captura/recorte del tablero de 100 casillas (Sección 1
    del manual) -- select_board_cell/nudge_board_marker/fire_board_action
  - grid_vc: rejilla antigua a pantalla completa (solo para el
    move_pointer_physical()
  - type_text: escribe como si fuera teclado (ydotool type)
  - run_terminal_command: ejecuta comando de shell
  - launch_app: abre una aplicación
  - input_action: acciones parametrizables de teclado + posición
"""

import shlex
import shutil
import subprocess
import re
import sys
import os
import threading
import time
# import pyatspi

import config
import keyboard_keys


from paths import (
    PROJECT_ROOT,
    COMMANDS_FILE,
    WEBAPP_CONFIG_FILE,
    print_paths_info,
)


from PySide6.QtCore import QTimer


try:
    import input_action
    import grid_vc
except ImportError:
    grid_vc = None

import board



def copy_to_clipboard(text: str) -> bool:
    """API pública: copia texto al portapapeles del sistema (wl-copy /
    xclip / xsel, el primero disponible). Usada por el campo "Texto" del
    GUI (acciones "copiar texto" / "seleccionar texto")."""
    return _copy_to_clipboard_cmd(text)


def _copy_to_clipboard_cmd(text: str) -> bool:
    """Copia al portapapeles con la primera herramienta que haya.

    Las tres llevan limite de espera. No es capricho: estos programas
    se quedan sujetando la seleccion mientras alguien pueda pegarla, y
    si el gestor del portapapeles no responde como se espera, la
    llamada se queda ahi colgada. Y este camino es justo el que usa el
    dictado con acentos y enes -- o sea, casi todo lo que se dicta en
    castellano. Colgarse aqui seria colgarse escribiendo.

    Un TimeoutExpired se trata como un fallo de esa herramienta y se
    prueba la siguiente, igual que si no estuviera instalada."""
    fallos = (FileNotFoundError, subprocess.TimeoutExpired)
    espera = _timeout_ydotool()
    try:
        subprocess.run(["wl-copy"], input=text.encode(), check=True, timeout=espera)
        return True
    except fallos:
        pass
    try:
        subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(),
                       check=True, timeout=espera)
        return True
    except fallos:
        pass
    try:
        subprocess.run(["xsel", "-b"], input=text.encode(), check=True, timeout=espera)
        return True
    except fallos:
        pass
    return False




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


def _find_ydotool() -> str | None:
    """Devuelve la ruta al binario `ydotool`, buscando primero en el
    PATH actual (shutil.which, se recalcula en cada llamada por si el
    entorno cambia) y si no aparece ahí, probando _YDOTOOL_FALLBACK_PATHS.
    None si no se encuentra en ningún sitio.

    La búsqueda vive en keyboard_keys.py para que actions.py e
    input_action.py compartan exactamente el mismo criterio (antes cada
    uno lo hacía a su manera: input_action llamaba a "ydotool" a secas y
    fallaba con FileNotFoundError en cuanto el PATH heredado no lo
    incluía). _YDOTOOL_FALLBACK_PATHS se conserva arriba solo como
    documentación de las rutas que se prueban."""
    return keyboard_keys.find_ydotool()


def _timeout_ydotool() -> float:
    """Cuanto se espera a ydotool antes de darlo por perdido.

    Sin limite, si el demonio enmudece la llamada se queda esperando
    para siempre en el hilo que la hizo, y el programa te oye pero no
    obedece. Ver config.YDOTOOL_TIMEOUT_S."""
    try:
        return float(getattr(config, "YDOTOOL_TIMEOUT_S", 5.0) or 5.0)
    except Exception:
        return 5.0


def _timeout_escribir(text: str) -> float:
    """Igual que _timeout_ydotool, pero para `ydotool type`.

    Escribir va caracter a caracter, asi que un dictado largo tarda de
    verdad: el limite crece con el texto en vez de ser fijo. Si fuese
    fijo, cortaria por la mitad las frases largas, que es peor que no
    tener limite."""
    base = _timeout_ydotool()
    try:
        por_caracter = float(getattr(config, "YDOTOOL_SEGUNDOS_POR_CARACTER", 0.05) or 0.05)
    except Exception:
        por_caracter = 0.05
    return base + len(text or "") * por_caracter


# ---------------------------------------------------------------------------
# Escribir texto que ydotool no sabe escribir
# ---------------------------------------------------------------------------
#
# MEDIDO el 2-sep-2026, fuera del programa:
#
#     $ ydotool type '¿Hola? ñ á'
#     Hola_
#
# ydotool no manda letras: manda POSICIONES DE TECLA, traducidas con una
# tabla fija de teclado ingles. Lo que no esta en ese teclado lo tira sin
# avisar. En un programa de dictado en espanol eso significa que los acentos
# y las eñes se perdian en silencio.
#
# Se probaron las alternativas antes de elegir:
#   - kdotool: solo maneja ventanas, no escribe.
#   - wtype:   instalado, pero KWin no soporta el protocolo que necesita
#              ("Compositor does not support the virtual keyboard protocol").
#              Habria sido lo mas limpio; si algun dia KWin lo soporta, es
#              el camino al que volver.
#   - dotool:  no esta empaquetado.
#
# Queda el portapapeles, que ademas se comporta igual en cualquier escritorio.

# Lo que ydotool SI escribe bien: letras y numeros ingleses, espacio, y los
# dos signos que ocupan la misma tecla en las distribuciones habituales.
# Todo lo demas va por el portapapeles. Se prefiere quedarse corto: teclear
# de mas rompe el texto en silencio, y pegar de mas solo cuesta un instante.
_TECLEABLES = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    " .,\n\t"
)

# Ventanas donde ctrl+v NO pega: en una terminal es ctrl+shift+v.
_TERMINALES = ("konsole", "yakuake", "terminal", "kitty", "alacritty",
               "xterm", "tilix", "gnome-terminal", "ptyxis", "wezterm")


def _necesita_portapapeles(text: str) -> bool:
    """¿Hay que pasar por el portapapeles para escribir esto?

    SOLO en Linux. Windows escribe con KEYEVENTF_UNICODE (ver
    backends/windows.py `_unidades`), que manda CARACTERES y no posiciones
    de tecla: alli los acentos y las eñes salen bien tecleandolos, y el
    rodeo por el portapapeles no solo sobraria -- usa herramientas de
    Wayland (`wl-copy`) que en Windows no existen, asi que fallaria y
    acabaria tecleando igualmente, con un error de por medio.

    Es justo el tipo de cosa que se cuela al portar: un arreglo correcto en
    un sistema, aplicado donde el problema no existe.
    """
    import sys as _sys
    if _sys.platform.startswith("win"):
        return False
    return any(c not in _TECLEABLES for c in text)


def _es_terminal() -> bool:
    """¿La ventana de delante es una terminal? Decide entre ctrl+v y
    ctrl+shift+v. Ante la duda dice que no: ctrl+v es lo normal."""
    try:
        import backends
        geo = backends.focused_window_geometry(excluir="")
        titulo = (geo[4] if geo else "").lower()
    except Exception:
        return False
    return any(t in titulo for t in _TERMINALES)


def _leer_portapapeles() -> str:
    try:
        r = subprocess.run(["wl-paste", "--no-newline"], capture_output=True, timeout=2)
        return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""
    except Exception:
        return ""


def _pegar_por_portapapeles(text: str) -> bool:
    """Deja el texto en el portapapeles y lo pega. Devuelve True si se pego.

    Se guarda lo que hubiera antes y se devuelve despues: pisarle a alguien
    lo que tenia copiado, sin avisar, es de las cosas que mas molestan.
    """
    anterior = _leer_portapapeles()
    if not _copy_to_clipboard_cmd(text):
        print("[actions] no se pudo copiar al portapapeles")
        return False

    atajo = "ctrl+shift+v" if _es_terminal() else "ctrl+v"
    try:
        import backends
        backends.send_key(atajo)
    except Exception as exc:
        print(f"[actions] no se pudo pegar con {atajo}: {exc!r}")
        return False

    # Se devuelve lo de antes, pero no al instante: la aplicacion todavia
    # esta leyendo el portapapeles cuando termina el atajo.
    if anterior:
        def _devolver():
            time.sleep(1.0)
            _copy_to_clipboard_cmd(anterior)
        threading.Thread(target=_devolver, daemon=True).start()
    return True


def type_text(text: str):
    """Escribe texto usando ydotool type (requiere ydotoold corriendo).
    ydotool inyecta eventos de teclado a nivel de dispositivo virtual
    (uinput): el compositor los entrega a lo que TENGA EL FOCO en ese
    momento, da igual de qué proceso sea -- no hace falta (ni hay forma
    fiable en Wayland) de comprobar qué ventana está enfocada antes de
    escribir. Si quieres asegurarte de que el foco esté en una ventana en
    concreto antes de llamar a esto, usa antes activate_target_window()
    (ver config.PASTE_TARGET_WINDOW_REGEX).

    El binario se busca con _find_ydotool() en vez de confiar en que
    "ydotool" esté en el PATH heredado por el proceso -- si VoiceController
    se lanza desde un acceso directo/autoarranque en vez de una terminal,
    el PATH puede no incluir dónde vive `ydotool` aunque funcione bien a
    mano en tu shell. Si falla por CUALQUIER motivo (no se encuentra el
    binario, ydotoold no está corriendo, permisos...) el texto NUNCA se
    pierde: cae al portapapeles."""
    if not text:
        return
    # En Windows no hay ydotool: se delega en la capa de plataforma, igual
    # que hace keyboard_keys.send_key. Se hace aquí y no en el llamante para
    # que todo el proyecto siga escribiendo con una sola función.
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        if not backends.get().type_text(text):
            _copy_to_clipboard_cmd(text)
        return
    # Si el texto lleva algo que ydotool no sabe escribir -- acentos, eñes,
    # signos espanoles -- se pega desde el portapapeles. Tecleandolo se
    # perderia sin avisar (ver el comentario grande de arriba).
    if _necesita_portapapeles(text):
        if _pegar_por_portapapeles(text):
            return
        print("[actions] no se pudo pegar; se intenta teclear, "
              "aunque puede perder acentos")

    ydotool_bin = _find_ydotool()
    if not ydotool_bin:
        print("[actions] ydotool no encontrado (ni en PATH ni en rutas habituales), "
              "copiando al portapapeles -- comprueba `which ydotool` en la MISMA "
              "terminal/entorno desde el que arrancas VoiceController")
        _copy_to_clipboard_cmd(text)
        return
    try:
        subprocess.run(
            [ydotool_bin, "type", text],
            timeout=_timeout_escribir(text),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[actions] ydotool falló (código {e.returncode}){': ' + stderr if stderr else ''} "
              f"-- copiando al portapapeles")
        _copy_to_clipboard_cmd(text)
    except Exception as e:
        print(f"[actions] Error inesperado escribiendo con ydotool: {e!r} -- copiando al portapapeles")
        _copy_to_clipboard_cmd(text)


# Acciones sobre la ventana que TENGA EL FOCO, vía kdotool (KWin/D-Bus).
# `windowstate` cambia propiedades; el resto son órdenes directas.
_WINDOW_ACTIONS = {
    "minimize":   ["windowminimize"],
    "maximize":   ["windowstate", "--add", "maximized"],
    "unmaximize": ["windowstate", "--remove", "maximized"],
    "fullscreen": ["windowstate", "--toggle", "fullscreen"],
    "close":      ["windowclose"],
    "raise":      ["windowraise"],
    "above":      ["windowstate", "--toggle", "above"],
}


def _poner_encima_windows(titulo: str, encima: bool) -> bool:
    """Lo mismo que hace KWin, en Windows: "siempre encima" si o no.

    POR QUE NO SE ACTIVA LA VENTANA, que seria lo obvio: Windows impide a
    proposito que un programa se ponga delante de la ventana activa por su
    cuenta (el bloqueo del primer plano). SetForegroundWindow falla, la
    barra de tareas parpadea y la ventana se queda donde estaba. Asi le
    fallaba a pipataki "trae control" en la VM el 12-sep-2026.

    Cambiar el orden de apilamiento con SetWindowPos NO necesita ese
    permiso. Marcar HWND_TOPMOST y desmarcarlo acto seguido la deja delante
    de todas las ventanas normales, y SIN QUITARLE EL FOCO a la que lo
    tenia -- que es justo lo que hace falta: se ve el GUI y las teclas
    siguen yendo al Bloc de notas.

    Se busca por titulo EXACTO (FindWindowW), no por "contiene": es para
    nuestra propia ventana y su titulo es fijo.
    """
    try:
        import ctypes
        from ctypes import wintypes as _w
        u = ctypes.windll.user32
        u.FindWindowW.argtypes = [_w.LPCWSTR, _w.LPCWSTR]
        u.FindWindowW.restype = _w.HWND
        u.SetWindowPos.argtypes = [_w.HWND, _w.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        hwnd = u.FindWindowW(None, titulo)
        if not hwnd:
            return False
        HWND_TOPMOST, HWND_NOTOPMOST = _w.HWND(-1), _w.HWND(-2)
        # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
        banderas = 0x0001 | 0x0002 | 0x0010 | 0x0040
        return bool(u.SetWindowPos(hwnd, HWND_TOPMOST if encima else HWND_NOTOPMOST,
                                   0, 0, 0, 0, banderas))
    except Exception as exc:
        print(f"[actions] no se pudo poner la ventana encima en Windows: {exc!r}")
        return False


def poner_ventana_encima(titulo: str, encima: bool = True) -> bool:
    """Marca o desmarca "siempre encima" la ventana que se llame `titulo`.

    A diferencia de window_action(), esto NO actua sobre la ventana con
    foco: la busca por nombre. Sirve para que el panel del modo servicio se
    vea por encima de lo que haya abierto SIN minimizarlo ni quitarle el
    foco del teclado.

    Bajo Wayland un cliente no puede subirse solo de forma fiable
    (Qt.raise_() no basta contra una ventana maximizada), asi que se le
    pide a KWin por kdotool. Si kdotool no esta, no pasa nada: la ventana
    se vera igual, solo que puede quedar detras.
    """
    import sys as _sys
    if _sys.platform.startswith("win"):
        return _poner_encima_windows(titulo, encima)
    binario = shutil.which("kdotool")
    if not binario:
        return False
    try:
        r = subprocess.run([binario, "search", "--title", titulo],
                           capture_output=True, text=True, timeout=3)
        ids = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if not ids:
            return False
        # El ultimo es el mas reciente, por si quedara alguno de antes.
        subprocess.run([binario, "windowstate",
                        "--add" if encima else "--remove", "above", ids[-1]],
                       capture_output=True, text=True, timeout=3)
        return True
    except Exception as exc:
        print(f"[actions] no se pudo poner la ventana encima: {exc!r}")
        return False


def window_action(kind: str) -> bool:
    """Aplica `kind` a la ventana que tenga el foco ahora mismo
    (minimizar, maximizar, cerrar...).

    Se hace con kdotool y NO con atajos de teclado porque minimizar o
    maximizar no tienen un atajo estándar: cada escritorio y cada tema
    usa el suyo, y muchos vienen sin asignar. Cerrar sí lo tiene
    (Alt+F4), pero se hace por el mismo camino para que todas se
    comporten igual.

    SALVAGUARDA: si la ventana con foco resulta ser el propio
    VoiceController, no se hace nada. VoiceController normalmente no se
    lleva el foco (Qt.WA_ShowWithoutActivating), pero si el usuario ha
    hecho clic en él, un "cierra ventana" dicho para otra aplicación
    cerraría el programa que está usando para hablar -- y quedaría sin
    forma de deshacerlo.
    """
    cmd = _WINDOW_ACTIONS.get(kind)
    if cmd is None:
        print(f"[actions] acción de ventana no reconocida: {kind!r}")
        return False
    kdotool = shutil.which("kdotool")
    if not kdotool:
        print("[actions] kdotool no está instalado: no se pueden manejar ventanas")
        return False
    try:
        nombre = subprocess.run(
            [kdotool, "getactivewindow", "getwindowname"],
            capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        nombre = ""
    if nombre and "voicecontroller" in nombre.lower():
        print(f"[actions] '{kind}' ignorado: la ventana con foco es el propio "
              "VoiceController")
        return False
    try:
        res = subprocess.run([kdotool, "getactivewindow"] + cmd,
                             capture_output=True, text=True, timeout=5)
        ok = res.returncode == 0
        print(f"[actions] ventana '{nombre or '?'}': {kind} -> "
              f"{'OK' if ok else (res.stderr or '').strip()[:80]}")
        return ok
    except Exception as exc:
        print(f"[actions] error en la acción de ventana {kind!r}: {exc!r}")
        return False


# ---------------------------------------------------------------------------
# La ventana a la que va el texto dictado
# ---------------------------------------------------------------------------
#
# POR QUE ESTO EXISTE, que es lo interesante.
#
# El pegado del dictado funcionaba, en modo ventana, POR CASUALIDAD. Antes de
# teclear se llama a gui.apartar_ventana(): al minimizarse
# VoiceController, KWin le devuelve el foco a la ventana de debajo, y el
# texto acierta. Nadie pidio ese foco nunca -- es un efecto colateral de
# minimizar.
#
# Se descubrio el 5-sep-2026 al hacer el modo servicio: sin ventana que
# minimizar, el efecto desaparecio y el dictado se perdia. Y de paso quedo a
# la vista que llevaba funcionando asi desde el primer dia.
#
# Que funcione por casualidad no es un fallo mientras funciona; es una
# fragilidad dormida. El dia que alguien cambie como se minimiza, el pegado
# se rompe y nadie sabra por que.
#
# Asi que se hace EXPLICITO, y en los dos modos: se recuerda cual es la
# ventana del usuario y se activa a proposito antes de escribir.

_NUESTRAS = ("VoiceController",)          # todas las nuestras empiezan asi
_ventana_destino = None                   # la ultima ventana AJENA que estuvo activa


def _nombre_de(ventana: str) -> str:
    kdotool = shutil.which("kdotool")
    if not kdotool or not ventana:
        return ""
    try:
        r = subprocess.run([kdotool, "getwindowname", ventana],
                           capture_output=True, text=True, timeout=3)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def ventana_activa_ajena():
    """Id de la ventana activa si NO es una nuestra; None en otro caso."""
    kdotool = shutil.which("kdotool")
    if not kdotool:
        return None
    try:
        r = subprocess.run([kdotool, "getactivewindow"],
                           capture_output=True, text=True, timeout=3)
        w = (r.stdout or "").strip()
        if not w:
            return None
        nombre = _nombre_de(w)
        if any(nombre.startswith(x) for x in _NUESTRAS):
            return None
        return w
    except Exception:
        return None


def recordar_ventana_destino() -> bool:
    """Apunta la ventana del usuario, si ahora mismo hay una activa.

    Se llama en los momentos en que el usuario esta MIRANDO donde quiere
    escribir: al empezar a dictar y al entrar en la vista foco. Ahi la
    ventana activa es la buena; mas tarde, con vcs por medio, ya no.
    """
    global _ventana_destino
    w = ventana_activa_ajena()
    if w:
        _ventana_destino = w
        return True
    return False


def asegurar_ventana_destino() -> bool:
    """Antes de escribir: que el foco NO este en una ventana nuestra.

    Si ya esta en una ajena, no se toca nada -- lo que hubiera pasado por
    minimizar, o porque el usuario acaba de pinchar ahi, vale igual.

    Si esta en una nuestra, se activa la que se recordo. Devuelve True si el
    foco quedo en una ventana ajena.
    """
    if ventana_activa_ajena():
        return True
    if not _ventana_destino:
        print("[actions] el foco esta en una ventana de VoiceController y no "
              "hay ninguna recordada: el texto puede perderse")
        return False
    kdotool = shutil.which("kdotool")
    if not kdotool:
        return False
    try:
        subprocess.run([kdotool, "windowactivate", _ventana_destino],
                       capture_output=True, text=True, timeout=3)
        print(f"[actions] foco devuelto a la ventana destino "
              f"({_nombre_de(_ventana_destino)[:40]!r})")
        return True
    except Exception as e:
        print(f"[actions] no se pudo activar la ventana destino: {e!r}")
        return False


def minimize_active_window() -> bool:
    """Minimiza la ventana actualmente activa/con foco (la que esté
    ocupando el escritorio) usando `kdotool getactivewindow
    windowminimize` -- mismo mecanismo que activate_window_by_name()
    (KWin vía D-Bus), pero en vez de activar una ventana por nombre,
    minimiza la que YA esté delante en este momento, sea cual sea.

    Pensada como alternativa/complemento a bring_to_front(): si activar
    VoiceController por encima de otra ventana maximizada no basta,
    quitar de en medio esa otra ventana sí funciona siempre. La usa
    gui.bring_to_front() automáticamente antes de intentar mostrarse.

    Devuelve True si se pudo LANZAR kdotool sin error (no garantiza
    que hubiera una ventana activa que minimizar); False si kdotool no
    está instalado o falló al lanzarse."""
    binary = shutil.which("kdotool")
    if not binary:
        print("[actions] kdotool no encontrado en PATH -- no se puede "
              "minimizar la ventana activa (ver activate_window_by_name "
              "para instrucciones de instalación)")
        return False
    try:
        subprocess.run(
            [binary, "getactivewindow", "windowminimize"],
            check=True,
            timeout=3,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.TimeoutExpired:
        print("[actions] kdotool tardó demasiado en responder (minimizar ventana activa)")
        return False
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[actions] Error minimizando la ventana activa con kdotool"
              f"{': ' + stderr if stderr else ''} -- ¿hay alguna ventana activa?")
        return False


def activate_window_by_name(name: str, permitir_propia: bool = False) -> bool:
    """Intenta traer al frente/activar la ventana cuyo TÍTULO contenga
    `name` usando `kdotool` (https://github.com/jinliu/kdotool) --
    kdotool ya compara sin distinguir mayúsculas/minúsculas por defecto
    (no hace falta pedírselo aparte; ver nota importante más abajo sobre
    NO anteponer "(?i)" al patrón). NO se puede hacer con
    `kstart`/kde-cli-tools: en KDE Frameworks 6, kstart se reescribió
    como puro lanzador de aplicaciones NUEVAS y perdió por completo las
    opciones --window/--windowclass/--activate que tenía en KF5 (esto se
    comprobó directamente en el código fuente de kde-cli-tools, y
    coincide con el error real "Opciones desconocidas: window, activate"
    que da kstart en KF6/Plasma 6).

    kdotool SÍ sirve para esto en Plasma 6/Wayland: genera un script de
    KWin al vuelo y lo ejecuta a través de la interfaz D-Bus de KWin.
    Instalación: `cargo install kdotool` (necesita Rust/cargo), o
    descargar el binario ya compilado desde
    https://github.com/jinliu/kdotool/releases

    Usada tanto por activate_target_window() (config.PASTE_TARGET_WINDOW_REGEX,
    fijo) como por command_router._try_parse_bring_window() (comando de
    voz "trae <nombre>"/"traer <nombre>", nombre dicho en el momento).

    Devuelve True si se pudo LANZAR kdotool sin error (no garantiza al
    100% que la ventana se haya activado -- si kdotool no encuentra
    ninguna ventana que coincida, termina sin error pero tampoco activa
    nada); False si `name` está vacío, kdotool no está instalado, o
    falló al lanzarse."""
    if not name or not name.strip():
        return False
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        return backends.get().activate_window(name)
    binary = shutil.which("kdotool")
    if not binary:
        print("[actions] kdotool no encontrado en PATH -- instálalo con "
              "`cargo install kdotool` o descarga el binario desde "
              "https://github.com/jinliu/kdotool/releases para poder "
              "activar ventanas por nombre (kstart ya no sirve para esto en KF6)")
        return False
    # NADA de anteponer "(?i)": el script que genera kdotool es
    # JAVASCRIPT (motor de scripting de KWin), no Rust/PCRE -- "(?i)" no
    # es sintaxis válida ahí y rompía el script generado (causaba el
    # error de D-Bus "No such object path" que se vio al probarlo).
    # kdotool YA compara sin distinguir mayúsculas por defecto (se ve en
    # su propio script generado: `const match_case = false;`), así que
    # no hace falta añadir nada -- solo se escapan caracteres especiales
    # de regex por seguridad.
    pattern = re.escape(name.strip())
    try:
        # PRIMERO SE BUSCA, Y SE MIRA SI HAY ALGO.
        #
        # Antes se lanzaba `search ... windowactivate` de una vez y se
        # devolvia True si el proceso no habia dado error -- pero kdotool
        # termina BIEN cuando no encuentra ninguna ventana, asi que "trae
        # loquesea" contestaba True siempre, hubiera traido algo o no. En
        # el log del 10-sep-2026 se ve 'trae docking' -> True con Dolphin
        # abierto y nada trayendose. Decir "hecho" sin haberlo hecho hace
        # perder mas tiempo que fallar.
        hallazgo = subprocess.run(
            [binary, "search", "--name", pattern],
            timeout=3, capture_output=True, text=True,
        )
        ids = [l.strip() for l in (hallazgo.stdout or "").splitlines() if l.strip()]

        # LA NUESTRA NO... SALVO QUE SE PIDA A PROPOSITO.
        #
        # kdotool busca por "contiene" y nuestro titulo es "VoiceController",
        # asi que "trae control" nos traia A NOSOTROS sin querer, y encima
        # contestando que si (10-sep-2026). Se descarta mirando el titulo de
        # lo encontrado, que es el dato de verdad -- no con una lista de
        # nombres, porque cualquier trozo del nuestro tiene el mismo
        # problema ("voice", "controller", "troll"...).
        #
        # Pero subirse uno mismo TAMBIEN se pide a proposito: el comando
        # "subir", el boton de Escucha, y "trae control" cuando el usuario
        # quiere ver el GUI mientras trabaja con la vista de foco. Para eso
        # esta permitir_propia. El 12-sep-2026 este filtro, pensado solo
        # para el accidente, dejo mudos todos esos comandos: bring_to_front()
        # se sube llamando aqui con nuestro propio titulo. Prohibir el
        # accidente se llevo por delante el uso.
        if not permitir_propia:
            ajenas = []
            for wid in ids:
                r = subprocess.run([binary, "getwindowname", wid],
                                   timeout=3, capture_output=True, text=True)
                titulo = (r.stdout or "").strip().splitlines()
                titulo = titulo[-1].strip() if titulo else ""
                if titulo and "voicecontroller" in titulo.lower().replace(" ", ""):
                    continue
                ajenas.append(wid)
            if ids and not ajenas:
                print(f"[actions] {name!r} solo encuentra mi propia ventana; "
                      f"no me traigo a mi mismo")
                return False
            ids = ajenas

        if not ids:
            print(f"[actions] no hay ninguna ventana que sea {name!r} "
                  f"(kdotool codigo {hallazgo.returncode})")
            return False
        subprocess.run(
            [binary, "search", "--name", pattern, "windowactivate"],
            check=True,
            timeout=3,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.TimeoutExpired:
        print("[actions] kdotool tardó demasiado en responder")
        return False
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[actions] Error activando ventana '{name}' con kdotool"
              f"{': ' + stderr if stderr else ''} -- ¿está esa ventana abierta?")
        return False


def activate_target_window() -> bool:
    """Intenta traer al frente/activar la ventana objetivo configurada en
    config.PASTE_TARGET_WINDOW_REGEX -- ver activate_window_by_name() (usa
    kdotool). No hace nada (devuelve False) si PASTE_TARGET_WINDOW_REGEX
    está vacío."""
    target = getattr(config, "PASTE_TARGET_WINDOW_REGEX", "") or ""
    return activate_window_by_name(target)


def _carpeta_de_partida() -> str:
    """Desde donde se lanzan los programas que abre VoiceController.

    POR QUE HACE FALTA
    ------------------
    Un proceso hijo hereda el directorio de trabajo del padre, y el de
    VoiceController es SU PROPIA CARPETA. Asi que al abrir Kate por voz y
    decir "guardar como", el dialogo proponia guardar dentro de la
    instalacion de VoiceController -- que no es de nadie y encima se borra al
    desinstalar. Lo conto pipataki el 12-sep-2026.

    No es cosa de Kate ni de ningun programa concreto: le pasaba a todos.

    Lo normal es que un programa abierto asi parta de la carpeta personal,
    que es donde uno guarda sus cosas. Quien quiera otra, en config_local.py:

        CARPETA_INICIAL = "~/Documentos"
    """
    ruta = getattr(config, "CARPETA_INICIAL", "") or ""
    if not ruta:
        return os.path.expanduser("~")
    # Se aceptan las tres formas de escribirlo, porque las tres son lo que a
    # uno le sale: "~/Documentos", "$HOME/Documentos" y "/home/$USER/Docs".
    # expanduser SOLO entiende la ~, asi que hace falta expandvars tambien --
    # sin el, un "$USER" se quedaria literal y la ruta no existiria.
    ruta = os.path.expanduser(os.path.expandvars(str(ruta)))
    return ruta if os.path.isdir(ruta) else os.path.expanduser("~")


def run_terminal_command(cmd: str):
    """Ejecuta un comando de shell (BLOQUEANTE)."""
    try:
        subprocess.run(shlex.split(cmd), check=True,
                       cwd=_carpeta_de_partida())
    except subprocess.CalledProcessError as e:
        print(f"[actions] Error ejecutando comando: {e}")
    except Exception as e:
        print(f"[actions] Error: {e}")


def launch_app(app_name: str):
    """Abre una aplicación (NO bloqueante)."""
    import sys as _sys
    if _sys.platform.startswith("win"):
        # os.startfile y NO Popen: en Windows muchos programas no estan en el
        # PATH sino registrados en "App Paths" (Firefox, Inkscape...), y
        # Popen solo mira el PATH. startfile hace lo mismo que Ejecutar
        # (Win+R), que es lo que la gente espera. cwd existe desde Python 3.10.
        try:
            try:
                os.startfile(app_name, cwd=_carpeta_de_partida())
            except TypeError:
                os.startfile(app_name)
            return
        except OSError:
            print(f"[actions] Aplicación no encontrada: {app_name}")
            return
        except Exception as e:
            print(f"[actions] Error lanzando app: {e}")
            return
    try:
        subprocess.Popen([app_name], cwd=_carpeta_de_partida(),
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        print(f"[actions] Aplicación no encontrada: {app_name}")
    except Exception as e:
        print(f"[actions] Error lanzando app: {e}")


# --- TABLERO DE 100 CASILLAS (Sección 1 del manual) ---
#
# Flujo: seleccionar (captura tablero.png + recorta casilla.png + reposiciona
# la GUI al lado simétrico) -> ajuste fino opcional (mueve el marcador dentro
# de la casilla, en píxeles) -> acción (mueve el puntero real a esa posición
# y hace click/doble click/click derecho/scroll). Todo bajo _with_vc_
# minimized() para que la propia ventana de VoiceController no salga en la
# captura de pantalla.

def select_board_cell(gui, cell: int, on_zones=None):
    """Paso 1-2 del manual: selecciona una casilla (1-100). Minimiza la
    GUI, (re)captura tablero.png si hace falta, recorta casilla.png para
    esa casilla y reposiciona la ventana al lado simétrico opuesto. NO
    mueve el puntero ni dispara ninguna acción todavía -- eso lo hace una
    palabra de acción posterior (ver fire_board_action).

    De paso, autodetecta las zonas clicables dentro de la casilla (ver
    board.detect_zones) y las numera sobre la vista ampliada; si se
    pasa on_zones(cell, zones), se llama con el resultado (en el hilo de
    Qt) para que el router pueda reconocer "<accion> <numero>" mientras
    esta casilla siga seleccionada."""
    def _do():
        gui.apartar_ventana()
        try:
            time.sleep(0.15)  # da tiempo a que el compositor oculte la ventana
            board.capture_tablero()
            ok = board.crop_casilla(cell)
        finally:
            gui.subir_ventana()
        if not ok:
            print(f"[actions] no se pudo recortar la casilla {cell}")
            return
        _, col = board.cell_row_col(cell)
        try:
            gui.reposition_for_board(col)
        except Exception as exc:
            print(f"[actions] error reposicionando la GUI: {exc!r}")
        zones = board.detect_zones(cell)
        if on_zones:
            try:
                on_zones(cell, zones)
            except Exception as exc:
                print(f"[actions] error en callback de zonas: {exc!r}")
        try:
            gui.show_board_cell(cell, 0, 0, zones)
        except Exception as exc:
            print(f"[actions] error mostrando la casilla en el GUI: {exc!r}")
    gui.run_on_main_thread(_do)


def show_zoom_out(gui, cell: int):
    """Comando de voz "menos zoom"/"zoom out": recorta y muestra el
    cuarto de escritorio (5x5 casillas) donde cae `cell`, sin numerar
    (ver board.capture_zoom_out) -- término medio de zoom entre la vista
    general del tablero y una casilla sola. Recaptura tablero.png antes
    para que el cuarto mostrado esté actualizado."""
    def _do():
        gui.apartar_ventana()
        try:
            time.sleep(0.15)
            board.capture_tablero()
            ok = board.capture_zoom_out(cell)
        finally:
            gui.subir_ventana()
        if not ok:
            print(f"[actions] no se pudo generar zoom_out.png para la casilla {cell}")
            return
        try:
            gui.show_zoom_out(cell, 0, 0)
        except Exception as exc:
            print(f"[actions] error mostrando zoom_out en el GUI: {exc!r}")
    gui.run_on_main_thread(_do)


def enter_foco(gui, nombre: str = "") -> bool:
    """Vista "foco": recaptura el escritorio y recorta la ventana en la que
    se estaba trabajando (ver board.capture_foco). Devuelve True si se pudo.

    A diferencia de enter_zoom_out_interactive(), esto NO se hace en el hilo
    del GUI: hay que saber AQUI si ha salido bien para poder avisar al
    usuario, y run_on_main_thread() no devuelve nada. La captura no toca la
    interfaz, asi que se puede hacer fuera; solo el pintado se manda al GUI.
    """
    # Con nombre, la ventana se TRAE AL FRENTE antes de capturarla: si
    # estuviera tapada por otra, el recorte ensenaria lo que hay encima, que
    # no es lo que ha pedido nadie. Es el mismo "trae <nombre>" de siempre.
    if nombre:
        if not activate_window_by_name(nombre):
            print(f"[actions] no se pudo traer al frente {nombre!r}; "
                  f"se captura de donde este")
        else:
            time.sleep(0.35)

    # El GUI se manda al fondo ANTES de capturar: si estuviera por delante,
    # saldria tapando justo la ventana que se quiere ensenar. Se le da un
    # respiro al compositor para que repinte antes de disparar la captura.
    if gui is not None:
        try:
            gui.send_to_back()
            time.sleep(0.35)
        except Exception as exc:
            print(f"[actions] no se pudo bajar el GUI antes de capturar: {exc!r}")

    # Fuera de la foto lo que sea nuestro. En modo ventana no hace nada
    # (send_to_back, arriba, ya bajó la ventana); en modo servicio apaga los
    # vcs, que si no salen dentro de foco.png -- y foco.png es lo que
    # el movil ensena de fondo en el touchpad.
    if gui is not None:
        try:
            gui.ocultar_para_captura()
            time.sleep(0.12)      # un fotograma para que el compositor repinte
        except Exception as exc:
            print(f"[actions] no se pudo despejar antes de capturar: {exc!r}")
    try:
        board.capture_tablero()
        ok_foco = board.capture_foco(nombre)
    finally:
        if gui is not None:
            try:
                gui.restaurar_tras_captura()
            except Exception as exc:
                print(f"[actions] no se pudo restaurar tras capturar: {exc!r}")
    if not ok_foco:
        return False

    def _do():
        try:
            gui.show_foco()
            # Y se sube de vuelta, para no tener que ir bajando y subiendo
            # el GUI a mano cada vez que se pide foco. En suave: subir del
            # otro modo minimizaria la ventana recien capturada.
            gui.traer_al_frente_suave()
        except Exception as exc:
            print(f"[actions] error mostrando el foco en el GUI: {exc!r}")

    if gui is not None:
        gui.run_on_main_thread(_do)
    return True


def enter_zoom_out_interactive(gui, cell: int, offset_x: int, offset_y: int):
    """Fase 2 del rediseño de accesibilidad: entra en modo zoom_out
    interactivo para `cell` -- recaptura tablero.png + zoom_out.png y
    muestra el puntero verde YA en (offset_x, offset_y) (calculado por
    el router a partir de la última posición real conocida, ver
    command_router._enter_zoom_out_interactive -- NUNCA se mueve el
    cursor real para entrar aquí, es pura recaptura + dibujo).

    Disparado por el comando de voz "mover <casilla n>" (antes movía el
    cursor real al instante; ahora solo posiciona el punto de partida
    para el ajuste con touchpad/compás -- la acción real no ocurre
    hasta confirmar con un comando de acción, ver fire_zoom_out_action)."""
    def _do():
        # Despejado antes de capturar: en servicio, sin esto, tablero.png y
        # zoom_out.png salen CON la rejilla y la diana dentro, y zoom_out.png
        # es el fondo del touchpad del móvil. En modo ventana no hace nada.
        try:
            gui.ocultar_para_captura()
            time.sleep(0.12)
        except Exception as exc:
            print(f"[actions] no se pudo despejar antes de capturar: {exc!r}")
        try:
            board.capture_tablero()
            ok = board.capture_zoom_out(cell)
        finally:
            try:
                gui.restaurar_tras_captura()
            except Exception as exc:
                print(f"[actions] no se pudo restaurar tras capturar: {exc!r}")
        if not ok:
            print(f"[actions] no se pudo generar zoom_out.png para la casilla {cell}")
            return
        try:
            gui.show_zoom_out(cell, offset_x, offset_y)
        except Exception as exc:
            print(f"[actions] error mostrando zoom_out en el GUI: {exc!r}")
    gui.run_on_main_thread(_do)


def nudge_zoom_out_marker(gui, cell: int, offset_x: int, offset_y: int):
    """Actualiza (sin recapturar nada) el marcador verde sobre
    zoom_out.png ya cargado, en (offset_x, offset_y) -- equivalente a
    nudge_board_marker() pero para el modo zoom_out interactivo (Fase 2).
    Usado por el ajuste fino por voz (compás) mientras se está
    posicionando el puntero verde antes de confirmar una acción."""
    def _do():
        try:
            gui.show_zoom_out(cell, offset_x, offset_y)
        except Exception as exc:
            print(f"[actions] error actualizando el marcador de zoom_out: {exc!r}")
    gui.run_on_main_thread(_do)


def _mover_puntero_real(x: int, y: int) -> bool:
    """EL único sitio desde el que se mueve el puntero físico.

    Existe porque ya se escapó dos veces: `grid_vc.move_pointer_physical`
    usa ydotool, y al contar las llamadas a ydotool no aparecía -- estaba
    escondida detrás de otro módulo. Se llamaba desde nueve sitios, y en
    Windows fallaban todos (los clics del móvil, entre ellos). Con un solo
    punto de paso, migrar la siguiente plataforma es cambiar una línea."""
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        return backends.move_pointer(x, y)
    if grid_vc is None:
        print("[actions] no hay con qué mover el puntero en esta plataforma")
        return False
    grid_vc.move_pointer_physical(x, y)
    return True


def _mover_puntero_relativo(dx: int, dy: int) -> bool:
    """Mueve el puntero DESDE DONDE ESTE, sin pasar por ninguna esquina.

    Hace falta para el arrastre: _mover_puntero_real() va a una posicion
    absoluta, y para eso resetea a la esquina primero. Con el boton
    pulsado eso convierte el arrastre en un garabato.
    """
    if not dx and not dy:
        return True
    import sys as _sys
    if _sys.platform.startswith("win"):
        return False          # la capa de Windows no tiene movimiento relativo
    if grid_vc is None:
        return False
    try:
        grid_vc.move_pointer_relative(dx, dy)
        return True
    except Exception as exc:
        print(f"[actions] no se pudo mover el puntero: {exc!r}")
        return False


def _execute_atomic_action(gui, real_x: int, real_y: int, kind: str, on_result=None):
    """Núcleo COMPARTIDO de toda acción atómica sobre el tablero:
    manda el GUI a un nivel inferior (gui.send_to_back(), ANTES y
    DESPUÉS -- evita que la ventana de VoiceController u otra, p.ej.
    Konsole, se lleve el clic si tapa la posición real en ese momento),
    mueve el puntero real y ejecuta `kind` ("move", "click",
    "click_right", "double_click", "scroll_up/down/left/right"), y
    refresca en segundo plano tablero+casilla+zoom_out de la casilla
    donde cayó el punto de acción (best-effort, solo para que la webapp
    tenga las capturas al día -- no afecta a la acción real, que ya se
    ejecutó antes de esto). Termina volviendo a la vista general
    (gui.show_board_overview() -- "la pantalla inicial" del PDF de
    diseño).

    Usada por fire_zoom_out_action() (offset respecto al centro del
    cuarto de escritorio, puntero verde del GUI) y fire_virtual_action()
    (fracción 0-1 de la imagen mostrada, puntero rojo de la webapp,
    Fase 3) -- ambas terminan calculando una posición REAL y delegan
    aquí el resto, para no duplicar el mismo bloque grande tres veces."""
    gui.send_to_back()
    try:
        if kind == "click":
            _mover_puntero_real(real_x, real_y)
            _board_click("0xC0")
        elif kind == "click_right":
            _mover_puntero_real(real_x, real_y)
            _board_click("0xC1")
        elif kind == "double_click":
            _mover_puntero_real(real_x, real_y)
            _board_click("0xC0")
            _board_click("0xC0")
        elif kind == "scroll_up":
            _mover_puntero_real(real_x, real_y)
            _scroll_key("103")
        elif kind == "scroll_down":
            _mover_puntero_real(real_x, real_y)
            _scroll_key("108")
        elif kind == "scroll_left":
            _mover_puntero_real(real_x, real_y)
            _scroll_key("105")
        elif kind == "scroll_right":
            _mover_puntero_real(real_x, real_y)
            _scroll_key("106")
        else:  # "move": solo mover el puntero, sin click
            _mover_puntero_real(real_x, real_y)
    except Exception as exc:
        print(f"[actions] error ejecutando acción atómica ({kind}): {exc!r}")
    finally:
        gui.send_to_back()

    try:
        # Despejado antes de capturar: casilla.png y zoom_out.png se recortan
        # de tablero.png, y son el fondo del touchpad del móvil. En modo
        # ventana no hace nada (send_to_back ya bajó la ventana).
        try:
            gui.ocultar_para_captura()
            time.sleep(0.12)
        except Exception as exc:
            print(f"[actions] no se pudo despejar antes de capturar: {exc!r}")
        try:
            board.capture_tablero()
        finally:
            try:
                gui.restaurar_tras_captura()
            except Exception as exc:
                print(f"[actions] no se pudo restaurar tras capturar: {exc!r}")
        new_cell = board.cell_from_absolute_position(real_x, real_y)
        if new_cell is not None:
            _refresh_casilla_and_zoom_out(new_cell, include_casilla=True)
        gui.show_board_overview()
    except Exception as exc:
        print(f"[actions] error refrescando tras la acción: {exc!r}")
    if on_result:
        on_result((real_x, real_y))


def fire_zoom_out_action(gui, cell: int, offset_x: int, offset_y: int, kind: str, on_result=None):
    """Ejecuta `kind` en la posición REAL correspondiente al puntero
    verde -- (offset_x, offset_y) respecto al centro del cuarto de
    escritorio (zoom_out) de `cell`. Esa posición real es
    board.zoom_out_absolute_position(cell, offset_x, offset_y): el
    centro del cuarto de escritorio + (offset_x, offset_y) -- "según el
    cuarto que sea, sumar media anchura/altura del escritorio, o nada,
    a la posición del puntero verde" (tal cual lo describió el
    usuario). El resto (send_to_back, ejecución, refresco, vuelta a la
    vista general) lo hace _execute_atomic_action(), compartida con
    fire_virtual_action() (Fase 3, webapp)."""
    def _do():
        real_pos = board.zoom_out_absolute_position(cell, offset_x, offset_y)
        if real_pos is None:
            print("[actions] fire_zoom_out_action: sin tablero.png capturado, no se puede actuar")
            if on_result:
                on_result(None)
            return
        _execute_atomic_action(gui, real_pos[0], real_pos[1], kind, on_result=on_result)
    gui.run_on_main_thread(_do)


def fire_foco_action(gui, offset_x: int, offset_y: int, kind: str, on_result=None):
    """Ejecuta `kind` en la posicion REAL del puntero verde de la vista
    "foco" -- (offset_x, offset_y) respecto al centro de la ventana que se
    esta ensenando.

    Esa posicion sale de board.foco_absolute_position(), que sabe en que
    punto del ESCRITORIO esta la ventana recortada: sin eso el puntero seria
    un dibujo bonito sobre una imagen y el clic caeria en cualquier sitio.

    El resto (ejecucion, refresco, vuelta a la vista general) lo hace
    _execute_atomic_action(), compartida con las otras dos vistas.
    """
    def _subir_al_acabar(real_pos):
        # El GUI vuelve a subir al terminar la accion -- pedido por el:
        # "igual que cuando dictamos", que tambien vuelve a mostrarse al
        # acabar. Sube SIN llevarse el foco (ver gui._do_restore), asi que
        # las teclas siguen yendo a la ventana en la que se trabaja.
        #
        # OJO, esto tiene un riesgo conocido y documentado: si el clic acaba
        # de abrir un menu, subir el GUI encima puede cerrarlo. Por eso solo
        # se hace en la vista FOCO, donde el usuario esta trabajando dentro
        # de una ventana concreta y quiere seguir viendola, y no en todos los
        # clics del tablero.
        try:
            gui.subir_ventana()
        except Exception as exc:
            print(f"[actions] no se pudo subir el GUI tras la accion: {exc!r}")
        if on_result:
            on_result(real_pos)

    def _do():
        real_pos = board.foco_absolute_position(offset_x, offset_y)
        if real_pos is None:
            print("[actions] fire_foco_action: no hay vista de foco, no se puede actuar")
            if on_result:
                on_result(None)
            return
        _execute_atomic_action(gui, real_pos[0], real_pos[1], kind,
                               on_result=_subir_al_acabar)
    gui.run_on_main_thread(_do)


def fire_virtual_action(gui, view: str, cell: int, fx: float, fy: float, kind: str, on_result=None):
    """Fase 3 del rediseño de accesibilidad (puntero ROJO de la
    webapp): ejecuta `kind` en la posición REAL correspondiente a una
    fracción (fx, fy, 0.0-1.0) de la imagen que la webapp esté
    mostrando de fondo en su touchpad virtual -- `view` es "tablero",
    "foco", "zoom_out" o "casilla" (los mismos casos que
    board.virtual_pointer_to_real_position()).

    El arrastre del punto rojo en sí es 100% del lado del cliente (la
    webapp no manda NADA por red mientras se arrastra) -- esta función
    solo se llama UNA vez, al confirmar la acción (clic/clic
    derecho/doble clic/scroll), igual que fire_zoom_out_action() para
    el puntero verde del GUI. El resto (send_to_back, ejecución,
    refresco, vuelta a la vista general) es exactamente el mismo
    código compartido, vía _execute_atomic_action()."""
    def _do():
        real_pos = board.virtual_pointer_to_real_position(view, cell, fx, fy)
        if real_pos is None:
            print(f"[actions] fire_virtual_action: no se pudo calcular la posición real (view={view!r}, cell={cell})")
            if on_result:
                on_result(None)
            return
        _execute_atomic_action(gui, real_pos[0], real_pos[1], kind, on_result=on_result)
    gui.run_on_main_thread(_do)


def refresh_board_overview(gui):
    """Vuelve a capturar tablero.png y actualiza la vista general del
    tablero en el GUI (sin ninguna casilla seleccionada)."""
    def _do():
        gui.apartar_ventana()
        try:
            time.sleep(0.15)
            board.capture_tablero()
        finally:
            gui.subir_ventana()
        try:
            gui.show_board_overview()
        except Exception as exc:
            print(f"[actions] error mostrando el tablero en el GUI: {exc!r}")
    gui.run_on_main_thread(_do)


def refrescar_vista(gui, vista, casilla=None, nombre="", offset=(0, 0),
                    on_zones=None, volver=None, ya_apartada=False):
    """Vuelve a capturar la vista que se esta mirando y la repinta, SIN
    mover el puntero verde. Comando "refrescar", y el refresco automatico
    cuando VC vuelve a primer plano tras una accion (pipataki, 12-sep-2026).

    vista: "overview" | "cell" | "zoom_out" | "foco", como _punto_actual().

    POR QUE NO SE REUTILIZAN LAS ENTRADAS A CADA VISTA: select_board_cell,
    enter_zoom_out_interactive y enter_foco ya capturan, pero ponen el
    puntero verde a cero al entrar. Refrescar no es entrar otra vez: quien
    habia colocado el puntero para seleccionar algo lo perderia.

    LA CAPTURA SE HACE CON VC APARTADO, SIEMPRE -- es la regla de las
    capturas sucias. Si quien llama ya lo tiene apartado (el baile de las
    teclas, el pegado del dictado), ya_apartada=True y no se aparta otra
    vez. Y se vuelve a ensenar DESPUES de capturar, por eso el "volver" es
    parte de esta funcion y no de quien llama:

        volver=None       gui.subir_ventana()  (lo de siempre)
        volver=<funcion>  esa, p.ej. gui.traer_al_frente_suave ("trae control")
        volver=False      no tocar la ventana (p.ej. si estaba oculta)

    Antes de capturar se espera REFRESCO_ESPERA_S: el resultado de lo que
    se acaba de hacer -- un menu, una pagina, el texto pegado -- tarda en
    pintarse, y una foto demasiado pronta enseña el antes.
    """
    ox, oy = (offset or (0, 0))[:2]

    def _do():
        if not ya_apartada:
            gui.apartar_ventana()
        zonas = []
        try:
            espera = float(getattr(config, "REFRESCO_ESPERA_S", 0.4) or 0)
            time.sleep(max(0.15, espera))
            board.capture_tablero()
            if vista == "cell" and casilla:
                board.crop_casilla(casilla)
                zonas = board.detect_zones(casilla) or []
                board.capture_zoom_out(casilla)       # la webapp, al dia tambien
            elif vista == "zoom_out" and casilla:
                board.capture_zoom_out(casilla)
            elif vista == "foco":
                if not board.capture_foco(nombre):
                    print(f"[actions] refrescar: la ventana del foco {nombre!r} ya no esta")
        except Exception as exc:
            print(f"[actions] error refrescando las capturas: {exc!r}")
        finally:
            try:
                if volver is None:
                    gui.subir_ventana()
                elif volver:
                    volver()
            except Exception as exc:
                print(f"[actions] error volviendo a ensenar el GUI: {exc!r}")
        try:
            if vista == "cell" and casilla:
                if on_zones:
                    on_zones(casilla, zonas)
                gui.show_board_cell(casilla, ox, oy, zonas)
            elif vista == "zoom_out" and casilla:
                gui.show_zoom_out(casilla, ox, oy)
            elif vista == "foco":
                gui.show_foco(ox, oy)
            else:
                gui.show_board_overview()
        except Exception as exc:
            print(f"[actions] error repintando la vista: {exc!r}")
        print(f"[actions] capturas refrescadas (vista {vista})")

    gui.run_on_main_thread(_do)


def deselect_board_cell(gui):
    """Vuelve a la vista general del tablero (sin recapturar), p.ej. tras
    ejecutar una acción o al decir "idle"/"subir"."""
    def _do():
        try:
            gui.show_board_overview()
        except Exception as exc:
            print(f"[actions] error volviendo a la vista general: {exc!r}")
    gui.run_on_main_thread(_do)


def nudge_board_marker(gui, cell: int, offset_x: int, offset_y: int, zones=None):
    """Actualiza (sin recapturar nada) el marcador de ajuste fino sobre
    casilla.png ya cargada, en la posición (offset_x, offset_y) -- ya
    recortada a los límites de la casilla por el router. `zones` (si se
    pasa) se redibuja también, para que las zonas numeradas sigan
    visibles mientras se ajusta a mano con el compás/direcciones."""
    def _do():
        try:
            gui.show_board_cell(cell, offset_x, offset_y, zones)
        except Exception as exc:
            print(f"[actions] error actualizando el marcador: {exc!r}")
    gui.run_on_main_thread(_do)


def _move_physical(gui, cell: int, offset_x: int, offset_y: int):
    """Mueve el puntero real a la posición (centro de la casilla + ajuste
    fino) y actualiza la etiqueta de posición / última posición."""
    x, y = board.cell_absolute_position(cell, offset_x, offset_y)
    try:
        _mover_puntero_real(x, y)
    except Exception as exc:
        print(f"[actions] error moviendo el puntero: {exc!r}")
    gui.update_position_label(cell, 0)
    gui.set_last_position(cell, 0)


# Los codigos de ydotool para el clic, traducidos al nombre que entiende
# la capa de plataforma. Se mantienen los hex en los llamantes para no
# tocar una docena de sitios.
_BOTONES = {"0xC0": "left", "0xC1": "right", "0xC2": "middle"}


def _board_click(button_hex: str):
    import sys as _sys
    if _sys.platform.startswith("win"):
        import backends
        backends.click(_BOTONES.get(button_hex, "left"))
        return
    try:
        subprocess.run(["ydotool", "click", button_hex], check=False,
                       timeout=_timeout_ydotool())
    except subprocess.TimeoutExpired:
        print(f"[actions] ydotool no respondió al hacer clic ({button_hex}) "
              "-- ¿está vivo ydotoold?")


# Codigo evdev de la tecla Mayus izquierda. Se usa para el "Mayus+clic"
# que selecciona un rango de texto.
_MAYUS_EVDEV = 42


def _click_crudo(hex_boton: str):
    """Un evento de raton SUELTO: solo pulsar, o solo soltar.

    `_board_click` manda "0xC0", que en ydotool es pulsar Y soltar. La parte
    alta del numero dice que se hace:

        0x40  solo PULSAR
        0x80  solo SOLTAR
        0xC0  las dos cosas (el clic normal de siempre)

    O sea que arrastrar ya se podia desde el primer dia y no lo sabiamos.
    """
    try:
        subprocess.run(["ydotool", "click", hex_boton], check=False,
                       timeout=_timeout_ydotool())
    except subprocess.TimeoutExpired:
        print(f"[actions] ydotool no respondio ({hex_boton})")


def _tecla_cruda(pulsacion: str) -> bool:
    """Un evento de tecla SUELTO: "42:1" es Mayus abajo, "42:0" arriba.

    Sirve para SOSTENER un modificador mientras se hace otra cosa -- el
    Mayus+clic de la seleccion de texto. Las funciones normales de teclado
    mandan la pulsacion entera y no valen para eso.
    """
    try:
        subprocess.run(["ydotool", "key", pulsacion], check=False,
                       timeout=_timeout_ydotool())
        return True
    except Exception as exc:
        print(f"[actions] no se pudo mandar la tecla {pulsacion}: {exc!r}")
        return False


def _soltarlo_todo():
    """Suelta el boton izquierdo y Mayus, pase lo que pase.

    ES LA PIEZA DE SEGURIDAD DE TODO ESTO. Un boton izquierdo que se queda
    hundido no es un fallo cualquiera: selecciona y ARRASTRA todo lo que
    toques despues, y puede soltarte un archivo en cualquier sitio. Un
    Mayus atascado convierte lo que dictes en mayusculas.

    Por eso se llama siempre desde un `finally`, y por eso manda soltar
    aunque no conste que este pulsado: soltar algo que ya estaba suelto no
    hace nada; no soltarlo te deja el escritorio inservible.
    """
    import backends
    try:
        backends.mouse_up("left")
    except Exception:
        pass
    try:
        backends.key_up("shift")
    except Exception:
        pass


def seleccionar_rango(gui, origen, fin, modo="texto", on_result=None):
    """Selecciona desde `origen` hasta `fin`, en coordenadas de pantalla.

    Dos formas, segun lo que haya debajo:

      "texto"  clic en el origen y MAYUS+CLIC en el final. Es lo que hace
               cualquier editor y cualquier lista, y no deja el boton
               pulsado entre medias.

      "area"   pulsar en el origen, mover, y soltar en el final: el
               recuadro de seleccion de los iconos. Tambien es, con otro
               nombre, ARRASTRAR Y SOLTAR.

    ENTRE LAS DOS ORDENES DE VOZ NO SE SOSTIENE NADA. El origen solo se
    recuerda; aqui se ejecuta todo seguido. Si se dejara el boton pulsado
    al fijar el origen, quedaria hundido los diez o quince segundos que
    tardas en decir la segunda orden -- y si algo fallara en medio, se
    queda asi. Es la familia del modificador atascado que ya nos mordio con
    ydotool, pero peor.
    """
    x1, y1 = int(origen[0]), int(origen[1])
    x2, y2 = int(fin[0]), int(fin[1])

    def _do():
        import backends
        gui.send_to_back()
        ok = True
        try:
            _mover_puntero_real(x1, y1)
            time.sleep(0.12)
            if modo == "area":
                backends.mouse_down("left")             # pulsar y NO soltar
                time.sleep(0.10)
                # POR PASOS Y EN RELATIVO. Dos cosas, y las dos costaron una
                # prueba fallida:
                #
                # - por pasos, porque muchos programas (Inkscape, los
                #   gestores de archivos) solo empiezan el recuadro cuando
                #   VEN el raton moverse con el boton pulsado; un salto no
                #   genera esos eventos y se lee como que no hubo arrastre;
                #
                # - en RELATIVO, porque el movimiento absoluto pasa primero
                #   por la esquina de la pantalla
                #   (grid_vc.move_pointer_physical), y con el boton
                #   pulsado eso dibuja un garabato en vez de un rectangulo.
                pasos = max(2, int(getattr(config, "ARRASTRE_PASOS", 12)))
                hecho_x = hecho_y = 0
                for i in range(1, pasos + 1):
                    toca_x = (x2 - x1) * i // pasos
                    toca_y = (y2 - y1) * i // pasos
                    backends.move_pointer_relative(toca_x - hecho_x,
                                                   toca_y - hecho_y)
                    hecho_x, hecho_y = toca_x, toca_y
                    time.sleep(0.02)
                time.sleep(0.15)                        # que el destino se entere
                backends.mouse_up("left")               # soltar: cierra el recuadro
            else:
                backends.click("left")                  # poner el cursor
                time.sleep(0.12)
                _mover_puntero_real(x2, y2)
                time.sleep(0.12)
                backends.key_down("shift")
                backends.click("left")
                backends.key_up("shift")
        except Exception as exc:
            ok = False
            print(f"[actions] error seleccionando: {exc!r}")
        finally:
            _soltarlo_todo()
            # LA VENTANA EN LA QUE SE ACABA DE SELECCIONAR ES LA BUENA.
            #
            # El clic la ha dejado activa, asi que este es el momento de
            # apuntarla: lo que venga despues -- "copiar", dictar -- tiene
            # que ir ahi y no a la nuestra.
            recordar_ventana_destino()
            gui.send_to_back()
            # Y que el foco SIGA ahi. Si se pierde, el usuario tiene que
            # pinchar en su ventana para recuperarlo... y un clic dentro
            # del texto DESHACE la seleccion que se acaba de hacer. Es
            # exactamente lo que le paso a pipataki el 10-sep-2026.
            asegurar_ventana_destino()
        print(f"[actions] seleccion {modo} de ({x1},{y1}) a ({x2},{y2}): "
              f"{'OK' if ok else 'FALLO'}")
        if on_result:
            try:
                on_result(ok, "")
            except Exception:
                pass

    gui.run_on_main_thread(_do)


def touchpad_move(dx: float, dy: float) -> bool:
    """Movimiento relativo estilo touchpad, para arrastrar el dedo por
    la pantalla táctil del móvil (ver webapp/app.py, ruta
    /board/touchpad) y mover el cursor real en tiempo real -- SIN pasar
    por el sistema de casillas/ajuste fino (eso es posicionamiento
    ABSOLUTO; esto es relativo puro, como un touchpad físico).

    A propósito NO usa gui.run_on_main_thread(): no toca ningún widget
    de Qt, solo lanza ydotool (subprocess, seguro desde cualquier
    hilo), así que se llama DIRECTAMENTE desde el hilo de la petición
    Flask -- menos salto de hilos = menos latencia, que es lo que
    importa para que el arrastre se sienta fluido.

    Devuelve True si se pudo mover, False si grid_vc/ydotool no
    están disponibles (mismo criterio que el resto de acciones de
    tablero)."""
    if grid_vc is None:
        print("[actions] touchpad_move: grid_vc no disponible")
        return False
    try:
        grid_vc.move_pointer_relative(dx, dy)
        return True
    except Exception as exc:
        print(f"[actions] error en touchpad_move: {exc!r}")
        return False


def touchpad_click(button: str = "left") -> bool:
    """Clic en la posición ACTUAL del cursor (no en una casilla) --
    equivalente táctil de un toque/tap en un touchpad físico. button:
    "left" o "right"."""
    button_hex = "0xC1" if button == "right" else "0xC0"
    try:
        _board_click(button_hex)
        return True
    except Exception as exc:
        print(f"[actions] error en touchpad_click: {exc!r}")
        return False


def fire_board_action(gui, cell: int, offset_x: int, offset_y: int, kind: str):
    """Paso 3 del manual: ejecuta la acción `kind` ('move', 'click',
    'click_right', 'double_click', 'scroll_up'/'down'/'left'/'right')
    sobre la posición ya ajustada (centro de la casilla + ajuste fino), y
    vuelve a la vista general del tablero al terminar.

    Tras el clic, el GUI se manda a un nivel INFERIOR (gui.send_to_back(),
    self.lower()) en vez de traerlo de vuelta al frente -- si la acción
    acaba de abrir un menú, la barra de tareas o el menú de inicio del
    escritorio, subir el GUI por encima justo después lo cerraba de
    golpe. Para volver a ver el GUI en primer plano hace falta pedirlo
    explícitamente (botón/acción "🎧 Escucha", comando de voz "subir").

    ANTES del clic también se usa send_to_back() en vez de
    apartar_ventana() (hide()) -- ocultar y volver a
    mostrar la ventana para CADA clic era un ciclo hide()/show()
    innecesario que, incluso lowered después, podía reactivar
    brevemente la ventana al reaparecer (ver WA_ShowWithoutActivating
    en gui.py). send_to_back() la deja SIEMPRE visible, solo cambia su
    posición en el orden de apilamiento -- nunca se oculta ni se
    vuelve a mapear."""
    def _do():
        gui.send_to_back()
        try:
            _move_physical(gui, cell, offset_x, offset_y)
            if kind == "click":
                _board_click("0xC0")
            elif kind == "click_right":
                _board_click("0xC1")
            elif kind == "double_click":
                _board_click("0xC0")
                _board_click("0xC0")
            elif kind == "scroll_up":
                _scroll_key("103")
            elif kind == "scroll_down":
                _scroll_key("108")
            elif kind == "scroll_left":
                _scroll_key("105")
            elif kind == "scroll_right":
                _scroll_key("106")
            # kind == "move": solo mover el puntero, sin click
        finally:
            gui.send_to_back()
        try:
            # DESPEJAR ANTES DE CAPTURAR. Hoy no hace casi nada
            # (send_to_back, justo arriba, ya bajó la ventana), pero el
            # despeje tiene que estar: sin él, tablero.png sale con lo
            # nuestro dentro, y de ahí se recortan zoom_out.png y
            # casilla.png, que son el fondo del touchpad en el móvil.
            #
            # Es lo que hacía que el touchpad se viera distinto en servicio
            # y en GUI.
            try:
                gui.ocultar_para_captura()
                # Lo que el clic abre -- un menu, una pagina -- tarda en
                # pintarse. Con 0,12 s la foto salia a veces con el ANTES.
                # El movil ya esperaba medio segundo (POST_ACTION_REFRESH).
                time.sleep(max(0.12, float(getattr(config, "REFRESCO_ESPERA_S", 0.4) or 0)))
            except Exception as exc:
                print(f"[actions] no se pudo despejar antes de capturar: {exc!r}")
            try:
                board.capture_tablero()
            finally:
                try:
                    gui.restaurar_tras_captura()
                except Exception as exc:
                    print(f"[actions] no se pudo restaurar tras capturar: {exc!r}")
            gui.show_board_overview()
            # casilla.png NO hace falta recapturarla aquí (include_casilla=False)
            # -- ya se capturó al seleccionar esta casilla (select_board_cell),
            # y este flujo de ajuste fino siempre actúa sobre una casilla YA
            # seleccionada, así que repetirlo sería trabajo duplicado. Pero
            # zoom_out.png nunca se toca en este flujo salvo que se pida
            # explícitamente ("zoom out") -- se refresca aquí en segundo
            # plano, sin mostrarlo, para que la webapp lo tenga siempre al
            # día tras CUALQUIER acción de ajuste fino, no solo cuando se
            # pide zoom explícitamente.
            _refresh_casilla_and_zoom_out(cell, include_casilla=False)
        except Exception as exc:
            print(f"[actions] error refrescando el tablero tras la acción: {exc!r}")
    gui.run_on_main_thread(_do)


def press_enter():
    """Envía la tecla Enter/Return vía ydotool (keycode evdev 28,
    KEY_ENTER) -- se usa tras pegar el texto confirmado en una ventana
    externa (ver command_router._paste_confirmed,
    config.AUTO_ENTER_AFTER_PASTE) para que, si el texto se pegó en un
    buscador o barra de direcciones, la búsqueda/navegación se dispare
    sola, sin depender de hacerlo a mano aparte. En un editor de texto
    normal el efecto es simplemente una línea nueva -- que es lo
    esperable si luego se sigue escribiendo ahí."""
    import sys as _sys
    if _sys.platform.startswith("win"):
        import keyboard_keys
        keyboard_keys.send_key("Return")
        return
    ydotool_bin = _find_ydotool()
    if not ydotool_bin:
        print("[actions] ydotool no encontrado -- no se pudo enviar Enter tras pegar")
        return
    try:
        subprocess.run(
            [ydotool_bin, "key", "28:1", "28:0"],
            timeout=_timeout_ydotool(),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        print(f"[actions] Error enviando Enter tras pegar{': ' + stderr if stderr else ''}")
    except Exception as e:
        print(f"[actions] Error inesperado enviando Enter tras pegar: {e!r}")


# En Linux el scroll se emula con teclas (Page Up/Down, flechas) porque
# ydotool no tiene rueda fiable; en Windows hay rueda de verdad, pero aqui
# llegan codigos evdev, asi que se traducen a la tecla que representan.
_TECLAS_SCROLL = {"104": "Prior", "109": "Next",
                  "103": "Up", "108": "Down",
                  "105": "Left", "106": "Right"}


def _scroll_key(key_code: str, veces: int = None):
    """Emula scroll con teclas, repitiendo la pulsacion.

    Una sola pulsacion mueve UNA linea, y decir "scroll abajo" para bajar un
    renglon no sirve de nada -- se queda corto y hay que repetirlo cinco
    veces. Se repite config.SCROLL_LINEAS veces, que es un ajuste de gusto:
    quien lea rapido querra mas.

    ydotool acepta varias pulsaciones en una sola llamada, asi que esto no
    lanza tres procesos.
    """
    if veces is None:
        veces = max(1, int(getattr(config, "SCROLL_LINEAS", 3)))
    import sys as _sys
    if _sys.platform.startswith("win"):
        import keyboard_keys
        keyboard_keys.send_key(_TECLAS_SCROLL.get(str(key_code), str(key_code)),
                               repeat=veces)
        return
    pulsaciones = []
    for _ in range(veces):
        pulsaciones += [f"{key_code}:1", f"{key_code}:0"]
    try:
        subprocess.run(["ydotool", "key", *pulsaciones], check=False,
                       timeout=_timeout_ydotool())
    except subprocess.TimeoutExpired:
        # Son flechas, sin modificadores: no puede quedarse nada pulsado.
        print("[actions] ydotool no respondió al hacer scroll "
              "-- ¿está vivo ydotoold?")



# --- DICCIONARIO DE HANDLERS (para compatibilidad con command_router) ---
# Formato DIRECTO de un solo tiro "<accion> <celda>" (sin ajuste fino):
# actúa sobre el centro exacto de la casilla, sin pasar por la selección
# interactiva de arriba. handler(gui, cell) -- ya NO recibe subcelda.

def _refresh_casilla_and_zoom_out(cell: int, include_casilla: bool):
    """Actualiza EN SEGUNDO PLANO casilla.png (si include_casilla) y
    zoom_out.png para `cell`, sin mostrar ninguna de las dos en el GUI
    -- para que la webapp siempre tenga estas dos capturas al día, sin
    depender de que se pida explícitamente vía el flujo interactivo
    (compás) o el comando de voz "zoom out". Debe llamarse SIEMPRE
    después de board.capture_tablero() (ambas recortan de tablero.png,
    ya capturado) y desde el hilo de Qt (ver gui.run_on_main_thread en
    cada llamador -- crop_casilla/capture_zoom_out usan QImage).

    include_casilla=False en el flujo de ajuste fino (fire_board_action):
    ahí casilla.png YA se capturó al seleccionar la casilla
    (select_board_cell), así que repetirlo aquí sería puro trabajo
    duplicado -- solo hace falta refrescar zoom_out.png, que ese flujo
    nunca toca. include_casilla=True en los comandos directos de un
    solo tiro (vc_move/click/etc., "mover 53" y similares): esos
    NUNCA pasan por select_board_cell, así que sin esto casilla.png se
    quedaba desactualizado indefinidamente tras usarlos."""
    if include_casilla:
        if not board.crop_casilla(cell):
            print(f"[actions] no se pudo refrescar casilla.png en segundo plano (casilla {cell})")
    if not board.capture_zoom_out(cell):
        print(f"[actions] no se pudo refrescar zoom_out.png en segundo plano (casilla {cell})")


def vc_move(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_click_left(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _board_click("0xC0")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_click_right(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _board_click("0xC1")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_double_click(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _board_click("0xC0")
        _board_click("0xC0")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_scroll_up(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _scroll_key("103")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_scroll_down(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _scroll_key("108")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_scroll_left(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _scroll_key("105")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


def vc_scroll_right(gui, cell):
    def _do():
        board.capture_tablero()
        _move_physical(gui, cell, 0, 0)
        _scroll_key("106")
        _refresh_casilla_and_zoom_out(cell, include_casilla=True)
    gui.run_on_main_thread(_do)


VC_HANDLERS = {
    "vc_move": vc_move,
    "vc_click_left": vc_click_left,
    "vc_click_right": vc_click_right,
    "vc_double_click": vc_double_click,
    "vc_scroll_up": vc_scroll_up,
    "vc_scroll_down": vc_scroll_down,
    "vc_scroll_left": vc_scroll_left,
    "vc_scroll_right": vc_scroll_right,
}

# Nombre de handler -> "kind" de fire_board_action(), para el flujo
# interactivo (selección + ajuste fino + acción sola).
VC_HANDLER_KIND = {
    "vc_move": "move",
    "vc_click_left": "click",
    "vc_click_right": "click_right",
    "vc_double_click": "double_click",
    "vc_scroll_up": "scroll_up",
    "vc_scroll_down": "scroll_down",
    "vc_scroll_left": "scroll_left",
    "vc_scroll_right": "scroll_right",
}


# --- NUEVO: Handlers parametrizables de input_action ---
# Estos se llaman desde command_router con parámetros del JSON

def execute_input_action(gui, action_data: dict):
    """
    Ejecuta una acción parametrizable desde input_action.
    
    Args:
        gui: referencia al GUI (para obtener última posición)
        action_data: diccionario con 'action_type' y parámetros
    
    action_data puede ser:
      - {"action_type": "key", "key": "ctrl+c"}
      - {"action_type": "type_text", "text": "hola"}
      - {"action_type": "click", "position": [45, 3]}
      - {"action_type": "click"}  # usa última posición
    """
    
    if not input_action:
        print("[actions] ERROR: input_action no disponible")
        return
    
    # Obtener última posición del GUI
    last_pos = gui.get_last_position()
    
    try:
        # Crear una copia de action_data sin modificar el original
        params = dict(action_data)
        action_type = params.pop("action_type", None)
        
        # Convertir "position" a tuple si viene como lista
        if "position" in params and isinstance(params["position"], list):
            params["position"] = tuple(params["position"])
        
        # Ejecutar la acción
        input_action.input_action(action_type, last_position=last_pos, **params)
    except Exception as e:
        print(f"[actions] Error ejecutando input_action: {e}")


def apartar_gui_si_estorba(gui) -> bool:
    """Aparta NUESTRA ventana si es la que tiene el foco. Devuelve si lo hizo.

    POR QUE HACE FALTA
    ------------------
    El teclado se inyecta a nivel de dispositivo (uinput, via ydotool), asi
    que la tecla la recibe QUIEN TENGA EL FOCO. Mientras VoiceController no
    se lo lleve nunca -- que es lo normal, por WA_ShowWithoutActivating --
    no hay nada que hacer y esto no toca nada.

    Pero el usuario PUEDE subirlo a proposito, diciendo "trae control", para
    ver el GUI mientras trabaja sobre otra ventana con la vista de foco. Ahi
    el foco de teclado si es nuestro, y un "copiar" se lo comia
    VoiceController en silencio. Lo conto pipataki el 12-sep-2026.

    Es el MISMO baile que hace el dictado desde el 5-sep, y por el mismo
    motivo: apartar el GUI, asegurarse de que el foco esta en la ventana
    buena, actuar, y volver a subirlo. Alli se descubrio que funcionaba de
    casualidad -- minimizar devolvia el foco de rebote -- y se hizo
    explicito; aqui no se habia hecho.
    """
    if ventana_activa_ajena():
        return False                      # el foco ya esta donde toca
    if gui is None:
        return False
    try:
        gui.apartar_ventana()
    except Exception as exc:
        print(f"[actions] no se pudo apartar el GUI: {exc!r}")
        return False
    time.sleep(config.PASTE_ACTIVATE_DELAY_MS / 1000)
    if not asegurar_ventana_destino():
        print("[actions] OJO: no hay ventana destino clara, la tecla puede "
              "no llegar a ningun sitio")
    time.sleep(config.PASTE_ACTIVATE_DELAY_MS / 1000)
    return True


def execute_keyboard_shortcut(gui, shortcut_name: str, preparar: bool = True,
                              al_volver=None) -> bool:
    """
    Ejecuta un atajo de teclado predefinido desde PREDEFINED_ACTIONS
    (ver input_action.py): "copy", "paste", "save", "tab", "enter",
    "space", "escape", "scroll_up"... Es lo que hay detrás de las
    entradas `"action": "keyboard:<nombre>"` de commands.json (ver
    command_router, estado IDLE).

    El teclado se inyecta a nivel de dispositivo virtual (uinput, vía
    ydotool), así que la tecla la recibe la ventana que TENGA EL FOCO. Por
    eso, SI el foco lo tiene nuestra ventana, se aparta antes y se devuelve
    después -- ver apartar_gui_si_estorba(). Si ya lo tiene otra, no se toca
    nada: es el caso normal y no hay que pagar ninguna espera.
    """

    if not input_action:
        print("[actions] ERROR: input_action no disponible")
        return False

    action_data = input_action.PREDEFINED_ACTIONS.get(shortcut_name)
    if not action_data:
        print(f"[actions] Atajo no reconocido: {shortcut_name}")
        return False

    # preparar=False lo usa "guardar como", que escribe el nombre MAS TARDE
    # (con un temporizador, esperando a que salga el dialogo): si el GUI
    # volviera al frente ahora, ese nombre acabaria escribiendose aqui. Alli
    # se hace el baile a mano y se devuelve el foco al terminar de escribir.
    aparto = apartar_gui_si_estorba(gui) if preparar else False

    try:
        # copia sin "action_type" -- si se dejara dentro de **params,
        # input_action() lo recibiría DOS veces (posicional + keyword) y
        # reventaría con TypeError antes de mandar nada
        params = dict(action_data)
        action_type = params.pop("action_type", None)
        return bool(input_action.input_action(action_type, last_position=None, **params))
    except Exception as e:
        print(f"[actions] Error ejecutando atajo '{shortcut_name}': {e}")
        return False
    finally:
        if aparto:
            # al_volver: lo que haga falta ANTES de volver a ensenar el GUI,
            # con VC todavia apartado -- el refresco de capturas, que asi sale
            # limpio. Si se da, se encarga el de volver a subirlo.
            try:
                if al_volver:
                    al_volver()
                else:
                    gui.subir_ventana()
            except Exception as exc:
                print(f"[actions] no se pudo devolver el GUI al frente: {exc!r}")
