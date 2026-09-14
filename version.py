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
version.py: Definición centralizada de la versión de VoiceController.

Esta es la fuente de verdad única para la versión.
Se importa en setup.py, __init__.py, y se puede consultar en CLI.

Patrón: MAJOR.MINOR.PATCH[-prerelease]
Ejemplos: 1.0.0, 1.0.1-beta, 1.1.0-rc1
"""

__version__ = "0.2.0"
__author__ = "pipataki"
__author_email__ = "pipataki@pipataki.net"
__license__ = "LGPL-3.0-or-later"
__url__ = "https://github.com/pipataki/VoiceController"
__repository__ = "https://github.com/pipataki/VoiceController"

# Información detallada de la versión
VERSION_INFO = {
    "version": __version__,
    "name": "VoiceController",
    "description": "Control del ordenador por voz, offline (español/inglés), en Linux (KDE Plasma) y Windows",
    "author": __author__,
    "author_email": __author_email__,
    "license": __license__,
    "url": __url__,
    "repository": __repository__,
    # pre-alpha, alpha, beta, stable. La alpha todavia no ha salido: hasta
    # la 0.1.0 decia "beta", que va DESPUES de la alpha.
    "status": "pre-alpha",
}


def get_version() -> str:
    """Retorna la versión actual."""
    return __version__


def print_version_info():
    """Imprime información completa de la versión."""
    print(f"{VERSION_INFO['name']} v{__version__}")
    print(f"Autor: {__author__} <{__author_email__}>")
    print(f"Licencia: {__license__}")
    print(f"Repositorio: {__repository__}")
    print(f"Estado: {VERSION_INFO['status']}")
    print(f"\n{VERSION_INFO['description']}")


if __name__ == "__main__":
    print_version_info()
