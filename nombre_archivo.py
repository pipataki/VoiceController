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
Convierte lo que se DICE en el nombre de un archivo.

    "notas"                    ->  notas          (sin extension: decide Dolphin)
    "notas punto texto"        ->  notas.txt      (extension por su nombre)
    "notas punto te equis te"  ->  notas.txt      (extension deletreada)
    "copia punto tar punto ge zeta"  ->  copia.tar.gz

LA REGLA, QUE ES DE PIPATAKI
------------------------
**Sin "punto" no se toca nada.** El nombre va tal cual y quien decida si
lleva extension es el gestor de archivos, no nosotros. En cuanto aparece
un "punto", lo que sigue es extension.

Y la extension se puede decir de dos maneras, en este orden:

  1. POR SU NOMBRE -- "texto", "documento", "imagen". Es lo rapido, y
     cubre lo que uno crea a mano el 95% de las veces.
  2. DELETREADA -- "te equis te". Es el paracaidas: sirve para CUALQUIER
     extension, incluidas las que no tienen nombre razonable (.sh, .py,
     .ini) y las que se inventen mañana.

Si no es ni una cosa ni la otra, NO SE CREA NADA y se avisa. Crear
"notas punto vete tu a saber" seria peor que no crear.

EL ALFABETO NO SE ESCRIBE AQUI
------------------------------
Ya existe, y ademas esta probado contra el modelo grande de Vosk: es el
que usa el modo `deletrear` (formulas), en `math_notation_es.VARIABLES` y
`math_notation_en.VARIABLES`. Copiarlo aqui seria la segunda fuente que
alguien arregla en un sitio y no en el otro.

Lo unico que hay que anadir son los nombres de letra que se dicen en DOS
palabras -- "uve doble", "i griega", "double u" --, porque en aquella
tabla estan pegados y el reconocedor los devuelve sueltos.

ANADIR EXTENSIONES PROPIAS
--------------------------
En `config_local.py`, sin tocar este fichero ni crear otro de datos:

    EXTENSIONES_HABLADAS = {"maqueta": "kra", "partitura": "mscz"}
