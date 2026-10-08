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
cesion_microfono.py: VoiceController le CEDE el micrófono a otra aplicación
(Pipe-Logic) mientras esta lo necesite, y lo recupera cuando lo suelta.

Por qué
-------
Con un micrófono ALSA directo (un aparato hw:N,M) el dispositivo
es de uno solo: mientras VoiceController lo tiene abierto, Pipe-Logic no
puede abrirlo. Y aunque se compartiera (PipeWire), las dos aplicaciones
oirían la misma frase y las dos actuarían. Cuando coinciden, manda
Pipe-Logic: VoiceController suelta el micrófono y se queda sin escuchar
hasta que se lo devuelvan.

Protocolo (para quien pide el micrófono)
----------------------------------------
Un socket Unix en `ruta_socket()` (normalmente
$XDG_RUNTIME_DIR/voicecontroller/microfono.sock):

    1. conectar
    2. enviar  "PIDO\\n"
    3. esperar "LIBRE\\n"   -> VoiceController ya ha CERRADO el micrófono
    4. usar el micrófono, con la conexión ABIERTA todo ese tiempo
    5. cerrar la conexión  -> VoiceController vuelve a abrirlo

La cesión dura lo que dure la conexión, y no hay un "devuelvo" que se pueda
olvidar: si Pipe-Logic se cierra o se cuelga, el sistema cierra su socket y
VoiceController recupera el micrófono solo. Si no hay socket (VoiceController
no está en marcha), el micrófono ya está libre: se usa sin más.

Desde Python vale `with pedir_microfono(): ...`, y para cualquier programa,
sin tocarlo, tools/ceder_microfono.py lo envuelve: `ceder_microfono.py --
pipe-logic`.

Cesión A MANO (botón "Pipe-Logic Mic", comando "micro lógico")
---------------------------------------------------------------
Pipe-Logic busca el micrófono ANTES de pedirlo, y mientras VoiceController
lo tiene abierto, PortAudio ni siquiera lo lista (medido el 8-oct-2026: con
VC escuchando, la búsqueda del micro por su nombre no da nada; cedido, sí). Así que
también se puede ceder a mano: ceder_manual() suelta el micrófono como si
alguien hubiera mandado PIDO, y dura hasta que se pulsa otra vez el botón
(alternar_manual) o hasta que Pipe-Logic lo devuelve: la primera conexión
PIDO que se cierre mientras está cedido a mano se lleva también la cesión
manual ("hasta que lo devuelva"). Pipe-Logic también la puede devolver
sin haber pedido nada (su botón "VC Mic", comando "micro control"):

    1. conectar   2. enviar "DEVUELVO\n"   3. recibir "OK\n" y cerrar

Y pregunta cada segundo si se lo han cedido a mano, para ponerse a escuchar
sola en cuanto pase: "ESTADO\n" -> "MANUAL\n" o "NADA\n".

Por voz desde VoiceController no se recupera: mientras está cedido, no oye.

