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
carpetas: abrir por voz una carpeta del perfil del usuario.

    "carpeta descargas"  ->  si ya esta abierta, la trae; si no, la abre

NUNCA CREA NADA. Si la carpeta no existe, se dice y no se hace nada. Es
una peticion explicita de pipataki y tiene razon: un comando de voz que crea
carpetas por su cuenta, con lo mal que se entienden a veces los nombres,
llenaria el perfil de carpetas fantasma con nombres mal oidos.

LOS NOMBRES SE PREGUNTAN AL SISTEMA, NO SE ESCRIBEN
---------------------------------------------------
Las carpetas estandar estan traducidas: en este equipo son "Descargas",
"Imagenes", "Musica"... y en un sistema en ingles serian "Downloads",
"Pictures", "Music". Escribir las rutas a mano funcionaria hoy y se
romperia con el primer cambio de idioma del escritorio.

`xdg-user-dir DOWNLOAD` devuelve la de verdad, sea cual sea el idioma. Si
esa herramienta no esta, se cae con elegancia a mirar los nombres mas
probables dentro de $HOME.

POR QUE SE HABLA CON DOLPHIN POR D-BUS
--------------------------------------
Lanzar `dolphin <ruta>` abriria una ventana MAS cada vez. Dolphin expone
dos metodos que evitan eso:

    isUrlOpen(url)              ¿ya la tienes abierta?
    openDirectories([url])      abrela EN LA VENTANA QUE YA HAY

