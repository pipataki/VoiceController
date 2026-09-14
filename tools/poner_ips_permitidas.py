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
Escribe WEBAPP_ALLOWED_IPS en config_local.py.

Lo usan los dos instaladores (install.sh e install.bat) para no repetir la
misma logica en bash y en cmd, que es donde se cuelan los errores tontos.

POR QUE EN config_local.py Y NO EN webapp_config.json
-----------------------------------------------------
Es un ajuste de ESTA maquina y de ESTA red. La IP del movil de uno no
significa nada en el ordenador de otro, y una instalacion en Windows no
tiene por que heredar la red de la de Linux. config_local.py es ademas el
fichero que NO se pisa al actualizar, que es justo lo que hace falta para
algo que costo trabajo averiguar.

Se valida antes de escribir. Una IP mal escrita en esta lista no da un
error visible: simplemente deja fuera al movil, en silencio, y quien lo
sufra buscara el fallo en la VPN, en el router o en el certificado. Antes
que eso, se avisa aqui.

    python3 tools/poner_ips_permitidas.py 10.8.0.2
    python3 tools/poner_ips_permitidas.py 10.8.0.10-50 192.168.1.7
"""

import ipaddress
import sys
from pathlib import Path

CLAVE = "WEBAPP_ALLOWED_IPS"


def valida(entrada: str) -> bool:
    """Los cuatro formatos que entiende webapp/app.py:_ip_en_lista()."""
    entrada = entrada.strip()
    try:
        if "/" in entrada:
            ipaddress.ip_network(entrada, strict=False)
        elif "-" in entrada:
            desde, hasta = (x.strip() for x in entrada.split("-", 1))
            if "." not in hasta:
                hasta = desde.rsplit(".", 1)[0] + "." + hasta
            ipaddress.ip_address(desde)
            ipaddress.ip_address(hasta)
        else:
            ipaddress.ip_address(entrada)
        return True
    except ValueError:
        return False


def main(argv):
    entradas = [x for x in argv if x.strip()]
    if not entradas:
        print("  no se ha puesto ninguna IP: se deja sin filtrar")
        return 0

    malas = [x for x in entradas if not valida(x)]
    if malas:
        print("  ESTAS NO SON IPs VALIDAS y no se escribe nada:")
        for m in malas:
            print(f"    {m}")
        print("  Formatos: 10.8.0.2  |  10.8.0.10-50  |  10.8.0.0/24")
        return 1

    destino = Path(__file__).resolve().parent.parent / "config_local.py"
    texto = destino.read_text(encoding="utf-8") if destino.exists() else ""

    # Si ya estaba puesta, se REEMPLAZA la linea en vez de anadir otra: dos
    # asignaciones a la misma variable no dan error en Python, gana la
    # ultima, y el fichero se queda diciendo dos cosas distintas.
    if CLAVE in texto:
        texto = "\n".join(l for l in texto.splitlines()
                          if not l.strip().startswith(CLAVE))

    texto = texto.rstrip() + (
        f"\n\n# Solo estos aparatos pueden conectarse a la webapp (ver config.py).\n"
        f"# Si cambias de movil o te cambia la IP, EDITA ESTO o dejara de\n"
        f"# responderte sin dar ninguna explicacion.\n"
        f"{CLAVE} = {entradas!r}\n")
    destino.write_text(texto, encoding="utf-8")
    print(f"  escrito en {destino.name}:  {CLAVE} = {entradas!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
