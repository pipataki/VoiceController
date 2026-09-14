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
merge_commands: añade los comandos NUEVOS de una versión sin pisar los tuyos.

El problema
-----------
`commands.json` es a la vez código y configuración personal. Cada versión
trae comandos nuevos (en un solo día se añadieron teclas especiales,
ayuda, standby, ventanas...), pero el usuario personaliza sus `aliases`
--que es justo lo que la aplicación anima a hacer--. Sobrescribirlo le
borra su trabajo; no tocarlo le deja sin los comandos nuevos.

Como es un diccionario por claves, se puede fusionar:

  - Clave que NO tienes -> se añade entera (comando nuevo).
  - Clave que YA tienes  -> **no se toca**, ni sus aliases ni su scope.
  - Se AVISA de las que la versión nueva cambió y tú tenías modificadas,
    para que decidas tú. No se resuelve solo: elegir por el usuario entre
    su alias y el del paquete es justo lo que no debe hacer un
    actualizador.

Uso
---
    ./venv/bin/python tools/merge_commands.py commands.default.json
    ./venv/bin/python tools/merge_commands.py commands.default.json --aplicar

Sin --aplicar solo enseña lo que haría. Con --aplicar hace copia antes.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DESTINO = PROJECT_ROOT / "commands.json"


def _es_seccion(valor):
    """Las secciones son diccionarios de comandos; el resto (cadenas de
    comentario, "routes"...) se trata como valor suelto."""
    return isinstance(valor, dict)


def fusionar(actual: dict, nuevo: dict):
    """Devuelve (resultado, añadidos, conflictos). No modifica `actual`."""
    resultado = json.loads(json.dumps(actual))   # copia honda
    anadidos, conflictos = [], []

    for seccion, contenido in nuevo.items():
        if seccion not in resultado:
            resultado[seccion] = contenido
            if _es_seccion(contenido):
                anadidos += [f"{seccion}/{k}" for k in contenido if not k.startswith("_")]
            else:
                anadidos.append(seccion)
            continue
        if not _es_seccion(contenido) or not _es_seccion(resultado[seccion]):
            continue

        # ORDENES RETIRADAS. La fusion anade pero nunca quita, y una orden que
        # el paquete ya no tiene seguiria saliendo en la ayuda de una
        # instalacion vieja. "_retiradas" dice cuales se quitan -- solo esas.
        # 14-sep-2026: "revive", porque de la espera se sale diciendo el
        # santo y sena, sin mas.
        for vieja in contenido.get("_retiradas") or []:
            if vieja in resultado[seccion]:
                del resultado[seccion][vieja]
                anadidos.append(f"{seccion}/{vieja}: retirada")

        for clave, entrada in contenido.items():
            if clave not in resultado[seccion]:
                resultado[seccion][clave] = entrada
                if not clave.startswith("_"):
                    anadidos.append(f"{seccion}/{clave}")
            elif resultado[seccion][clave] != entrada and not clave.startswith("_"):
                # EXISTE EN LOS DOS. Antes se dejaba tal cual y se avisaba,
                # y eso dejaba fuera cosas que no son personalizaciones sino
                # AÑADIDOS del paquete: el 6-sep-2026 se anadieron los campos
                # help_en y alias_en a 69 comandos ya existentes, y al
                # actualizar nadie los habria recibido -- la ayuda en ingles
                # se habria quedado en espanol sin decir por que.
                #
                # Ahora se distingue:
                #
                #   - campo que TU no tienes  -> se anade (es nuevo del
                #     paquete, no puede pisar nada);
                #   - alias nuevos            -> se anaden al final,
                #     conservando los tuyos y su orden;
                #   - campo que tienes con OTRO valor -> se respeta el tuyo
                #     y se avisa, como siempre.
                mio, suyo = resultado[seccion][clave], entrada
                # ALIAS RETIRADOS. La fusion anade alias pero nunca quita, y eso
                # deja un problema cuando el PAQUETE mueve un alias de un comando a
                # otro: el 12-sep-2026 "refresca" y "refresh" pasaron de F5 a
                # refrescar las capturas, y en una instalacion vieja F5 los habria
                # conservado, chocando con el comando nuevo. "aliases_retirados" dice
                # cuales quita el paquete. Solo esos: lo que el usuario anadio por su
                # cuenta no se toca.
                if isinstance(mio, dict) and isinstance(suyo, dict):
                    retirar = suyo.get("aliases_retirados") or []
                    if retirar and isinstance(mio.get("aliases"), list):
                        antes = len(mio["aliases"])
                        mio["aliases"] = [a for a in mio["aliases"] if a not in retirar]
                        if len(mio["aliases"]) != antes:
                            anadidos.append(f"{seccion}/{clave}: {antes - len(mio['aliases'])} alias retirados")
                if isinstance(mio, dict) and isinstance(suyo, dict):
                    for campo, valor in suyo.items():
                        if campo not in mio:
                            mio[campo] = valor
                            anadidos.append(f"{seccion}/{clave}:{campo}")
                        elif campo == "aliases" and isinstance(mio[campo], list) \
                                and isinstance(valor, list):
                            nuevos_alias = [a for a in valor if a not in mio[campo]]
                            if nuevos_alias:
                                mio[campo].extend(nuevos_alias)
                                anadidos.append(
                                    f"{seccion}/{clave}: {len(nuevos_alias)} alias")
                        elif mio[campo] != valor:
                            conflictos.append((f"{seccion}/{clave}:{campo}",
                                               mio[campo], valor))
                else:
                    conflictos.append((f"{seccion}/{clave}", mio, suyo))
    return resultado, anadidos, conflictos


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("nuevo", help="commands.json de la versión nueva")
    ap.add_argument("--destino", default=str(DESTINO))
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    destino = Path(args.destino)
    if not destino.is_file():
        # instalación desde cero: no hay nada que fusionar
        if args.aplicar:
            shutil.copy2(args.nuevo, destino)
            print(f"No había {destino}: copiado tal cual (instalación nueva).")
        else:
            print(f"No hay {destino}: se copiaría tal cual (instalación nueva).")
        return

    actual = json.loads(destino.read_text(encoding="utf-8"))
    nuevo = json.loads(Path(args.nuevo).read_text(encoding="utf-8"))
    resultado, anadidos, conflictos = fusionar(actual, nuevo)

    if anadidos:
        print(f"COMANDOS NUEVOS ({len(anadidos)}):")
        for a in anadidos:
            print(f"  + {a}")
    else:
        print("No hay comandos nuevos.")

    if conflictos:
        print(f"\nCAMBIADOS EN LA VERSIÓN NUEVA, pero TÚ los tienes modificados "
              f"({len(conflictos)}).")
        print("Se respeta lo tuyo. Míralos por si te interesa el cambio:\n")
        for clave, mio, suyo in conflictos:
            print(f"  {clave}")
            print(f"      tuyo   : {json.dumps(mio, ensure_ascii=False)}")
            print(f"      versión: {json.dumps(suyo, ensure_ascii=False)}")

    if not args.aplicar:
        print("\nRepite con --aplicar para escribirlo.")
        return

    copia = destino.with_suffix(".json.antes_merge")
    shutil.copy2(destino, copia)
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    print(f"\nEscrito {destino} ({len(anadidos)} comandos añadidos).")
    print(f"Copia previa en {copia}")


if __name__ == "__main__":
    main()
