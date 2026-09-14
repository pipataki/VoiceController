#!/usr/bin/env python3
# VoiceController -- control del ordenador por voz, pensado para accesibilidad.
# Copyright (C) 2026  pipataki <pipataki@pipataki.net>
#
# Este programa es software libre: puedes redistribuirlo y/o modificarlo bajo
# los terminos de la Licencia Publica General Reducida GNU (LGPL)
# publicada por la Free Software Foundation, en su version 3 o
# cualquier version posterior.
#
# Se distribuye SIN NINGUNA GARANTIA. Ver <https://www.gnu.org/licenses/>.

"""
merge_prosody: mete las palabras NUEVAS de una version sin quitar las tuyas.

El mismo problema que con los comandos, y la misma solucion -- pero la
fusion es distinta, y por eso no vale merge_commands.py.

En `commands.json` los aliases son una ELECCION: si alguien decidio que su
comando se dice de otra forma, meterle el alias del paquete le estropea lo
que quiso. Por eso alli, la clave que ya existe no se toca.

En `prosody.json` las listas son ACUMULATIVAS: son palabras que suenan a
pregunta o a exclamacion, y tener mas es tener mejor prosodia. Aqui lo
correcto es la UNION -- se anaden las nuevas y se conservan las tuyas.

Uso
---
    ./venv/bin/python tools/merge_prosody.py prosody.default.json
    ./venv/bin/python tools/merge_prosody.py prosody.default.json --aplicar

Sin --aplicar solo dice lo que haria. Con --aplicar hace copia antes.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MIO = RAIZ / "prosody.json"


def fusionar(mio: dict, nuevo: dict):
    """Devuelve (resultado, lista de lo anadido)."""
    salida = json.loads(json.dumps(mio))    # copia honda
    anadido = []

    # Lo que el usuario ha excluido no vuelve nunca, aunque el paquete lo
    # traiga. Sin esto, quitar una palabra no serviria de nada: reaparece en
    # la siguiente actualizacion y no hay forma de decir que no la quieres.
    excluidas = set()
    for idioma, lista in (mio.get("quitadas") or {}).items():
        if not idioma.startswith("_") and isinstance(lista, list):
            excluidas.update(lista)

    # De paso se limpian de las listas las palabras excluidas. No es
    # imprescindible -- el cargador ya las descuenta -- pero dejar una
    # palabra escrita en la lista Y en "quitadas" a la vez es confuso de
    # leer, y este fichero esta pensado para editarlo a mano.
    if excluidas:
        for seccion, contenido in salida.items():
            if seccion in ("quitadas",) or not isinstance(contenido, dict):
                continue
            for idioma, entradas in contenido.items():
                if idioma.startswith("_") or not isinstance(entradas, list):
                    continue
                contenido[idioma] = [e for e in entradas if e not in excluidas]

    for seccion, contenido in nuevo.items():
        if seccion.startswith("_"):
            # Los comentarios del paquete SI se actualizan: explican lo que
            # hace la version nueva, y dejar el texto viejo confunde.
            salida[seccion] = contenido
            continue
        if not isinstance(contenido, dict):
            continue
        if seccion not in salida or not isinstance(salida[seccion], dict):
            salida[seccion] = contenido
            n = sum(len(v) for k, v in contenido.items()
                    if not k.startswith("_") and isinstance(v, list))
            anadido.append(f"seccion nueva {seccion!r} ({n} entradas)")
            continue

        for idioma, entradas in contenido.items():
            if idioma.startswith("_"):
                salida[seccion][idioma] = entradas
                continue
            if not isinstance(entradas, list):
                continue
            mias = salida[seccion].get(idioma)
            if not isinstance(mias, list):
                salida[seccion][idioma] = list(entradas)
                anadido.append(f"{seccion}/{idioma}: {len(entradas)} entradas")
                continue
            # UNION conservando el orden: primero lo tuyo, luego lo nuevo.
            faltan = [e for e in entradas
                      if e not in mias and e not in excluidas]
            if faltan:
                salida[seccion][idioma] = mias + faltan
                anadido.append(f"{seccion}/{idioma}: +{len(faltan)} "
                               f"({', '.join(map(repr, faltan[:5]))}"
                               f"{'...' if len(faltan) > 5 else ''})")
    return salida, anadido


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("nuevo", help="prosody.default.json de la version nueva")
    ap.add_argument("--aplicar", action="store_true",
                    help="escribir de verdad (si no, solo dice que haria)")
    args = ap.parse_args()

    ruta_nuevo = Path(args.nuevo)
    if not ruta_nuevo.exists():
        print(f"no encuentro {ruta_nuevo}")
        return 1
    if not MIO.exists():
        shutil.copy2(ruta_nuevo, MIO)
        print(f"no habia {MIO.name}: copiado del paquete")
        return 0

    try:
        mio = json.loads(MIO.read_text(encoding="utf-8"))
        nuevo = json.loads(ruta_nuevo.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"no se pudo leer alguno de los dos: {exc}")
        return 1

    resultado, anadido = fusionar(mio, nuevo)

    # Ojo: "nada que anadir" no es lo mismo que "nada que hacer". La
    # limpieza de las palabras excluidas tambien es un cambio, y si se sale
    # aqui nunca llegaria a escribirse.
    hay_cambios = bool(anadido) or resultado != mio
    if not hay_cambios:
        print("ya tienes todo lo de esta version")
        return 0
    if not anadido:
        print("nada nuevo que anadir, pero hay que limpiar palabras excluidas")

    if anadido:
        print("se anadiria:")
        for linea in anadido:
            print("   ", linea)

    if not args.aplicar:
        print("\n(nada escrito -- repite con --aplicar)")
        return 0

    copia = MIO.with_suffix(".json.antes")
    shutil.copy2(MIO, copia)
    MIO.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"\nhecho. Copia de lo que tenias en {copia.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