Asi, pedir tres carpetas seguidas deja tres pestañas en una ventana, no
tres ventanas. Y si Dolphin no esta abierto, entonces si se lanza.
"""

import os
import shutil
import subprocess

# Nombre que se dice -> clave de xdg-user-dir. Las claves son las del
# estandar freedesktop y NO se traducen; lo que se traduce es la carpeta a
# la que apuntan, que es justo el motivo de preguntar en vez de suponer.
_ESTANDAR = {
    "escritorio": "DESKTOP",
    "documentos": "DOCUMENTS",
    "descargas": "DOWNLOAD",
    "musica": "MUSIC",
    "imagenes": "PICTURES",
    "fotos": "PICTURES",
    "videos": "VIDEOS",
    "plantillas": "TEMPLATES",
    "publico": "PUBLICSHARE",
    # Y las inglesas, por si el escritorio esta en ingles o se dicen asi.
    "desktop": "DESKTOP",
    "documents": "DOCUMENTS",
    "downloads": "DOWNLOAD",
    "download": "DOWNLOAD",
    "music": "MUSIC",
    "pictures": "PICTURES",
    "videos_en": "VIDEOS",
}

_TIEMPO = 4          # segundos de espera para xdg-user-dir y qdbus


def _qdbus():
    """El binario de qdbus que haya: en Plasma 6 se llama qdbus6."""
    return shutil.which("qdbus6") or shutil.which("qdbus")


def _servicio_dolphin():
    """El nombre del servicio D-Bus de Dolphin, o None si no esta abierto.

    Es del estilo `org.kde.dolphin-33472`: lleva el PID pegado, asi que hay
    que buscarlo cada vez y no se puede escribir fijo.
    """
    q = _qdbus()
    if not q:
        return None
    try:
        r = subprocess.run([q], capture_output=True, text=True, timeout=_TIEMPO)
        for linea in (r.stdout or "").splitlines():
            linea = linea.strip()
            if linea.startswith("org.kde.dolphin"):
                return linea
    except Exception:
        pass
    return None


def ruta_de(nombre_normalizado):
    """La ruta de esa carpeta, o None si no la hay.

    Se prueba, en este orden:
      1. carpeta estandar del perfil (xdg-user-dir);
      2. una carpeta con ese nombre directamente dentro de $HOME.

    NO se crea nada: si no existe, se devuelve None y quien llame avisa.
    """
    clave = _ESTANDAR.get(nombre_normalizado)
    if clave:
        binario = shutil.which("xdg-user-dir")
        if binario:
            try:
                r = subprocess.run([binario, clave], capture_output=True,
                                   text=True, timeout=_TIEMPO)
                ruta = (r.stdout or "").strip()
                # xdg-user-dir devuelve $HOME cuando no conoce la clave: eso
                # no es la carpeta pedida, es "no se".
                if ruta and os.path.isdir(ruta) and ruta != os.path.expanduser("~"):
                    return ruta
            except Exception:
                pass

    # Sin xdg-user-dir, o para una carpeta cualquiera del perfil: se busca
    # por nombre dentro de $HOME, sin distinguir mayusculas ni acentos.
    casa = os.path.expanduser("~")
    try:
        import unicodedata

        def _plano(t):
            t = unicodedata.normalize("NFD", t)
            return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()

        buscado = _plano(nombre_normalizado)
        for entrada in os.listdir(casa):
            completa = os.path.join(casa, entrada)
            if os.path.isdir(completa) and _plano(entrada) == buscado:
                return completa
    except Exception:
        pass
    return None


_ultima_abierta = None      # lo ultimo que abrimos NOSOTROS, ver carpeta_actual()


def _al_frente():
    """Sube la ventana de Dolphin. Devuelve si se pudo.

    Se usa el MISMO camino que el comando "trae" (kdotool, via actions), en
    vez del activateWindow de Dolphin: en Wayland ese metodo pide un token
    de activacion que nosotros no tenemos, y el de "trae" ya esta probado.
    """
    try:
        import actions
        return bool(actions.activate_window_by_name("Dolphin"))
    except Exception as exc:
        print(f"[carpetas] no se pudo subir Dolphin: {exc!r}")
        return False


def abrir(ruta):
    """Trae la carpeta si ya esta abierta; si no, la abre.

    Devuelve (ok, que_se_hizo) para que quien llame pueda decirlo.
    """
    global _ultima_abierta
    q = _qdbus()
    servicio = _servicio_dolphin()
    url = "file://" + ruta
    _ultima_abierta = ruta

    if q and servicio:
        objeto = "/dolphin/Dolphin_1"
        try:
            r = subprocess.run([q, servicio, objeto,
                                "org.kde.dolphin.MainWindow.isUrlOpen", url],
                               capture_output=True, text=True, timeout=_TIEMPO)
            ya_abierta = (r.stdout or "").strip().lower() == "true"
        except Exception:
            ya_abierta = False

        if ya_abierta:
            # Saber que esta abierta no la pone delante. Este comando se
            # llama "carpeta X" y lo que espera quien lo dice es VERLA:
            # decir "traida" sin traerla es mentir en la respuesta.
            return (True, "traida") if _al_frente() else (True, "ya estaba abierta")

        try:
            subprocess.run([q, servicio, objeto,
                            "org.kde.dolphin.MainWindow.openDirectories",
                            url, "false"],
                           capture_output=True, text=True, timeout=_TIEMPO)
            # openDirectories cambia de carpeta la ventana que ya hay, pero
            # tampoco la sube: si estaba detras, sigue detras.
            _al_frente()
            return True, "abierta en la ventana que ya habia"
        except Exception as exc:
            print(f"[carpetas] no se pudo hablar con Dolphin: {exc!r}")

    # Dolphin cerrado (o sin qdbus): se lanza uno.
    binario = shutil.which("dolphin")
    if not binario:
        return False, "no encuentro Dolphin"
    try:
        subprocess.Popen([binario, ruta],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "abierta en una ventana nueva"
    except Exception as exc:
        return False, f"no se pudo abrir: {exc!r}"


def terminal_en(ruta):
    """Abre una terminal en esa carpeta."""
    binario = shutil.which("konsole")
    args = [binario, "--workdir", ruta] if binario else None
    if not args:
        binario = shutil.which("x-terminal-emulator") or shutil.which("xterm")
        if not binario:
            return False
        args = [binario]
    try:
        subprocess.Popen(args, cwd=ruta,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as exc:
        print(f"[carpetas] no se pudo abrir la terminal: {exc!r}")
        return False


# ---------------------------------------------------------------------------
# CREAR DENTRO DE LA CARPETA QUE DOLPHIN ESTE MOSTRANDO
# ---------------------------------------------------------------------------
#
# PRIMERO SE INTENTO CON EL DIALOGO DE DOLPHIN, Y NO VALIA
# --------------------------------------------------------
# La idea original era disparar sus acciones `create_dir` / `create_file` y
# dejar que EL abriera su dialogo en la carpeta que tuviera delante, sin que
# nosotros calculasemos ninguna ruta. Elegante, y muerta en la primera
# prueba real (pipataki, 10-sep-2026):
#
#   `create_file` no crea "un archivo": crea la plantilla ARCHIVO DE TEXTO.
#   Escribas lo que escribas, sale .txt. No hay forma de poner otra
#   extension, asi que "arranque punto ese ache" era imposible.
#
# Y ademas obligaba a teclear dentro de un dialogo, que es la clase de cosa
# que se estropea sola.
#
# COMO SE SABE QUE CARPETA ESTA MIRANDO
# -------------------------------------
# Dolphin NO publica la carpeta actual: se miro su interfaz D-Bus entera y
# no existe ningun getter. Pero publica dos cosas que juntas bastan:
#
#   - el TITULO de la ventana, que es el nombre de la carpeta ("Música");
#   - `isUrlOpen(url)`, que dice si una ruta concreta esta abierta.
#
# El titulo no da la ruta -- puede haber muchas carpetas "Música" --, pero
# convierte el problema en una lista corta de candidatas, y `isUrlOpen`
# hace de juez. Se prueban por orden de probabilidad y gana la primera que
# diga que si. Si ninguna lo dice, NO SE CREA NADA: mas vale no crear que
# crear en el sitio equivocado, que no se deshace con un "atras".

import os.path


def carpeta_actual():
    """La carpeta que Dolphin tiene delante, o None si no se puede saber."""
    q = _qdbus()
    servicio = _servicio_dolphin()
    if not q or not servicio:
        return None
    objeto = "/dolphin/Dolphin_1"

    def abierta(ruta):
        try:
            r = subprocess.run([q, servicio, objeto,
                                "org.kde.dolphin.MainWindow.isUrlOpen",
                                "file://" + ruta],
                               capture_output=True, text=True, timeout=_TIEMPO)
            return (r.stdout or "").strip().lower() == "true"
        except Exception:
            return False

    try:
        r = subprocess.run([q, servicio, objeto,
                            "org.qtproject.Qt.QWidget.windowTitle"],
                           capture_output=True, text=True, timeout=_TIEMPO)
        titulo = (r.stdout or "").strip()
    except Exception:
        titulo = ""
    if not titulo:
        return None

    casa = os.path.expanduser("~")
    candidatas = []

    # 1. Lo ultimo que abrimos nosotros. Es el caso corriente -- "carpeta
    #    descargas" y acto seguido "crear archivo ..." -- y ahi la ruta la
    #    sabemos de verdad, sin adivinar nada.
    if _ultima_abierta and os.path.basename(_ultima_abierta) == titulo:
        candidatas.append(_ultima_abierta)

    # 2. La propia casa, que se titula con el nombre del usuario.
    if titulo in (os.path.basename(casa), "Inicio", "Home", "Carpeta personal"):
        candidatas.append(casa)

    # 3. Justo dentro de casa, y las estandar del perfil.
    candidatas.append(os.path.join(casa, titulo))
    for clave in set(_ESTANDAR.values()):
        r = ruta_de_clave(clave)
        if r and os.path.basename(r) == titulo:
            candidatas.append(r)

    # 4. Ya rebuscando, pero sin barrer el disco entero.
    try:
        r = subprocess.run(["find", casa, "-maxdepth", "3", "-type", "d",
                            "-name", titulo], capture_output=True,
                           text=True, timeout=_TIEMPO)
        candidatas.extend((r.stdout or "").split("\n"))
    except Exception:
        pass

    vistas = set()
    for c in candidatas:
        c = (c or "").rstrip("/")
        if not c or c in vistas:
            continue
        vistas.add(c)
        if os.path.isdir(c) and abierta(c):
            return c
    return None


def ruta_de_clave(clave):
    """La ruta de una carpeta estandar por su clave freedesktop."""
    binario = shutil.which("xdg-user-dir")
    if not binario:
        return None
    try:
        r = subprocess.run([binario, clave], capture_output=True,
                           text=True, timeout=_TIEMPO)
        ruta = (r.stdout or "").strip()
        return ruta if ruta and os.path.isdir(ruta) else None
    except Exception:
        return None


def crear(que, nombre):
    """Crea una carpeta o un archivo VACIO donde Dolphin este mirando.

    Devuelve (ok, detalle). No sobrescribe nada: si ya existe, se dice.
    """
    if que not in ("carpeta", "archivo"):
        return False, f"no se que es {que!r}"
    nombre = (nombre or "").strip()
    if not nombre:
        return False, "hace falta un nombre"
    if "/" in nombre or nombre in (".", ".."):
        return False, "ese nombre no vale para un archivo"

    donde = carpeta_actual()
    if not donde:
        return False, "no se en que carpeta estas"

    destino = os.path.join(donde, nombre)
    if os.path.exists(destino):
        return False, "ya existe"
    try:
        if que == "carpeta":
            os.mkdir(destino)
        else:
            # 'x' falla si existe, en vez de vaciar lo que hubiera. Entre
            # dos frases mal oidas, borrar el trabajo de alguien seria lo
            # peor que podria hacer este comando.
            with open(destino, "x"):
                pass
        return True, destino
    except PermissionError:
        return False, "no tienes permiso ahi"
    except OSError as exc:
        return False, f"{exc.strerror or exc}"
