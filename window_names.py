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
window_names.py: nombres de ventana conocidos para el comando de voz
"trae <nombre>"/"traer <nombre>" (ver command_router._try_parse_bring_window).

Por qué existe este módulo aparte de corrections.py/corrections.json:
`kdotool` (ver actions.activate_window_by_name) compara el nombre que le
pasamos contra el TÍTULO REAL de la ventana -- y aunque se le antepone
`(?i)` para que la comparación sea insensible a mayúsculas, en la
práctica no siempre basta (ver sesión de pruebas: "kate" en minúsculas
tal cual dictado no encontraba la ventana "Kate"). En vez de depender
solo de eso, este módulo guarda un diccionario aparte
{nombre_normalizado: "Capitalización Real"} para las apps que uses
habitualmente, y se usa para normalizar el nombre ANTES de pasárselo a
kdotool. Se guarda en un archivo propio (window_names.json) en vez de
reutilizar corrections.json a propósito: ese es para el aprendizaje de
correcciones de palabra del dictado (un sistema totalmente distinto, con
su propia estructura estricta/ambigua) y mezclar aquí lo llenaría de
entradas que no pintan nada ahí, además de hacer más difícil encontrar
las cosas en cada archivo.

Si un nombre dicho NO está en el diccionario, se usa tal cual se dijo
("lo que diga") -- este módulo es un atajo para los casos conocidos, no
una lista cerrada.
"""

import json
import sys
import unicodedata

import paths

# Nombres conocidos de partida (apps habituales en un escritorio
# KDE/Kali) -- añade o edita libremente las que uses tú, ver save()/
# add() más abajo. La clave debe ser la forma normalizada (ver
# command_router._normalize: minúsculas, sin acentos) de como
# probablemente lo dictes; el valor es la capitalización REAL que tiene
# el título de la ventana en tu sistema.
_DEFAULTS = {
    "kate": "Kate",
    "cate": "Kate",
    "console": "Konsole",
    # DOLPHIN, y aqui hay una leccion. El 9-sep-2026 pipataki no conseguia
    # enfocarlo, y el log dijo que el problema no era el foco sino el
    # reconocimiento: Vosk nunca oyo "dolphin". Oyo "dolci", "delfin" y
    # "doki" -- es una palabra inglesa dicha a un modelo espanol.
    #
    # Lo que SI oyo perfecto (confianza 1.00) fue "explorador". Por eso se
    # anaden las dos cosas: lo que se oye mal, y una palabra espanola que
    # se oye bien y es la que conviene decir.
    "dolfin": "Dolphin",
    "dolphin": "Dolphin",
    "dolci": "Dolphin",
    "delfin": "Dolphin",
    "doki": "Dolphin",
    "dolfi": "Dolphin",
    "explorador": "Dolphin",
    "archivos": "Dolphin",
    "gestor de archivos": "Dolphin",
    "carpetas": "Dolphin",
    "inksqueip": "Inkscape",
    "gimp": "GIMP",
    "faierfox": "Firefox",
    "chromium": "Chromium",
    "krita": "Krita",
    "ocular": "Okular",
    "okular": "Okular",
    "espectacle": "Spectacle",
    "espectacol": "Spectacle",
    "spectacle": "Spectacle",
    "ark": "Ark",
    "arc": "Ark",
    "kcalc": "KCalc",
    "calculadora": "KCalc",
    "systemsettings": "System Settings",
    "configuracion del sistema": "System Settings",
    "config sistema": "System Settings",
    "sistema config": "System Settings",
}


# EN WINDOWS LOS PROGRAMAS SON OTROS, Y ALGUNOS NO SE PUEDEN BUSCAR POR TITULO.
#
# La tabla de arriba es de KDE: "explorador" -> Dolphin, "texto" -> Kate. En
# Windows ninguno existe, y pipataki lo vio el 12-sep-2026 en la VM: "foco
# explorador" buscaba una ventana llamada Dolphin.
#
# Y el Explorador de Windows 10 se TITULA CON EL NOMBRE DE LA CARPETA
# ("Descargas", "Este equipo"): no hay ningun trozo fijo de titulo que buscar.
# Por eso esos se buscan por CLASE DE VENTANA, que es fija, no depende de la
# carpeta abierta ni del idioma del sistema:
#
#     clase:CabinetWClass       el Explorador de archivos
#     clase:Notepad             el Bloc de notas
#     clase:ConsoleWindowClass  la consola (cmd)
#
# backends/windows.py entiende el prefijo "clase:". La calculadora es una
# aplicacion moderna y su clase la comparten todas, asi que va por titulo.
_DEFAULTS_WINDOWS = {
    "explorador": "clase:CabinetWClass",
    "explorer": "clase:CabinetWClass",
    "archivos": "clase:CabinetWClass",
    "carpetas": "clase:CabinetWClass",
    "gestor de archivos": "clase:CabinetWClass",
    "texto": "clase:Notepad",
    "editor": "clase:Notepad",
    "bloc de notas": "clase:Notepad",
    "notepad": "clase:Notepad",
    "consola": "clase:ConsoleWindowClass",
    "terminal": "clase:ConsoleWindowClass",
    "simbolo del sistema": "clase:ConsoleWindowClass",
    "calculadora": "Calculadora",
}


def _por_defecto() -> dict:
    """Los nombres de fabrica PARA ESTA PLATAFORMA."""
    base = dict(_DEFAULTS)
    if sys.platform.startswith("win"):
        base.update(_DEFAULTS_WINDOWS)
    return base


def _clave(nombre):
    """Una clave del fichero, como se busca de verdad: minusculas y sin
    tildes. Es la MISMA regla que command_router._normalize aplica a lo
    que se dice; si algun dia cambia alli, tiene que cambiar aqui."""
    nombre = unicodedata.normalize("NFD", str(nombre or ""))
    return "".join(c for c in nombre
                   if unicodedata.category(c) != "Mn").lower().strip()


def load() -> dict:
    """Carga window_names.json. Si no existe todavía, lo crea con
    _DEFAULTS (así el comando "trae <nombre>" funciona de fábrica con
    las apps más habituales, sin que el usuario tenga que configurar
    nada a mano primero). Si existe pero está corrupto, vuelve a
    _DEFAULTS sin tocar el archivo (para no perder lo que hubiera si
    solo fue un fallo de lectura puntual)."""
    try:
        with open(paths.WINDOW_NAMES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # SE MEZCLA, no se devuelve el fichero a secas.
            #
            # Antes, con el fichero ya creado, los nombres NUEVOS que
            # trajera una version del programa no llegaban nunca: se
            # devolvia el JSON tal cual. Es el mismo fallo que tenia
            # commands.json antes de la fusion por campo -- el usuario
            # actualiza, y lo nuevo no aparece sin decir por que.
            #
            # Lo del usuario MANDA: si ha cambiado un nombre a mano, su
            # valor gana sobre el de fabrica.
            base = _por_defecto()
            combinado = dict(base)
            # LAS CLAVES SE NORMALIZAN AL LEER.
            #
            # Lo que se busca aqui es el nombre YA normalizado (minusculas
            # y sin tildes, ver command_router._normalize), asi que una
            # clave escrita "Dolphin" o "Música" en el fichero no la
            # encontraria NADIE nunca -- y sin dar ningun error, que es lo
            # peor. pipataki se topo con eso el 10-sep-2026.
            #
            # El valor NO se toca: es la capitalizacion real del titulo de
            # la ventana y tiene que ir tal cual esta escrito.
            for k, v in data.items():
                k = _clave(k)
                # UN VALOR IGUAL AL DE FABRICA DE LINUX NO ES UNA ELECCION.
                #
                # Hasta el 12-sep-2026 el primer arranque copiaba la tabla
                # entera de _DEFAULTS a window_names.json. En la VM de
                # Windows eso dejo "archivos": "Dolphin" escrito en el
                # fichero del usuario, y como lo del usuario manda, tapaba
                # para siempre cualquier valor de Windows. Nadie lo habia
                # elegido: lo habia copiado el programa.
                #
                # Asi que un valor que coincide con el de fabrica de Linux,
                # en una clave que esta plataforma define distinto, se toma
                # por lo que es -- relleno -- y gana el de la plataforma. Lo
                # que el usuario haya cambiado de verdad sigue mandando.
                if k in base and _DEFAULTS.get(k) == v and base[k] != v:
                    continue
                combinado[k] = v
            return combinado
    except FileNotFoundError:
        # Se crea VACIO. Los nombres de fabrica viven en el codigo y se
        # mezclan en cada carga; copiarlos al fichero era lo que los dejaba
        # congelados en la version y la plataforma del primer arranque. En
        # el fichero va solo lo que el usuario anada.
        save({})
        return _por_defecto()
    except json.JSONDecodeError as exc:
        # RUIDOSO A PROPOSITO. Antes se volvia a _DEFAULTS en silencio, y
        # eso es lo peor de los dos mundos: el programa parece ir bien y
        # los nombres que el usuario haya anadido a mano NO EXISTEN, sin
        # que nada lo diga. Le paso a pipataki el 10-sep-2026 -- una coma de
        # mas al final del fichero -- y solo se vio al mirarlo por otra
        # cosa. Un fichero de configuracion que se ignora callando es un
        # fichero de configuracion roto.
        print(f"[window_names] {paths.WINDOW_NAMES_FILE} NO SE PUEDE LEER: "
              f"{exc.msg}, linea {exc.lineno} columna {exc.colno}. "
              f"Se usan los nombres de fabrica y SE IGNORA lo que hayas "
              f"anadido ahi. Arregla el fichero y reinicia.")
    return _por_defecto()


def save(data: dict):
    """Persiste window_names.json. Si falla (permisos, disco...), no
    interrumpe nada -- simplemente no se guardan los cambios."""
    try:
        with open(paths.WINDOW_NAMES_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
    except OSError:
        pass


def lookup(name_norm: str) -> str | None:
    """Devuelve la capitalización real conocida para `name_norm` (ya
    normalizado, ver command_router._normalize), o None si no hay
    ninguna entrada para ese nombre -- en ese caso, quien llame debe
    usar el nombre tal como se dijo, sin modificar."""
    return load().get(name_norm)


def add(name_norm: str, real_title: str):
    """Añade/actualiza una entrada y la guarda. No se usa automáticamente
    en ningún sitio todavía (el comando de voz actual es de solo
    lectura) -- pensado para editar window_names.json a mano, o para un
    futuro comando de voz tipo "recuerda ventana <nombre> como
    <titulo>" si se decide añadir esa enseñanza más adelante."""
    data = load()
    data[name_norm] = real_title
    save(data)
