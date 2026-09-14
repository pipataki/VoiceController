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
backends: la capa que toca el sistema, elegida sola según la plataforma.

Por qué existe
--------------
Todo lo que VoiceController le hace al ordenador -- escribir una tecla,
mover el ratón, hacer clic, capturar la pantalla, minimizar una ventana --
pasa por herramientas que en Linux son `ydotool`, `kdotool` y
`spectacle`. Ninguna existe fuera de Linux, y `ydotool` en particular
escribe por `/dev/uinput`, que es del kernel.

Eso significaba que el programa no era portable: no por su diseño, sino
porque esas llamadas estaban repartidas por seis módulos. Aquí se
concentran detrás de UNA interfaz, y cada plataforma trae su
implementación.

Cómo se elige
-------------
Sola, por `sys.platform`, salvo que se fuerce con `config.BACKEND`
("linux", "windows" o "auto"). Forzarlo sirve sobre todo para probar: en
una máquina Linux se puede pedir el backend de Windows y ver que falla
con un mensaje claro en vez de a medias.

Qué hace cada backend
---------------------
    send_key(spec, repeat)        "ctrl+c", "Tab", "Down"
    move_pointer(x, y)            píxeles físicos absolutos
    click(boton)                  "left" | "right" | "middle"
    scroll(direccion, veces)      "up" | "down" | "left" | "right"
    screenshot(destino)           captura del escritorio a un fichero
    window_action(kind)           minimize/maximize/close... sobre la del foco
    available()                   (bool, motivo) -- ¿se puede usar aquí?

El backend de Linux NO reimplementa nada: delega en el código que ya
estaba probado (`keyboard_keys`, `grid_vc`, `actions`, `board`). El
objetivo de esta capa era hacer sitio para otras plataformas, no
reescribir lo que ya funciona.
"""

import sys

_backend = None


def _elegir():
    import config
    forzado = getattr(config, "BACKEND", "auto")
    if forzado == "auto":
        nombre = "windows" if sys.platform.startswith("win") else "linux"
    else:
        nombre = forzado
    if nombre == "windows":
        from . import windows as mod
    else:
        from . import linux as mod
    return mod


def get():
    """Devuelve el backend de esta máquina, cargándolo la primera vez."""
    global _backend
    if _backend is None:
        _backend = _elegir()
        disponible, motivo = _backend.available()
        estado = "OK" if disponible else f"INCOMPLETO -- {motivo}"
        print(f"[backends] plataforma: {_backend.NOMBRE} ({estado})")
    return _backend


# Atajos, para que quien llame no tenga que hacer get() cada vez.
def send_key(spec, repeat=1):        return get().send_key(spec, repeat)
def move_pointer(x, y):              return get().move_pointer(x, y)
def click(boton="left"):             return get().click(boton)
def scroll(direccion, veces=1):      return get().scroll(direccion, veces)
def screenshot(destino):             return get().screenshot(destino)
def window_action(kind):             return get().window_action(kind)
def available():                     return get().available()
def type_text(text):                 return get().type_text(text)
def play_wav(datos, rate=None):      return get().play_wav(datos, rate)
def activate_window(nombre):         return get().activate_window(nombre)

# --- primitivas del ARRASTRE ------------------------------------------------
#
# Hacen falta para seleccionar por voz (ver actions.seleccionar_rango): un
# recuadro de seleccion se dibuja pulsando en una esquina, moviendose, y
# soltando en la otra. Con `click()` -- que pulsa y suelta de golpe -- eso no
# se puede hacer.
#
# `move_pointer_relative` existe aparte de `move_pointer` porque el
# movimiento ABSOLUTO en Linux pasa primero por la esquina de la pantalla
# (grid_vc.move_pointer_physical), y con el boton pulsado eso convierte
# el arrastre en un garabato. Lo descubrimos el 6-sep-2026 probandolo.
def mouse_down(boton="left"):        return get().mouse_down(boton)
def mouse_up(boton="left"):          return get().mouse_up(boton)
def move_pointer_relative(dx, dy):   return get().move_pointer_relative(dx, dy)
def key_down(nombre):                return get().key_down(nombre)
def key_up(nombre):                  return get().key_up(nombre)


def _geometria_logica():
    """True si el backend activo entrega la geometria de ventanas en
    pixeles logicos (hay que escalarla para usarla sobre la captura)."""
    return bool(getattr(get(), "GEOMETRIA_LOGICA", True))


def __getattr__(nombre):
    # GEOMETRIA_LOGICA se resuelve al pedirla, porque el backend se elige
    # en tiempo de ejecucion.
    if nombre == "GEOMETRIA_LOGICA":
        return _geometria_logica()
    raise AttributeError(nombre)


def window_geometry_by_name(nombre, excluir="VoiceController"):
    """(x, y, ancho, alto, titulo, False) de la ventana cuyo titulo contenga
    `nombre`, o None si no hay ninguna. La usa el comando "foco <nombre>".

    Si la plataforma no lo implementa devuelve None."""
    fn = getattr(get(), "window_geometry_by_name", None)
    if fn is None:
        return None
    return fn(nombre, excluir)


def focused_window_geometry(excluir="VoiceController"):
    """(x, y, ancho, alto, titulo, recordada) de la ventana en la que se
    estaba trabajando, o None. La usa la vista "foco".

    `recordada` es True si no es la ventana activa de ahora sino la ultima
    conocida -- el comando de voz lo avisa.

    Si la plataforma no lo implementa devuelve None en vez de fallar: la
    vista simplemente no estara disponible ahi."""
    fn = getattr(get(), "focused_window_geometry", None)
    if fn is None:
        return None
    return fn(excluir)
