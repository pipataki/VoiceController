#!/usr/bin/env python3
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
probar_backend: comprueba, una por una, las cosas que el programa le hace
al sistema operativo.

Para qué
--------
La capa `backends/` concentra todo lo que VoiceController necesita del
sistema: escribir teclas, mover el ratón, hacer clic, capturar la pantalla
y manejar ventanas. En Linux funciona; en Windows está escrita pero nunca
se ha ejecutado.

Este script prueba cada pieza por separado y dice cuál va y cuál no, para
saber qué falta portar sin tener que descubrirlo usando el programa entero.

Cómo se usa
-----------
    python tools/probar_backend.py            # solo lo que no toca nada
    python tools/probar_backend.py --todo     # incluye teclas y ratón

Por defecto NO escribe ni hace clic: esas pruebas mueven el ratón de
verdad y teclean en la ventana que tenga el foco, así que hay que pedirlas
a propósito. Con --todo, abre el Bloc de notas (o un editor) y escribe
ahí, para no soltar texto en cualquier sitio.
"""

import argparse
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

VERDE, ROJO, GRIS, FIN = "\033[32m", "\033[31m", "\033[90m", "\033[0m"
SI, NO = "\u2713", "\u2717"
if sys.platform.startswith("win"):
    # La consola de Windows usa cp1252 por defecto y revienta con
    # UnicodeEncodeError al imprimir marcas Unicode. Se usan ASCII y sin
    # colores: menos bonito, pero legible en cualquier terminal.
    VERDE = ROJO = GRIS = FIN = ""
    SI, NO = "[OK]", "[!!]"

RESULTADOS = []


def prueba(nombre, fn, detalle=""):
    """Ejecuta una comprobación y anota el resultado sin cortar el resto:
    que falle una pieza no debe impedir saber si las demás funcionan."""
    try:
        ok = fn()
        estado = "OK" if ok else "FALLA"
    except Exception as exc:
        ok, estado = False, f"ERROR: {type(exc).__name__}: {exc}"
    RESULTADOS.append((nombre, ok, estado))
    color = VERDE if ok else ROJO
    print(f"  {color}{SI if ok else NO}{FIN} {nombre:<34} {estado}")
    if detalle and not ok:
        print(f"      {GRIS}{detalle}{FIN}")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--todo", action="store_true",
                    help="incluye teclas y ratón (mueven el cursor y escriben de verdad)")
    args = ap.parse_args()

    print("=" * 62)
    print(f" Plataforma: {sys.platform}  |  Python {sys.version.split()[0]}")
    print("=" * 62)

    # --- 1. ¿carga la capa? -------------------------------------------
    print("\n[1] La capa de plataforma")
    try:
        import backends
        b = backends.get()
        print(f"  backend elegido: {b.NOMBRE}")
        disponible, motivo = b.available()
        print(f"  {'listo' if disponible else 'INCOMPLETO'}: {motivo or 'todo presente'}")
    except Exception as exc:
        print(f"  {ROJO}no se pudo cargar: {exc!r}{FIN}")
        return 1

    # --- 2. dependencias ----------------------------------------------
    print("\n[2] Bibliotecas que necesita")
    if sys.platform.startswith("win"):
        for mod in ("pydirectinput", "mss", "pygetwindow", "sounddevice", "vosk"):
            prueba(mod, lambda m=mod: __import__(m) is not None,
                   f"pip install {mod}")
    else:
        import shutil
        for cmd in ("ydotool", "kdotool", "spectacle"):
            prueba(cmd, lambda c=cmd: shutil.which(c) is not None)

    # --- 3. capturas (no toca nada) ------------------------------------
    print("\n[3] Capturar la pantalla")
    destino = RAIZ / "_prueba_captura.png"
    def cap():
        b.screenshot(str(destino))
        return destino.exists() and destino.stat().st_size > 1000
    if prueba("captura de pantalla", cap, "revisa mss (Windows) o spectacle (Linux)"):
        print(f"      {GRIS}{destino.stat().st_size // 1024} KB en {destino.name}{FIN}")
        destino.unlink(missing_ok=True)

    # --- 4. ventanas (solo consulta) -----------------------------------
    print("\n[4] Ventanas")
    def ventana_activa():
        if sys.platform.startswith("win"):
            import pygetwindow
            v = pygetwindow.getActiveWindow()
            if v: print(f"      {GRIS}con el foco: {v.title[:44]!r}{FIN}")
            return v is not None
        import subprocess, shutil
        if not shutil.which("kdotool"):
            return False
        r = subprocess.run(["kdotool", "getactivewindow", "getwindowname"],
                           capture_output=True, text=True, timeout=5)
        if r.stdout.strip(): print(f"      {GRIS}con el foco: {r.stdout.strip()[:44]!r}{FIN}")
        return r.returncode == 0
    prueba("leer la ventana activa", ventana_activa)

    if not args.todo:
        print(f"\n{GRIS}  (teclas y ratón no se prueban sin --todo: escriben y"
              f" mueven el cursor de verdad){FIN}")
    else:
        # --- 5. teclas y ratón ----------------------------------------
        print("\n[5] Teclado y ratón  --  ABRE UN EDITOR DE TEXTO Y DALE EL FOCO")
        for i in (3, 2, 1):
            print(f"  {i}...", flush=True); time.sleep(1)
        prueba("escribir texto (ctrl+n / letras)",
               lambda: all(b.send_key(k) for k in ("h", "o", "l", "a")))
        prueba("combinación con modificador", lambda: b.send_key("ctrl+a"))
        prueba("tecla especial (Tab)", lambda: b.send_key("Tab"))
        prueba("repetición (Down x3)", lambda: b.send_key("Down", 3))
        prueba("mover el puntero", lambda: b.move_pointer(300, 300))
        prueba("scroll abajo", lambda: b.scroll("down", 2))
        print(f"\n{GRIS}  El clic NO se prueba solo: pulsaría en donde esté el"
              f" cursor, sin saber qué hay debajo.{FIN}")

    # --- resumen -------------------------------------------------------
    print("\n" + "=" * 62)
    fallos = [n for n, ok, _ in RESULTADOS if not ok]
    print(f" {len(RESULTADOS) - len(fallos)} de {len(RESULTADOS)} comprobaciones OK")
    if fallos:
        print(f" Falla: {', '.join(fallos)}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
