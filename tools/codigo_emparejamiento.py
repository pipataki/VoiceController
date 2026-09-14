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

"""Dice el código de emparejamiento de este ordenador.

Es el número que hay que comparar con el que enseña el móvil la primera vez
que se conecta. Sale del certificado del PC, así que no hay nada que generar
ni que guardar: mientras el certificado no cambie, el código es siempre el
mismo.

La misma cuenta está en la app de Android (Emparejamiento.java, en sus
fuentes, que no viajan en este repositorio). Si se cambia una hay que cambiar
la otra.
"""
import hashlib
import ssl
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def huella(pem: Path) -> str:
    """SHA-256 del certificado en su forma binaria (DER), que es lo que
    también ve el móvil por la red -- del PEM en texto saldría otra cosa."""
    der = ssl.PEM_cert_to_DER_cert(pem.read_text())
    return hashlib.sha256(der).hexdigest()


def codigo(huella_hex: str) -> str:
    doce = str(int(huella_hex[:16], 16) % 10**12).zfill(12)
    return f"{doce[0:3]} {doce[3:6]} {doce[6:9]} {doce[9:12]}"


def main() -> int:
    pem = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "webapp_cert.pem"
    if not pem.exists():
        print(f"No encuentro el certificado en {pem}.")
        print("Se crea al configurar el acceso desde el móvil, en install.sh.")
        return 1
    h = huella(pem)
    print()
    print("  Código de emparejamiento de este ordenador:")
    print()
    print(f"      {codigo(h)}")
    print()
    print("  Dilo o compáralo con el que te enseñe el móvil la primera vez")
    print("  que conectes. Si coinciden, es este ordenador.")
    print()
    print(f"  (huella completa: {h})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
