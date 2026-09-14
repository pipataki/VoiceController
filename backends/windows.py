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
Backend de Windows.

PROBADO EN UNA MÁQUINA REAL, en parte. Se verificó en una VM con
Windows 10 por SSH: 13 de 13 en el diagnóstico y 6 de 6 en la prueba de
teclado (ver MANIFEST.md, "Windows: la capa backends, verificada en una
máquina real").

LO QUE SIGUE SIN PROBAR son las primitivas del arrastre añadidas el
6-sep-2026 -- mouse_down, mouse_up, move_pointer_relative, key_down y
key_up -- que son las que usa seleccionar por voz. Escritas contra la API
de pydirectinput, que las documenta, pero nadie las ha ejecutado.

Y un aviso que costó una tanda entera de falsos negativos: **una sesión
SSH en Windows no tiene escritorio**. BitBlt y GetForegroundWindow no
tienen a qué mirar, así que cualquier cosa gráfica probada por SSH dará un
falso negativo. Para eso hay que lanzarlo DENTRO de la sesión del usuario
con una tarea programada (schtasks /ru <usuario> /it) que deje el
resultado en un fichero.

Equivalencias con lo que hace el backend de Linux:

    teclado/ratón   ydotool     ->  pydirectinput  (usa SendInput de Win32,
                                    que funciona también dentro de juegos y
                                    aplicaciones que ignoran otras APIs)
    capturas        spectacle   ->  mss            (rápida y sin dependencias
                                    del escritorio)
    ventanas        kdotool     ->  pygetwindow    (envuelve las funciones de
                                    ventana de Win32)

Se instalan con:
    pip install pydirectinput mss pygetwindow

Diferencias que hay que tener presentes al probarlo
---------------------------------------------------
1. **El scroll SÍ existe de verdad.** En Linux se emula con flechas porque
   ydotool no expone la rueda; aquí hay rueda real, así que el resultado
   no será idéntico -- probablemente mejor, pero distinto.
2. **Las coordenadas son lógicas, no físicas.** Con escalado de pantalla
   (125%, 150%...) Windows miente sobre el tamaño salvo que el proceso se
   declare "DPI aware". Se hace al importar; si aun así el puntero cae
   desplazado, es por ahí.
3. **No hay demonio que arrancar.** El equivalente de `ydotoold` no
   existe: SendInput funciona sin más.
"""

import sys

NOMBRE = "windows"

_pdi = None
_mss = None
_gw = None


def _cargar():
    """Importa lo que haga falta, una sola vez y solo si se usa."""
    global _pdi, _mss, _gw
    if _pdi is None:
        try:
            import pydirectinput
            pydirectinput.FAILSAFE = False   # si no, mover a una esquina aborta
            pydirectinput.PAUSE = 0.0        # sin pausa entre acciones
            _pdi = pydirectinput
        except ImportError:
            _pdi = False
    if _mss is None:
        try:
            import mss as _m
            _mss = _m
        except ImportError:
            _mss = False
    if _gw is None:
        try:
            import pygetwindow
            _gw = pygetwindow
        except ImportError:
            _gw = False


def _dpi_aware():
    """Sin esto, con escalado de pantalla Windows devuelve coordenadas
    'virtuales' y el puntero cae desplazado respecto a lo que se ve."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # por monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


if sys.platform.startswith("win"):
    _dpi_aware()


def available():
    _cargar()
    faltan = [n for n, m in (("pydirectinput", _pdi), ("mss", _mss),
                             ("pygetwindow", _gw)) if not m]
    if not sys.platform.startswith("win"):
        return False, "este backend solo sirve en Windows"
    if _pdi is False:
        return False, "falta pydirectinput (sin él no se escribe nada)"
    if faltan:
        return True, f"faltan {', '.join(faltan)}: se pierden capturas o ventanas"
    return True, ""


# Nombres de tecla de VoiceController -> nombres de pydirectinput. Los que
# no aparecen se pasan tal cual (letras, dígitos).
_TECLAS = {
    "return": "enter", "intro": "enter", "escape": "esc",
    "backspace": "backspace", "page_up": "pageup", "page_down": "pagedown",
    "kpenter": "enter", "printscreen": "printscreen",
    "leftctrl": "ctrl", "control": "ctrl", "leftshift": "shift",
    "leftalt": "alt", "meta": "win", "super": "win",
}


# Teclas que pydirectinput NO entrega bien. La Windows es el caso claro:
# la manda como scancode 0x5B sin la marca de "tecla extendida", y el
# shell solo reconoce la de verdad (0xE05B). Resultado: keyDown/keyUp
# dicen True y el menu Inicio no se abre. Para estas se manda la TECLA
# VIRTUAL con SendInput, que no depende de scancodes.
_VIRTUALES = {"win": 0x5B, "super": 0x5B, "winleft": 0x5B, "winright": 0x5C,
              "apps": 0x5D}


def _tecla_virtual(vk, soltar):
    e = _INPUT(type=_INPUT_KEYBOARD)
    e.u.ki = _KEYBDINPUT(vk, 0, _KEYEVENTF_KEYUP if soltar else 0, 0, None)
    return e


def _enviar_virtual(vk):
    eventos = [_tecla_virtual(vk, False), _tecla_virtual(vk, True)]
    lote = (_INPUT * len(eventos))(*eventos)
    enviados = _user32.SendInput(len(eventos), lote, _ct.sizeof(_INPUT))
    return enviados == len(eventos)


def send_key(spec, repeat=1):
    _cargar()
    if not _pdi:
        return False
    # Tecla suelta de las problematicas (sin modificadores): via virtual.
    solo = str(spec).strip().lower()
    if solo in _VIRTUALES:
        bien = True
        for _ in range(max(1, int(repeat))):
            bien = _enviar_virtual(_VIRTUALES[solo]) and bien
        if not bien:
            print(f"[backends.windows] no se pudo enviar {spec!r}")
        return bien
    partes = [p.strip().lower() for p in str(spec).split("+") if p.strip()]
    if not partes:
        return False
    teclas = [_TECLAS.get(p, p) for p in partes]
    modificadores, principal = teclas[:-1], teclas[-1]
    # Se miran los valores devueltos: pydirectinput NO lanza excepción
    # cuando no consigue inyectar (por ejemplo desde una sesión sin
    # escritorio), simplemente devuelve False. Dando por bueno "no ha
    # petado" se informaba de éxito con el teclado sin llegar a ninguna
    # parte, que es la peor forma de fallar: silenciosa.
    try:
        bien = True
        for m in modificadores:
            bien = _pdi.keyDown(m) and bien
        for _ in range(max(1, int(repeat))):
            bien = _pdi.press(principal) and bien
        # Los modificadores se sueltan SIEMPRE, aunque algo haya fallado:
        # dejar Ctrl pulsada convierte cada tecla siguiente en un atajo.
        for m in reversed(modificadores):
            bien = _pdi.keyUp(m) and bien
        if not bien:
            print(f"[backends.windows] {spec!r} no se pudo inyectar "
                  f"(¿sesión sin escritorio?)")
        return bool(bien)
    except Exception as exc:
        print(f"[backends.windows] error enviando {spec!r}: {exc!r}")
        return False


def move_pointer(x, y):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.moveTo(int(x), int(y))
        return True
    except Exception as exc:
        print(f"[backends.windows] error moviendo el puntero: {exc!r}")
        return False


# --- primitivas del arrastre ------------------------------------------------
#
# Hacen falta para seleccionar por voz (ver actions.seleccionar_rango). En
# Linux salen de ydotool; aqui de pydirectinput, que ya las trae:
#
#     ydotool click 0x40   ->  _pdi.mouseDown()
#     ydotool click 0x80   ->  _pdi.mouseUp()
#     ydotool mousemove    ->  _pdi.moveRel(..., relative=True)
#     ydotool key 42:1     ->  _pdi.keyDown("shift")
#
# ESTAS CINCO SIGUEN SIN PROBAR. El resto del fichero se verifico en una VM
# real (ver la cabecera), pero estas se anadieron el 6-sep-2026 y nadie las
# ha ejecutado. Escritas contra la API de pydirectinput, que las documenta.

def mouse_down(boton="left"):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.mouseDown(button=boton if boton in ("left", "right", "middle")
                       else "left")
        return True
    except Exception as exc:
        print(f"[backends.windows] error pulsando el boton: {exc!r}")
        return False


def mouse_up(boton="left"):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.mouseUp(button=boton if boton in ("left", "right", "middle")
                     else "left")
        return True
    except Exception as exc:
        print(f"[backends.windows] error soltando el boton: {exc!r}")
        return False


def move_pointer_relative(dx, dy):
    """Mueve DESDE DONDE ESTE. `relative=True` es importante: sin eso,
    pydirectinput calcula la posicion absoluta y le afecta la curva de
    aceleracion del raton de Windows, con lo que el arrastre no acaba
    donde se le dijo."""
    if not dx and not dy:
        return True
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.moveRel(int(dx), int(dy), relative=True)
        return True
    except TypeError:
        # Versiones antiguas de pydirectinput no aceptan `relative`.
        try:
            _pdi.moveRel(int(dx), int(dy))
            return True
        except Exception as exc:
            print(f"[backends.windows] error moviendo en relativo: {exc!r}")
            return False
    except Exception as exc:
        print(f"[backends.windows] error moviendo en relativo: {exc!r}")
        return False


def key_down(nombre):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.keyDown(nombre)
        return True
    except Exception as exc:
        print(f"[backends.windows] error manteniendo {nombre!r}: {exc!r}")
        return False


def key_up(nombre):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.keyUp(nombre)
        return True
    except Exception as exc:
        print(f"[backends.windows] error soltando {nombre!r}: {exc!r}")
        return False


def click(boton="left"):
    _cargar()
    if not _pdi:
        return False
    try:
        _pdi.click(button={"left": "left", "right": "right",
                           "middle": "middle"}.get(boton, "left"))
        return True
    except Exception as exc:
        print(f"[backends.windows] error en el clic: {exc!r}")
        return False


# Constantes de mouse_event (winuser.h). Se llama a la API de Windows
# directamente porque no todas las versiones de pydirectinput traen
# scroll()/hscroll(): la 1.0.4 no las tiene, y el fallo solo aparece en
# tiempo de ejecución. Con ctypes el scroll no depende de la versión.
_MOUSEEVENTF_WHEEL  = 0x0800
_MOUSEEVENTF_HWHEEL = 0x01000


def scroll(direccion, veces=1):
    """Aquí SÍ hay rueda de verdad, a diferencia de Linux (ver el docstring
    del módulo). Se usa un paso de 120, que es lo que manda Windows por
    cada muesca de la rueda."""
    paso = 120 * max(1, int(veces))
    evento, cantidad = {
        "up":    (_MOUSEEVENTF_WHEEL,   paso),
        "down":  (_MOUSEEVENTF_WHEEL,  -paso),
        "left":  (_MOUSEEVENTF_HWHEEL, -paso),
        "right": (_MOUSEEVENTF_HWHEEL,  paso),
    }.get(direccion, (None, 0))
    if evento is None:
        return False
    try:
        import ctypes
        ctypes.windll.user32.mouse_event(evento, 0, 0, cantidad, 0)
        return True
    except Exception as exc:
        print(f"[backends.windows] error en el scroll: {exc!r}")
        return False


def screenshot(destino):
    _cargar()
    if not _mss:
        return False
    try:
        with _mss.mss() as sct:
            img = sct.grab(sct.monitors[0])      # 0 = todos los monitores
            _mss.tools.to_png(img.rgb, img.size, output=str(destino))
        return True
    except Exception as exc:
        print(f"[backends.windows] error capturando: {exc!r}")
        return False


def window_action(kind):
    _cargar()
    if not _gw:
        return False
    try:
        v = _gw.getActiveWindow()
        if v is None:
            return False
        # Misma salvaguarda que en Linux: no actuar sobre la propia ventana
        # de VoiceController, o un "cierra ventana" cerraría el programa con
        # el que se está hablando.
        if "voicecontroller" in (v.title or "").lower():
            print("[backends.windows] ignorado: el foco es el propio VoiceController")
            return False
        if kind == "minimize":     v.minimize()
        elif kind == "maximize":   v.maximize()
        elif kind == "unmaximize": v.restore()
        elif kind == "close":      v.close()
        elif kind == "raise":      v.activate()
        else:
            print(f"[backends.windows] acción de ventana no soportada: {kind!r}")
            return False
        return True
    except Exception as exc:
        print(f"[backends.windows] error en la acción de ventana: {exc!r}")
        return False


# --- escribir texto literal ------------------------------------------
# NO se usa pydirectinput para esto. Manda scancodes, que dependen de la
# distribución del teclado: con una distribución española no sabría sacar
# acentos ni la ñ, y el dictado en español los necesita constantemente.
# SendInput con KEYEVENTF_UNICODE manda el CARÁCTER, no la tecla, así que
# escribe cualquier cosa sin importar la distribución.
#
# OJO con el tamaño de INPUT: la unión hay que declararla ENTERA aunque
# aquí solo se use el teclado, porque quien la dimensiona es MOUSEINPUT
# (32 bytes), no KEYBDINPUT (24). Si se declara solo con el teclado,
# sizeof(INPUT) sale 32 en vez de 40, y SendInput rechaza la llamada
# devolviendo 0 **sin poner código de error**: no escribe nada y no se
# queja. Costó encontrarlo.
_KEYEVENTF_UNICODE = 0x0004
_KEYEVENTF_KEYUP   = 0x0002
_INPUT_KEYBOARD    = 1

import ctypes as _ct
from ctypes import wintypes as _wt


class _MOUSEINPUT(_ct.Structure):
    _fields_ = [("dx", _wt.LONG), ("dy", _wt.LONG),
                ("mouseData", _wt.DWORD), ("dwFlags", _wt.DWORD),
                ("time", _wt.DWORD), ("dwExtraInfo", _ct.POINTER(_ct.c_ulong))]


class _KEYBDINPUT(_ct.Structure):
    _fields_ = [("wVk", _wt.WORD), ("wScan", _wt.WORD),
                ("dwFlags", _wt.DWORD), ("time", _wt.DWORD),
                ("dwExtraInfo", _ct.POINTER(_ct.c_ulong))]


class _HARDWAREINPUT(_ct.Structure):
    _fields_ = [("uMsg", _wt.DWORD), ("wParamL", _wt.WORD),
                ("wParamH", _wt.WORD)]


class _INPUTUNION(_ct.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(_ct.Structure):
    _fields_ = [("type", _wt.DWORD), ("u", _INPUTUNION)]


def _unidades(caracter):
    """Los eventos (bajar y subir) de un carácter. Fuera del plano básico
    -- emoji y demás -- Windows quiere los dos "surrogates" UTF-16."""
    punto = ord(caracter)
    codigos = ([punto] if punto <= 0xFFFF
               else [0xD800 + ((punto - 0x10000) >> 10),
                     0xDC00 + ((punto - 0x10000) & 0x3FF)])
    eventos = []
    for codigo in codigos:
        for arriba in (False, True):
            e = _INPUT(type=_INPUT_KEYBOARD)
            e.u.ki = _KEYBDINPUT(
                0, codigo,
                _KEYEVENTF_UNICODE | (_KEYEVENTF_KEYUP if arriba else 0),
                0, None)
            eventos.append(e)
    return eventos


# NO se usa `ctypes.windll.user32`: ese objeto está CACHEADO y lo comparte
# todo el proceso. Al declararle argtypes con nuestro _INPUT, pydirectinput
# --que llama a la misma SendInput con su propia estructura-- empieza a
# fallar con "expected LP__INPUT instead of LP_Input", y de pronto dejan de
# funcionar las teclas y el ratón, que no se habían tocado. Con WinDLL se
# obtiene un manejador propio y nadie más se entera.
_user32 = _ct.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = (_wt.UINT, _ct.POINTER(_INPUT), _ct.c_int)
_user32.SendInput.restype = _wt.UINT


def type_text(text):
    if not text:
        return True
    u32 = _user32
    try:
        for caracter in str(text):
            eventos = _unidades(caracter)
            lote = (_INPUT * len(eventos))(*eventos)
            enviados = u32.SendInput(len(eventos), lote, _ct.sizeof(_INPUT))
            if enviados != len(eventos):
                print(f"[backends.windows] SendInput solo aceptó {enviados} de "
                      f"{len(eventos)} eventos para {caracter!r}")
                return False
        return True
    except Exception as exc:
        print(f"[backends.windows] error escribiendo texto: {exc!r}")
        return False


def play_wav(datos, rate=None):
    """`winsound` viene con Python y reproduce un WAV desde memoria, así que
    no hace falta ninguna dependencia. Eso sí, necesita la CABECERA del WAV:
    si llegan datos PCM en crudo (que es como los manda el respaldo de
    espeak, con `rate`), se le pone una delante."""
    import winsound
    import io
    import wave
    try:
        if rate:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(int(rate))
                w.writeframes(datos)
            datos = buf.getvalue()
        winsound.PlaySound(datos, winsound.SND_MEMORY)
        return True
    except Exception as exc:
        print(f"[backends.windows] error reproduciendo: {exc!r}")
        return False


def _clase_de(hwnd):
    """La clase de ventana de Windows (GetClassNameW), o "" si no se sabe."""
    try:
        import ctypes as _c
        buf = _c.create_unicode_buffer(256)
        n = _c.windll.user32.GetClassNameW(_c.c_void_p(hwnd), buf, 256)
        return buf.value if n else ""
    except Exception:
        return ""


def _encaja(v, buscado):
    """¿La ventana `v` es la que se busca? `buscado` va ya en minusculas.

    "clase:<nombre>" compara la CLASE de ventana en vez del titulo. Hace
    falta para el Explorador, que se titula con el nombre de la carpeta
    abierta y no tiene ningun trozo fijo de titulo que buscar -- ver
    window_names._DEFAULTS_WINDOWS. Lo demas, por titulo y por "contiene".
    """
    if buscado.startswith("clase:"):
        return _clase_de(getattr(v, "_hWnd", None)).lower() == buscado[6:].strip()
    return bool(v.title) and buscado in v.title.lower()


def activate_window(nombre):
    """Trae al frente la ventana cuyo título contenga `nombre`.

    Se compara en minúsculas y por "contiene", igual que hace kdotool en
    Linux con su `(?i)`: quien dicta "kate" no va a acertar la
    capitalización ni el título completo."""
    _cargar()
    if not _gw or not nombre or not str(nombre).strip():
        return False
    buscado = str(nombre).strip().lower()
    try:
        for v in _gw.getAllWindows():
            if not _encaja(v, buscado):
                continue
            # A diferencia de window_action(), aquí NO se excluye la ventana
            # de VoiceController: window_action actúa sobre la que tenga el
            # foco (y cerrarla dejaría al usuario sin con qué hablar), pero
            # quien pide traer una ventana POR SU NOMBRE la está pidiendo a
            # propósito. En Linux tampoco se excluye: si aquí se filtrara,
            # las dos plataformas harían cosas distintas.
            if v.isMinimized:
                v.restore()
            v.activate()
            return True
        print(f"[backends.windows] no hay ninguna ventana que contenga {nombre!r}")
        return False
    except Exception as exc:
        print(f"[backends.windows] error activando {nombre!r}: {exc!r}")
        return False



# ---------------------------------------------------------------------------
# Vista "foco": geometria de la ventana en la que se estaba trabajando
# ---------------------------------------------------------------------------
#
# Equivalente de lo que en Linux hace kdotool. La usa board.capture_foco()
# para recortar esa ventana del escritorio ya capturado.
#
# OJO CON EL RECTANGULO. GetWindowRect() -- que es lo que devuelve
# pygetwindow -- incluye los BORDES INVISIBLES que Windows 10 anade alrededor
# de las ventanas para poder redimensionarlas: unos 7 pixeles por lado y
# abajo. Recortando por ahi, la imagen sale con una franja de escritorio
# alrededor y, lo que importa, el mapeo de coordenadas queda descuadrado esos
# pixeles.
#
# Lo correcto es DwmGetWindowAttribute con DWMWA_EXTENDED_FRAME_BOUNDS, que da
# el marco que se VE. Si DWM no contesta (compositor apagado, Windows 7), se
# usa lo que haya y se pierde precision, pero no se rompe nada.

_ULTIMA_AJENA_WIN = None
_DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _marco_visible(hwnd):
    """(x, y, ancho, alto) del marco que se ve, o None si DWM no contesta."""
    try:
        import ctypes as _c
        from ctypes import wintypes as _w

        class _RECT(_c.Structure):
            _fields_ = [("left", _c.c_long), ("top", _c.c_long),
                        ("right", _c.c_long), ("bottom", _c.c_long)]

        rect = _RECT()
        res = _c.windll.dwmapi.DwmGetWindowAttribute(
            _w.HWND(hwnd), _c.c_uint(_DWMWA_EXTENDED_FRAME_BOUNDS),
            _c.byref(rect), _c.sizeof(rect))
        if res != 0:
            return None
        ancho = rect.right - rect.left
        alto = rect.bottom - rect.top
        if ancho <= 0 or alto <= 0:
            return None
        return rect.left, rect.top, ancho, alto
    except Exception:
        return None


# Ver la nota de backends/linux.py. Aqui la geometria sale de GetWindowRect
# (via pygetwindow) y viene en pixeles FISICOS, los mismos de la captura:
# no hay que convertir nada.
#
# MEDIO COMPROBADO. La VM de pruebas esta al 175% (AppliedDPI = 168) y a
# 2560x1600, y el 12-sep-2026 pipataki verifico ahi que el punto verde y los
# items naranja de la CASILLA caen donde deben. Pero eso no pasa por esta
# constante: la casilla sale de la captura, no de la geometria de ninguna
# ventana.
#
# Lo que SI depende de ella es la vista FOCO ("foco kate"), que recorta la
# ventana con esta geometria. Si el proceso no fuera "per-monitor DPI
# aware", estas coordenadas saldrian virtualizadas y el foco recortaria un
# trozo mas pequeno de la cuenta. Si pasa eso, basta con poner True.
GEOMETRIA_LOGICA = False


def _recordada_win():
    if _ULTIMA_AJENA_WIN is None:
        return None
    x, y, ancho, alto, titulo, _ = _ULTIMA_AJENA_WIN
    return (x, y, ancho, alto, titulo, True)


def focused_window_geometry(excluir="VoiceController"):
    """(x, y, ancho, alto, titulo, recordada) de la ventana activa, o None.

    Misma regla que en Linux: si la activa es la nuestra se devuelve la
    ultima que no lo era, marcada como recordada.
    """
    global _ULTIMA_AJENA_WIN
    _cargar()
    if not _gw:
        return _recordada_win()

    try:
        v = _gw.getActiveWindow()
    except Exception as exc:
        print(f"[backends.windows] no se pudo saber la ventana activa: {exc!r}")
        return _recordada_win()

    if v is None:
        return _recordada_win()

    titulo = (getattr(v, "title", "") or "").strip()
    if not titulo:
        # Sin titulo no se puede descartar que sea la nuestra.
        return _recordada_win()
    if excluir and excluir.lower() in titulo.lower():
        return _recordada_win()
    if getattr(v, "isMinimized", False):
        # Minimizada no se ve en el escritorio capturado: recortar ahi daria
        # un trozo de fondo de pantalla.
        return _recordada_win()

    marco = _marco_visible(getattr(v, "_hWnd", None))
    if marco is None:
        try:
            marco = (int(v.left), int(v.top), int(v.width), int(v.height))
        except Exception:
            return _recordada_win()

    x, y, ancho, alto = marco
    if ancho <= 0 or alto <= 0:
        return _recordada_win()

    _ULTIMA_AJENA_WIN = (x, y, ancho, alto, titulo, False)
    return _ULTIMA_AJENA_WIN


def window_geometry_by_name(nombre, excluir="VoiceController"):
    """(x, y, ancho, alto, titulo, False) de la ventana cuyo titulo contenga
    `nombre`, o None. Para el comando "foco <nombre>".

    Se compara en minusculas y por "contiene", igual que activate_window():
    quien dicta "kate" no va a acertar el titulo completo.

    Se pide el marco VISIBLE (ver _marco_visible): GetWindowRect incluye los
    bordes invisibles de Windows 10 y descuadraria el recorte.
    """
    _cargar()
    if not _gw or not nombre or not str(nombre).strip():
        return None
    buscado = str(nombre).strip().lower()
    try:
        for v in _gw.getAllWindows():
            titulo = (v.title or "").strip()
            if not _encaja(v, buscado):
                continue
            if excluir and excluir.lower() in titulo.lower():
                continue
            if getattr(v, "isMinimized", False):
                # Minimizada no esta en el escritorio capturado.
                continue
            marco = _marco_visible(getattr(v, "_hWnd", None))
            if marco is None:
                try:
                    marco = (int(v.left), int(v.top), int(v.width), int(v.height))
                except Exception:
                    continue
            x, y, ancho, alto = marco
            if ancho <= 0 or alto <= 0:
                continue
            return (x, y, ancho, alto, titulo, False)
    except Exception as exc:
        print(f"[backends.windows] error buscando la ventana {nombre!r}: {exc!r}")
    return None
