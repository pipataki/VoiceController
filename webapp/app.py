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
webapp/app.py: Servidor Flask para micrófono remoto y streaming.

IMPORTANTE: Este archivo debe estar en webapp/app.py
             pero paths.py debe estar en la raíz del proyecto.

Para que funcione correctamente, necesitas:
1. Copiar paths.py a la raíz (~/VoiceController/paths.py)
2. Usar: from paths import ... (funciona porque sys.path se configura en paths.py)
"""

import os
import sys
import json
import base64
import datetime
import hashlib
import hmac
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from flask import Flask, request, Response, send_from_directory, jsonify

# --- IMPORTAR PATHS CENTRAL (FUNCIONA INCLUSO DESDE webapp/ GRACIAS A sys.path) ---
from paths import (
    WEBAPP_CONFIG_FILE,
    WEBAPP_UPLOADS_DIR,
    WEBAPP_STATIC_DIR,
    WEBAPP_CERT_FILE,
    WEBAPP_KEY_FILE,
    BOARD_DIR,
)
import board
import actions
import config

# --- BRIDGE DE COMANDOS TÁCTILES (tablero) ---
#
# La webapp corre en un hilo de background DENTRO DEL MISMO PROCESO que la
# GUI de escritorio (ver main.py: start_background_server() se lanza desde
# el proceso principal, no es un servicio aparte). Por eso puede llamar
# directamente a router.handle_touch(text) -- exactamente la misma entrada
# que usa el tablero táctil del GUI de escritorio -- sin necesitar sockets
# ni colas propias. main.py la conecta con set_command_bridge() al arrancar.
_command_bridge = None
_refresh_bridge = None


def set_command_bridge(fn):
    """fn(text: str) -- normalmente router.handle_touch. Se llama desde
    main.py tras crear el CommandRouter."""
    global _command_bridge
    _command_bridge = fn


def set_refresh_bridge(fn):
    """fn() -- sin argumentos, normalmente board.capture_tablero() +
    gui.show_board_overview() (ver main.py). Se llama tras un clic del
    touchpad (ver board_touchpad()) para que la imagen que ve la webapp
    refleje el resultado, sin depender de pulsar "Actualizar" a mano.

    NO se llama tras cada movimiento del touchpad (solo tras clic):
    board.capture_tablero() usa spectacle, que tarda hasta
    SPECTACLE_TIMEOUT_S=1.5s -- llamarlo en cada delta de arrastre
    (cada ~30ms) mataría la fluidez del gesto. El propio arrastre no
    necesita ver la imagen actualizarse en vivo; lo que importa es que
    el resultado se vea en cuanto sueltas/haces clic."""
    global _refresh_bridge
    _refresh_bridge = fn


# --- BRIDGE DE AUDIO (micrófono remoto del móvil -> reconocedor) ---
#
# HALLAZGO: el pipeline de audio de red YA EXISTÍA por el lado del
# reconocedor (ver voice_recognizer.DualLanguageRecognizer.start_network()/
# feed_external_audio(), recognizer_worker.RecognizerWorker.network_audio_chunk/
# switch_to_network_requested) pero NADA en todo el proyecto los conectaba
# con /receive_audio -- el audio subido por el móvil se guardaba en disco
# y ahí se quedaba, sin que nadie lo leyera ni lo decodificara. Por eso el
# micrófono del móvil "se activaba bien" (permiso, subida) pero no se
# reconocía ni una palabra: nunca llegaba al reconocedor.
_audio_bridge = None
_network_switch_bridge = None
# Ponlo a True si hace falta ver en consola cada trozo de audio descartado
# por no ser un WebM autocontenido (ver receive_audio()).
DEBUG_AUDIO_CHUNKS = False
_switched_to_network = False  # para llamar a _network_switch_bridge() UNA sola vez, no en cada chunk


def set_audio_bridge(fn):
    """fn(pcm_bytes: bytes) -- normalmente
    recognizer_worker.network_audio_chunk.emit. Se llama con cada trozo de
    audio YA DECODIFICADO a PCM16 mono a config.SAMPLE_RATE Hz (ver
    _decode_webm_to_pcm16() y receive_audio())."""
    global _audio_bridge
    _audio_bridge = fn


_network_connected_bridge = None


def set_network_connected_bridge(fn):
    """fn() -- normalmente router.on_network_connected. Se llama la
    primera vez que llega audio decodificado del móvil, para que la
    aplicación pueda grabar el perfil de voz DE ESE MICRÓFONO (ver
    command_router.start_mobile_enrollment): es la única ocasión en que
    se tiene audio suyo."""
    global _network_connected_bridge
    _network_connected_bridge = fn


def set_network_switch_bridge(fn):
    """fn() -- sin argumentos, normalmente
    recognizer_worker.switch_to_network_requested.emit. Se llama UNA sola
    vez, la primera vez que se decodifica audio del móvil con éxito -- si
    se llamara en cada chunk, cada llamada reinicia el reconocedor entero
    (recarga los modelos Kaldi), perdiendo el estado de la frase en curso.
    Para volver a escuchar el micrófono local del escritorio, usar el
    comando de voz "micrófono local"/"mic local" (ver command_router.py)."""
    global _network_switch_bridge
    _network_switch_bridge = fn


_local_switch_bridge = None
_last_network_audio_ts = 0.0
_network_watchdog_started = False
# Si no llega ni un solo trozo de audio del móvil en este margen mientras
# se está en modo red, se asume que la sesión murió sin avisar (cierre
# de la app a lo bruto, WiFi perdido, etc.) y se vuelve sola al micrófono
# local -- sin esto, si nadie llegó a decir "micrófono local" A TIEMPO
# (antes de perder el audio del móvil), el reconocedor se queda sin
# NINGÚN input: ni el del móvil, que ya no llega, ni el físico del
# escritorio, que se ignora mientras se esté en modo red -- y sin audio
# ya no hay forma de decir "micrófono local" para arreglarlo. Bastante
# más generoso que el intervalo real entre trozos (varios segundos, ver
# recorder.start() en el JS) para no disparar en falso por una pausa
# normal al hablar.
# OJO: tiene que ser MAYOR que el trozo de audio más largo que mande el
# móvil, más el hueco entre trozos. Mientras se pide el santo y seña los
# trozos son de 15 s (LOGIN_CHUNK_MS en index.html), así que con 12 s el
# vigilante cortaba la sesión ANTES de que llegara el siguiente trozo:
# en el log real, "vuelto al micrófono local (sin audio durante 12s)" una
# y otra vez, justo mientras se intentaba dar el santo y seña. 25 s deja
# margen de sobra para un trozo de 15 s más su subida.
NETWORK_AUDIO_WATCHDOG_TIMEOUT_S = 25.0
NETWORK_AUDIO_WATCHDOG_POLL_S = 2.0


def set_local_switch_bridge(fn):
    """fn() -- sin argumentos, normalmente
    recognizer_worker.switch_to_device_requested.emit("default"). Se
    llama (a) explícitamente al cerrar sesión en la webapp
    (ver release_mic()) y (b) automáticamente por el vigilante de abajo
    si el audio del móvil se corta sin avisar."""
    global _local_switch_bridge
    _local_switch_bridge = fn


# --- Fase 3 (PDF NuevoGUI): puente con el puntero ROJO de la webapp ---

_board_state_bridge = None
_virtual_action_bridge = None


def set_board_state_bridge(fn):
    """fn() -> {"view": "tablero"|"zoom_out"|"casilla", "cell": int|None}
    -- normalmente router.get_board_state. Expuesto en GET /board/info
    para que la webapp sepa qué imagen mostrar de fondo en su touchpad
    virtual (zoom_out.png/casilla.png/nada) y en qué casilla, siguiendo
    exactamente el mismo estado que el puntero verde del GUI."""
    global _board_state_bridge
    _board_state_bridge = fn


_session_state_bridge = None


def set_session_state_bridge(fn):
    """fn() -> {"awaiting_login": bool, "standby": bool} -- normalmente
    router.get_session_state. Sirve para dos cosas:

    1. NO servir capturas de la pantalla mientras el PC no esté
       identificado (ver board_image()).
    2. Que el móvil sepa que se le está pidiendo el santo y seña y deje
       de hacer nada más que grabar (ver index.html)."""
    global _session_state_bridge
    _session_state_bridge = fn


def _session_state() -> dict:
    if _session_state_bridge is None:
        return {"awaiting_login": False, "standby": False}
    try:
        return _session_state_bridge() or {}
    except Exception:
        return {"awaiting_login": False, "standby": False}


_pairing_bridge = None
_ultimo_anuncio_ts = 0.0


_pointer_bridge = None


def set_pointer_bridge(fn):
    """fn(fx, fy) -- normalmente router.actualizar_puntero_rojo.

    El punto ROJO vive en el movil: hasta ahora el PC solo sabia donde
    estaba cuando se pulsaba un boton. Eso vale mientras se use el dedo,
    pero no en modo cara -- si alguien mueve el puntero con la cabeza es
    porque NO puede pulsar botones, y sin esto no habria forma de decir
    "pulsa" y que actue donde esta mirando."""
    global _pointer_bridge
    _pointer_bridge = fn


def set_pairing_bridge(fn):
    """fn() -- normalmente router._decir_codigo_emparejamiento. Se llama
    cuando un móvil sin emparejar avisa de que está intentando conectarse,
    para que el ordenador diga su código EN VOZ ALTA y el usuario pueda
    compararlo con el que le enseña el teléfono.

    Es lo que evita tener que acordarse de ningún comando: se abre la app,
    y el ordenador habla solo."""
    global _pairing_bridge
    _pairing_bridge = fn


def set_virtual_action_bridge(fn):
    """fn(view, cell, fx, fy, kind) -- normalmente
    router.fire_virtual_action_from_webapp. Se llama UNA sola vez por
    acción confirmada (POST /board/virtual_action) -- el arrastre del
    punto rojo en sí es 100% del lado del cliente, no manda nada por
    red."""
    global _virtual_action_bridge
    _virtual_action_bridge = fn


def _ip_en_lista(remota: str, lista) -> bool:
    """¿Está `remota` en `lista`? Cuatro formas de escribirla:

        "10.8.0.2"                 una sola, fija
        "10.8.0.10-10.8.0.50"    un rango, con guion
        "10.8.0.10-50"             el mismo rango, abreviado
        "10.8.0.0/24"              el mismo rango, en CIDR

    El guion existe porque es como la gente escribe un rango cuando lo
    dice en voz alta o lo apunta en un papel. CIDR es exacto pero hay
    que saberse las mascaras, y equivocarse ahi no da error: da un
    rango distinto del que uno creia, que es peor.

    La forma abreviada ("10.8.0.10-50") solo vale para el ultimo
    numero, que es el unico que suele moverse dentro de una red casera.
    """
    if not lista:
        return False
    import ipaddress
    try:
        ip = ipaddress.ip_address(remota)
    except ValueError:
        return False
    for entrada in lista:
        entrada = str(entrada).strip()
        if not entrada:
            continue
        try:
            if "/" in entrada:
                if ip in ipaddress.ip_network(entrada, strict=False):
                    return True
            elif "-" in entrada:
                desde, hasta = (x.strip() for x in entrada.split("-", 1))
                if "." not in hasta:
                    # "10.8.0.10-50" -> el ultimo numero se completa con
                    # los tres primeros del extremo de la izquierda
                    hasta = desde.rsplit(".", 1)[0] + "." + hasta
                primera = ipaddress.ip_address(desde)
                ultima = ipaddress.ip_address(hasta)
                if primera > ultima:
                    primera, ultima = ultima, primera
                if primera <= ip <= ultima:
                    return True
            elif ip == ipaddress.ip_address(entrada):
                return True
        except ValueError:
            # Una entrada mal escrita no debe dejar pasar a nadie por
            # accidente, pero tampoco callarse: se avisa y se sigue con
            # las demas.
            print(f"[webapp] entrada de IP no válida, se ignora: {entrada!r}")
    return False


def _lista_ips(clave_config: str, clave_json: str):
    """Junta las dos procedencias de la lista de IPs.

    config_local.py manda -- es el sitio donde vive lo de CADA maquina y
    lo que sobrevive a las actualizaciones. webapp_config.json se sigue
    leyendo para no romper las instalaciones que ya lo tuvieran puesto
    ahi, que era el unico sitio posible antes.
    """
    valores = []
    try:
        valores += list(getattr(config, clave_config, None) or [])
    except Exception:
        pass
    try:
        valores += list(CONFIG.get(clave_json) or [])
    except Exception:
        pass
    return valores


def _ip_permitida(remota: str) -> bool:
    """Filtro por IP. Se configura en config_local.py:

        WEBAPP_BLOCKED_IPS = ["10.8.0.50", "192.168.0.0/16"] <- prohibidas
        WEBAPP_ALLOWED_IPS = ["10.8.0.2"]                  <- SOLO estas

    (y se sigue leyendo "blocked_ips"/"allowed_ips" de webapp_config.json,
    que era el unico sitio posible antes -- ver _lista_ips)

    Ausentes o vacías = no se filtra nada. La lista de bloqueo se
    comprueba primero: prohibir gana sobre permitir.

    Es una capa MÁS, no un sustituto de la contraseña: una IP se puede
    falsificar en una red local. Sirve para que un aparato que no sea el
    tuyo ni llegue a intentar autenticarse.

    IMPORTANTE para una distribución futura: si esto se deja puesto y el
    usuario cambia de teléfono o su router le da otra IP, la aplicación
    dejará de responderle SIN EXPLICACIÓN APARENTE y lo reportará como
    fallo. Por eso viene vacío de fábrica, y por eso el script de primera
    instalación debe PREGUNTARLO explícitamente (ver MANIFEST,
    Actualización 43) en vez de dejarlo a que alguien encuentre el
    fichero."""
    if _ip_en_lista(remota, _lista_ips("WEBAPP_BLOCKED_IPS", "blocked_ips")):
        return False
    permitidas = _lista_ips("WEBAPP_ALLOWED_IPS", "allowed_ips")
    if not permitidas:
        return True
    return _ip_en_lista(remota, permitidas)


def _release_network_mic(reason: str):
    """Vuelve al micrófono local y resetea el estado de red -- común a
    release_mic() (cierre de sesión explícito) y al vigilante (corte sin
    avisar)."""
    global _switched_to_network
    if not _switched_to_network:
        return
    if _local_switch_bridge is not None:
        try:
            _local_switch_bridge()
            print(f"[webapp] vuelto al micrófono local ({reason})")
        except Exception as exc:
            print(f"[webapp] error volviendo al micrófono local: {exc!r}")
    _switched_to_network = False


def _network_audio_watchdog():
    while True:
        time.sleep(NETWORK_AUDIO_WATCHDOG_POLL_S)
        if _switched_to_network and (time.time() - _last_network_audio_ts) > NETWORK_AUDIO_WATCHDOG_TIMEOUT_S:
            _release_network_mic("sin audio del móvil durante "
                                  f"{NETWORK_AUDIO_WATCHDOG_TIMEOUT_S:.0f}s -- vigilante")


def _ensure_network_watchdog_started():
    global _network_watchdog_started
    if _network_watchdog_started:
        return
    _network_watchdog_started = True
    t = threading.Thread(target=_network_audio_watchdog, daemon=True)
    t.start()


_ffmpeg_missing_warned = False


def _decode_webm_to_pcm16(webm_bytes: bytes, sample_rate: int) -> bytes | None:
    """Decodifica un trozo de audio WebM/Opus (tal cual lo graba
    MediaRecorder en el navegador) a PCM16 mono crudo, al sample rate que
    espera el reconocedor (config.SAMPLE_RATE, ver voice_recognizer.py).

    Requiere `ffmpeg` en el PATH del sistema (no es una dependencia nueva
    del proyecto en sí -- si no está instalado, se avisa por consola una
    sola vez y esta función siempre devuelve None a partir de ahí, sin
    reintentar en cada petición).

    IMPORTANTE: esto SOLO funciona porque cada trozo subido por la webapp
    es un WebM autocontenido y decodificable por sí solo (cabecera propia)
    -- así es como quedó el ciclo de grabación tras el rediseño del
    usuario (cada trozo nace de un MediaRecorder nuevo, no es un
    fragmento a medias de una grabación continua). Si en el futuro se
    vuelve a un `recorder.start(1500)` sin reiniciar el MediaRecorder
    entre trozos, los trozos 2º en adelante dejarían de ser
    autocontenidos y esta decodificación fallaría."""
    import shutil as _shutil
    global _ffmpeg_missing_warned
    ffmpeg_bin = _shutil.which("ffmpeg")
    if not ffmpeg_bin:
        if not _ffmpeg_missing_warned:
            # El consejo depende del sistema: decirle a alguien en Windows
            # que use apt no le sirve de nada y le hace perder el tiempo.
            import sys as _sys
            if _sys.platform.startswith("win"):
                como = ("descárgalo de https://www.gyan.dev/ffmpeg/builds/ y "
                        "añade su carpeta 'bin' al PATH, o instálalo con "
                        "'winget install Gyan.FFmpeg'")
            elif _sys.platform == "darwin":
                como = "instálalo con 'brew install ffmpeg'"
            else:
                como = "instálalo con 'sudo apt install ffmpeg' (Kali/Debian)"
            print("[webapp] ffmpeg no encontrado en PATH -- el micrófono del "
                  f"móvil no se puede decodificar ni reconocer. {como}, y "
                  "reinicia VoiceController.")
            _ffmpeg_missing_warned = True
        return None
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le",
             "-ar", str(sample_rate), "-ac", "1", "pipe:1"],
            input=webm_bytes,
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            print(f"[webapp] ffmpeg no pudo decodificar un trozo de audio del "
                  f"móvil: {stderr[:300]}")
            return None
        return result.stdout
    except subprocess.TimeoutExpired:
        print("[webapp] ffmpeg tardó demasiado decodificando audio del móvil")
        return None
    except Exception as exc:
        print(f"[webapp] error decodificando audio del móvil: {exc!r}")
        return None

# --- RUTAS ---
CONFIG_PATH = str(WEBAPP_CONFIG_FILE)
UPLOAD_DIR = str(WEBAPP_UPLOADS_DIR)
CERT_PATH = str(WEBAPP_CERT_FILE)
KEY_PATH = str(WEBAPP_KEY_FILE)
STATIC_FOLDER = str(WEBAPP_STATIC_DIR)

# --- CONFIGURACIÓN GENERAL ---
HOST = "127.0.0.1"
PORT = 5000

# --- CARGAR CONFIGURACIÓN ---
# El móvil es OPCIONAL: si no se configuró, se desactiva ESA parte y ya.
#
# Antes esto lanzaba una excepción, y como main.py importa este módulo al
# arrancar, quedarse sin webapp_config.json impedía abrir el programa
# ENTERO -- sin ninguna pista de que el problema era una función opcional
# que ni siquiera se estaba usando. Le pasa a cualquiera que instale
# diciendo que no al móvil, en Windows y en Linux.
DISPONIBLE = os.path.exists(CONFIG_PATH)

if DISPONIBLE:
    with open(CONFIG_PATH, "r") as f:
        CONFIG = json.load(f)
else:
    # Todo lo de abajo usa CONFIG.get(...) con valores por defecto, y
    # verify_password() ya rechaza a todo el mundo si no hay hash: con el
    # diccionario vacío el módulo se importa sin peligro y el servidor
    # simplemente no arranca.
    CONFIG = {}

HOST = CONFIG.get("host", HOST)

# Dónde ESCUCHAR y qué NOMBRE lleva el certificado son cosas distintas, y
# antes las hacía la misma variable.
#
# Con "bind": "0.0.0.0" el servidor responde por TODAS las direcciones del
# equipo -- la de la red local y la de la VPN, por ejemplo -- mientras el
# certificado sigue emitido a nombre de `host` (más los de `cert_names`).
# Eso permite que una MISMA app de Android, que lleva dentro una única URL
# y un único certificado, valga para varias instalaciones.
#
# Sin esta separación había que elegir: o servías en la VPN o en la LAN,
# y el certificado quedaba atado a esa elección.
BIND = CONFIG.get("bind", HOST)
PORT = int(CONFIG.get("port", PORT))

# --- AUTENTICACIÓN ---
ADMIN_USER = CONFIG.get("user", "admin")
ADMIN_HASH = CONFIG.get("password_hash")

# --- STREAMING ---
ENABLE_STREAMING = bool(CONFIG.get("enable_streaming", True))
STREAM_FPS = float(CONFIG.get("stream_fps", 2))

# --- HTTPS ---
ENABLE_HTTPS = bool(CONFIG.get("use_https", True))

# --- FLASK APP ---
app = Flask(__name__, static_folder=STATIC_FOLDER, static_url_path="")

_server = None
_server_thread = None


# Las credenciales se leían UNA sola vez, al importar el módulo. Cambiar la
# contraseña en webapp_config.json no tenía ningún efecto hasta reiniciar el
# programa entero, y el único síntoma era un 401: el fichero decía una cosa y
# el servidor seguía con otra, sin avisar de nada.
#
# Costó una hora de depuración creyendo que el problema era la contraseña.
# Ahora se relee sola cuando cambia la fecha del fichero.
_CRED_MTIME = None


def _credenciales_vigentes():
    """Devuelve (usuario, hash) releyendo el fichero si ha cambiado."""
    global ADMIN_USER, ADMIN_HASH, _CRED_MTIME
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        return ADMIN_USER, ADMIN_HASH
    if mtime != _CRED_MTIME:
        try:
            with open(CONFIG_PATH, "r") as f:
                datos = json.load(f)
            ADMIN_USER = datos.get("user", ADMIN_USER)
            ADMIN_HASH = datos.get("password_hash", ADMIN_HASH)
            _CRED_MTIME = mtime
        except Exception as e:
            # Un fichero a medio escribir no debe dejar a nadie fuera:
            # se conservan las credenciales que ya funcionaban.
            print(f"[webapp] no se pudo releer {CONFIG_PATH}: {e}")
    return ADMIN_USER, ADMIN_HASH


def verify_password(provided_password: str) -> bool:
    """Verifica la contraseña contra el hash PBKDF2."""
    _, admin_hash = _credenciales_vigentes()
    if not admin_hash:
        return False
    try:
        parts = admin_hash.split("$")
        algo = parts[0]
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        target = parts[3]
        dk = hashlib.pbkdf2_hmac("sha256", provided_password.encode(), salt, iterations)
        return hmac.compare_digest(dk.hex(), target)
    except Exception:
        return False


def check_auth_header(auth_header: str) -> bool:
    """Verifica el header de autenticación HTTP Basic."""
    if not auth_header:
        return False
    try:
        if not auth_header.startswith("Basic "):
            return False
        b64 = auth_header.split(" ", 1)[1]
        decoded = base64.b64decode(b64).decode(errors="ignore")
        if ":" not in decoded:
            return False
        user, pwd = decoded.split(":", 1)
        admin_user, _ = _credenciales_vigentes()
        if user != admin_user:
            return False
        return verify_password(pwd)
    except Exception:
        return False


def require_auth():
    """Comprueba autenticación del request actual."""
    auth = request.headers.get("Authorization")
    if check_auth_header(auth):
        return True
    return False


def auth_required():
    """Decorator para proteger rutas individuales."""
    def decorator(f):
        def wrapper(*args, **kwargs):
            remota = request.remote_addr or ""
            if not _ip_permitida(remota):
                motivo = ("está en la lista de prohibidas"
                          if _ip_en_lista(remota, _lista_ips("WEBAPP_BLOCKED_IPS",
                                                             "blocked_ips"))
                          else "no está en la lista de permitidas")
                print(f"[webapp] rechazada conexión desde {remota} "
                      f"({motivo}, ver WEBAPP_ALLOWED_IPS en config_local.py)")
                return Response("Forbidden", 403)
            if not require_auth():
                return Response(
                    "Authentication required",
                    401,
                    {"WWW-Authenticate": 'Basic realm="VoiceController"'}
                )
            return f(*args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator


# --- RUTAS ---

@app.route("/", methods=["GET"])
def index():
    """Sirve el HTML sin protección."""
    return send_from_directory(STATIC_FOLDER, "index.html")


@app.route("/receive_audio", methods=["POST"])
@auth_required()
def receive_audio():
    """Recibe chunks de audio desde el micrófono remoto (protegido).

    Además de guardar el trozo en disco (como antes, útil para depurar),
    ahora también lo decodifica a PCM16 (_decode_webm_to_pcm16()) y lo
    entrega al reconocedor de voz vía _audio_bridge -- antes esto último
    NUNCA pasaba, así que el micrófono del móvil se subía bien pero jamás
    llegaba a reconocerse ni una palabra (ver set_audio_bridge() más
    arriba para el porqué)."""
    # El formato lo dice quien envía. Dos casos:
    #   "webm"  (por defecto) -- lo que manda el navegador con MediaRecorder,
    #           y hay que decodificar con ffmpeg.
    #   "pcm16" -- PCM crudo de 16 bits, mono, a config.SAMPLE_RATE, que es
    #           lo que manda la app de Android cuando graba ella misma. No
    #           necesita ffmpeg NI cabecera que validar.
    #
    # La segunda vía existe porque el WebView de Chromium no consigue abrir
    # el micrófono en algunos móviles (ver MANIFEST.md), y de paso quita a
    # ffmpeg de los requisitos del servidor.
    formato = (request.args.get("formato") or "webm").lower()
    filename = request.args.get("filename") or "upload"
    filename = os.path.basename(filename)
    extension = "pcm" if formato == "pcm16" else "webm"
    save_path = os.path.join(UPLOAD_DIR, f"{filename}.{extension}")
    datos = None
    try:
        if request.files and "audio" in request.files:
            f = request.files["audio"]
            datos = f.read()
            with open(save_path, "wb") as out:
                out.write(datos)
        else:
            datos = request.get_data()
            with open(save_path, "wb") as out:
                out.write(datos)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    recognized = False
    # Umbral mínimo antes de intentar decodificar: cada vez que
    # stopBtn.click() llama a recorder.stop() (ver webapp/static/index.html),
    # el propio MediaRecorder dispara un dataavailable ADICIONAL con lo
    # poco (o nada) que quedara sin enviar + los bytes de cierre del
    # contenedor WebM -- un trozo casi vacío, de unos pocos cientos de
    # bytes, que ev.data.size > 0 deja pasar igual en el JS aunque no
    # tenga apenas audio real. Ese trozo residual es justo el que fallaba
    # al decodificar con ffmpeg, siempre justo "en el corte" (coincidencia
    # exacta con lo reportado). Cualquier trozo de habla real, incluso
    # muy corto, pesa bastante más que esto (referencia: ~500-1300 bytes
    # para 20-50ms de audio Opus sintético de prueba) -- 2000 bytes deja
    # margen de sobra sin arriesgarse a descartar un comando corto real.
    MIN_AUDIO_CHUNK_BYTES = 2000
    # 640 bytes = 20 ms a 16 kHz, 16 bits, mono. Por debajo de eso no hay
    # nada que reconocer, pero el umbral es MUY inferior al del WebM porque
    # aquí no hay contenedor ni trozo de cierre que descartar.
    MIN_PCM_BYTES = 640
    if formato == "pcm16":
        if datos and len(datos) < MIN_PCM_BYTES:
            datos = None
    elif datos and len(datos) < MIN_AUDIO_CHUNK_BYTES:
        datos = None  # se descarta en silencio -- no es un error, es el cierre del MediaRecorder
    # Red de seguridad del lado del servidor: todo WebM/Matroska autocontenido
    # empieza por la firma EBML 1A 45 DF A3. El trozo que suelta
    # recorder.stop() al cerrar es un fragmento de cluster SIN cabecera (los
    # de este proyecto empezaban por 43 C3 ...), y ffmpeg no puede
    # decodificarlo por definición -- no tiene sentido lanzar un proceso para
    # que falle y llenar el log. El cliente ya no debería mandarlos (ver
    # chunkSent en index.html); esto cubre navegadores que troceen distinto.
    if (formato != "pcm16" and datos
            and not datos.startswith(b"\x1a\x45\xdf\xa3")):
        if DEBUG_AUDIO_CHUNKS:
            print(f"[webapp] trozo de audio sin cabecera EBML "
                  f"({len(datos)} bytes): descartado sin llamar a ffmpeg")
        datos = None
    if datos and _audio_bridge is not None:
        # El PCM ya viene listo; el WebM hay que decodificarlo.
        pcm = datos if formato == "pcm16" else _decode_webm_to_pcm16(datos, config.SAMPLE_RATE)
        if pcm:
            global _switched_to_network, _last_network_audio_ts
            if not _switched_to_network and _network_switch_bridge is not None:
                try:
                    _network_switch_bridge()
                    _switched_to_network = True
                    _ensure_network_watchdog_started()
                    # Primera conexión del móvil: si todavía no hay perfil
                    # de voz de ESTE micrófono, es el momento de grabarlo
                    # (ver command_router.on_network_connected). El
                    # reconocedor tarda un poco en arrancar en modo red,
                    # así que se avisa con un pequeño retraso para que las
                    # frases del enrolado no caigan en el vacío.
                    if _network_connected_bridge is not None:
                        threading.Timer(3.0, _network_connected_bridge).start()
                except Exception as exc:
                    print(f"[webapp] error cambiando a micrófono de red: {exc!r}")
            _last_network_audio_ts = time.time()
            try:
                _audio_bridge(pcm)
                recognized = True
            except Exception as exc:
                print(f"[webapp] error entregando audio al reconocedor: {exc!r}")

    # El estado del PC viaja de vuelta en la MISMA respuesta de la subida.
    #
    # El movil ya hace esta peticion una vez por ciclo para mandar su trozo
    # de audio, y hasta el 5-sep-2026 la respuesta volvia practicamente
    # vacia: para saber si el PC habia dicho algo, o si estaba pidiendo el
    # santo y sena, tenia que hacer OTRA peticion en el hueco, con el
    # microfono ya cerrado. Medido sobre el log real, esa ida y vuelta se
    # llevaba cerca de 1,1 s de cada ciclo de 7,5 s -- tiempo en el que el
    # ordenador esta sordo.
    #
    # Aqui sale gratis: ni una peticion mas, y la informacion es incluso
    # MAS fresca, porque se calcula despues de haber procesado el audio que
    # se acaba de subir. Es decir, si lo que acabas de decir ha hecho que
    # el PC hable, el movil se entera en esta misma respuesta.
    respuesta = {"ok": True, "saved": save_path, "recognized": recognized}
    try:
        respuesta["estado"] = _estado_para_movil()
    except Exception as exc:
        # Que falle el estado no debe tumbar la subida del audio, que es lo
        # importante de esta ruta. El movil se apana con su consulta de
        # siempre si aqui no viene nada.
        print(f"[webapp] no se pudo adjuntar el estado a la subida: {exc!r}")
    return jsonify(respuesta)


@app.route("/release_mic", methods=["POST"])
@auth_required()
def release_mic():
    """Vuelve al micrófono local del escritorio de forma explícita e
    inmediata -- llamada por la webapp al cerrar sesión (ver
    logoutBtn.onclick en index.html), para no depender solo del
    vigilante (_network_audio_watchdog, hasta
    NETWORK_AUDIO_WATCHDOG_TIMEOUT_S=12s de margen) cuando el cierre es
    limpio y sabemos justo en ese momento que ya no va a llegar más
    audio del móvil."""
    _release_network_mic("cierre de sesión explícito")
    return jsonify({"ok": True})


@app.route("/stream", methods=["GET"])
@auth_required()
def stream():
    """Transmite el escritorio en tiempo real (protegido).

    DEPRECADO: desde el tablero de 100 casillas (board.py) ya no hace
    falta streaming -- la webapp carga directamente /board/tablero.png
    (estática, se sobrescribe sola en cada acción), igual que el GUI de
    escritorio. Se deja esta ruta por compatibilidad, pero desactivada
    por defecto (ver 'enable_streaming' en webapp_config.json)."""
    if not ENABLE_STREAMING:
        return "", 404

    interval = 1.0 / STREAM_FPS if STREAM_FPS > 0 else 0.5

    def generate():
        while True:
            start = time.monotonic()
            try:
                frame = _capture_desktop_frame()
            except Exception as exc:
                print(f"[webapp] error capturando frame: {exc!r}")
                time.sleep(interval)
                continue
            yield b"--frame\r\nContent-Type: image/png\r\nContent-Length: %d\r\n\r\n" % len(frame)
            yield frame
            yield b"\r\n"
            elapsed = time.monotonic() - start
            time.sleep(max(0.0, interval - elapsed))

    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route("/board/tap", methods=["POST"])
@auth_required()
def board_tap():
    """Toque sobre la imagen del tablero (tablero.png) en la webapp:
    {"x": 0.0-1.0, "y": 0.0-1.0} (fracción del ancho/alto de la imagen tal
    y como se muestra) -> selecciona la casilla correspondiente, igual que
    tocar el tablero en el GUI de escritorio o decir el número en voz."""
    if _command_bridge is None:
        return jsonify({"ok": False, "error": "bridge no conectado todavía"}), 503
    data = request.get_json(silent=True) or {}
    try:
        fx = float(data.get("x"))
        fy = float(data.get("y"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "faltan x/y (0.0-1.0)"}), 400
    cell = board.cell_from_fraction(fx, fy)
    _command_bridge(str(cell))
    return jsonify({"ok": True, "cell": cell})


@app.route("/board/action", methods=["POST"])
@auth_required()
def board_action():
    """Botón de la webapp equivalente a una palabra de voz: {"text": "..."}
    -- p.ej. "click", "doble click", "oeste", "oeste 3", "subir"... Se pasa
    tal cual por la MISMA gramática que la voz (ver command_router.
    handle_touch), así que cualquier palabra de control válida en modo
    escucha funciona aquí también."""
    if _command_bridge is None:
        return jsonify({"ok": False, "error": "bridge no conectado todavía"}), 503
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "falta 'text'"}), 400
    _command_bridge(text)
    return jsonify({"ok": True, "text": text})


@app.route("/board/touchpad", methods=["POST"])
@auth_required()
def board_touchpad():
    """Touchpad táctil real: arrastra el dedo por la pantalla del móvil
    y el cursor real se mueve en tiempo real por el mismo gesto -- a
    diferencia de /board/tap y /board/action (que trabajan con
    posiciones ABSOLUTAS: casilla numerada + ajuste fino), esta ruta es
    movimiento RELATIVO puro, como un touchpad físico de verdad. Ver
    actions.touchpad_move()/touchpad_click() y
    grid_vc.move_pointer_relative().

    Cuerpo JSON, dos variantes (una petición = una u otra, no ambas):
      - {"dx": <número>, "dy": <número>} -- mueve el cursor esa
        cantidad de píxeles físicos desde su posición actual.
      - {"click": "left"|"right"} -- clic en la posición ACTUAL del
        cursor (equivalente a un toque/tap en un touchpad físico).

    A propósito NO pasa por _command_bridge/la gramática de voz (esto
    no es una "palabra"): llama directamente a actions.touchpad_*,
    para la menor latencia posible mientras se arrastra el dedo."""
    data = request.get_json(silent=True) or {}
    if "click" in data:
        button = "right" if data.get("click") == "right" else "left"
        ok = actions.touchpad_click(button)
        if ok and _refresh_bridge is not None:
            try:
                _refresh_bridge()
            except Exception as exc:
                print(f"[webapp] error refrescando tras clic de touchpad: {exc!r}")
        return jsonify({"ok": ok, "click": button})
    try:
        dx = float(data.get("dx", 0))
        dy = float(data.get("dy", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "dx/dy inválidos"}), 400
    ok = actions.touchpad_move(dx, dy)
    return jsonify({"ok": ok})


@app.route("/board/live_capture", methods=["POST"])
@auth_required()
def board_live_capture():
    """Vuelve a capturar tablero.png (escritorio COMPLETO, no la
    ventana del GUI -- para eso está vc.png) bajo demanda. Pensada para
    la vista en vivo opcional de la webapp (ver #liveViewToggle en
    index.html), que llama a esto en un intervalo MIENTRAS está
    activada -- a propósito NO es automática/continua por defecto (el
    usuario tiene que encenderla a mano, y se autopausa durante la
    grabación de audio, ver stopLiveView() en el JS) para no competir
    con el audio si no hace falta -- mismo criterio que el resto de
    refrescos de esta webapp (ver comentario en board_info())."""
    ok = board.capture_tablero()
    from paths import TABLERO_FILE
    mtime = TABLERO_FILE.stat().st_mtime if TABLERO_FILE.exists() else None
    return jsonify({"ok": ok, "mtime": mtime})


def _tts_id() -> int:
    """id de la última frase hablada, o 0 si no hay voz o no se manda al
    móvil. Nunca lanza: es un extra dentro de /board/info y no debe poder
    tumbar la respuesta que de verdad importa (la del tablero)."""
    try:
        import config as _config
        if not getattr(_config, "TTS_SEND_TO_MOBILE", False):
            return 0
        import tts
        return tts.get_speaker().mobile_pending()[0]
    except Exception:
        return 0


# Nombres de captura que se pueden pedir. Lista blanca explícita: la
# ruta recibe un nombre de fichero, y sin esto un ".." bien puesto serviría
# cualquier fichero del disco.
_IMAGENES_TABLERO = {"tablero.png", "vc.png", "casilla.png", "zoom_out.png",
                     "foco.png"}


@app.route("/board/<path:nombre>", methods=["GET"])
@auth_required()
def board_image(nombre):
    """Sirve las capturas del tablero CON autenticación y solo si el PC
    ya está identificado.

    Antes las servía Flask como ficheros estáticos (viven bajo
    webapp/static/board/ y la app usa static_url_path=""), y eso las
    dejaba accesibles **sin contraseña ninguna**: cualquiera en la red
    que pidiera /board/tablero.png veía el escritorio entero. Comprobado
    antes de arreglarlo: devolvía 200 sin credenciales.

    Además no se sirven mientras el PC esté pidiendo el santo y seña o en
    standby: aunque alguien tuviera la contraseña de la webapp, no debe
    ver la pantalla hasta que el dueño se haya identificado por voz."""
    if nombre not in _IMAGENES_TABLERO:
        return jsonify({"ok": False, "error": "no encontrado"}), 404
    estado = _session_state()
    if estado.get("awaiting_login") or estado.get("standby"):
        return jsonify({"ok": False, "error": "sesión no iniciada en el PC"}), 403
    ruta = BOARD_DIR / nombre
    if not ruta.is_file():
        return jsonify({"ok": False, "error": "todavía no capturada"}), 404
    return send_from_directory(str(BOARD_DIR), nombre,
                               max_age=0, conditional=False)


def _estado_para_movil():
    """El estado completo que el movil necesita para pintarse: que
    imagenes hay y de cuando, en que vista esta el PC, si ha dicho algo en
    alto, y si esta pidiendo el santo y sena o en espera.

    Existe como funcion, y no dentro de board_info(), porque lo devuelven
    DOS sitios: la consulta /board/info de toda la vida, y desde el
    5-sep-2026 tambien la respuesta de /receive_audio.

    Ese segundo sitio es el que importa. El movil ya habla con el PC una
    vez por ciclo para subir su trozo de audio, y hasta ahora esa
    respuesta volvia practicamente vacia: el movil tenia que hacer OTRA
    peticion, en el hueco y con el microfono cerrado, solo para
    preguntar como estaban las cosas. Medido sobre el log real, esa ida y
    vuelta costaba cerca de 1,1 s de cada ciclo de 7,5 s.

    Viajando en la respuesta de la subida sale gratis: ni una peticion
    mas, y ademas la informacion es MAS fresca que antes, porque se
    calcula despues de haber procesado el audio que se acaba de subir.

    Los dos sitios comparten esta funcion a proposito: si divergieran,
    el movil se comportaria distinto segun por donde se hubiera enterado
    de las cosas, y eso es imposible de depurar.
    """
    from paths import TABLERO_FILE, VC_FILE, ZOOM_OUT_FILE, CASILLA_FILE, FOCO_FILE
    has_tablero = TABLERO_FILE.exists()
    has_vc = VC_FILE.exists()
    has_foco = FOCO_FILE.exists()
    has_zoom_out = ZOOM_OUT_FILE.exists()
    has_casilla = CASILLA_FILE.exists()
    state = {"view": "tablero", "cell": None}
    if _board_state_bridge is not None:
        try:
            state = _board_state_bridge() or state
        except Exception as exc:
            print(f"[webapp] error leyendo el estado del tablero: {exc!r}")
    return {
        "ok": True,
        "rows": board.ROWS,
        "cols": board.COLS,
        "total_cells": board.TOTAL_CELLS,
        "has_tablero": has_tablero,
        "mtime": TABLERO_FILE.stat().st_mtime if has_tablero else None,
        "has_vc": has_vc,
        "vc_mtime": VC_FILE.stat().st_mtime if has_vc else None,
        "has_foco": has_foco,
        "foco_mtime": FOCO_FILE.stat().st_mtime if has_foco else None,
        "has_zoom_out": has_zoom_out,
        "zoom_out_mtime": ZOOM_OUT_FILE.stat().st_mtime if has_zoom_out else None,
        "has_casilla": has_casilla,
        "casilla_mtime": CASILLA_FILE.stat().st_mtime if has_casilla else None,
        "view": state.get("view"),
        "cell": state.get("cell"),
        # Hay un origen de seleccion fijado: el movil pinta su punto de
        # AMARILLO, igual que el GUI. Sin esto, en remoto no habria ninguna
        # senal de que el programa esta esperando el final de la seleccion
        # -- y en remoto es donde mas falta hace, porque no se ve la
        # pantalla del ordenador.
        "seleccion": bool(state.get("seleccion")),
        # id de lo último que ha dicho VoiceController en alto: si cambia,
        # el móvil se baja /tts/latest.wav y lo reproduce (ver
        # config.TTS_SEND_TO_MOBILE). Va aquí, dentro de una consulta que
        # el móvil YA hace en el hueco entre trozos de audio, para no
        # añadir ningún sondeo nuevo que compita con la grabación -- que
        # es lo que causaba los cortes de audio (ver el comentario grande
        # sobre esto en index.html).
        "tts_id": _tts_id(),
        # Estado de la sesión en el PC: mientras esté pidiendo el santo y
        # seña, el móvil debe limitarse a grabar audio (ver index.html) --
        # ni refrescos ni imágenes, que es lo que le partía la frase por
        # la mitad y le impedía identificarse.
        **_session_state(),
    }

@app.route("/board/info", methods=["GET"])
@auth_required()
def board_info():
    """Metadatos útiles para la webapp: tamaño de la rejilla, si ya hay
    captura de tablero.png, vc.png (espejo de la ventana del GUI, ver
    GUI._maybe_capture_vc_snapshot en gui.py), zoom_out.png y
    casilla.png disponibles, y su fecha de modificación (mtime,
    segundos desde epoch) de cada una -- la webapp las usa para
    detectar sola cuando hay una captura NUEVA y refrescar la imagen
    correspondiente, EN RESPUESTA A ACCIONES concretas (no por sondeo
    continuo -- ver comentario sobre cortes de audio en index.html) --
    ver pollBoardInfo() ahí.

    Fase 3 (PDF NuevoGUI, puntero rojo): además incluye "view"/"cell"
    (ver set_board_state_bridge() -- normalmente router.get_board_state())
    -- qué imagen debería estar mostrando el touchpad virtual de fondo
    AHORA MISMO (misma "pantalla" que el puntero verde del GUI de
    escritorio) y en qué casilla."""
    return jsonify(_estado_para_movil())


@app.route("/board/virtual_action", methods=["POST"])
@auth_required()
def board_virtual_action():
    """Fase 3 del rediseño de accesibilidad (PDF NuevoGUI): confirma
    UNA acción del puntero ROJO de la webapp -- el arrastre en sí
    (mover el punto rojo sobre la imagen de fondo del touchpad virtual)
    es 100% del lado del cliente, sin ninguna petición de red; esta
    ruta se llama SOLO al confirmar (clic/clic derecho/doble
    clic/scroll), igual que el puntero verde del GUI.

    Cuerpo JSON: {"fx": 0.0-1.0, "fy": 0.0-1.0, "kind": "click"|"click_right"|
    "double_click"|"scroll_up"|"scroll_down"|"scroll_left"|"scroll_right"}
    -- fx/fy son la posición del punto rojo como fracción de la imagen
    de fondo que la webapp esté mostrando AHORA MISMO (ver GET
    /board/info, campos "view"/"cell") -- el servidor traduce esa
    fracción a una posición REAL de escritorio
    (board.virtual_pointer_to_real_position, misma función ya usada
    por el puntero verde) y ejecuta la acción de forma atómica."""
    if _virtual_action_bridge is None:
        return jsonify({"ok": False, "error": "bridge no conectado"}), 503
    data = request.get_json(silent=True) or {}
    try:
        fx = float(data.get("fx", 0.5))
        fy = float(data.get("fy", 0.5))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "fx/fy inválidos"}), 400
    kind = data.get("kind")
    if kind not in ("click", "click_right", "double_click",
                    "scroll_up", "scroll_down", "scroll_left", "scroll_right"):
        return jsonify({"ok": False, "error": "kind inválido"}), 400
    state = {"view": "tablero", "cell": None}
    if _board_state_bridge is not None:
        try:
            state = _board_state_bridge() or state
        except Exception:
            pass
    view = data.get("view") or state.get("view") or "tablero"
    cell = data.get("cell", state.get("cell"))
    try:
        # El puente devuelve un MOTIVO (texto) cuando el ordenador no debe
        # actuar ahora -- en espera, pidiendo el santo y sena, o bloqueado.
        # Ver command_router._por_que_no_puedo_actuar(). Devuelve None
        # cuando la accion se ha ejecutado.
        motivo = _virtual_action_bridge(view, cell, fx, fy, kind)
    except Exception as exc:
        print(f"[webapp] error disparando acción virtual: {exc!r}")
        return jsonify({"ok": False, "error": str(exc)}), 500
    if motivo:
        # 409: la peticion es correcta, pero el estado del ordenador no
        # permite atenderla. No es un 403 (eso seria un problema de
        # permisos) ni un 401 (la sesion del movil es valida).
        return jsonify({"ok": False, "error": motivo}), 409
    return jsonify({"ok": True})


@app.route("/tts/latest.wav", methods=["GET"])
@auth_required()
def tts_latest():
    """Último aviso hablado por VoiceController, en WAV, para que el móvil
    lo reproduzca también (ver config.TTS_SEND_TO_MOBILE).

    El móvil lo pide en el HUECO ENTRE TROZOS de grabación, cuando su
    micrófono está parado -- si sonara con el micrófono abierto, el propio
    móvil grabaría la voz de VoiceController y se la mandaría de vuelta al
    PC como si fuera una orden. Ver stopBtn.onclick en index.html.

    No se guarda historial: solo la última frase. Si llegan dos seguidas,
    lo que interesa oír es la última, no ponerse al día con las viejas."""
    try:
        import tts
        _id, wav = tts.get_speaker().mobile_pending()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    if not wav:
        return jsonify({"ok": False, "error": "todavía no se ha dicho nada"}), 404
    return Response(wav, mimetype="audio/wav",
                    headers={"Cache-Control": "no-store"})


@app.route("/board/pointer", methods=["POST"])
@auth_required()
def board_pointer():
    """El movil dice donde tiene el punto rojo.

    Lo manda solo cuando se mueve de verdad (ver index.html): con la
    pegajosidad puesta son unas pocas veces por segundo como mucho, y son
    dos numeros. No se manda nada mas.
    """
    datos = request.get_json(silent=True) or {}
    try:
        fx = float(datos.get("fx"))
        fy = float(datos.get("fy"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "faltan fx/fy"}), 400
    if _pointer_bridge is not None:
        try:
            _pointer_bridge(fx, fy)
        except Exception as exc:
            print(f"[webapp] no se pudo anotar el puntero: {exc!r}")
    return jsonify({"ok": True})


@app.route("/pair/announce", methods=["POST"])
def pair_announce():
    """Un móvil está intentando emparejarse: se dice el código en alto.

    VA SIN CONTRASEÑA, y tiene que ser así: quien todavía no se ha
    emparejado tampoco ha podido entrar. No es un agujero, porque esto no
    da acceso a nada -- solo hace que el ordenador diga un número que, de
    todas formas, va escrito en el certificado que cualquiera puede pedirle.

    Si hay alguien en medio suplantando al PC, el teléfono enseñará el
    código del impostor y el ordenador dirá el suyo: no coincidirán, que es
    exactamente para lo que sirve compararlos.

    Se limita a uno cada 20 segundos para que nadie en la red pueda usarlo
    para hacer hablar al ordenador sin parar.
    """
    global _ultimo_anuncio_ts
    if not _ip_permitida(request.remote_addr or ""):
        return jsonify({"ok": False}), 403

    ahora = time.time()
    if ahora - _ultimo_anuncio_ts < 20:
        return jsonify({"ok": True, "dicho": False, "motivo": "hace nada que se dijo"})
    _ultimo_anuncio_ts = ahora

    if _pairing_bridge is None:
        print("[webapp] un móvil pide el código de emparejamiento, pero no hay voz")
        return jsonify({"ok": True, "dicho": False})

    print(f"[webapp] {request.remote_addr} se está emparejando: digo el código")
    try:
        _pairing_bridge()
    except Exception as exc:
        print(f"[webapp] no se pudo decir el código: {exc!r}")
        return jsonify({"ok": True, "dicho": False})
    return jsonify({"ok": True, "dicho": True})


@app.route("/health", methods=["GET"])
def health():
    """Health check sin protección."""
    return jsonify({
        "ok": True,
        "host": HOST,
        "port": PORT,
        "streaming": ENABLE_STREAMING,
        "project_root": str(WEBAPP_CONFIG_FILE.parent),
    })


def _capture_desktop_frame() -> bytes:
    """Captura un frame del escritorio con spectacle."""
    fd, path = tempfile.mkstemp(suffix=".png", prefix="vc_stream_")
    os.close(fd)
    try:
        subprocess.run(
            ["spectacle", "-b", "-n", "-o", path],
            check=True, timeout=5,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with open(path, "rb") as f:
            return f.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def _get_or_create_self_signed_cert():
    """Genera (una sola vez) un certificado autofirmado persistente."""
    if CERT_PATH and KEY_PATH and os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        return CERT_PATH, KEY_PATH

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VoiceController")])

    # El certificado cubre VARIOS nombres, no solo HOST.
    #
    # Con uno solo, en cuanto se llega al PC por otra dirección el navegador
    # (o Android) rechaza la conexión por no coincidir el nombre. Pasa con
    # DHCP en cuanto el router cambia la IP, y pasa con un emulador de
    # Android, que ve al anfitrión como 10.0.2.2.
    #
    # Los extras se ponen en webapp_config.json:  "cert_names": ["10.0.2.2"]
    import ipaddress
    nombres = ["localhost", HOST] + list(CONFIG.get("cert_names", []))
    san_entries = []
    for n in nombres:
        n = str(n).strip()
        if not n:
            continue
        try:
            entrada = x509.IPAddress(ipaddress.ip_address(n))
        except ValueError:
            entrada = x509.DNSName(n)
        if entrada not in san_entries:
            san_entries.append(entrada)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName(san_entries), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(KEY_PATH, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    return CERT_PATH, KEY_PATH


def start_background_server():
    """Inicia el servidor Flask en un hilo background."""
    global _server, _server_thread
    if not DISPONIBLE:
        print("[webapp] no hay webapp_config.json: el móvil queda desactivado. "
              "Para activarlo, ejecuta webapp/gen_config.py o vuelve a pasar "
              "el instalador diciendo que sí al móvil.")
        return None
    if _server is not None:
        return _server

    from werkzeug.serving import make_server

    ssl_context = None
    if ENABLE_HTTPS:
        try:
            ssl_context = _get_or_create_self_signed_cert()
        except Exception as exc:
            print(
                f"[webapp] no se pudo preparar HTTPS ({exc!r}); sirviendo por HTTP. "
                "El micrófono remoto NO funcionará."
            )
            ssl_context = None

    _server = make_server(BIND, PORT, app, threaded=True, ssl_context=ssl_context)

    scheme = "https" if ssl_context else "http"
    print(f"[webapp] sirviendo en {scheme}://{HOST}:{PORT}")
    if ssl_context:
        print(
            "[webapp] certificado autofirmado: el navegador del móvil avisará "
            "de 'conexión no segura' la primera vez — hay que aceptar/continuar."
        )

    def _serve():
        _server.serve_forever()

    _server_thread = threading.Thread(target=_serve, daemon=True, name="voicecontroller-webapp")
    _server_thread.start()
    return _server


def stop_background_server():
    """Detiene el servidor Flask."""
    global _server, _server_thread
    if _server is not None:
        try:
            _server.shutdown()
        finally:
            _server = None
    if _server_thread is not None:
        _server_thread.join(timeout=2)
        _server_thread = None


if __name__ == "__main__":
    app.run(host=BIND, port=PORT)