Solo Linux (y macOS): en Windows no se arranca y todo sigue como antes.
"""

import os
import socket
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

import config

PETICION = b"PIDO\n"
RESPUESTA = b"LIBRE\n"
# Pipe-Logic devuelve la cesión a mano (su botón "VC Mic" o "micro
# control"): se manda DEVUELVO, se contesta OK y se cierra.
DEVOLUCION = b"DEVUELVO\n"
CONFIRMACION = b"OK\n"
# Pipe-Logic pregunta si se le ha cedido a mano, para ponerse a escuchar
# sola en cuanto pase.
PREGUNTA = b"ESTADO\n"

# Cuántas aplicaciones tienen ahora mismo el micrófono pedido. Mientras sea
# mayor que cero, VoiceController no abre el micrófono local (ver
# voice_recognizer.start()).
_titulares = 0
_lock = threading.Lock()
_reconocedor = None

# Cesión a mano (ver docstring). _manual_lock pone en fila los cambios para
# que dos pulsaciones seguidas no se crucen (RLock: alternar lo toma y
# _poner_manual lo vuelve a tomar dentro); nunca se toma teniendo _lock.
_manual = False
_manual_lock = threading.RLock()
_al_cambiar = None


def ruta_socket() -> Path:
    ruta = getattr(config, "CEDER_MICROFONO_SOCKET", None)
    if ruta:
        return Path(ruta)
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / "voicecontroller" / "microfono.sock"
    return Path(tempfile.gettempdir()) / f"voicecontroller-{os.getuid()}" / "microfono.sock"


def cedido() -> bool:
    """True mientras alguna aplicación tenga el micrófono pedido."""
    return _titulares > 0


def registrar_reconocedor(reconocedor):
    """El reconocedor al que hay que pedirle que suelte/recupere el
    micrófono. Si la petición llega antes (mientras cargan los modelos),
    basta con cedido(): su start() no abrirá nada."""
    global _reconocedor
    _reconocedor = reconocedor


def _ceder():
    global _titulares
    with _lock:
        _titulares += 1
        primero = _titulares == 1
    if primero:
        print("[cesion_microfono] otra aplicación pide el micrófono: se lo cedo")
        rec = _reconocedor
        if rec is not None:
            rec.ceder_microfono()


def _recuperar():
    global _titulares
    with _lock:
        _titulares -= 1
        ultimo = _titulares == 0
    if ultimo:
        print("[cesion_microfono] me devuelven el micrófono")
        rec = _reconocedor
        if rec is not None:
            rec.recuperar_microfono()


def _atender(conexion: socket.socket):
    with conexion:
        try:
            linea = conexion.makefile("rb").readline(64)
        except OSError:
            return
        if linea.strip() == PREGUNTA.strip():
            try:
                conexion.sendall(b"MANUAL\n" if _manual else b"NADA\n")
            except OSError:
                pass
            return
        if linea.strip() == DEVOLUCION.strip():
            devolver_manual()
            try:
                conexion.sendall(CONFIRMACION)
            except OSError:
                pass
            return
        if linea.strip() != PETICION.strip():
            return
        _ceder()
        try:
            # Para el LIBRE el micrófono tiene que estar ya CERRADO: si no,
            # quien lo pide intentaría abrirlo y se lo encontraría ocupado.
            conexion.sendall(RESPUESTA)
            # La cesión dura lo que la conexión: se espera a que la cierren
            # (o a que se muera quien la abrió, que para el caso es igual).
            while conexion.recv(1024):
                pass
        except OSError:
            pass
        finally:
            _recuperar()
            # Quien lo ha pedido lo devuelve: si además estaba cedido a mano,
            # esa cesión también se acaba aquí ("hasta que lo devuelva").
            if _manual:
                devolver_manual()


def cedido_a_mano() -> bool:
    """True mientras el micrófono esté cedido con el botón o por voz."""
    return _manual


def al_cambiar(fn):
    """fn(cedido_a_mano: bool) se llama en cada cambio de la cesión a mano,
    desde un hilo que NO es el de Qt (main.py lo pasa por una señal)."""
    global _al_cambiar
    _al_cambiar = fn


def _avisar():
    fn = _al_cambiar
    if fn is not None:
        try:
            fn(_manual)
        except Exception as exc:
            print(f"[cesion_microfono] error avisando del cambio: {exc!r}")


def _poner_manual(valor: bool):
    global _manual
    with _manual_lock:
        if _manual == valor:
            return
        _manual = valor
        if valor:
            print("[cesion_microfono] cedo el micrófono a mano (Pipe-Logic Mic)")
            _ceder()
        else:
            print("[cesion_microfono] se acaba la cesión a mano")
            _recuperar()
    _avisar()


def ceder_manual():
    """Suelta el micrófono hasta devolver_manual() o hasta que Pipe-Logic
    lo devuelva. Vuelve cuando ya está cerrado."""
    _poner_manual(True)


def devolver_manual():
    _poner_manual(False)


def alternar_manual():
    """El botón: cede si no estaba cedido a mano, y si lo estaba, lo
    recupera. Lo hace en otro hilo para no parar la ventana mientras se
    cierra el micrófono."""
    def _alternar():
        with _manual_lock:
            _poner_manual(not _manual)
    threading.Thread(target=_alternar, daemon=True, name="cesion_manual").start()


def _escuchar(servidor: socket.socket):
    while True:
        try:
            conexion, _ = servidor.accept()
        except OSError:
            return
        threading.Thread(target=_atender, args=(conexion,), daemon=True).start()


def arrancar_servidor() -> bool:
    """Abre el socket y atiende peticiones en un hilo aparte. False si no
    se puede (Windows, desactivado, u otro VoiceController ya lo tiene)."""
    if not getattr(config, "CEDER_MICROFONO_ENABLED", True):
        return False
    if not hasattr(socket, "AF_UNIX"):
        print("[cesion_microfono] sin sockets Unix en este sistema: no se cede el micrófono")
        return False
    ruta = ruta_socket()
    try:
        ruta.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if ruta.exists():
            # Un socket de una ejecución anterior que no se borró. Pero si
            # alguien contesta, es otro VoiceController en marcha: no se le
            # quita.
            prueba = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                prueba.connect(str(ruta))
                print(f"[cesion_microfono] {ruta} ya lo atiende otro proceso; no se arranca")
                return False
            except OSError:
                ruta.unlink()
            finally:
                prueba.close()
        servidor = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        servidor.bind(str(ruta))
        os.chmod(ruta, 0o600)
        servidor.listen(4)
    except OSError as exc:
        print(f"[cesion_microfono] no se pudo abrir {ruta}: {exc!r}")
        return False
    threading.Thread(target=_escuchar, args=(servidor,), daemon=True,
                     name="cesion_microfono").start()
    print(f"[cesion_microfono] atendiendo peticiones de micrófono en {ruta}")
    return True


@contextmanager
def pedir_microfono(timeout: float = 5.0):
    """Lado de quien PIDE el micrófono (Pipe-Logic, o tools/ceder_microfono.py).

        with pedir_microfono():
            ... grabar ...

    Si VoiceController no está en marcha, no hay nada que pedir y el bloque
    se ejecuta igual."""
    conexion = None
    try:
        conexion = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conexion.settimeout(timeout)
        conexion.connect(str(ruta_socket()))
        conexion.sendall(PETICION)
        if conexion.makefile("rb").readline(64) != RESPUESTA:
            raise OSError("respuesta inesperada")
        conexion.settimeout(None)
    except OSError:
        if conexion is not None:
            conexion.close()
        conexion = None
    try:
        yield
    finally:
        if conexion is not None:
            conexion.close()
