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
Backend de Linux: ydotool + kdotool + spectacle.

DELIBERADAMENTE no reimplementa nada. Cada función delega en el código
que ya estaba escrito y probado en el proyecto -- `keyboard_keys`,
`grid_vc`, `actions`, `board` -- porque el objetivo de la capa
`backends` era hacer sitio para otras plataformas, no reescribir lo que
ya funciona y arriesgarse a romperlo.
"""

import shutil

NOMBRE = "linux"


def available():
    """(hay_lo_imprescindible, qué falta). Se distingue entre lo que deja
    la aplicación inútil y lo que solo quita funciones: sin `ydotool` no
    se escribe NADA; sin `kdotool` solo se pierden los comandos de
    ventana."""
    import keyboard_keys
    faltan = [] if keyboard_keys.find_ydotool() else ["ydotool"]
    opcionales = ([] if keyboard_keys.find_kdotool() else ["kdotool"]) + \
                 ([] if shutil.which("spectacle") else ["spectacle"])
    if faltan:
        return False, f"falta {', '.join(faltan)} (sin él no se escribe ni una tecla)"
    if opcionales:
        return True, f"sin {', '.join(opcionales)}: se pierden ventanas o capturas"
    return True, ""


def send_key(spec, repeat=1):
    import keyboard_keys
    return keyboard_keys.send_key(spec, repeat=repeat)


def move_pointer(x, y):
    import grid_vc
    grid_vc.move_pointer_physical(int(x), int(y))
    return True


_BOTONES = {"left": "0xC0", "right": "0xC1", "middle": "0xC2"}


def click(boton="left"):
    import actions
    actions._board_click(_BOTONES.get(boton, "0xC0"))
    return True


# --- primitivas del arrastre ------------------------------------------------
#
# En ydotool la parte ALTA del numero de boton dice que se hace:
#
#     0x40  solo PULSAR        0x80  solo SOLTAR        0xC0  las dos
#
# Y la baja, cual: 0 izquierdo, 1 derecho, 2 central. Asi que "pulsar el
# izquierdo" es 0x40 y "soltarlo" 0x80. Estaba disponible desde el primer
# dia sin que nadie lo usara.
_PULSAR = {"left": "0x40", "right": "0x41", "middle": "0x42"}
_SOLTAR = {"left": "0x80", "right": "0x81", "middle": "0x82"}


def mouse_down(boton="left"):
    import actions
    actions._click_crudo(_PULSAR.get(boton, "0x40"))
    return True


def mouse_up(boton="left"):
    import actions
    actions._click_crudo(_SOLTAR.get(boton, "0x80"))
    return True


def move_pointer_relative(dx, dy):
    """Mueve DESDE DONDE ESTE, sin pasar por la esquina.

    move_pointer() va a una posicion absoluta, y para eso
    grid_vc.move_pointer_physical() resetea a la esquina primero. Con
    el boton pulsado eso convierte el arrastre en un garabato -- medido el
    6-sep-2026.
    """
    if not dx and not dy:
        return True
    import grid_vc
    grid_vc.move_pointer_relative(int(dx), int(dy))
    return True


# Codigos evdev de los modificadores que hacen falta sostener.
_MODIFICADORES = {"shift": 42, "ctrl": 29, "alt": 56}


def key_down(nombre):
    import actions
    codigo = _MODIFICADORES.get(nombre)
    if codigo is None:
        return False
    return actions._tecla_cruda(f"{codigo}:1")


def key_up(nombre):
    import actions
    codigo = _MODIFICADORES.get(nombre)
    if codigo is None:
        return False
    return actions._tecla_cruda(f"{codigo}:0")


# El scroll se hace con flechas porque ydotool no expone la rueda del
# ratón -- ver actions._scroll_key, que es de donde viene esta tabla.
_FLECHAS = {"up": "103", "down": "108", "left": "105", "right": "106"}


def scroll(direccion, veces=1):
    import actions
    codigo = _FLECHAS.get(direccion)
    if not codigo:
        return False
    for _ in range(max(1, int(veces))):
        actions._scroll_key(codigo)
    return True


def screenshot(destino=None):
    """Captura el escritorio. Con `destino`, deja el fichero AHÍ.

    En Linux la captura la hace board.capture_tablero(), que escribe
    siempre en su sitio fijo (paths.TABLERO_FILE) porque el resto del
    programa lo espera ahí. Pero el backend de Windows sí honra el
    destino, y dos implementaciones de la misma función no pueden hacer
    cosas distintas: quien las llame no sabría con cuál está hablando.
    Así que se captura y, si piden otro sitio, se copia."""
    import shutil
    import board
    from paths import TABLERO_FILE
    if not board.capture_tablero():
        return False
    if destino and str(destino) != str(TABLERO_FILE):
        try:
            shutil.copy2(TABLERO_FILE, destino)
        except Exception as exc:
            print(f"[backends.linux] no se pudo copiar la captura a {destino}: {exc!r}")
            return False
    return True


def window_action(kind):
    import actions
    return actions.window_action(kind)


def type_text(text):
    """Escribe texto literal, no una tecla: aquí van los acentos y la ñ.

    Delega en actions.type_text, que ya sabe caer al portapapeles si
    ydotool falla -- ese respaldo es importante y no se duplica aquí."""
    import actions
    actions.type_text(text)
    return True


def play_wav(datos, rate=None):
    """Reproduce un WAV que ya está en memoria. `rate` solo hace falta
    cuando los datos son PCM en crudo, sin cabecera."""
    import subprocess
    import shutil
    if not shutil.which("paplay"):
        print("[backends.linux] no está paplay: no se puede reproducir")
        return False
    orden = ["paplay"]
    if rate:
        orden += ["--raw", f"--rate={int(rate)}"]
    try:
        # Limite generoso a proposito (config.AUDIO_TIMEOUT_S): aqui no se
        # trata de cortar nada, sino de que un reproductor colgado no deje
        # el hilo esperando para siempre. Reproducir dura lo que dura el
        # audio, y una ayuda larga puede durar bastante.
        try:
            import config
            espera = float(getattr(config, "AUDIO_TIMEOUT_S", 120.0) or 120.0)
        except Exception:
            espera = 120.0
        subprocess.run(orden, input=datos, check=False, capture_output=True,
                       timeout=espera)
        return True
    except Exception as exc:
        print(f"[backends.linux] error reproduciendo: {exc!r}")
        return False


def activate_window(nombre):
    """Trae al frente la ventana cuyo título case con `nombre`."""
    import actions
    return actions.activate_window_by_name(nombre)



# ---------------------------------------------------------------------------
# Vista "foco": geometria de la ventana en la que se estaba trabajando
# ---------------------------------------------------------------------------
#
# La usa board.capture_foco() para recortar esa ventana del escritorio ya
# capturado. Como el recorte se hace sobre tablero.png y se conoce el
# rectangulo exacto, un toque en el movil se traduce a su punto real sin
# perder precision -- igual que en la vista zoom_out.
#
# En KDE/Wayland todo pasa por kdotool, que habla con KWin por D-Bus.

_ULTIMA_AJENA = None          # geometria de la ultima ventana que NO era la nuestra


def _kdotool(*args) -> str:
    import subprocess
    import keyboard_keys
    binario = keyboard_keys.find_kdotool()
    if binario is None:
        return ""
    try:
        r = subprocess.run([binario, *args], capture_output=True,
                           text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout
        # SE DICE. Antes se devolvia "" sin mas y el fallo salia mucho mas
        # arriba disfrazado de "no hay ninguna ventana": indistinguible de
        # que la ventana de verdad no estuviera. El 10-sep-2026 costo una
        # tarde no poder distinguir esos dos casos.
        salida = (r.stderr or "").strip().replace("\n", " ")[:200]
        print(f"[backends] kdotool {' '.join(args)} -> codigo {r.returncode}"
              f"{': ' + salida if salida else ''}")
        return ""
    except subprocess.TimeoutExpired:
        print(f"[backends] kdotool {' '.join(args)} tardo demasiado (5 s)")
        return ""
    except Exception as exc:
        print(f"[backends] kdotool {' '.join(args)} fallo: {exc!r}")
        return ""


# En que unidades entrega este backend la geometria de las ventanas.
#
# kdotool habla en pixeles LOGICOS (los de KWin): con la pantalla a escala
# 1,8 dice 2133x1200 donde la captura mide 3840x2160. Quien use esas
# coordenadas sobre la imagen capturada tiene que convertirlas antes -- lo
# hace board.capture_foco().
#
# Se DECLARA en vez de adivinarse: el backend de Windows entrega fisicas, y
# aplicarle la conversion alli descuadraria el recorte por el otro lado.
GEOMETRIA_LOGICA = True


def _leer_geometria(salida):
    """(x, y, ancho, alto) de lo que escupe `kdotool getwindowgeometry`, o
    None si no se entiende.

    LOS NUMEROS PUEDEN VENIR CON DECIMALES:

        Position: 680,158
        Geometry: 772.7777777777778x882.7777777777778

    Eso sale cuando la pantalla tiene un escalado que no es un multiplo
    exacto -- 772,77 son 1391 pixeles reales entre 1,8. El codigo anterior
    hacia int("772.7777") directamente, saltaba la excepcion, y la funcion
    devolvia None... que arriba se leia como "no hay ninguna ventana". Asi
    que "foco" dejaba de funcionar CON TODO, y culpando a la ventana.
    (pipataki, 10-sep-2026.)

    Estaba ademas escrito dos veces, una en cada funcion que lo necesitaba.
    Ahora esta una sola vez: era el caso de manual de por que eso se paga.
    """
    x = y = ancho = alto = None
    for linea in (salida or "").splitlines():
        linea = linea.strip()
        try:
            if linea.startswith("Position:"):
                x, y = (round(float(v)) for v in
                        linea.split(":", 1)[1].strip().split(",")[:2])
            elif linea.startswith("Geometry:"):
                ancho, alto = (round(float(v)) for v in
                               linea.split(":", 1)[1].strip().split("x")[:2])
        except Exception:
            return None
    if None in (x, y, ancho, alto) or ancho <= 0 or alto <= 0:
        return None
    return x, y, ancho, alto


def _recordada():
    """La ultima buena conocida, marcada como recordada (no es la activa)."""
    if _ULTIMA_AJENA is None:
        return None
    x, y, ancho, alto, titulo, _ = _ULTIMA_AJENA
    return (x, y, ancho, alto, titulo, True)


def focused_window_geometry(excluir: str = "VoiceController"):
    """(x, y, ancho, alto, titulo, recordada) de la ventana activa, o None.

    `recordada` es True cuando NO es la ventana activa de ahora mismo sino la
    ultima conocida -- pasa si la activa es la nuestra. Quien llame deberia
    decirselo al usuario: no es lo mismo ver lo que tienes delante que ver lo
    ultimo que usaste.

    Si la activa es la nuestra se devuelve la ULTIMA que estuvo activa sin
    serlo: hablando por voz lo normal es que la ventana buena ya sea la
    activa, pero si el usuario acaba de tocar el GUI de VoiceController la
    activa seria la nuestra, y ensenarsela no le sirve de nada.
    """
    global _ULTIMA_AJENA

    # kdotool devuelve el titulo vacio de vez en cuando (visto en pruebas:
    # dos llamadas seguidas, una con nombre y otra sin el). Se reintenta una
    # vez, porque de ese titulo depende reconocer NUESTRA propia ventana: si
    # se cuela, la vista de foco se ensenaria a si misma.
    titulo = ""
    for _ in range(2):
        salida = _kdotool("getactivewindow", "getwindowname")
        if salida.strip():
            titulo = salida.strip().splitlines()[-1].strip()
        if titulo:
            break

    if not titulo:
        # Sin saber de quien es la ventana, mejor la ultima buena conocida
        # que arriesgarse a capturar la nuestra.
        return _recordada()

    if excluir.lower() in titulo.lower():
        return _recordada()           # puede ser None la primera vez

    geo = _kdotool("getactivewindow", "getwindowgeometry")
    if not geo:
        return _recordada()

    medidas = _leer_geometria(geo)
    if medidas is None:
        print(f"[backends] no entiendo la geometria de la ventana activa: "
              f"{geo.strip()!r}")
        return _recordada()
    x, y, ancho, alto = medidas

    _ULTIMA_AJENA = (x, y, ancho, alto, titulo, False)
    return _ULTIMA_AJENA


def window_geometry_by_name(nombre: str, excluir: str = "VoiceController"):
    """(x, y, ancho, alto, titulo, False) de la ventana cuyo TITULO contenga
    `nombre`, o None si no hay ninguna abierta.

    Para el comando "foco <nombre>" ("foco kate", "foco firefox"). Nace de
    una limitacion real: KWin sabe en que orden estan apiladas las ventanas,
    pero kdotool no lo expone -- su `search` devuelve workspace.windowList(),
    que NO es el orden de apilamiento (comprobado: la ventana activa salia la
    tercera de cinco). Sin ese orden no hay forma fiable de decir "la que
    esta justo debajo de la nuestra".

    Decir el nombre lo resuelve mejor que adivinarlo: no depende de ningun
    orden, funciona con muchas ventanas abiertas, y quien lo usa ya sabe en
    que programa quiere trabajar.
    """
    if not nombre or not nombre.strip():
        return None
    ids = [l.strip() for l in _kdotool("search", "--title", nombre.strip()).splitlines()
           if l.strip()]
    for wid in ids:
        titulo = _kdotool("getwindowname", wid).strip().splitlines()
        titulo = titulo[-1].strip() if titulo else ""
        if not titulo:
            continue
        if excluir and excluir.lower() in titulo.lower():
            continue          # la nuestra no: no tiene sentido enfocarse a si misma
        geo = _kdotool("getwindowgeometry", wid)
        medidas = _leer_geometria(geo)
        if medidas is None:
            print(f"[backends] no entiendo la geometria de {titulo!r}: "
                  f"{geo.strip()!r}")
            continue
        x, y, ancho, alto = medidas
        return (x, y, ancho, alto, titulo, False)
    return None
