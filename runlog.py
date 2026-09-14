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
runlog: deja en disco todo lo que el programa cuenta por consola.

POR QUE EXISTE
--------------
El 4 de septiembre de 2026 el ordenador se quedo bloqueado mientras
alguien probaba el santo y sena en remoto, y hubo que reiniciar a lo
bruto. Al volver no habia ni una linea sobre lo que estaba haciendo la
aplicacion: todo se contaba por consola, y la consola murio con el
reinicio. `config.LOG_FILE` llevaba declarado desde siempre, pero no lo
leia nadie.

COMO
----
No se toca ninguno de los 571 `print()` del programa. Se desdobla
`sys.stdout` y `sys.stderr`: lo que sale sigue viendose en el terminal
igual que antes, y ademas se escribe en el fichero con la hora delante.
Asi entran tambien los `Traceback` que Python manda a stderr, que son
justo los que uno quiere leer despues de un cuelgue.

LO IMPORTANTE: SE VACIA EN CADA LINEA
-------------------------------------
El fichero se abre sin buffer de linea y se hace `flush()` en cada salto
de linea. Es mas lento, y da igual: un log que se pierde en el corte de
corriente no sirve para nada, y el caso que hay que cubrir es
exactamente ese. Lo que se escribio, esta en el disco.

Del arranque anterior se guarda una copia (`.log.1`) antes de empezar el
nuevo, porque cuando algo se cuelga lo que interesa leer es el log de la
sesion que se murio, no el de la que acabas de arrancar para mirarlo.
"""

import atexit
import os
import sys
import threading
import time
from datetime import datetime

_original_stdout = None
_original_stderr = None
_fichero = None
_lock = threading.Lock()


class _Desdoble:
    """Escribe en la consola y en el fichero a la vez.

    Va poniendo la hora al principio de cada linea. Hace falta llevar la
    cuenta de si venimos a mitad de linea porque `print()` no manda el
    texto y el salto de linea en la misma llamada a `write()`: si se
    pusiera la hora en cada `write()` sin mirar, saldrian marcas de hora
    en medio de las frases.
    """

    def __init__(self, consola, fichero, etiqueta=""):
        self._consola = consola
        self._fichero = fichero
        self._etiqueta = etiqueta
        self._a_medias = False

    def write(self, texto):
        if not texto:
            return 0
        # La consola primero y sin candado: si el fichero da problemas,
        # que al menos se siga viendo el programa por el terminal.
        try:
            self._consola.write(texto)
        except Exception:
            pass

        with _lock:
            try:
                self._volcar(texto)
            except Exception:
                # Un log que rompe el programa al que sirve seria peor
                # que no tener log. Se calla y se sigue.
                pass
        return len(texto)

    def _volcar(self, texto):
        if self._fichero is None or self._fichero.closed:
            return
        marca = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        cabecera = f"{marca} {self._etiqueta}" if self._etiqueta else f"{marca} "

        # Se parte por lineas conservando los saltos, para poder decidir
        # linea a linea si toca poner la hora y si toca vaciar a disco.
        for trozo in texto.splitlines(keepends=True):
            if not self._a_medias:
                self._fichero.write(cabecera)
            self._fichero.write(trozo)
            if trozo.endswith(("\n", "\r")):
                self._a_medias = False
                # Aqui esta la gracia de todo el modulo: al disco, ya.
                self._fichero.flush()
            else:
                self._a_medias = True

    def flush(self):
        try:
            self._consola.flush()
        except Exception:
            pass
        with _lock:
            try:
                if self._fichero and not self._fichero.closed:
                    self._fichero.flush()
            except Exception:
                pass

    # --- lo que otras librerias esperan de un stdout de verdad ---

    def isatty(self):
        try:
            return self._consola.isatty()
        except Exception:
            return False

    def fileno(self):
        # Se delega en la consola a proposito. Si algo pide el descriptor
        # (un subproceso al que se le pasa stdout=sys.stdout, por
        # ejemplo), su salida ira al terminal y NO al fichero. Es la
        # concesion honesta: preferible eso a fingir un descriptor que no
        # existe y romper el subproceso.
        return self._consola.fileno()

    @property
    def encoding(self):
        return getattr(self._consola, "encoding", "utf-8")

    def writable(self):
        return True

    def readable(self):
        return False

    def seekable(self):
        return False


def _rotar(ruta, max_bytes):
    """Aparta el log del arranque anterior antes de empezar el nuevo."""
    try:
        if not os.path.exists(ruta):
            return
        anterior = f"{ruta}.1"
        if os.path.exists(anterior):
            os.remove(anterior)
        os.replace(ruta, anterior)
    except Exception:
        # Si no se puede rotar se sigue igual: se anadira al que haya, y
        # si ha crecido demasiado lo corta el control de tamano.
        try:
            if os.path.getsize(ruta) > max_bytes:
                os.remove(ruta)
        except Exception:
            pass


def empezar():
    """Arranca el desdoble. Se llama una vez, lo primero de todo.

    Devuelve la ruta del log, o None si esta desactivado o no se ha
    podido abrir el fichero (en cuyo caso el programa sigue tal cual,
    imprimiendo solo por consola como hacia antes).
    """
    global _original_stdout, _original_stderr, _fichero

    if _fichero is not None:
        return getattr(_fichero, "name", None)

    import config

    if not getattr(config, "ENABLE_LOG_FILE", False):
        return None

    ruta = str(getattr(config, "LOG_FILE", "") or "")
    if not ruta:
        return None

    max_mb = float(getattr(config, "LOG_MAX_MB", 5) or 5)
    _rotar(ruta, int(max_mb * 1024 * 1024))

    try:
        # buffering=1 es buffer de linea; ademas se hace flush explicito
        # en cada salto, que es lo que de verdad garantiza el disco.
        _fichero = open(ruta, "a", encoding="utf-8", errors="replace", buffering=1)
    except Exception as e:
        print(f"[runlog] no se pudo abrir {ruta}: {e!r} -- solo consola")
        return None

    _original_stdout = sys.stdout
    _original_stderr = sys.stderr
    sys.stdout = _Desdoble(_original_stdout, _fichero)
    sys.stderr = _Desdoble(_original_stderr, _fichero, etiqueta="!! ")

    atexit.register(terminar)

    inicio = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[runlog] === arranque {inicio} (pid {os.getpid()}) ===")
    print(f"[runlog] log en {ruta} (el del arranque anterior, en {ruta}.1)")
    return ruta


def terminar():
    """Cierra el log dejando constancia de que el cierre fue ordenado.

    Esa linea final es la que distingue, al leerlo despues, un programa
    que termino como debia de uno que se quedo cortado a media frase
    porque el equipo se fue abajo.
    """
    global _fichero
    if _fichero is None:
        return
    try:
        fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[runlog] === cierre ordenado {fin} ===")
    except Exception:
        pass
    try:
        sys.stdout = _original_stdout or sys.__stdout__
        sys.stderr = _original_stderr or sys.__stderr__
    except Exception:
        pass
    try:
        _fichero.flush()
        _fichero.close()
    except Exception:
        pass
    _fichero = None