"""

import re
import unicodedata

# Extensiones que se pueden decir por su nombre. Corta a proposito: son las
# que se crean a mano. Todo lo demas se deletrea, que para eso esta.
_POR_NOMBRE_ES = {
    "texto": "txt",
    "documento": "odt",
    "hoja": "ods",
    "hoja de calculo": "ods",
    "presentacion": "odp",
    "imagen": "png",
    "foto": "jpg",
    "audio": "mp3",
    "musica": "mp3",
    "video": "mp4",
    "comprimido": "zip",
    "guion": "sh",
    "script": "sh",
    "pagina": "html",
    "pagina web": "html",
    "web": "html",
    "datos": "csv",
    "python": "py",
    "marcas": "md",
    "markdown": "md",
    "libro": "epub",
    "subtitulos": "srt",
    "base de datos": "db",
    "configuracion": "conf",
    "registro": "log",
    "hoja de calculo": "ods",
}

_POR_NOMBRE_EN = {
    "text": "txt",
    "document": "odt",
    "sheet": "ods",
    "spreadsheet": "ods",
    "presentation": "odp",
    "image": "png",
    "photo": "jpg",
    "picture": "jpg",
    "audio": "mp3",
    "music": "mp3",
    "video": "mp4",
    "archive": "zip",
    "script": "sh",
    "page": "html",
    "web page": "html",
    "web": "html",
    "data": "csv",
    "python": "py",
    "markdown": "md",
    "book": "epub",
    "subtitles": "srt",
    "database": "db",
    "config": "conf",
    "log": "log",
}

# Extensiones que el reconocedor puede devolver ENTERAS, de una pieza.
# Es lista blanca a proposito. La tentacion era aceptar cualquier palabra
# corta, y con eso "punto casa" creaba un archivo ".casa": justo la basura
# que este comando existe para no generar. Lo que no este aqui, se deletrea.
_DE_UNA_PIEZA = {
    "txt", "md", "csv", "json", "xml", "yaml", "ini", "conf", "log",
    "pdf", "odt", "ods", "odp", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "png", "jpg", "jpeg", "gif", "svg", "webp", "ico",
    "mp3", "mp4", "wav", "ogg", "flac", "avi", "mkv", "webm",
    "zip", "tar", "gz", "bz2", "xz", "rar", "iso",
    "html", "htm", "css", "js", "py", "sh", "c", "cpp", "java", "rs", "go",
    "sql", "db", "epub", "srt", "ttf", "otf",
}

# Nombres de letra que se dicen en dos palabras. En la tabla del modo
# formula estan pegados ("uvedoble"), porque alli se escriben; hablando
# salen sueltos.
_LETRAS_PARTIDAS_ES = [
    ("uve doble", "w"), ("ube doble", "w"), ("doble uve", "w"),
    ("doble ve", "w"), ("uve doble ve", "w"),
    ("i griega", "y"), ("y griega", "y"),
]
_LETRAS_PARTIDAS_EN = [
    ("double u", "w"), ("double you", "w"),
]

# La palabra que abre la extension.
_PUNTO_ES = ("punto",)
_PUNTO_EN = ("dot", "point")

# Lo que no puede ir en un nombre de archivo. La barra separa carpetas y el
# nulo corta la cadena: los dos crearian algo distinto de lo que se pidio.
_PROHIBIDO = re.compile(r"[/\x00]")


def _plano(t):
    """Sin tildes y en minusculas, para comparar."""
    t = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _tablas(idioma):
    """(extensiones por nombre, alfabeto, letras de dos palabras, 'punto')
    para el idioma pedido. El alfabeto se toma del modo formula."""
    if idioma == "en":
        import math_notation_en as mn
        nombres, partidas, punto = dict(_POR_NOMBRE_EN), _LETRAS_PARTIDAS_EN, _PUNTO_EN
    else:
        import math_notation_es as mn
        nombres, partidas, punto = dict(_POR_NOMBRE_ES), _LETRAS_PARTIDAS_ES, _PUNTO_ES

    # Su tabla mapea nombre-de-letra -> letra, a veces con espacio detras
    # ("t ") porque en una formula hace falta separar. Aqui estorba.
    letras = {_plano(k): v.strip() for k, v in mn.VARIABLES.items()
              if len(v.strip()) == 1 and v.strip().isalpha()}

    # Lo que el usuario haya anadido en config_local gana.
    try:
        import config
        propias = getattr(config, "EXTENSIONES_HABLADAS", None) or {}
        for k, v in propias.items():
            nombres[_plano(k)] = str(v).lstrip(".")
    except Exception:
        pass
    return nombres, letras, partidas, punto


def _extension(trozo, nombres, letras, partidas):
    """Un trozo dicho tras 'punto' -> la extension, o None si no se entiende."""
    dicho = _plano(trozo).strip()
    if not dicho:
        return None

    # 1. Por su nombre. Tambien los de dos palabras ("hoja de calculo").
    if dicho in nombres:
        return nombres[dicho]

    # 2. Deletreada. Primero se pegan las letras que se dicen en DOS
    #    palabras, para que "uve doble" no se lea como "u" + "be doble".
    #    Tiene que ir antes de contar palabras, o "uve doble" parece dos.
    for frase, letra in partidas:
        dicho = dicho.replace(frase, "\x01" + letra)
    trozos = dicho.split()

    # 3. Una sola palabra que no es letra: solo vale si es una extension
    #    conocida. La tentacion era aceptar cualquier palabra corta, y con
    #    eso "punto casa" creaba ".casa" -- justo la basura que este
    #    comando existe para no generar.
    if len(trozos) == 1 and not trozos[0].startswith("\x01") \
            and trozos[0] not in letras:
        return trozos[0] if trozos[0] in _DE_UNA_PIEZA else None

    salida = []
    for palabra in trozos:
        if palabra.startswith("\x01"):
            salida.append(palabra[1:])
        elif palabra in letras:
            salida.append(letras[palabra])
        else:
            return None
    return "".join(salida) or None


def _cola_extension(palabras, nombres, letras, partidas):
    """Cuantas palabras del FINAL son la extension, y cual es.

    Devuelve (cuantas, extension) o (0, None) si el final no parece una
    extension. Nunca se come la frase entera: tiene que quedar al menos una
    palabra de nombre delante.
    """
    tope = len(palabras) - 1          # siempre queda nombre
    if tope <= 0:
        return 0, None

    # Por su nombre, mirando primero las de dos palabras ("hoja de calculo")
    # para que no gane "calculo" a secas.
    for cuantas in (3, 2, 1):
        if cuantas > tope:
            continue
        trozo = " ".join(palabras[-cuantas:])
        if trozo in nombres:
            return cuantas, nombres[trozo]

    # Deletreada: la ristra MAS LARGA de nombres de letra que hay al final.
    # Se pegan antes las que se dicen en dos palabras ("uve doble").
    cola = " ".join(palabras)
    for frase, letra in partidas:
        cola = cola.replace(frase, "\x01" + letra)
    piezas = cola.split()
    tope = len(piezas) - 1
    n = 0
    while n < tope:
        p = piezas[-(n + 1)]
        if p.startswith("\x01") or p in letras:
            n += 1
        else:
            break
    if n:
        ext = "".join(p[1:] if p.startswith("\x01") else letras[p]
                      for p in piezas[-n:])
        # Cuantas palabras del original se han gastado: las pegadas valian
        # por dos.
        gastadas = sum(2 if p.startswith("\x01") else 1 for p in piezas[-n:])
        return gastadas, ext

    # Una sola palabra que ya es una extension entera ("pdf", "html").
    if palabras[-1] in _DE_UNA_PIEZA:
        return 1, palabras[-1]
    return 0, None


def nombre_de(dicho, idioma=None):
    """Lo dicho -> (nombre_de_archivo, None)  o  (None, lo_que_no_se_entendio).

    NO HACE FALTA DECIR "PUNTO". Decision de pipataki del 10-sep-2026, con el
    log delante: el reconocedor se come esa palabra -- "archivo punto texto"
    sale como "adjunto texto", con confianza 0,99 --, asi que exigirla era
    exigir algo que el motor no entrega. **El punto lo ponemos nosotros.**

    La extension se reconoce por el FINAL de la frase, de dos maneras:

        crear archivo apuntes texto          ->  apuntes.txt
        crear archivo apuntes te equis te    ->  apuntes.txt

    LA SEGUNDA CASI NUNCA LLEGA. Probado por pipataki el 10-sep-2026: el modelo
    grande del espanol recompone las letras en palabras -- "te equis te" sale
    como "tote existe" -- asi que el deletreo funciona cuando el motor
    acierta, que es pocas veces. Se deja porque no estorba y porque con otro
    modelo (o en ingles) puede ir mejor, pero **el camino bueno es el
    nombre**, y por eso la tabla de nombres se ha hecho larga. Lo que falte,
    se anade en config_local.py con EXTENSIONES_HABLADAS.

    Si el final no es ninguna de las dos, todo es el nombre y el archivo se
    queda sin extension -- que es justo lo que hay que hacer cuando no se
    entiende: no inventar.

    "punto" sigue valiendo si el motor llega a oirlo, porque no estorba.
    """
    if idioma is None:
        try:
            import config
            idioma = getattr(config, "LENGUA_MATERNA", "es")
        except Exception:
            idioma = "es"

    dicho = (dicho or "").strip()
    if not dicho:
        return None, ""

    nombres, letras, partidas, punto = _tablas(idioma)
    plano = _plano(dicho)

    # 1. Con "punto" dicho, manda el punto: parte por todos, y asi
    #    "copia punto tar punto ge zeta" sigue saliendo copia.tar.gz.
    trozos = re.split(r"\b(?:%s)\b" % "|".join(punto), plano)
    if len(trozos) > 1:
        base = _limpio(dicho[:len(trozos[0])])
        if not base:
            return None, dicho
        partes = [base]
        for trozo in trozos[1:]:
            ext = _extension(trozo, nombres, letras, partidas)
            if not ext:
                return None, trozo.strip() or dicho
            partes.append(ext)
        return ".".join(partes), None

    # 2. Sin "punto": se mira si el final es una extension.
    palabras = plano.split()
    cuantas, ext = _cola_extension(palabras, nombres, letras, partidas)
    if not cuantas:
        return _limpio(dicho), None

    # El nombre se corta del texto ORIGINAL, para conservar sus tildes.
    originales = dicho.split()
    base = _limpio(" ".join(originales[:len(originales) - cuantas]))
    if not base:
        return _limpio(dicho), None
    return f"{base}.{ext}", None


def _limpio(nombre):
    """Quita lo que no puede ir en un nombre de archivo."""
    nombre = _PROHIBIDO.sub("", (nombre or "").strip())
    # Un nombre que empieza por punto seria un archivo oculto sin querer.
    return nombre.lstrip(".").strip()
