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
Máquina de estados de VoiceController.

Estados:
  IDLE       -> reposo. Aquí funcionan los comandos INMEDIATOS de scope
                "idle"/"any" (ver commands.json -> control_words), los
                comandos del tablero DIRECTOS ("mover 45 3", "click derecho
                45 3"...) y los comandos de apps DIRECTOS ("terminal" ->
                abre Konsole). "dictar"/"type" pasa a DICTATING.
  DICTATING  -> todo lo que se reconoce se va añadiendo al buffer visible en
                la ventana, EXCEPTO si coincide con un comando de scope
                "dictating"/"any" (ver abajo).

Las palabras de control tienen un 'scope' en commands.json:
  - "idle"      -> solo se reconocen en reposo (ej. "cerrar" cierra la app)
  - "dictating" -> solo se reconocen mientras dictas texto (ej. "okey" para
                   confirmar, "clous"/"exit" para cerrar, "ereis"/"clin"/
                   "reset" para borrar el texto, "idel"/"lisen" para volver
                   a reposo SIN enviar el texto). Se usan palabras poco
                   probables en una frase normal en español, precisamente
                   para poder dictar con libertad sin disparar un comando
                   por accidente (p.ej. "cerrar" o "borrar" sí podrían
                   aparecer en un texto normal, por eso esos NO valen aquí).
  - "any"       -> siempre (ej. "rejilla").

Sobre "reset" (scope dictating): borra el texto pero SE QUEDA en modo
dictado (no vuelve a IDLE), para poder corregir y seguir dictando sin tener
que decir "dictar" otra vez. "idel"/"lisen" (y el botón "Idle" del GUI) sí
vuelven a IDLE, descartando lo que hubiera en el buffer.

Sobre "corrige"/"correct"/"fix" (scope dictating, action correct_last_word):
como "reset" pero borra SOLO la última palabra del Pre-Texto (ver
_correct_last_word), para arreglar un fallo puntual de reconocimiento sin
tener que volver a dictar todo el fragmento. También disponible como botón
"Corregir" del GUI y como entrada del menú de bandeja.

Sobre "corrige/corregir/correct/fix <numero> <modificador>" (ver
_try_parse_correct_word / _correct_word): variante del comando anterior
que, en vez de disparar sola, va seguida de un número (posición 1-based de
la palabra dentro del Pre-Texto, contando por espacios) y un modificador
-- "mayuscula"/"capital" (pone en mayúscula solo la inicial, ej. "sevilla"
-> "Sevilla"), "minuscula" (inverso), "siglas"/"acronimo" (mayúsculas
completas, para acrónimos como "renfe" -> "RENFE"), "cifras"/"numero"
(convierte a su cifra si la palabra es un número español, ej. "once" ->
"11"), "letras"/"palabra" (deja la palabra tal cual se dictó). Corrige esa
palabra sola, sin tocar el resto del Pre-Texto ni salir de dictado/
fórmula. Se comprueba ANTES que el disparador solo, así que "corregir 4
mayuscula" no se confunde con "corregir" a secas.

Esta corrección puntual además se APRENDE (ver corrections.py) para
aplicarse la próxima vez que se dicte la misma palabra:
  - Por defecto ("corregir 4 mayuscula"): aprendizaje ESTRICTO -- la
    próxima vez que aparezca esa palabra en el texto dictado, se le aplica
    el mismo modificador automáticamente y sin avisar (pensado para
    palabras sin otro significado razonable, ej. "sevilla" -> "Sevilla").
  - Añadiendo "ambiguo" al final ("corregir 1 siglas ambiguo"): la
    palabra puede resolverse de VARIAS formas según el contexto (ej.
    "once" -> "ONCE" siglas, "11" cifras, o "once" tal cual letras).
    Cada corrección ambigua que se enseñe para la misma palabra se añade
    como una opción más (no sustituye a las anteriores). Nunca se
    auto-aplica sola; la próxima vez que la palabra aparezca se PREGUNTA
    en el campo Sugerencias, enumerando todas las opciones aprendidas
    (ej. '¿"once" como "siglas", "cifras" o "letras"?'), y se resuelve
    diciendo directamente el nombre de la opción elegida (ver
    _try_resolve_ambiguous_choice) -- se descarta sola en cuanto llega
    texto nuevo si no se contesta.
El diccionario aprendido es GLOBAL, no depende del idioma ni de la
sesión (ver corrections.json).

Además, por defecto (sin enseñar nada), cualquier cantidad dictada como
palabras se normaliza sola a cifra (ej. "treinta y cinco" -> "35") -- ver
_apply_default_number_normalization, que usa numbers_es. Esto NO se
aplica a una palabra que ya tenga una corrección aprendida (estricta o
con opciones ambiguas): en ese caso manda lo aprendido/lo que se
pregunte, no la conversión automática.

Comandos del tablero DIRECTOS (formato "<accion> <casilla 1-100>", un solo
número, sin sub-celda) y de apps DIRECTOS (frase exacta -> lanza una
aplicación, ver 'app_commands' en commands.json) se ejecutan en cuanto se
reconocen en IDLE, sin necesitar "dictar" ni confirmación.

Tablero de 100 casillas (Sección 1 del manual, ver board.py): en IDLE,
decir un número SOLO (1-100) selecciona esa casilla -- captura tablero.png,
recorta casilla.png, reposiciona la GUI al lado simétrico. A partir de ahí:
  - una palabra de dirección (ver 'board_directions' en commands.json:
    oeste/este/norte/sur, con alias izquierda/derecha/arriba/abajo) mueve
    el marcador de ajuste fino dentro de la casilla, sin poder salir de
    ella;
  - una palabra de acción SOLA (ver 'vc_commands': click, doble
    click, click derecho, scroll ...) ejecuta esa acción en la posición ya
    ajustada, y vuelve a la vista general del tablero.
Esto es aparte del formato directo de un solo tiro de arriba
("<accion> <casilla>"), que sigue funcionando para quien prefiera saltarse
el ajuste fino e ir directo al centro de la casilla.

Zonas clicables autodetectadas (ver board.detect_zones / zones.py): en
cuanto se selecciona una casilla, además de mostrar el recorte ampliado se
analiza automáticamente en busca de elementos de alto contraste (botones,
iconos, texto...) y se numeran 1..N sobre la imagen. Mientras esas zonas
sigan detectadas y la casilla siga seleccionada, "<accion> <numero>" (ej.
"click 1", "doble click 2", "click derecho 3", "mover 1") actúa
directamente sobre el centro de esa zona -- sin necesidad de ajustar a
mano con las direcciones/compás -- y termina deseleccionando la casilla
igual que cualquier otra acción de tablero. Este número se interpreta
como índice de zona, NO como otra casilla, mientras haya una casilla ya
seleccionada (ver _try_parse_board_zone_action).

Dictado libre ("dictar" -> texto -> "okey"/"oquei"/"okei"): para escribir
texto normal como si fuera teclado, o -por compatibilidad- para mandar un
comando del tablero con el prefijo "posicion" en vez del formato
directo de arriba (ver _try_parse_vc). Al confirmar:
  1. Si empieza por la palabra disparadora -> comando del tablero
     (formato "posicion <casilla> <acción>").
  2. Si no, si el texto completo coincide con un alias de
     'terminal_commands' -> se ejecuta como comando de shell (bloqueante).
  3. Si no, se sube al campo "Texto" (ver Sección 2 del manual), pendiente
     de "copiar texto"/"pegar texto".

Sobre el detector de "final" de Vosk: si hablas sin pausa clara entre el
dictado y la palabra de control, Vosk puede juntarlo todo en un único
resultado final en vez de darte la palabra de control aislada. Para no
depender de una pausa perfecta, además de comprobar coincidencia EXACTA con
toda la frase, comprobamos si la ÚLTIMA palabra del resultado es una
palabra de control válida en el estado actual: si lo es, se trata como tal
(para "confirm" el resto de la frase se añade al buffer antes de confirmar;
para el resto, el resto se descarta).

Sobre "formato humano" del texto dictado (prosody.py): IDLE es el estado de
escucha ("silencio"): ahí solo se admiten acciones/comandos, nunca texto, y
voice_recognizer.py NO analiza entonación (se lo decimos vía
set_dictating_callback, para no gastar CPU en algo que no se va a escribir).
En cuanto se reconoce "dictar" (en cualquiera de los dos idiomas) se pasa a
DICTATING y, SOLO a partir de ahí, cada frase final se analiza
prosódicamente y se le da forma (mayúscula inicial + puntuación según si
sonó a afirmación/pregunta/exclamación/sugerencia). Una pausa seguida de
una palabra "suelta" que resulta ser un comando (confirm/reset/idle) y otra
pausa es justo lo que YA distingue Vosk como un resultado final aparte: por
eso ese resultado nunca pasa por el "humanizado" de texto, se trata como
comando.
"""

import math
import unicodedata
from pathlib import Path
import time
import re

import actions
import numbers_es
import numbers_en
import textos

# EL PARSER DE NUMEROS DE LA LENGUA MATERNA
# -----------------------------------------
# Las casillas, las zonas, "corrige <nº>" y "mover <casilla>" pasan todas
# por aquí. Hasta el 5-sep-2026 esto era numbers_es a secas, y por eso con
# el inglés de principal la interfaz numérica entera quedaba muerta:
# "thirty two" se reconocía perfectamente y acto seguido salía
# "no entendido", porque no había quien tradujera el número.
#
# Se elige por la LENGUA MATERNA y no por el idioma de la frase oída: quien
# dicta y quien cuenta es la materna, y la otra lengua solo caza comandos
# (ver config.LENGUA_MATERNA).
#
# Es una función y no una constante a propósito: config.LENGUA_MATERNA
# puede cambiar en caliente, y una constante calculada al importar se
# quedaría con el valor del arranque -- justo el fallo que ya nos costó una
# tarde con los umbrales de config_local.
_PARSERS_DE_NUMEROS = {"es": numbers_es, "en": numbers_en}


def _numeros():
    """El módulo de números que toca según la lengua materna."""
    return _PARSERS_DE_NUMEROS.get(
        getattr(config, "LENGUA_MATERNA", "es"), numbers_es)
import threading

import config
import habilidades
import tts
import speaker_id

_HIM = speaker_id.SpeakerVerifier.HIM
_OTHER = speaker_id.SpeakerVerifier.OTHER
_UNKNOWN = speaker_id.SpeakerVerifier.UNKNOWN
import board
import corrections
import carpetas
import nombre_archivo
import window_names

import math_notation_es
import math_notation_en

# El vocabulario matemático de la lengua materna. Mismo criterio que
# _numeros(): función y no constante, porque config.LENGUA_MATERNA puede
# cambiar en caliente.
_MATES = {"es": math_notation_es, "en": math_notation_en}


def _mates():
    """El módulo de notación matemática que toca según la materna."""
    return _MATES.get(getattr(config, "LENGUA_MATERNA", "es"),
                      math_notation_es)

DEBUG = True  # imprime en terminal cada resultado final reconocido y por qué se interpretó así

# Nota: las palabras de control durante el dictado (confirmar/borrar/salir/
# idle) viven SOLO en commands.json (control_words, scope "dictating"), que
# ya mezcla sinónimos en español e inglés a propósito. Antes existía aquí un
# segundo mapa hardcodeado (DICTATING_COMMANDS) que se usaba en su lugar y
# no coincidía con los alias reales del JSON (ej. "borrar" vs "borra" de
# commands.json) — por eso esos comandos se escribían como texto en vez de
# ejecutarse. Se quitó para que solo haya una fuente de verdad.


def _guardar_perfil_con_copia(destino, contenido: str):
    """Guarda un perfil de voz Y deja una copia fechada en .backups/.

    Un perfil cuesta varios minutos de grabación guiada, y es lo único
    del proyecto que NO se puede regenerar solo: hay que volver a hablarle
    al ordenador. Ya se perdió uno por un borrado accidental, así que
    cada vez que se escribe queda una copia con fecha. Ocupan unos pocos
    kilobytes.
    """
    from pathlib import Path as _Path
    destino = _Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8")
    try:
        copias = _Path(config.PROJECT_ROOT) / ".backups" / "profiles"
        copias.mkdir(parents=True, exist_ok=True)
        marca = time.strftime("%Y%m%d_%H%M%S")
        (copias / f"{destino.stem}_{marca}.json").write_text(contenido, encoding="utf-8")
    except Exception as exc:
        print(f"[command_router] no se pudo guardar copia del perfil: {exc!r}")


def _normalize(text: str) -> str:
    text = text.strip().lower()
    # quita acentos para comparar "sí" == "si", "veintidós" == "veintidos", etc.
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return text


# Modificadores admitidos por "corregir <numero> <modificador>" (ver
# CommandRouter._try_parse_correct_word / _correct_word): cada alias, ya
# normalizado (sin acentos, ver _normalize), mapea al nombre canónico del
# modificador que entiende _apply_word_modifier.
_WORD_MODIFIERS = {
    "mayuscula": "mayuscula",     # "sevilla" -> "Sevilla" (solo inicial)
    "capital": "mayuscula",
    "propio": "mayuscula",
    "minuscula": "minuscula",     # inverso de mayuscula (por simetria)
    "siglas": "siglas",           # "renfe" -> "RENFE" (palabra entera)
    "acronimo": "siglas",
    "cifras": "cifras",           # "once" -> "11" (ver numbers_es)
    "numero": "cifras",
    "digitos": "cifras",
    "letras": "letras",           # deja la palabra tal como se dictó
    "palabra": "letras",
}

# Núcleo alfanumérico de una palabra (con posible puntuación pegada delante/
# detrás, ej. "sevilla," o "¿sevilla?"), para poder aplicarle un modificador
# de mayúsculas/minúsculas sin tocar esa puntuación. \w en Python 3 ya
# incluye letras acentuadas/ñ, así que no hace falta una clase aparte.
_WORD_CORE_RE = re.compile(r"^(\W*)(\w+)(\W*)$", re.UNICODE)


def _apply_word_modifier(word: str, modifier: str) -> str:
    """Aplica `modifier` (ver _WORD_MODIFIERS) solo al núcleo alfanumérico
    de `word`, respetando cualquier puntuación pegada delante/detrás. Si
    `word` no tiene núcleo alfanumérico reconocible, se devuelve tal cual."""
    match = _WORD_CORE_RE.match(word)
    if not match:
        return word
    prefix, core, suffix = match.groups()
    if modifier == "mayuscula":
        core = core[0].upper() + core[1:]
    elif modifier == "minuscula":
        core = core.lower()
    elif modifier == "siglas":
        core = core.upper()
    elif modifier == "cifras":
        # convierte la palabra (si es un numero español reconocible, ej.
        # "once"/"treinta") a su cifra -- ver numbers_es.parse_number_prefix.
        # Si no se puede reconocer como número de una sola palabra, se deja
        # el núcleo tal cual (nunca revienta).
        value, consumed = _numeros().parse_number_prefix([_normalize(core)], 0)
        if value is not None and consumed == 1:
            core = str(value)
    elif modifier == "letras":
        pass  # sin cambios: mantiene la palabra tal como se dictó
    else:
        return word
    return prefix + core + suffix


def _join_opciones(options) -> str:
    """Enumera las opciones en la lengua materna: ["siglas","cifras"] ->
    '"siglas" o "cifras"' / '"initials" or "digits"'.

    Se llamaba _join_options_es y era española por dentro: la "o" estaba
    escrita en el código. Ahora la conjunción sale de textos.
    """
    opciones = [f'"{o}"' for o in options]
    if len(opciones) <= 1:
        return opciones[0] if opciones else ""
    return (", ".join(opciones[:-1]) + " "
            + textos.t("o_enumeracion") + " " + opciones[-1])


def _join_options_es(options) -> str:
    """Formatea una lista de opciones (nombres de modificador) como
    enumeración hablada en español: ["siglas","cifras","letras"] ->
    '"siglas", "cifras" o "letras"'. Con una sola opción, solo la cita."""
    quoted = [f'"{o}"' for o in options]
    if len(quoted) == 1:
        return quoted[0]
    return ", ".join(quoted[:-1]) + " o " + quoted[-1]


# Puntuación final aplicada al "formato humano" del texto dictado, según el
# sentence_type que estima prosody.py (entonación + texto). Solo se usa
# mientras se dicta (ver on_final): en estado de escucha (silencio) lo que
# se reconoce nunca es texto, así que esto no aplica ahí.
_SENTENCE_PUNCTUATION = {
    "statement": ".",
    "question": "?",
    "exclamation": "!",
    "suggestion": "...",
}


def _humanize_chunk(text: str, sentence_type: str) -> str:
    """Da forma de frase "humana" a un fragmento dictado: primera letra en
    mayúscula + puntuación final según la entonación estimada. Si el
    fragmento ya termina en puntuación (p.ej. Vosk no suele añadir, pero por
    si acaso), se respeta tal cual."""
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]



    # LOS SIGNOS DE APERTURA SON ESPAÑOLES, y solo se ponen en español.
    # En inglés, "¿What time is it?" no es una peculiaridad simpática: es
    # una falta de ortografía en cada frase dictada. Ver config.LENGUA_MATERNA.
    if textos.idioma() == "es":
        if sentence_type == "question":
            text = f"¿{text}"
        elif sentence_type == "exclamation":
            text = f"¡{text}"
    elif sentence_type == "statement":
        text = f"{text}"
    elif sentence_type == "sugestion":
        text = f"{text}"

    if text[-1] not in ".!?…":
        text += _SENTENCE_PUNCTUATION.get(sentence_type, ".")
    return text

def _mathematize_chunk(text: str, sentence_type: str = "statement") -> str:
    """Da forma de fórmula/pseudocódigo a un fragmento dictado en modo
    'formuling': lo traduce a notación simbólica vía math_notation_es
    (letras -> variables, "mas"/"por"/"entre"... -> +/*//, "igual a" -> =,
    números dictados -> dígitos, etc.).

    A diferencia de _humanize_chunk, aquí NO se aplica mayúscula inicial
    ni puntuación de cierre según sentence_type: en modo fórmula la
    entonación de la frase no tiene ningún significado (no estamos
    haciendo una pregunta ni una exclamación, estamos dictando una
    expresión), así que sentence_type se ignora a propósito. Se conserva
    en la firma solo para que esta función sea intercambiable con
    _humanize_chunk en el punto de llamada.

    Dentro del modo fórmula, la traducción es SIEMPRE literal (se llama a
    to_symbolic directamente, sin pasar por looks_like_math): el usuario
    ya eligió explícitamente el modo diciendo "formula"/"math", así que no
    hace falta la heurística de detección que usa math_notation_es cuando
    se analiza texto fuera de este modo."""
    text = text.strip()
    if not text:
        return text
    normalized = _normalize(text)
    if not normalized:
        return text
    return _mates().to_symbolic(normalized)





class CommandRouter:
    def __init__(self, commands_config: dict, gui):
        self.cfg = commands_config

        # Detección de intrusos (ver config.INTRUDER_* y
        # _register_intruder_strike). `_intruder_locked_until` es a la vez
        # el interruptor y el reloj: 0.0 = desbloqueado, math.inf =
        # bloqueado sin caducidad, cualquier otro valor = instante en que
        # caduca. Con un solo campo no puede quedarse "bloqueado" con el
        # reloj caducado ni al revés.
        self._intruder_strikes = 0
        self._intruder_locked_until = 0.0

        # True mientras la ultima voz oida no se haya reconocido como suya
        # (ver _preguntar_si_eres_tu). No bloquea nada: solo sirve para que
        # el GUI pueda ensenar en que situacion esta sin decir ni una
        # palabra, y se apaga en cuanto se le vuelve a reconocer.
        self._dudando = False

        # cuántas veces no se ha entendido algo dicho por él -- se cuenta
        # siempre, aunque la voz se calle (ver _maybe_say_not_understood)
        self._not_understood_count = 0

        # último comando reconocido y cuándo, para no ejecutarlo dos veces
        # cuando los dos motores transcriben la misma voz (ver
        # _es_comando_repetido y config.DUPLICATE_COMMAND_WINDOW_S)
        self._ultimo_comando = None
        self._ultimo_comando_ts = 0.0
        self._ultimo_comando_lang = None

        # Santo y seña (ver config.VOICE_LOGIN_*). Arranca SIN identificar:
        # main.py llama a start_voice_login() en cuanto está todo montado.
        # Identificación SEPARADA por micrófono. El del móvil y el del PC
        # llevan su propio estado y su propio contador de intentos, sin
        # sincronizarse: así se puede entrar desde el móvil aunque el PC
        # esté sin identificar, y un fallo en uno no bloquea el otro.
        # Compartirlos no tenía sentido: son dos sitios físicos distintos,
        # con condiciones de audio distintas.
        inicial = not getattr(config, "VOICE_LOGIN_ENABLED", False)
        self._sesiones = {
            "device": {"ok": inicial, "ts": 0.0, "fallos": 0},
            "network": {"ok": inicial, "ts": 0.0, "fallos": 0},
        }
        self._source = "device"   # de dónde vino la última frase

        # Enrolado del micrófono del móvil (ver start_mobile_enrollment)
        self._enroll_state = None
        self._enrollment_callback = None
        self._reload_profiles_callback = None

        # Contador que le pide al móvil recargarse entero. Sube cuando
        # cambia algo que su sesión de grabación no puede asumir en
        # caliente -- ver _finish_mobile_enrollment.
        self._client_reload_id = 0
        self._awaiting_login_callback = None

        # Standby (ver config.STANDBY_AFTER_IDLE_S): en espera no se obedece
        # nada. Se sale diciendo el santo y seña.
        self._standby = False
        self._last_heard_ts = time.monotonic()
        self.gui = gui
        self.state = "IDLE"
        self.primary_buffer = ""     # Pre-Texto: lo que se está dictando ahora mismo
        self.secondary_buffer = ""
        # palabra tal como se dictó ORIGINALMENTE, una entrada por cada
        # palabra de primary_buffer (mismo índice 1-based que usan
        # _correct_word/_try_parse_correct_word) -- solo difiere de la
        # palabra ya mostrada cuando _apply_default_number_normalization
        # convirtió un número dictado a cifra automáticamente (ver ese
        # método). Se usa para poder aprender/corregir sobre la palabra
        # que de verdad se dijo (ej. "once") aunque el Pre-Texto ya
        # muestre la cifra (ej. "11"). Debe mantenerse SIEMPRE en el
        # mismo tamaño que primary_buffer.split(" ") -- se resetea/ajusta
        # en cualquier sitio que toque primary_buffer.
        self._word_origins = []
        self.confirmed_text = ""     # Texto: acumulado ya confirmado ("entra"/"okey"), campo 1 del GUI
        self._active_suggestion = None  # dict {"type": ..., "text": ...} o None -- campo 3 del GUI
        self.formuling = False  # True cuando estamos en modo 'deletrear' (letra a letra)
        self._ignore_text_until = 0.0
        # La lengua materna (config.LENGUA_MATERNA) es la principal: la que
        # dicta, la que cuenta los números y la que estructura. La otra
        # solo caza comandos.
        self.primary_language = getattr(config, "LENGUA_MATERNA", "es")
        self.secondary_language = "en" if self.primary_language == "es" else "es"
        self.dictation_language = self.primary_language
        # Tablero de 100 casillas (ver board.py): None = ninguna casilla
        # seleccionada (vista general); si no, número 1-100 ya seleccionado
        # y offset_x/offset_y (píxeles) del ajuste fino dentro de ella.
        self.board_selected_cell = None
        self.board_offset_x = 0
        self.board_offset_y = 0
        # zonas clicables autodetectadas (board.detect_zones) para la
        # casilla seleccionada -- lista de offsets físicos (dx, dy),
        # índice 0 = zona "1"; se rellena de forma asíncrona (ver
        # _on_board_zones_detected) tras _select_board_cell(), y permite
        # reconocer "<accion> <numero>" (ej. "click 1") mientras la
        # casilla siga seleccionada
        self.board_zones = []
        # --- Fase 2 del rediseño de accesibilidad (puntero verde/rojo,
        # ver PDF NuevoGUI): modo zoom_out interactivo -- None = no
        # activo; si no, casilla cuyo CUARTO de escritorio se está
        # mostrando, con offset_x/offset_y (píxeles) del puntero verde
        # respecto al centro de esa región. Independiente de
        # board_selected_cell/board_offset_x/y (modo "cell" -- casilla
        # ampliada), son mutuamente excluyentes pero NO se ha fusionado
        # el código para no arriesgar el modo "cell" ya probado.
        self._zoom_out_active_cell = None
        self._zoom_out_offset_x = 0
        self._zoom_out_offset_y = 0
        # Vista "foco": la ventana en la que se estaba trabajando. No lleva
        # casilla asociada -- la region es la de la ventana, no la de la
        # rejilla (ver board.capture_foco).
        self._foco_activo = False
        # True mientras se esta recapturando tras una accion de foco:
        # sirve para avisar si llegan ordenes mas rapido de lo que se
        # puede refrescar la imagen.
        self._foco_recapturando = False
        self._ultimo_aviso_ritmo = 0.0
        # Donde tiene el movil su punto ROJO. Lo manda el propio movil
        # (POST /board/pointer): el PC no puede saberlo de otra forma.
        self._rojo_fx = None
        self._rojo_fy = None
        # Origen de una seleccion a medias: (x, y) en pantalla, o None.
        # Solo se RECUERDA -- no se pulsa nada hasta la segunda orden.
        self._seleccion_origen = None
        # El ultimo desplazamiento, listo para "otra"/"again": una funcion sin
        # argumentos que vuelve a hacer EXACTAMENTE lo mismo y en el mismo
        # sitio. Hace falta guardar el sitio y no la frase: tras un "scroll
        # abajo" en una casilla la casilla se suelta, y repetir la frase ya no
        # la encontraria. None si todavia no ha habido ninguno.
        self._ultimo_desplazamiento = None

        self._foco_offset_x = 0
        self._foco_offset_y = 0
        self._set_language_mode = lambda mode: None  # se conecta desde main.py con set_language_mode_callback()
        self._set_dictating = lambda flag: None  # se conecta desde main.py con set_dictating_callback()
        self._switch_to_local_mic = lambda: None  # se conecta desde main.py con set_switch_to_local_mic_callback()
        # ensure UI reflects initial formuling state
        try:
            self.gui.update_formuling_indicator(False)
        except Exception:
            pass
        self._sync_language_combo_ui()

        self._idle_control_map, self._dictating_control_map, self._any_control_map = (
            self._build_scoped_alias_maps(self.cfg["control_words"])
        )
        # Las frases de control que son DESPLAZAMIENTOS de teclado ("desplaza
        # abajo", "desplaza abajo una"...): las que "otra" sabe repetir. Salen
        # de commands.json -- los comandos cuyo nombre empieza por "scroll_"
        # --, asi que un alias nuevo entra solo. "arriba" a secas no esta: es
        # pulsar una flecha, no desplazar.
        self._alias_desplazamiento_teclado = {
            _normalize(alias)
            for nombre, entrada in self.cfg["control_words"].items()
            if nombre.startswith("scroll_") and isinstance(entrada, dict)
            for alias in entrada.get("aliases", [])
        }
        self._terminal_alias_map = self._build_alias_map(self.cfg["terminal_commands"], key_field="cmd")
        self._app_command_alias_map = self._build_alias_map(self.cfg.get("app_commands", {}), key_field="exec")
        # EN WINDOWS, SU PROPIO PROGRAMA. "texto" lanzaba "kate" y "explorar"
        # lanzaba "dolphin" tambien alli, donde no existen (pipataki, 12-sep-2026).
        # exec_windows dice cual toca; sin el campo se usa exec, que para
        # firefox o inkscape es el mismo nombre en las dos.
        import sys as _sys
        if _sys.platform.startswith("win"):
            for _nombre, _entrada in self.cfg.get("app_commands", {}).items():
                if _nombre.startswith("_") or not isinstance(_entrada, dict):
                    continue
                _exe = _entrada.get("exec_windows")
                if _exe:
                    for _alias in _entrada.get("aliases", [_nombre]):
                        self._app_command_alias_map[_normalize(_alias)] = _exe

        # acciones del tablero: coincidencia EXACTA sobre lo que queda tras
        # quitar "<disparador> <casilla>" del principio del texto (formato
        # LEGACY "posicion ... <accion>", vía dictado+confirmación) -- y
        # TAMBIÉN se reutiliza para reconocer una palabra de acción SOLA
        # (sin casilla) cuando ya hay una casilla seleccionada en el tablero.
        self._vc_action_alias_map = self._build_alias_map(self.cfg["vc_commands"], key_field="handler")
        # lo mismo pero como lista de tokens, para el formato DIRECTO
        # "<accion> <casilla>" (accion puede ser 1 o 2 palabras, ej. "click"
        # vs "click derecho": se ordena por longitud descendente para probar
        # primero el alias más largo/específico)
        self._vc_action_prefix_list = self._build_action_prefix_list(self.cfg["vc_commands"])
        # palabra(s) que marcan el inicio de un comando del tablero en el
        # formato LEGACY "posicion <casilla> <accion>"
        self._vc_trigger_aliases = {
            _normalize(a) for a in self.cfg.get("vc_trigger", {}).get("aliases", ["vc"])
        }
        # direcciones de ajuste fino del tablero (oeste/este/norte/sur y
        # alias izquierda/derecha/arriba/abajo) -> vector (dx, dy)
        self._board_direction_alias_map = {}
        for _name, _entry in self.cfg.get("board_directions", {}).items():
            if _name.startswith("_"):
                continue
            vector = tuple(_entry["vector"])
            for alias in _entry.get("aliases", [_name]):
                self._board_direction_alias_map[_normalize(alias)] = vector

        # disparador(es) de "corregir <numero> <modificador>" (ver
        # _try_parse_correct_word): reutiliza los mismos alias que
        # "corrige/corregir/correct/fix" solo (correct_last_word), tal
        # cual estén definidos en commands.json -- si el usuario los
        # cambia ahí, este formato los sigue automáticamente.
        self._correct_word_trigger_aliases = {
            _normalize(a)
            for a in self.cfg.get("control_words", {}).get("corregir_palabra", {}).get(
                "aliases", ["corrige", "corregir", "correct", "fix"]
            )
        }

        # correcciones de palabra aprendidas ("corregir <numero>
        # <modificador> [ambiguo]"), ver corrections.py -- se cargan una
        # vez al arrancar y se guardan en disco cada vez que se aprende
        # una nueva (ver _correct_word)
        self._corrections = corrections.load()

    def set_language_mode_callback(self, fn):
        """fn(mode: str) -> conecta con DualLanguageRecognizer.set_language_mode."""
        self._set_language_mode = fn

    def set_dictating_callback(self, fn):
        """fn(is_dictating: bool) -> conecta con DualLanguageRecognizer.set_dictating.
        Así el reconocedor solo analiza prosodia (formato humano del texto)
        mientras estamos realmente dictando, nunca en estado de escucha."""
        self._set_dictating = fn

    def set_switch_to_local_mic_callback(self, fn):
        """fn() -> sin argumentos, conecta con
        RecognizerWorker.switch_to_device_requested.emit. Comando de voz
        "micrófono local"/"mic local" (ver control_words en commands.json,
        acción "switch_to_local_mic") -- vuelve a escuchar el micrófono
        físico del escritorio tras haber estado usando el del móvil (ver
        webapp/app.py set_network_switch_bridge() para el otro sentido,
        que se activa solo, sin comando de voz, en cuanto llega el primer
        audio del móvil)."""
        self._switch_to_local_mic = fn

    def _set_state(self, new_state: str):
        self.state = new_state
        # Un origen de seleccion no sobrevive a un cambio de estado: para
        # cuando se dicte y se vuelva, nadie se acuerda de que estaba
        # puesto, y el siguiente "fin de la seleccion" seleccionaria desde
        # donde no toca.
        if getattr(self, "_seleccion_origen", None):
            self._seleccion_cancelar(callado=True)
        # leaving dictation disables formuling mode
        if new_state == "IDLE":
            self.formuling = False
            try:
                self.gui.update_formuling_indicator(False)
            except Exception:
                pass
        self.gui.update_state_indicator(new_state)
        self._set_language_mode(self.primary_language)
        self._set_dictating(new_state == "DICTATING")
        if new_state == "DICTATING":
            # Se apunta AHORA cual es la ventana del usuario, que es cuando
            # esta mirandola. Al pegar, mas tarde, ya puede haber otras
            # ventanas o el propio GUI por medio y la activa no valdria.
            # Ver actions.recordar_ventana_destino().
            try:
                actions.recordar_ventana_destino()
            except Exception as exc:
                if DEBUG:
                    print(f"[command_router] no se pudo recordar la ventana "
                          f"destino: {exc!r}")

    def set_dictation_language(self, language: str):
        """Cambia el idioma principal (el que dicta).

        AVISA ANTES, y hace falta: desde el 5-sep-2026 el secundario usa el
        modelo pequeño, así que cambiar de principal obliga a cargar el
        modelo grande del idioma que entra. Son unos 7 segundos EN LOS QUE
        NO SE RECONOCE NADA -- ni siquiera para cancelar.

        Sin aviso, eso se vive como que el programa se ha colgado, y quien
        usa esto no tiene forma de comprobar que sigue vivo. Con el aviso
        es una espera anunciada.

        El ahorro que compra esa espera son casi 6,7 GB de RAM y la mitad
        de la CPU en todo momento (ver config.py, sección de modelos).
        """
        if language not in ("es", "en"):
            return
        cambia_de_verdad = language != self.primary_language
        self.primary_language = language
        # La materna manda tambien sobre los números: si no se moviera
        # aquí, cambiar de idioma dejaría las casillas hablando el idioma
        # anterior. Ver _numeros().
        config.LENGUA_MATERNA = language
        config.OTRA_LENGUA = "en" if language == "es" else "es"
        self.secondary_language = "en" if language == "es" else "es"
        self.dictation_language = language
        self._sync_language_combo_ui()
        if cambia_de_verdad:
            # El aviso va en el idioma AL QUE SE VA, no en el que se
            # deja: es lo primero que se oye del idioma nuevo, y sirve de
            # confirmación de que el cambio ha ocurrido. config.LENGUA_MATERNA
            # ya se movió arriba, así que textos.t() da el idioma correcto.
            aviso = textos.t("cambiando_idioma", idioma=textos.t(f"idioma_{language}"))
            try:
                self.gui.update_suggestion(aviso, True)
            except Exception:
                pass
            try:
                tts.get_speaker().say(aviso, tts.HELP)
            except Exception as exc:
                if DEBUG:
                    print(f"[command_router] no se pudo avisar del cambio de "
                          f"idioma: {exc!r}")
        self._set_language_mode(self.primary_language)

    def _arm_text_suppression(self, seconds: float = 0.5):
        self._ignore_text_until = max(self._ignore_text_until, time.monotonic() + seconds)

    # ---------- campo "Texto" (confirmado): copiar / pegar / seleccionar / vaciar ----------

    def _copy_confirmed(self):
        if not self.confirmed_text:
            return
        actions.copy_to_clipboard(self.confirmed_text)
        if DEBUG:
            print("[command_router] Texto copiado al portapapeles")

    def _paste_confirmed(self, clear_display: bool = True):
        """Escribe el Texto ya confirmado (el nivel definitivo, tras
        "entra"/confirm) en la ventana externa que tenga el foco, vía
        actions.type_text() (ydotool).

        ANTES de escribir, manda el propio GUI detrás/oculto un momento
        (self.gui.apartar_ventana(), el mismo mecanismo ya
        usado para las acciones de vc) y lo trae de vuelta al
        frente justo después (self.gui.subir_ventana()) --
        aunque el GUI ya no tiene ningún flag de "siempre encima", si se
        había interactuado con sus propios controles (tablero,
        compás...) puede quedarse "de por medio" y robar el foco a la
        ventana externa donde se quiere escribir. Ocultándolo un
        instante, esa ventana externa -- CUALQUIERA que sea, no hace
        falta saber cuál -- recupera el foco de forma natural. Esto
        sustituye al intento anterior con `kstart`/kde-cli-tools (que ya
        no sirve para esto en KDE Frameworks 6: perdió las opciones
        --window/--activate en la reescritura para KF6) y no necesita
        ninguna herramienta externa ni saber el título de la ventana.

        Si además config.PASTE_TARGET_WINDOW_REGEX está configurado, se
        intenta TAMBIÉN activar esa ventana en concreto con `kdotool`
        (actions.activate_target_window(), ver docstring ahí) como paso
        extra opcional -- no hace falta para el caso normal.

        Si config.AUTO_ENTER_AFTER_PASTE está activo (por defecto sí),
        justo después de escribir y ANTES de devolver el foco a
        VoiceController se envía un Enter (actions.press_enter()) -- si
        no, al confirmar una búsqueda en un navegador el texto quedaba
        escrito pero la búsqueda no se disparaba sola, porque el foco
        volvía a VoiceController antes de que hubiera ocasión de pulsar
        Enter a mano. En un editor de texto normal el efecto es
        simplemente una línea nueva.

        Se llama tanto a mano (comando de voz "pegar texto"/botón) como
        AUTOMÁTICAMENTE justo tras confirmar un dictado si
        config.AUTO_PASTE_ON_CONFIRM está activo (ver _confirm_and_route) --
        en ese caso no hace falta decir "pegar texto" aparte.

        self.confirmed_text (el ACUMULADOR interno) SIEMPRE se vacía tras
        pegar, se pida como se pida -- si no se vaciara, la próxima vez
        que se confirme algo se reenviaría también lo ya enviado antes
        (type_text manda el acumulado completo, no solo lo nuevo).

        `clear_display` controla solo lo que se VE en el campo "Texto":
        - True (comportamiento de siempre para "pegar texto" a mano):
          también se borra de la pantalla, como confirmación visual de
          "ya se envió, campo listo para lo siguiente".
        - False: el campo se queda mostrando el texto que se acaba de
          enviar, en vez de vaciarse -- como registro de lo último que
          se mandó.

        El auto-pegado de _confirm_and_route lo decide con
        config.CLEAR_TEXT_FIELD_AFTER_AUTO_PASTE (por defecto True:
        también limpia). Antes pasaba False siempre, y el texto se
        quedaba en pantalla después de haber cumplido su función,
        pareciendo pendiente de enviar."""
        if not self.confirmed_text:
            return
        text_sent = self.confirmed_text
        try:
            self.gui.apartar_ventana()
        except Exception as exc:
            if DEBUG:
                print(f"[command_router] error mandando el GUI detrás: {exc!r}")
        time.sleep(config.PASTE_ACTIVATE_DELAY_MS / 1000)
        if actions.activate_target_window():  # extra opcional, ver PASTE_TARGET_WINDOW_REGEX
            time.sleep(config.PASTE_ACTIVATE_DELAY_MS / 1000)
        # EXPLICITO, y en los dos modos.
        #
        # Hasta el 5-sep-2026 esto funcionaba por casualidad: minimizar el
        # GUI (arriba) hace que KWin le devuelva el foco a la ventana de
        # debajo, y el texto acertaba de rebote. Nadie pidio ese foco nunca.
        # Se vio al hacer el modo servicio -- sin ventana que minimizar, el
        # efecto desaparecio y el dictado se perdia sin decir nada.
        #
        # Si el foco ya esta en una ventana ajena, esto no hace nada. Solo
        # actua cuando lo tiene una nuestra, que es el caso que rompia.
        if not actions.asegurar_ventana_destino():
            print("[command_router] OJO: no hay ventana destino clara, "
                  "el texto puede no llegar a ningun sitio")
        time.sleep(config.PASTE_ACTIVATE_DELAY_MS / 1000)
        actions.type_text(text_sent)
        if config.AUTO_ENTER_AFTER_PASTE:
            time.sleep(config.PASTE_ENTER_DELAY_MS / 1000)
            actions.press_enter()
        try:
            # VC vuelve a primer plano: con las capturas de DESPUES de pegar,
            # tomadas mientras aun esta apartado.
            self._refrescar(ya_apartada=True)
        except Exception as exc:
            if DEBUG:
                print(f"[command_router] error restaurando el GUI al frente: {exc!r}")
        if DEBUG:
            print(f"[command_router] Texto pegado (enviado por teclado){' y vaciado' if clear_display else ' (queda visible)'}"
                  f"{' + Enter' if config.AUTO_ENTER_AFTER_PASTE else ''}")
        self.confirmed_text = ""
        self.gui.update_texto("" if clear_display else text_sent)

    def _select_confirmed(self):
        if not self.confirmed_text:
            return
        actions.copy_to_clipboard(self.confirmed_text)
        try:
            self.gui.highlight_texto(True)
        except Exception:
            pass

    def _clear_confirmed(self):
        self.confirmed_text = ""
        self.gui.update_texto("")
        try:
            self.gui.highlight_texto(False)
        except Exception:
            pass

    # ---------- campo "Sugerencias" ----------

    def _clear_suggestion(self):
        if self._active_suggestion is not None:
            self._active_suggestion = None
            try:
                self.gui.clear_suggestion()
            except Exception:
                pass

    # Formas de referirse a VoiceController mismo en "trae <nombre>" --
    # normalizadas (ver _normalize), para no depender de ninguna
    # herramienta externa cuando lo que se pide es traer el propio GUI.
    _SELF_WINDOW_NAMES = frozenset({
        "controlador de voz",
        "control de voz",
        "voicecontroller",
        "voice controller",
        "el controlador de voz",
    })

    # Los titulos con los que se compara cuando el nombre dicho no esta en la
    # lista de arriba. Una lista cerrada no vale: la gente no dice el nombre
    # entero. pipataki usa "trae control" -- forma perfectamente razonable -- y
    # el 11-sep-2026 dejo de funcionar porque no estaba escrita.
    _SELF_TITULOS = ("voicecontroller", "voice controller",
                     "controlador de voz", "control de voz")
    _ARTICULOS = ("el ", "la ", "mi ", "al ", "un ", "una ", "este ", "esta ")

    def _es_ventana_propia(self, nombre_norm: str) -> bool:
        """¿Se esta refiriendo a NUESTRA ventana?

        Vale cualquier forma razonable de nombrarla: el nombre entero, un
        trozo del principio ("control", "controlador", "voice"), o sus
        palabras sueltas en cualquier orden ("control voz").

        Se exigen 4 letras para no cazar de mas: "voz" a secas se queda
        fuera a proposito, porque puede ser la ventana de otro programa.
        """
        n = (nombre_norm or "").strip()
        for a in self._ARTICULOS:
            if n.startswith(a):
                n = n[len(a):].strip()
                break
        if not n:
            return False
        if n in self._SELF_WINDOW_NAMES:
            return True
        if len(n) < 4:
            return False
        for titulo in self._SELF_TITULOS:
            if n in titulo:
                return True
            if all(palabra in titulo for palabra in n.split()):
                return True
        return False

    # Formas de decir "guardar como" antes del nombre. Se aceptan las mismas
    # que ya estaban como alias, para no tener dos listas que mantener.
    _GUARDAR_COMO_INICIOS = (
        ("guardar", "como"), ("guarda", "como"), ("save", "as"),
    )

    @staticmethod
    def _limpiar_nombre_de_fichero(nombre: str) -> str:
        """Deja el nombre en ASCII y sin caracteres que rompan.

        SIN acentos ni eñes, por decision suya: "acción" se guarda como
        "accion" y "mañana" como "manana". No es que sean invalidos -- en
        Linux y en Windows moderno funcionan -- sino que un nombre en ASCII
        viaja bien a cualquier sitio: un pendrive con formato antiguo, un
        script, otro sistema, un correo. Los nombres de fichero se acaban
        moviendo, y ahi es donde una tilde da la lata.

        Las mayusculas SI se conservan: no dan problemas en ninguna parte y
        son lo que el usuario ha dicho.
        """
        import unicodedata
        # NFKD separa la letra de su tilde, y luego se tiran las tildes.
        # La ñ hay que cambiarla a mano: al descomponerla queda n + virgulilla,
        # que asi tambien cae, pero se deja explicito para que se lea.
        descompuesto = unicodedata.normalize("NFKD", nombre)
        sin_tildes = "".join(c for c in descompuesto
                             if not unicodedata.combining(c))
        prohibidos = '/\\:*?"<>|'
        limpio = "".join(c for c in sin_tildes
                         if c not in prohibidos and 32 <= ord(c) < 127)
        limpio = limpio.strip().rstrip(". ")
        # Nombres reservados de Windows: con estos el dialogo falla y no
        # explica por que.
        reservados = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} \
                     | {f"lpt{i}" for i in range(1, 10)}
        if limpio.lower() in reservados:
            limpio += "_"
        return limpio

    def _try_parse_guardar_como(self, text: str, norm: str) -> bool:
        """"guardar como <nombre>": abre el dialogo y escribe el nombre.

        Idea suya, y de las que se ven usando: al abrirse el dialogo de
        guardar, el nombre del fichero **queda seleccionado**. Asi que
        escribir encima lo sustituye, y con decir "intro" despues ya esta
        guardado con el nombre que se queria. Si dices "guardar como" es
        justamente para decir COMO.

        Sin nombre detras no hace nada aqui: lo atiende el alias de siempre,
        que abre el dialogo y ya.
        """
        tokens = norm.split()
        if len(tokens) < 3:
            return False
        if tuple(tokens[:2]) not in self._GUARDAR_COMO_INICIOS:
            return False

        # El nombre se coge del texto ORIGINAL, no del normalizado.
        #
        # Los acentos y las eñes NO dan problemas en un nombre de fichero, ni
        # en Linux ni en Windows moderno: son nombres validos y corrientes.
        # Quitarlos seria feo en un programa español -- que "acción" se
        # guarde como "accion" es peor, no mejor.
        #
        # Lo que si rompe de verdad son / \ : * ? " < > | y los caracteres de
        # control: ilegales o problematicos segun el sistema. Dictando es
        # dificil que aparezcan -- el reconocedor devuelve palabras, no
        # simbolos -- pero puede pasar, y un nombre invalido deja el dialogo
        # atascado sin decir por que.
        nombre = " ".join(text.split()[2:]).strip()
        nombre = self._limpiar_nombre_de_fichero(nombre)
        if not nombre:
            return False

        print(f"[command_router] guardar como -> {nombre!r}")
        # A MANO, y no con el baile automatico de execute_keyboard_shortcut:
        # aqui el nombre se escribe MAS TARDE, cuando el dialogo ha salido.
        # Si el GUI volviera al frente al disparar el atajo, ese nombre
        # acabaria escribiendose en nuestra ventana.
        aparto = actions.apartar_gui_si_estorba(self.gui)
        if not actions.execute_keyboard_shortcut(self.gui, "save_as",
                                                 preparar=False):
            print("[command_router] no se pudo abrir el dialogo de guardar como")
            if aparto:
                self.gui.subir_ventana()
            return True

        def _escribir_nombre():
            # El dialogo tarda en aparecer, y escribir antes de que este
            # manda el nombre a la ventana de debajo -- que es lo que se
            # estaba editando. Por eso se espera.
            try:
                actions.type_text(nombre)
            except Exception as exc:
                print(f"[command_router] no se pudo escribir el nombre: {exc!r}")
            finally:
                # Ahora si: el nombre ya esta escrito. restore_after_vc_
                # action solo emite una señal, asi que se puede llamar desde
                # este hilo del temporizador sin tocar Qt por fuera.
                if aparto:
                    try:
                        self.gui.subir_ventana()
                    except Exception:
                        pass

        threading.Timer(config.GUARDAR_COMO_ESPERA_S, _escribir_nombre).start()

        if self.gui is not None:
            try:
                self.gui.update_suggestion(textos.t("guardar_como", nombre=nombre))
            except Exception:
                pass
        return True

    def _try_parse_foco_window(self, text: str, norm: str) -> bool:
        """"foco <nombre>" / "focus <nombre>": ensena LA VENTANA de esa
        aplicacion, ej. "foco kate", "foco firefox".

        Nace de un limite real: KWin sabe en que orden estan apiladas las
        ventanas, pero kdotool no lo expone, asi que no hay forma fiable de
        pedir "la que esta justo debajo de la nuestra". Decir el nombre lo
        resuelve mejor que adivinarlo -- no depende de ningun orden y
        funciona con muchas ventanas abiertas.

        Se corrige la capitalizacion real del titulo con window_names, igual
        que hace "trae <nombre>": quien dicta "kate" no va a acertar como se
        escribe de verdad en la barra de titulo.

        Devuelve True si el texto encajo con el patron (se haya encontrado la
        ventana o no); False si no encajo, para que on_final siga probando.
        """
        # "poco" esta aqui a proposito: el motor espanol oye "foco" como
        # "poco" bastante a menudo, y con confianza alta (medido: 0.97, 0.93).
        # Solo vale en la forma de DOS palabras -- "poco kate" es una orden,
        # "poco" a secas es una palabra normal y no debe disparar nada.
        tokens = norm.split()
        if len(tokens) < 2 or tokens[0] not in ("foco", "focus", "poco",
                                                "enfoca", "enfocar"):
            return False
        original = text.split()
        nombre = " ".join(original[1:]).strip()
        if not nombre:
            return False
        if self._es_ventana_propia(_normalize(nombre)):
            # Enfocarse a si mismo no tiene sentido: lo que se veria es la
            # propia ventana que ya se esta mirando.
            try:
                tts.get_speaker().say(textos.t("no_puedo_enfocarme"), tts.HELP)
            except Exception:
                pass
            return True
        conocido = window_names.lookup(_normalize(nombre))
        self._entrar_en_foco(conocido if conocido else nombre)
        return True

    def _try_parse_carpeta(self, text: str, norm: str) -> bool:
        """Carpetas del perfil, por voz. Cuatro ordenes:

            carpeta <nombre>          la trae si esta abierta, o la abre
            terminal en <nombre>      una consola ahi dentro
            crear carpeta <nombre>    crea una carpeta DONDE ESTE Dolphin
            crear archivo <nombre>    idem, un archivo

        NUNCA CREA UNA CARPETA QUE NO EXISTA al pedirla. Si no esta, se
        dice y ya. Es peticion de pipataki: un comando de voz que crea carpetas
        solo, con lo mal que se entienden algunos nombres, llenaria el
        perfil de carpetas fantasma.

        Y para crear no se calcula ninguna ruta: se le pide a Dolphin, que
        abre su dialogo en la carpeta que tenga delante. Ver carpetas.py.
        """
        # Las mas largas primero: "crear carpeta x" no puede caer en
        # "carpeta x".
        if norm.startswith("crear carpeta ") or norm.startswith("crear archivo "):
            que = "carpeta" if norm.startswith("crear carpeta ") else "archivo"
            nombre = text.strip()[len("crear ") + len(que):].strip()
            if not nombre:
                self._aviso_seleccion("carpeta_sin_nombre", True)
                return True

            # La extension se dice con "punto" delante. SIN "punto" el
            # nombre va tal cual y quien decida si lleva extension es el
            # gestor de archivos, no nosotros -- regla de pipataki. Ver
            # nombre_archivo.py. A las carpetas no se les aplica: una
            # carpeta no tiene extension, y si alguien dice "punto" dentro
            # del nombre de una carpeta lo querra literal.
            if que == "archivo":
                limpio, no_entendido = nombre_archivo.nombre_de(nombre)
                if limpio is None:
                    print(f"[command_router] extension no entendida en "
                          f"{nombre!r}: {no_entendido!r}")
                    self.gui.update_suggestion(
                        textos.t("extension_rara", trozo=no_entendido), True)
                    return True
                nombre = limpio

            ok, detalle = carpetas.crear(que, nombre)
            if not ok and detalle == "no se en que carpeta estas":
                self.gui.update_suggestion(
                    textos.t("carpeta_sin_saber_donde"), True)
                return True
            print(f"[command_router] crear {que} {nombre!r}: "
                  f"{'OK' if ok else 'FALLO'} ({detalle})")
            self.gui.update_suggestion(
                textos.t(("carpeta_creada" if que == "carpeta"
                          else "archivo_creado") if ok else "carpeta_no_creada",
                         nombre=nombre, motivo=detalle), not ok)
            return True

        for prefijo, accion in (("carpeta ", "abrir"),
                                ("terminal en ", "terminal"),
                                ("consola en ", "terminal")):
            if not norm.startswith(prefijo):
                continue
            nombre = norm[len(prefijo):].strip()
            if not nombre:
                return False
            ruta = carpetas.ruta_de(nombre)
            if ruta is None:
                print(f"[command_router] carpeta {nombre!r}: no existe en el perfil")
                self.gui.update_suggestion(
                    textos.t("carpeta_no_existe", nombre=nombre), True)
                return True
            if accion == "terminal":
                ok = carpetas.terminal_en(ruta)
                print(f"[command_router] terminal en {ruta}: {'OK' if ok else 'FALLO'}")
                self.gui.update_suggestion(
                    textos.t("terminal_en" if ok else "carpeta_no_abre",
                             nombre=nombre, motivo=""), not ok)
            else:
                ok, detalle = carpetas.abrir(ruta)
                print(f"[command_router] carpeta {ruta}: "
                      f"{'OK' if ok else 'FALLO'} ({detalle})")
                self.gui.update_suggestion(
                    textos.t("carpeta_abierta" if ok else "carpeta_no_abre",
                             nombre=nombre, motivo=detalle), not ok)
            return True
        return False

    def _try_parse_bring_window(self, text: str, norm: str) -> bool:
        """"trae <nombre>"/"traer <nombre>" (solo se comprueba en estado
        IDLE, ver on_final -- en DICTATING "trae" podría ser una palabra
        normal dentro de una frase dictada, así que no se intercepta ahí):
        trae al frente la ventana de una aplicación por su nombre, ej.
        "trae kate", "trae firefox", "trae inkscape".

        Si el nombre es alguna forma de referirse al propio
        VoiceController (ver _SELF_WINDOW_NAMES, ej. "trae controlador
        de voz"), se usa el mismo mecanismo interno que ya usa el
        comando "subir" (self.gui.subir_ventana(), sin
        depender de ninguna herramienta externa -- VoiceController
        siempre puede traerse a sí mismo solo).

        Para cualquier OTRO nombre, primero se busca en window_names.py
        (window_names.lookup) si hay una capitalización REAL conocida
        para ese nombre (ej. "kate" dicho -> "Kate", que es como
        aparece de verdad en el título de la ventana) -- si la hay, se
        usa esa; si no, se usa el nombre tal cual se dijo. Luego se
        intenta activar esa ventana externa con
        actions.activate_window_by_name() (usa `kdotool`, ver docstring
        ahí). Se hace así (en vez de confiar solo en que kdotool compare
        sin distinguir mayúsculas) porque en la práctica no siempre
        basta -- ver window_names.py para más detalle.

        Devuelve True si el texto reconocido encajó con este patrón (se
        haya podido traer la ventana o no -- p.ej. si esa app no está
        abierta, kdotool simplemente no encuentra nada, pero el patrón
        de voz sigue siendo válido); False si no encajó en absoluto
        (menos de 2 palabras, o no empieza por "trae"/"traer"), para que
        on_final siga probando otras cosas con ese texto."""
        tokens = norm.split()
        # SOLO "trae"/"traer". No se acepta "foco <nombre>": son dos cosas
        # distintas y mezclarlas seria un error. `trae` trae al frente una
        # ventana de otro programa; `foco` es la VISTA foco de VoiceController,
        # que captura la pantalla y la amplia. Se probo a aceptar los dos el
        # 10-sep-2026 y pipataki lo paro en el sitio.
        if len(tokens) < 2 or tokens[0] not in ("trae", "traer"):
            return False
        # nombre tal como se dictó de verdad (conserva mayúsculas/acentos),
        # no la versión normalizada -- kdotool hace su propia comparación
        original_tokens = text.split()
        name = " ".join(original_tokens[1:]).strip()
        if not name:
            return False
        if self._es_ventana_propia(_normalize(name)):
            try:
                # traer_al_frente_suave y NO subir_ventana:
                # aquel es show()+raise_(), y bajo Wayland el compositor
                # ignora que un cliente se suba solo contra una ventana
                # maximizada. Este refuerza por KWin. Y NO bring_to_front,
                # que MINIMIZA la ventana activa -- que es justo la que se
                # esta mirando con la vista de foco.
                # Y con las capturas AL DIA: es el momento en que se vuelve a
                # mirar el GUI, casi siempre tras hacer algo en otra ventana.
                # Se captura con VC apartado y se sube despues (pipataki, 12-sep).
                self._refrescar(volver=self.gui.traer_al_frente_suave)
            except Exception as exc:
                if DEBUG:
                    print(f"[command_router] error trayendo VoiceController al frente: {exc!r}")
            if DEBUG:
                print(f"[command_router] 'trae {name}' -> VoiceController al frente (sin kdotool)")
            return True
        # nombre conocido (ver window_names.py) -> capitalización real del
        # título de la ventana; si no hay entrada conocida, se usa tal
        # cual se dijo ("lo que diga")
        known = window_names.lookup(_normalize(name))
        target_name = known if known else name
        ok = actions.activate_window_by_name(target_name)
        if DEBUG:
            print(f"[command_router] {text.strip()!r} -> activate_window_by_name({target_name!r}"
                  f"{', conocido' if known else ', sin normalizar'}) -> {ok}")
        return True

    # nombres que activan/desactivan el seguimiento táctil del círculo
    # verde (ver gui.set_touch_follow_enabled) -- "cara" está reservado
    # para un futuro seguimiento por cámara/detección facial, TODAVÍA NO
    # IMPLEMENTADO (ver docstring del módulo)
    _INPUT_MODE_TOUCH_WORDS = frozenset({"tactil", "touch"})
    _INPUT_MODE_FACE_WORDS = frozenset({"cara", "face"})

    def _try_parse_input_mode(self, norm: str) -> bool:
        """"táctil"/"touch" o "cara"/"face": elige la fuente del
        seguimiento del círculo verde en la casilla ampliada -- pensado
        para cuando en el futuro haya DOS fuentes posibles (táctil y
        cámara/detección facial) y convenga poder decir explícitamente
        cuál usar si "se lían" entre sí. Por ahora "cara" solo
        DESACTIVA el seguimiento táctil sin activar nada en su lugar
        (el seguimiento por cámara todavía no está implementado -- ver
        docstring del módulo)."""
        if norm in self._INPUT_MODE_TOUCH_WORDS:
            self.gui.set_touch_follow_enabled(True)
            if DEBUG:
                print("[command_router] modo de seguimiento del círculo verde: táctil")
            return True
        if norm in self._INPUT_MODE_FACE_WORDS:
            self.gui.set_touch_follow_enabled(False)
            if DEBUG:
                print("[command_router] modo de seguimiento del círculo verde: cara "
                      "(TODAVÍA NO IMPLEMENTADO -- seguimiento táctil desactivado, "
                      "ningún seguimiento activo por ahora)")
            return True
        return False

    def _correct_last_word(self):
        """Corrige el Pre-Texto borrando SOLO su última palabra, sin
        tocar el resto ni salir de DICTATING/formuling -- para arreglar
        un fallo puntual de reconocimiento sin tener que volver a
        dictar todo el fragmento con "reset". No hace nada si el
        Pre-Texto ya está vacío."""
        if not self.primary_buffer.strip():
            return
        words = self.primary_buffer.rsplit(" ", 1)
        self.primary_buffer = words[0].rstrip() if len(words) > 1 else ""
        if self._word_origins:
            self._word_origins.pop()
        if self.formuling:
            try:
                self.gui.update_pretexto_formuling(self.primary_buffer, preview="")
            except Exception:
                self.gui.update_pretexto(self.primary_buffer, preview="")
        else:
            self.gui.update_pretexto(self.primary_buffer, preview="")
        self._clear_suggestion()
        self._arm_text_suppression(0.4)
        if DEBUG:
            print(f"[command_router] corregida ultima palabra -> Pre-Texto={self.primary_buffer!r}")

    def _correct_word(self, index: int, modifier: str, ambiguous: bool = False):
        """Corrige la palabra número `index` (1-based, contando por
        espacios sobre el Pre-Texto tal cual está ahora mismo) aplicando
        `modifier` (ver _WORD_MODIFIERS/_apply_word_modifier) SOLO a esa
        palabra -- ej. "corregir 4 mayuscula" pone en mayúscula la
        inicial de la palabra 4 ("sevilla" -> "Sevilla"); "corregir 5
        siglas" pasa la palabra 5 a mayúsculas completas (para
        siglas/acrónimos, ej. "renfe" -> "RENFE"). No toca el resto del
        Pre-Texto ni cambia de estado. No hace nada si `index` cae fuera
        del número de palabras actual (ver _try_parse_correct_word, que
        ya valida el modificador antes de llegar aquí).

        Además APRENDE esta corrección (ver corrections.py) para
        aplicarla sola la próxima vez que se dicte la misma palabra:
        estricta por defecto, o ambigua (solo como sugerencia, nunca
        automática) si `ambiguous` es True -- ver docstring del módulo.

        Si la palabra en esa posición se convirtió sola a cifra (ver
        _apply_default_number_normalization, ej. "once" -> "11" en la
        primera vez que se dicta, antes de enseñar nada sobre ella), la
        corrección/el aprendizaje se hacen sobre la palabra tal como se
        dictó de verdad (ver self._word_origins), no sobre la cifra ya
        mostrada -- así "corregir 2 siglas ambiguo" tras dictar "la once
        es..." aprende sobre "once", no sobre "11", y el Pre-Texto pasa a
        mostrar "ONCE" en vez de quedarse en "11"."""
        words = self.primary_buffer.split(" ") if self.primary_buffer else []
        if not (1 <= index <= len(words)):
            if DEBUG:
                print(f"[command_router] corregir palabra {index}: fuera de rango "
                      f"({len(words)} palabra(s) en el Pre-Texto)")
            return
        original_word = words[index - 1]
        origin_word = self._word_origins[index - 1] if 1 <= index <= len(self._word_origins) else None
        disp_match = _WORD_CORE_RE.match(original_word)
        disp_prefix = disp_match.group(1) if disp_match else ""
        disp_core = disp_match.group(2) if disp_match else original_word
        disp_suffix = disp_match.group(3) if disp_match else ""
        if origin_word is not None and disp_core.isdigit() and _normalize(origin_word) != _normalize(disp_core):
            base_word = disp_prefix + origin_word + disp_suffix
        else:
            base_word = original_word
        new_word = _apply_word_modifier(base_word, modifier)
        words[index - 1] = new_word
        self.primary_buffer = " ".join(words)
        if 1 <= index <= len(self._word_origins):
            self._word_origins[index - 1] = base_word
        if self.formuling:
            try:
                self.gui.update_pretexto_formuling(self.primary_buffer, preview="")
            except Exception:
                self.gui.update_pretexto(self.primary_buffer, preview="")
        else:
            self.gui.update_pretexto(self.primary_buffer, preview="")
        self._clear_suggestion()
        self._arm_text_suppression(0.4)

        core_match = _WORD_CORE_RE.match(base_word)
        word_norm = _normalize(core_match.group(2) if core_match else base_word)
        if word_norm:
            corrections.learn(self._corrections, word_norm, modifier, ambiguous)
            corrections.save(self._corrections)

        if DEBUG:
            nivel = "ambigua" if ambiguous else "estricta"
            print(f"[command_router] corregida palabra {index} ({modifier}) -> "
                  f"Pre-Texto={self.primary_buffer!r} (aprendida como {nivel}: {word_norm!r})")

    def _apply_strict_corrections(self, chunk: str) -> str:
        """Aplica sobre `chunk` (fragmento recién dictado, ya humanizado)
        cualquier corrección aprendida como ESTRICTA (ver corrections.py):
        si alguna de sus palabras coincide con una ya corregida antes de
        esa forma, se le aplica el mismo modificador automáticamente, sin
        avisar. Las correcciones AMBIGUAS nunca se tocan aquí (ver
        _check_ambiguous_suggestion)."""
        if not chunk:
            return chunk
        words = chunk.split(" ")
        changed = False
        for i, word in enumerate(words):
            core_match = _WORD_CORE_RE.match(word)
            word_norm = _normalize(core_match.group(2) if core_match else word)
            modifier = corrections.find_strict(self._corrections, word_norm)
            if modifier:
                words[i] = _apply_word_modifier(word, modifier)
                changed = True
        return " ".join(words) if changed else chunk

    def _check_ambiguous_suggestion(self, chunk: str):
        """Tras añadir `chunk` (ya humanizado/corregido) al final de
        primary_buffer, comprueba si alguna de sus palabras coincide con
        una palabra que tiene opciones AMBIGUAS aprendidas (ver
        corrections.py: cada corrección "ambiguo" que se enseña para la
        misma palabra se va acumulando como una opción más, no se pisa).
        Si hay alguna, se pregunta en el campo Sugerencias, ej.:

            ❓ "once" ¿como "siglas", "cifras" o "letras"? Dilo para aplicarlo.

        y se resuelve diciendo directamente el nombre de una de esas
        opciones (ver _try_resolve_ambiguous_choice, llamado desde
        on_final) -- no hace falta pasar por "vale". La pregunta se
        descarta sola en cuanto llegue texto nuevo (ver _clear_suggestion
        en on_final) o al confirmar/resetear/salir de dictado.

        Si hay varias palabras del chunk con opciones ambiguas, se
        pregunta solo por la última (la más reciente es la más probable
        de necesitar corrección todavía)."""
        if not chunk:
            return
        words = self.primary_buffer.split(" ") if self.primary_buffer else []
        chunk_word_count = len(chunk.split())
        offset = len(words) - chunk_word_count  # índice 0-based de la 1ª palabra del chunk dentro del buffer
        for i in range(chunk_word_count - 1, -1, -1):
            buffer_index = offset + i
            if not (0 <= buffer_index < len(words)):
                continue
            word = words[buffer_index]
            core_match = _WORD_CORE_RE.match(word)
            core = core_match.group(2) if core_match else word
            word_norm = _normalize(core)
            options = corrections.find_ambiguous(self._corrections, word_norm)
            if options:
                index = buffer_index + 1  # 1-based, igual que _correct_word
                self._active_suggestion = {
                    "type": "ambiguous_choice",
                    "index": index,
                    "options": list(options),
                }
                self.gui.update_suggestion(
                    textos.t("corregir_como", palabra=core,
                             opciones=_join_opciones(options))
                )
                if DEBUG:
                    print(f"[command_router] pregunta ambigua: palabra {index} "
                          f"({word!r}) -> opciones {options!r}")
                return

    def _try_resolve_ambiguous_choice(self, norm_text: str) -> bool:
        """Si hay una pregunta ambigua activa (ver _check_ambiguous_suggestion)
        y `norm_text` (la frase reconocida, ya normalizada) es exactamente
        el nombre de una de sus opciones (o un alias suyo -- ver
        _WORD_MODIFIERS, ej. decir "capital" también vale para la opción
        "mayuscula"), aplica esa opción a la palabra señalada y descarta
        la pregunta. Devuelve True si se resolvió así (para que on_final no
        trate ese texto como dictado normal); False si no había pregunta
        activa o el texto no coincidía con ninguna opción -- en ese caso
        on_final sigue su curso normal, tratándolo como texto dictado."""
        sug = self._active_suggestion
        if not sug or sug.get("type") != "ambiguous_choice":
            return False
        modifier = _WORD_MODIFIERS.get(norm_text.strip())
        if modifier is None or modifier not in sug["options"]:
            return False
        index = sug["index"]
        words = self.primary_buffer.split(" ") if self.primary_buffer else []
        if 1 <= index <= len(words):
            new_word = _apply_word_modifier(words[index - 1], modifier)
            words[index - 1] = new_word
            self.primary_buffer = " ".join(words)
            if 1 <= index <= len(self._word_origins):
                self._word_origins[index - 1] = new_word
            self.gui.update_pretexto(self.primary_buffer, preview="")
            if DEBUG:
                print(f"[command_router] pregunta ambigua resuelta: palabra {index} "
                      f"-> Pre-Texto={self.primary_buffer!r} (elegido {modifier!r})")
        self._clear_suggestion()
        self._arm_text_suppression(0.4)
        return True

    def _apply_default_number_normalization(self, text: str):
        """Por defecto, cualquier cantidad numérica dictada como palabras
        se normaliza sola a cifra (ej. "treinta y cinco" -> "35"), sin
        necesidad de enseñar nada -- ver numbers_es.parse_number_prefix.
        La única excepción es una palabra que YA tiene una corrección
        aprendida (estricta o con opciones ambiguas, ver corrections.py):
        esa palabra se deja tal cual llegó, para que decida
        _apply_strict_corrections (si es estricta) o
        _check_ambiguous_suggestion (si es ambigua) más adelante en
        on_final, en vez de convertirla a ciegas aquí.

        Se llama sobre `text` (el fragmento recién reconocido, en crudo,
        SIN humanizar todavía) -- así no hay que lidiar con puntuación
        pegada a las palabras.

        Devuelve (texto_normalizado, origenes): `origenes` tiene UNA
        entrada por cada palabra de `texto_normalizado` con la palabra tal
        como se dictó de verdad -- para una palabra convertida a cifra
        (número de una sola palabra, ej. "once" -> "11") es esa palabra
        original ("once"); para el resto, la propia palabra. Para un
        número de VARIAS palabras (ej. "treinta y cinco" -> "35") no hay
        una única palabra original que recordar, así que se usa None (ver
        _correct_word, que cae de vuelta a la palabra ya mostrada en ese
        caso -- es un caso raro de enseñar ambigüedad sobre un número
        compuesto). Se usa para poder enseñar/corregir sobre la palabra
        que de verdad se dijo aunque el Pre-Texto ya muestre la cifra
        (ver self._word_origins)."""
        if not text:
            return text, []
        words = text.split(" ")
        norm_words = [_normalize(w) for w in words]
        out = []
        origins = []
        i = 0
        n = len(words)
        while i < n:
            word_norm = norm_words[i]
            has_learned = (
                corrections.find_strict(self._corrections, word_norm) is not None
                or bool(corrections.find_ambiguous(self._corrections, word_norm))
            )
            if not has_learned:
                value, consumed = _numeros().parse_number_prefix(norm_words, i)
                if value is not None and consumed > 0:
                    out.append(str(value))
                    origins.append(words[i] if consumed == 1 else None)
                    i += consumed
                    continue
            out.append(words[i])
            origins.append(words[i])
            i += 1
        return " ".join(out), origins

    def check_pause_suggestion(self):
        """Llamado por el GUI (vía set_pause_callback) tras una pausa sin
        actividad de texto mientras se dicta (config.PAUSE_SUGGESTION_MS).

        Por ahora solo cubre el caso descrito en el manual: si estamos en
        dictado NORMAL (no en modo fórmula) y lo dictado hasta ahora "suena"
        a una expresión numérica/matemática, se ofrece pasarla a dígitos y
        notación simbólica en el propio Pre-Texto."""
        if self.state != "DICTATING":
            return
        text = self.primary_buffer.strip()
        if not text:
            self._clear_suggestion()
            return

        if not self.formuling:
            norm = _normalize(text)
            tokens = norm.split()
            if _mates().looks_like_math(tokens):
                symbolic = _mates().to_symbolic(norm).strip()
                if symbolic and symbolic != text:
                    self._active_suggestion = {"type": "to_math", "text": symbolic}
                    self.gui.update_suggestion(
                        textos.t("parece_expresion", simbolico=symbolic)
                    )
                    if DEBUG:
                        print(f"[command_router] sugerencia: {text!r} -> {symbolic!r}")
                    return

        self._clear_suggestion()

    @staticmethod
    def _build_alias_map(section: dict, key_field: str):
        """Construye {alias_normalizado: valor_del_campo_key_field} ignorando entradas '_comentario'."""
        alias_map = {}
        for name, entry in section.items():
            if name.startswith("_"):
                continue
            value = entry[key_field]
            for alias in entry.get("aliases", [name]):
                alias_map[_normalize(alias)] = value
        return alias_map

    @staticmethod
    def _build_scoped_alias_maps(section: dict):
        """Construye tres {alias_normalizado: action}, uno por scope
        ('idle', 'dictating', 'any'), a partir de control_words."""
        idle_map, dictating_map, any_map = {}, {}, {}
        by_scope = {"idle": idle_map, "dictating": dictating_map, "any": any_map}
        for name, entry in section.items():
            if name.startswith("_"):
                continue
            action = entry["action"]
            scope = entry.get("scope", "any")
            target = by_scope.get(scope, any_map)
            for alias in entry.get("aliases", [name]):
                target[_normalize(alias)] = action
        return idle_map, dictating_map, any_map

    @staticmethod
    def _build_action_prefix_list(section: dict):
        """Devuelve [(alias_tokens_tuple, handler_name), ...] ordenado por
        longitud de alias descendente, para el formato directo
        '<accion> <celda> <subcelda>'."""
        items = []
        for name, entry in section.items():
            if name.startswith("_"):
                continue
            handler_name = entry["handler"]
            for alias in entry.get("aliases", [name]):
                alias_tokens = tuple(_normalize(alias).split())
                items.append((alias_tokens, handler_name))
        items.sort(key=lambda pair: len(pair[0]), reverse=True)
        return items

    def _try_parse_vc(self, norm_text: str):
        """Formato LEGACY (vía dictado+confirmación): si norm_text es
        '<disparador> <casilla 1-100> <accion>', devuelve
        (handler_name, cell). None si no se puede parsear."""
        tokens = norm_text.split()
        if not tokens or tokens[0] not in self._vc_trigger_aliases:
            return None

        cell, consumed = _numeros().parse_number_prefix(tokens, 1)
        if cell is None or not (1 <= cell <= board.TOTAL_CELLS):
            return None

        action_start = 1 + consumed
        action_text = " ".join(tokens[action_start:])
        handler_name = self._vc_action_alias_map.get(action_text)
        if handler_name is None:
            return None

        return handler_name, cell

    @staticmethod
    def _fix_misheard_number(tokens: list) -> list:
        """Sustituye palabras que el reconocedor confunde con un número
        (ver config.NUMBER_MISHEARD) -- SOLO en el argumento de un
        comando, nunca en texto dictado.

        Con "diez", que es corto, Vosk falla a menudo: en un log real,
        5 de 11 "mover diez" se oyeron como "mover tie", "mover tier" o
        "mover pie". Esta corrección es segura AQUÍ porque el contexto ya
        está fijado -- delante hay una palabra de acción reconocida, así
        que lo que sigue solo puede ser un número. La misma sustitución
        aplicada al dictado convertiría "pie" en "10", que sería un
        destrozo."""
        tabla = getattr(config, "NUMBER_MISHEARD", None)
        if not tabla:
            return tokens
        return [tabla.get(t, t) for t in tokens]

    def _try_parse_direct_vc(self, norm_text: str):
        """Formato directo de un solo tiro (sin 'dictar' ni confirmación,
        sin ajuste fino): '<accion> <casilla 1-100>', ej. 'mover 57',
        'click derecho 57'. Devuelve (handler_name, cell) o None si no
        encaja limpiamente."""
        tokens = norm_text.split()
        for alias_tokens, handler_name in self._vc_action_prefix_list:
            n = len(alias_tokens)
            if tuple(tokens[:n]) != alias_tokens:
                continue
            # el argumento numérico pasa por la tabla de confusiones
            # (ver _fix_misheard_number): aquí el contexto ya es
            # inequívoco, delante hay una acción reconocida
            arreglados = tokens[:n] + self._fix_misheard_number(tokens[n:])
            cell, consumed = _numeros().parse_number_prefix(arreglados, n)
            if cell is None or not (1 <= cell <= board.TOTAL_CELLS):
                continue
            if n + consumed != len(arreglados):
                continue  # sobran palabras al final: no es un match limpio
            return handler_name, cell
        return None

    def _try_parse_board_zone_action(self, norm_text: str):
        """'<accion> <numero>' (ej. 'click 1', 'doble click 2', 'mover
        3'), pero interpretando el número como el índice (1-based) de
        una ZONA CLICABLE AUTODETECTADA (ver board.detect_zones), no
        como una casilla del tablero. Solo tiene sentido con una casilla
        ya seleccionada y zonas ya detectadas (self.board_zones no
        vacío) -- se comprueba aquí para no confundirse con el formato
        directo '<accion> <casilla 1-100>'. Devuelve (handler_name,
        zone_num) o None."""
        if not self.board_zones:
            return None
        tokens = norm_text.split()
        for alias_tokens, handler_name in self._vc_action_prefix_list:
            n = len(alias_tokens)
            if tuple(tokens[:n]) != alias_tokens:
                continue
            zone_num, consumed = _numeros().parse_number_prefix(tokens, n)
            if zone_num is None or n + consumed != len(tokens):
                continue
            if not (1 <= zone_num <= len(self.board_zones)):
                continue
            return handler_name, zone_num
        return None

    def _refrescar(self, volver=None, ya_apartada=False):
        """Vuelve a capturar la vista que se este mirando, sin mover el
        puntero verde. Ver actions.refrescar_vista, que es quien lo hace.

        La vista y la posicion salen de _punto_actual(), que es la que sabe
        leer el raton encima de la miniatura: leer los offsets del router a
        pelo daria la posicion por voz, que puede no ser la que se ve.
        """
        punto = self._punto_actual()
        if punto:
            _, offset, vista, casilla = punto
        else:
            vista, casilla, offset = "overview", None, (0, 0)
        actions.refrescar_vista(
            self.gui, vista, casilla=casilla,
            nombre=getattr(self, "_foco_nombre", "") or "",
            offset=offset,
            on_zones=self._on_board_zones_detected if vista == "cell" else None,
            volver=volver, ya_apartada=ya_apartada)

    def _punto_actual(self):
        """Todo lo que hace falta saber del punto verde de una vez:

            (posicion_absoluta, offset_de_la_vista, vista, casilla)

        La posicion absoluta es para ACTUAR (mover el raton, hacer clic);
        el offset y la vista son para DIBUJAR, porque el recuadro de la
        seleccion se pinta sobre la captura y ahi las coordenadas son las
        de la vista, no las del escritorio.

        Devuelve None si no hay punto puesto.
        """
        # EL RATON MANDA, EN LAS TRES VISTAS.
        #
        # El punto verde sigue al raton sobre la miniatura del GUI en las
        # tres (ver gui._do_touch_track: acepta "cell", "zoom_out" y
        # "foco"), y esa posicion vive en gui.get_touch_offset(), NO en los
        # offsets del router -- esos solo los mueven las ordenes de voz.
        #
        # Consultarlo SOLO en la rama de casilla fue el fallo del
        # 6-sep-2026: pipataki colocaba el punto con el raton en vista foco y el
        # recuadro salia siempre desde el centro, porque aqui se leia el
        # ajuste por voz, que valia 0. Es la misma fuente que usa el clic
        # (_try_parse_board_action_green); leer otra distinta da un origen
        # que no es el punto que se ve.
        def _con_raton(por_voz):
            try:
                tactil = self.gui.get_touch_offset()
                if tactil is not None:
                    return tuple(tactil)
            except Exception:
                pass
            return por_voz

        try:
            if getattr(self, "_foco_activo", False):
                off = _con_raton((self._foco_offset_x, self._foco_offset_y))
                pos = board.foco_absolute_position(*off)
                return (pos, off, "foco", None) if pos else None
            celda = getattr(self, "_zoom_out_active_cell", None)
            if celda:
                off = _con_raton((self._zoom_out_offset_x, self._zoom_out_offset_y))
                pos = board.zoom_out_absolute_position(celda, *off)
                return (pos, off, "zoom_out", celda) if pos else None
            if self.board_selected_cell:
                off = _con_raton((self.board_offset_x, self.board_offset_y))
                pos = board.cell_absolute_position(self.board_selected_cell, *off)
                return (pos, off, "cell", self.board_selected_cell) if pos else None
        except Exception as exc:
            print(f"[command_router] no se pudo saber donde esta el punto: {exc!r}")
        return None

    def _posicion_absoluta_actual(self):
        """Solo la posicion en pixeles de pantalla. Ver _punto_actual()."""
        punto = self._punto_actual()
        return punto[0] if punto else None

    # ------------------------------------------------------------------
    # SELECCIONAR: dos coordenadas y una accion
    # ------------------------------------------------------------------
    #
    # Idea de pipataki. Se dice "seleccionar" donde empieza, se mueve el punto,
    # y se dice "fin de la seleccion" donde acaba.
    #
    # ENTRE LAS DOS ORDENES NO SE SOSTIENE NADA en el sistema: el origen
    # solo se apunta aqui. Ver actions.seleccionar_rango() para por que eso
    # importa tanto.
    #
    # El final NUNCA se llama "fin" a secas, y esto lo cazo pipataki: "fin" era
    # alias de cerrar_idle, y decirlo para terminar una seleccion habria
    # CERRADO EL PROGRAMA. Desde el 13-sep-2026 "fin" es la tecla Fin, que
    # tampoco es terminar una seleccion.
    #
    # Y de rebote sale ARRASTRAR Y SOLTAR, que es lo mismo con otro final.

    def _aviso_seleccion(self, clave: str, urgente: bool = False):
        """Un aviso en la linea de sugerencias, sin reventar si falla."""
        try:
            self.gui.update_suggestion(textos.t(clave), urgente)
        except Exception as exc:
            if DEBUG:
                print(f"[command_router] no se pudo avisar: {exc!r}")

    def _seleccion_fijar_origen(self):
        punto = self._punto_actual()
        if punto is None:
            self._aviso_seleccion("seleccion_sin_punto", True)
            return
        pos, offset, vista, celda = punto
        self._seleccion_origen = pos
        try:
            self.gui.set_seleccion_pendiente(True)
            # Y donde dibujarlo: el recuadro se pinta sobre la captura, en
            # coordenadas de la vista. Sin esto no se veria que se va a
            # seleccionar hasta despues de hacerlo.
            self.gui.set_seleccion_origen(offset, vista, celda)
        except Exception:
            pass
        print(f"[command_router] origen de seleccion en {pos} "
              f"(vista={vista}, offset={offset})")
        self._aviso_seleccion("seleccion_origen")

    def _seleccion_terminar(self, modo: str):
        if not self._seleccion_origen:
            self._aviso_seleccion("seleccion_sin_origen", True)
            return
        fin = self._posicion_absoluta_actual()
        if fin is None:
            self._aviso_seleccion("seleccion_sin_punto", True)
            return
        origen = self._seleccion_origen
        # SI EL PUNTO NO SE HA MOVIDO, no se selecciona nada: seria un clic
        # en el sitio, y encima el log diria "OK" tan tranquilo. Paso la
        # primera vez que se probo -- origen y destino eran los dos
        # (960,540), el centro de la ventana en vista foco, porque entre
        # las dos ordenes no hubo ninguna de movimiento.
        #
        # El origen NO se borra: se deja puesto para que baste con mover el
        # punto y repetir el final, sin tener que empezar de cero.
        if abs(fin[0] - origen[0]) < 3 and abs(fin[1] - origen[1]) < 3:
            print(f"[command_router] el punto no se ha movido desde {origen}: "
                  f"no hay nada que seleccionar")
            self._aviso_seleccion("seleccion_sin_mover", True)
            return
        self._seleccion_cancelar(callado=True)
        actions.seleccionar_rango(self.gui, origen, fin, modo)
        self._aviso_seleccion("seleccion_hecha")

    def _seleccion_cancelar(self, callado: bool = False):
        """Olvida el origen y apaga el amarillo.

        Se llama tambien al cambiar de estado: un origen que sobrevive a un
        "tablero" o a un "dictar" es un cepo -- el usuario ya no se acuerda,
        y el siguiente "fin de la seleccion" selecciona desde donde no toca.
        """
        habia = self._seleccion_origen is not None
        self._seleccion_origen = None
        try:
            self.gui.set_seleccion_pendiente(False)
            self.gui.set_seleccion_origen(None, None, None)
        except Exception:
            pass
        if habia and not callado:
            self._aviso_seleccion("seleccion_cancelada")

    def _try_parse_bare_cell(self, norm_text: str):
        """Un número SOLO (1-100), ej. 'cincuenta y siete' -> 57. Es la
        selección de casilla del tablero (Paso 1 del manual). Devuelve el
        número o None si no es (exactamente) eso."""
        tokens = norm_text.split()
        if not tokens:
            return None
        cell, consumed = _numeros().parse_number_prefix(tokens, 0)
        if cell is None or consumed != len(tokens):
            return None
        if not (1 <= cell <= board.TOTAL_CELLS):
            return None
        return cell

    def _try_parse_board_direction(self, norm_text: str):
        """'<direccion>' o '<direccion> <n>' (ej. 'oeste', 'oeste 3').
        Devuelve (vector_dx_dy, pixeles) o None."""
        tokens = norm_text.split()
        if not tokens:
            return None
        vector = self._board_direction_alias_map.get(tokens[0])
        if vector is None:
            return None
        if len(tokens) == 1:
            return vector, config.BOARD_NUDGE_STEP_PX
        pixels, consumed = _numeros().parse_number_prefix(tokens, 1)
        if pixels is None or 1 + consumed != len(tokens) or pixels <= 0:
            return None
        return vector, pixels

    # palabras que marcan el flag "ambiguo" al final de "corregir <numero>
    # <modificador> [ambiguo]" (ver _try_parse_correct_word / corrections.py)
    _AMBIGUOUS_FLAG_WORDS = {"ambiguo", "ambigua", "ambiguous"}

    def _try_parse_correct_word(self, norm_text: str):
        """'<corrige/corregir/correct/fix> <numero> <modificador>
        [ambiguo]' (ej. 'corregir 4 mayuscula', 'corrige 5 siglas
        ambiguo'): corrige UNA palabra concreta del Pre-Texto por su
        posición (1-based). Distinto de decir el disparador SOLO, que
        sigue borrando la última palabra (ver control_action
        'correct_last_word'). El flag final opcional "ambiguo" marca el
        aprendizaje de esta corrección como AMBIGUO en vez de ESTRICTO
        (ver corrections.py / _correct_word). Devuelve (indice,
        modificador_canonico, ambiguo) o None si no encaja limpiamente
        (incluye un modificador no reconocido -- ver _WORD_MODIFIERS)."""
        tokens = norm_text.split()
        if not tokens or tokens[0] not in self._correct_word_trigger_aliases:
            return None
        index, consumed = _numeros().parse_number_prefix(tokens, 1)
        if index is None or index < 1:
            return None
        rest_tokens = tokens[1 + consumed:]
        ambiguous = bool(rest_tokens) and rest_tokens[-1] in self._AMBIGUOUS_FLAG_WORDS
        if ambiguous:
            rest_tokens = rest_tokens[:-1]
        modifier_text = " ".join(rest_tokens)
        modifier = _WORD_MODIFIERS.get(modifier_text)
        if modifier is None:
            return None
        return index, modifier, ambiguous

    # ---------- tablero de 100 casillas: selección / ajuste fino / acción ----------

    def _select_board_cell(self, cell: int):
        # Igual que con el zoom: elegir una casilla apaga el foco. Son vistas
        # mutuamente excluyentes, y dejarlo activo por detras hace que su
        # recaptura reaparezca luego sin haberla pedido.
        self._foco_activo = False
        self.board_selected_cell = cell
        self.board_offset_x = 0
        self.board_offset_y = 0
        self.board_zones = []
        if DEBUG:
            print(f"[command_router] casilla seleccionada: {cell}")
        actions.select_board_cell(self.gui, cell, on_zones=self._on_board_zones_detected)
        try:
            self.gui.set_board_active(True)
        except Exception:
            pass

    def _on_board_zones_detected(self, cell: int, zones: list):
        """Callback de actions.select_board_cell(), llamado en el hilo
        de Qt tras recortar casilla.png y detectar sus zonas clicables.
        Se ignora si mientras tanto se seleccionó/deseleccionó otra
        casilla (detección obsoleta)."""
        if self.board_selected_cell != cell:
            return
        self.board_zones = zones
        if DEBUG:
            print(f"[command_router] {len(zones)} zona(s) detectada(s) en casilla {cell}")

    def _deselect_board_cell(self):
        if self.board_selected_cell is None:
            return
        self.board_selected_cell = None
        self.board_offset_x = 0
        self.board_offset_y = 0
        self.board_zones = []
        actions.deselect_board_cell(self.gui)
        try:
            self.gui.set_board_active(False)
        except Exception:
            pass

    def _nudge_board(self, vector: tuple, pixels: int):
        if self.board_selected_cell is None:
            return
        dx, dy = vector
        ox, oy = board.clamp_offset(
            self.board_selected_cell,
            self.board_offset_x + dx * pixels,
            self.board_offset_y + dy * pixels,
        )
        self.board_offset_x, self.board_offset_y = ox, oy
        if DEBUG:
            print(f"[command_router] ajuste fino -> offset=({ox},{oy})")
        actions.nudge_board_marker(self.gui, self.board_selected_cell, ox, oy, self.board_zones)

    # ---------- Fase 2: modo zoom_out interactivo (puntero verde, PDF NuevoGUI) ----------

    def _enter_zoom_out_interactive(self, cell: int):
        """Entra en modo zoom_out interactivo para `cell` -- comando de
        voz "mover <casilla n>" (antes movía el cursor real al
        instante; ahora solo entra en un modo de ajuste, ver PDF de
        diseño "NuevoGUI"). El puntero verde arranca SIEMPRE en el
        CENTRO del cuadrante (offset 0,0) -- ANTES se intentaba
        extrapolar desde la última posición real conocida, pero el
        seguimiento táctil (gui._do_touch_track) necesita partir de un
        punto de referencia fiable y consistente para calcular bien el
        movimiento; centrado siempre es ese punto fiable, sin depender
        de ningún cálculo de extrapolación previo."""
        ox, oy = 0, 0
        # Cualquier otra vista APAGA el foco. Si no, se queda activo por
        # detras: su recaptura se cuela luego encima de lo que estes mirando,
        # y la webapp sigue creyendo que la vista es "foco". Lo noto el --
        # despues de hacer clic aparecia la ventana enfocada sin haberla
        # pedido.
        self._foco_activo = False
        self._zoom_out_active_cell = cell
        self._zoom_out_offset_x, self._zoom_out_offset_y = ox, oy
        if DEBUG:
            print(f"[command_router] modo zoom_out interactivo -> casilla {cell}, puntero verde centrado (0,0)")
        actions.enter_zoom_out_interactive(self.gui, cell, ox, oy)

    def _nudge_zoom_out(self, vector: tuple, pixels: int):
        if self._zoom_out_active_cell is None:
            return
        dx, dy = vector
        cell = self._zoom_out_active_cell
        ox, oy = board.zoom_out_clamp_offset(
            cell,
            self._zoom_out_offset_x + dx * pixels,
            self._zoom_out_offset_y + dy * pixels,
        )
        self._zoom_out_offset_x, self._zoom_out_offset_y = ox, oy
        if DEBUG:
            print(f"[command_router] ajuste fino zoom_out -> offset=({ox},{oy})")
        actions.nudge_zoom_out_marker(self.gui, cell, ox, oy)

    def _nudge_foco(self, vector: tuple, pixels: int):
        """Mueve el puntero verde de la vista foco con las palabras del
        compas. Puro dibujo: el raton real no se toca."""
        if not self._foco_activo:
            return
        dx, dy = vector
        ox, oy = board.foco_clamp_offset(self._foco_offset_x + dx * pixels,
                                         self._foco_offset_y + dy * pixels)
        self._foco_offset_x, self._foco_offset_y = ox, oy
        if DEBUG:
            print(f"[command_router] foco: puntero verde a offset=({ox},{oy})")
        if self.gui is not None:
            try:
                self.gui.show_foco(ox, oy)
            except Exception as exc:
                print(f"[command_router] no se pudo mover el puntero del foco: {exc!r}")

    def _fire_foco_action(self, handler_name: str, offset: tuple | None = None):
        """Actua en la posicion REAL del puntero verde de la vista foco.

        Igual que en zoom_out: mientras se coloca el puntero no se mueve
        nada real; solo al decir la accion se actua en el punto que le
        corresponde en el escritorio.
        """
        if not self._foco_activo:
            return
        kind = actions.VC_HANDLER_KIND.get(handler_name)
        if kind is None:
            return
        ox, oy = offset if offset is not None else (self._foco_offset_x, self._foco_offset_y)
        if DEBUG:
            origen = "verde/tactil" if offset is not None else "ajuste fino/compas"
            print(f"[command_router] accion de foco ({origen}): {kind} offset=({ox},{oy})")
        # Si todavia se esta refrescando la imagen de la accion anterior, lo
        # que se ve en pantalla es de ANTES, y el clic puede caer donde no
        # toca. No se bloquea nada -- un programa de accesibilidad no puede
        # pedirle a nadie que vaya despacio -- pero se avisa, en pantalla y
        # sin voz. Idea suya: "puede sugerir que no digiere si le avasallan".
        if self._foco_recapturando:
            ahora = time.monotonic()
            if ahora - self._ultimo_aviso_ritmo > 20:
                self._ultimo_aviso_ritmo = ahora
                if self.gui is not None:
                    try:
                        self.gui.update_suggestion(
                            "Voy por detras: espera a ver la imagen nueva")
                    except Exception:
                        pass

        actions.fire_foco_action(self.gui, ox, oy, kind)

        def _otra_vez():
            # Con el foco aun abierto, por el camino de siempre (recaptura
            # incluida); si ya se salio, en el mismo punto de la pantalla.
            if self._foco_activo:
                self._fire_foco_action(handler_name, offset=(ox, oy))
            else:
                actions.fire_foco_action(self.gui, ox, oy, kind)
        self._recordar_desplazamiento(kind, _otra_vez)

        # A diferencia de zoom_out, la vista foco NO se cierra al actuar.
        #
        # zoom_out esta pensado para apuntar una vez a un sitio del
        # escritorio y salir. Foco es lo contrario: estas TRABAJANDO dentro
        # de un programa, y ahi quieres pulsar varias veces seguidas sin
        # repetir "foco" a cada una.
        #
        # Se vuelve a capturar, ademas, porque despues de un clic la ventana
        # ya no esta como estaba: quedarse con la imagen vieja seria enseñar
        # algo que ya no existe, y el siguiente clic caeria donde no toca.
        self._foco_offset_x = 0
        self._foco_offset_y = 0

        self._foco_recapturando = True

        def _recapturar():
            try:
                if self._foco_activo and actions.enter_foco(self.gui):
                    return
            except Exception as exc:
                print(f"[command_router] no se pudo recapturar el foco: {exc!r}")
            self._foco_activo = False
        def _recapturar_y_soltar():
            try:
                _recapturar()
            finally:
                self._foco_recapturando = False

        # Con un respiro: la ventana tiene que terminar de reaccionar al clic
        # antes de fotografiarla, o se captura el estado anterior.
        threading.Timer(0.6, _recapturar_y_soltar).start()

    def _fire_zoom_out_action(self, handler_name: str, offset: tuple | None = None):
        if self._zoom_out_active_cell is None:
            return
        kind = actions.VC_HANDLER_KIND.get(handler_name)
        if kind is None:
            return
        cell = self._zoom_out_active_cell
        ox, oy = offset if offset is not None else (self._zoom_out_offset_x, self._zoom_out_offset_y)
        if DEBUG:
            origen = "verde/táctil" if offset is not None else "ajuste fino/compás"
            print(f"[command_router] acción de zoom_out ({origen}): {kind} en casilla {cell} offset=({ox},{oy})")
        actions.fire_zoom_out_action(self.gui, cell, ox, oy, kind, on_result=self._on_zoom_out_action_result)
        self._recordar_desplazamiento(kind, lambda: actions.fire_zoom_out_action(
            self.gui, cell, ox, oy, kind, on_result=self._on_zoom_out_action_result))
        # se reconoce como terminado AQUÍ (ver PDF: "solo se reconoce
        # como terminado cuando la acción... se lleve a cabo") -- no se
        # espera a on_result (que llega más tarde, desde el hilo de Qt,
        # y solo sirve para actualizar la última posición conocida)
        self._zoom_out_active_cell = None
        self._zoom_out_offset_x = 0
        self._zoom_out_offset_y = 0

    def _on_zoom_out_action_result(self, real_pos):
        """Callback de actions.fire_zoom_out_action(), llamado en el
        hilo de Qt cuando la acción atómica termina de verdad -- ya no
        se usa para arrancar el siguiente "mover <n>" (que ahora
        siempre centra el puntero verde, ver _enter_zoom_out_interactive),
        se deja solo para depuración/uso futuro."""
        if DEBUG and real_pos is not None:
            print(f"[command_router] acción de zoom_out completada en posición real {real_pos}")

    # ---------- Fase 3 (PDF NuevoGUI): puente con la webapp (puntero rojo) ----------

    def _entrar_en_foco(self, nombre: str = "") -> None:
        """Entra en la vista "foco" -- comando de voz "foco"/"focus".

        Con `nombre` ("foco kate"), se ensena ESA ventana. Sin el, la que
        estuviera activa.

        Recaptura el escritorio y recorta de ahi la ventana activa. Los otros
        dos modos interactivos se apagan: son mutuamente excluyentes, igual
        que zoom_out y casilla entre si.
        """
        self._zoom_out_active_cell = None
        self.board_selected_cell = None
        self._foco_activo = True
        self._foco_offset_x = 0
        self._foco_offset_y = 0
        # Se guarda para "refrescar": recapturar el foco es volver a
        # recortar ESTA ventana, y sin el nombre se recortaria la activa.
        self._foco_nombre = nombre
        ok = actions.enter_foco(self.gui, nombre)
        if not ok:
            self._foco_activo = False
            # Corto a proposito: es un aviso, no una explicacion. Quien lo
            # oiga ya sabe que acaba de pedir foco.
            if nombre:
                texto = f"{nombre} no tiene foco. Abrela."
                en_pantalla = f"{nombre}: no hay ninguna ventana asi"
                print(f"[command_router] foco: no hay ventana {nombre!r}")
            else:
                texto = "Foco vacio."
                en_pantalla = "Foco vacio: no hay ninguna ventana"
                print("[command_router] foco vacio: no hay ventana que ensenar")
            if self.gui is not None:
                try:
                    self.gui.update_suggestion(en_pantalla)
                except Exception:
                    pass
            try:
                tts.get_speaker().say(texto, tts.HELP)
            except Exception:
                pass
            return
        # NO se avisa por voz de que la ventana sea "la ultima conocida".
        #
        # El GUI se baja ANTES de mirar cual es la activa, asi que lo normal
        # es que delante quede ya la ventana buena -- mismo comportamiento
        # que al entrar el texto dictado: baja, actua, sube. Si aun asi la
        # activa sigue siendo la nuestra, la que se ensena es igualmente la
        # que el usuario estaba usando, que es lo que ha pedido. Decirselo
        # cada vez seria dar la lata con algo que no tiene que hacer.
        #
        # Queda como nota en pantalla, que no interrumpe a nadie.
        recordada = board.foco_recordada()
        en_pantalla = ("Ultima ventana conocida" if recordada
                       else "Vista de la ventana activa")

        print("[command_router] vista foco activa"
              + ("  (ventana recordada)" if recordada else ""))
        if self.gui is not None:
            try:
                self.gui.update_suggestion(en_pantalla)
            except Exception:
                pass

    def actualizar_puntero_rojo(self, fx: float, fy: float) -> None:
        """El movil dice donde tiene su punto rojo. Lo llama la webapp."""
        self._rojo_fx = min(max(float(fx), 0.0), 1.0)
        self._rojo_fy = min(max(float(fy), 0.0), 1.0)

    def _actuar_en_puntero_rojo(self, handler_name: str) -> bool:
        """Ejecuta la accion donde el MOVIL tiene su punto rojo.

        Es lo que hace usable el modo cara: quien mueve el puntero con la
        cabeza no puede pulsar los botones de la pantalla, asi que la unica
        forma de hacer clic es decirlo.
        """
        if self._rojo_fx is None:
            try:
                tts.get_speaker().say(textos.t("sin_puntero_movil"),
                                      tts.HELP)
            except Exception:
                pass
            return False
        kind = actions.VC_HANDLER_KIND.get(handler_name)
        if kind is None:
            return False
        estado = self.get_board_state()
        if DEBUG:
            print(f"[command_router] accion en el puntero rojo: {kind} "
                  f"fx={self._rojo_fx:.3f} fy={self._rojo_fy:.3f} "
                  f"view={estado['view']}")
        self.fire_virtual_action_from_webapp(
            estado["view"], estado["cell"], self._rojo_fx, self._rojo_fy, kind)
        return True

    def get_board_state(self) -> dict:
        """Qué imagen debería estar mostrando la webapp AHORA MISMO como
        fondo de su touchpad virtual (puntero rojo), para que siga
        exactamente la misma "pantalla" que el GUI de escritorio
        (puntero verde) -- llamado por webapp/app.py vía
        set_board_state_bridge(), expuesto en GET /board/info.

        Devuelve {"view": "tablero"|"foco"|"zoom_out"|"casilla", "cell": int|None}
        -- "tablero" (cell=None) es la "pantalla inicial" del PDF (nada
        seleccionado); "zoom_out"/"casilla" son los mismos dos modos
        interactivos que ya usa el GUI (mutuamente excluyentes, se
        comprueban en el mismo orden que en on_final())."""
        if self._foco_activo:
            return {"view": "foco", "cell": None,
                    "seleccion": bool(self._seleccion_origen)}
        if self._zoom_out_active_cell is not None:
            return {"view": "zoom_out", "cell": self._zoom_out_active_cell,
                    "seleccion": bool(self._seleccion_origen)}
        if self.board_selected_cell is not None:
            return {"view": "casilla", "cell": self.board_selected_cell,
                    "seleccion": bool(self._seleccion_origen)}
        return {"view": "tablero", "cell": None,
                "seleccion": bool(self._seleccion_origen)}

    def fire_virtual_action_from_webapp(self, view: str, cell, fx: float, fy: float, kind: str):
        """Puente para actions.fire_virtual_action() desde la webapp
        (POST /board/virtual_action, ver webapp/app.py
        set_virtual_action_bridge()) -- el arrastre del punto ROJO en
        la webapp es 100% del lado del cliente (ver JS,
        webapp/static/index.html), esto solo se llama UNA vez, al
        confirmar la acción, igual que el puntero verde del GUI
        (_fire_zoom_out_action).

        Tras disparar la acción, se resetea el estado interactivo
        (`_zoom_out_active_cell`/`board_selected_cell`) -- la acción ya
        se confirmó, se vuelve a la "pantalla inicial" tanto para el
        GUI (gui.show_board_overview(), dentro de
        actions.fire_virtual_action) como para el propio estado del
        router, que es de donde lee get_board_state() para la
        webapp."""
        # Los toques del movil NO pasan por el filtro de voz -- entran por
        # HTTP, autenticados con la contrasena de la webapp -- asi que sin
        # esta comprobacion siguen actuando aunque el ordenador este en
        # espera o pidiendo el santo y sena. Lo vio el 5-sep-2026: la
        # pantalla decia "di tu santo y sena" y desde el movil se podia
        # hacer clic donde fuera.
        #
        # No es un detalle: la espera existe justo para que dejar el
        # ordenador solo no lo deje abierto. Si el movil se queda con la
        # sesion abierta en el navegador, cualquiera que lo coja se salta
        # la espera entera. La contrasena de la webapp protege el canal;
        # esto protege el ESTADO.
        motivo = self._por_que_no_puedo_actuar()
        if motivo:
            print(f"[command_router] acción del móvil rechazada ({motivo}): "
                  f"{kind} view={view}")
            return motivo

        if cell is None:
            cell = self._zoom_out_active_cell or self.board_selected_cell or 1
        if DEBUG:
            print(f"[command_router] acción virtual desde la webapp: {kind} "
                  f"view={view} cell={cell} fx={fx:.3f} fy={fy:.3f}")
        actions.fire_virtual_action(self.gui, view, cell, fx, fy, kind)
        # Tambien los del movil y los de "<accion> rojo": pasan todos por aqui.
        self._recordar_desplazamiento(kind, lambda: self.fire_virtual_action_from_webapp(
            view, cell, fx, fy, kind))
        self._zoom_out_active_cell = None
        self._zoom_out_offset_x = 0
        self._zoom_out_offset_y = 0
        # La vista "foco" tambien se cierra al actuar, igual que las otras:
        # sin esto, el movil se quedaria ensenando la ventana como estaba
        # ANTES del clic, y el GUI habria vuelto a la vista general.
        self._foco_activo = False
        self._foco_offset_x = 0
        self._foco_offset_y = 0
        self._deselect_board_cell()

    # Secciones de commands.json que se recorren para armar la ventana de
    # ayuda, en el orden en que aparecen en ella. Solo se listan las
    # entradas que tengan un campo "help" (texto de una línea) -- así la
    # lista es CURADA y editable desde el propio commands.json: añadir o
    # quitar un "help" es lo único que hace falta para que un comando
    # entre o salga de la ayuda, sin tocar código.
    # (nombre_seccion, solo_en_idle): vc_commands y app_commands se
    # listan SOLO en idle porque, aunque en commands.json tengan scope
    # "any", mientras se dicta no actúan como comandos -- lo que se dice
    # ahí es texto para el Pre-Texto. Listarlos en dictado sería mentir.
    _HELP_SECTIONS = (
        ("control_words", False),
        ("vc_commands", True),
        ("app_commands", True),
        # Los comandos que son UN NUMERO. Decir "cuarenta y cinco" entra en
        # la casilla 45, y hasta el 5-sep-2026 eso NO SALIA EN LA AYUDA:
        # existia en el codigo (_try_parse_bare_cell) pero no en
        # commands.json, y la ayuda se construye leyendo commands.json.
        # Quien preguntara "que puedo decir" no se enteraba de lo mas util
        # que tiene el programa.
        ("comandos_con_rango", True),
        # Los que llevan un nombre detras ("carpeta descargas"): tampoco
        # pueden ser alias fijos, y sin esto no saldrian en la ayuda.
        ("comandos_con_nombre", True),
    )

    # RESUMIR LAS ACCIONES MECANICAS EN UNA LINEA
    # ------------------------------------------------------------------
    # En escucha, control_words aporta 58 lineas de las 64 de la ayuda. Y
    # 40 de esas 58 son teclas y acciones de toda la vida -- copiar, Intro,
    # maximizar -- que no hace falta leer una por una: quien las necesita ya
    # sabe que existen, y quien no, no las estaba buscando.
    #
    # Asi que van agrupadas: una linea por grupo, con unos pocos ejemplos y
    # cuantas quedan. La ayuda pasa de 64 lineas a 30, que es lo que se
    # puede leer de una ojeada.
    #
    # LO QUE NO SE AGRUPA, que es la decision de verdad: las propias del
    # programa (ayuda, dictar, standby, tablero, foco, cerrar...) se
    # quedan con su linea entera. Esas SI hay que leerlas: no se pueden
    # adivinar, no existen fuera de aqui, y son las que sacan de un atasco.
    #
    # Un comando que se anada manana a commands.json y no este aqui sale con
    # su linea propia. Es el fallo correcto: aparece de mas, no de menos.
    _GRUPOS_AYUDA = (
        ("grupo_portapapeles", (
            "copiar", "pegar", "cortar", "seleccionar_todo", "deshacer",
            "guardar", "guardar_como", "buscar", "nuevo_archivo",
            "imprimir", "renombrar", "actualizar_vista")),
        ("grupo_teclas", (
            "enter", "escape", "tab", "tabulador_atras", "retroceso",
            "eliminar", "espacio", "inicio", "fin", "pagina_arriba",
            "pagina_abajo", "arriba", "abajo", "izquierda", "derecha")),
        ("grupo_desplazar", (
            "scroll_arriba", "scroll_abajo", "scroll_izquierda",
            "scroll_derecha", "scroll_arriba_una", "scroll_abajo_una",
            "scroll_izquierda_una", "scroll_derecha_una",
            "repetir_desplazamiento")),
        ("grupo_ventanas", (
            "minimizar_ventana", "maximizar_ventana", "restaurar_ventana",
            "pantalla_completa", "cerrar_la_ventana", "ventana_encima",
            "pestana_siguiente", "pestana_anterior", "cambiar_ventana")),
    )

    # Cuantos ejemplos se ensenan de cada grupo antes del "y N mas".
    _EJEMPLOS_POR_GRUPO = 4

    def _help_lines(self, state: str, situacion: str = None):
        """Devuelve (lineas, n_sin_descripcion) para el estado dado
        ("IDLE" o "DICTATING"), leyendo commands.json -- así los aliases
        que se muestran son EXACTAMENTE los que están activos, incluidos
        los que el usuario haya personalizado."""
        wanted = "idle" if state == "IDLE" else "dictating"
        situacion = situacion or self._situacion()
        lines, undocumented = [], 0

        # LAS DIRECCIONES, primero y solo donde sirven.
        #
        # board_directions no estaba en la ayuda EN ABSOLUTO, y es lo unico
        # util cuando estas dentro de una casilla: mover el punto verde. Se
        # descubrio el 5-sep-2026 al replantear la ayuda.
        #
        # Van arriba a proposito: si estas dentro de una casilla, eso es lo
        # que quieres saber, no la lista de teclas especiales.
        if situacion in self._SITUACIONES_CON_DIRECCIONES:
            cardinales, diagonales = [], []
            for name, entry in self.cfg.get("board_directions", {}).items():
                if name.startswith("_") or not isinstance(entry, dict):
                    continue
                alias = [a for a in (entry.get("aliases") or [name])
                         if a not in self._DIRECCIONES_EN_INGLES]
                if not alias:
                    continue
                # CARDINALES y DIAGONALES eligen distinto, y no es capricho:
                #
                #   cardinales -> el SEGUNDO alias. El primero es el termino
                #     de mapa ("oeste") y el segundo el de andar por casa
                #     ("izquierda"), que es como habla la gente.
                #
                #   diagonales -> el PRIMERO, que es la forma canonica en
                #     espanol de Espana: noreste, noroeste, sureste,
                #     suroeste. Las variantes con "d" -- nordeste, sudeste,
                #     sudoeste -- se siguen ACEPTANDO al decirlas (estan en
                #     los alias), pero chirrian al leerlas: meter esa "d" es
                #     un anglicismo.
                #
                # La primera version cogia el ultimo alias espanol en los
                # dos casos, y en las diagonales eso daba justo la variante
                # con "d".
                es_diagonal = len(name) > 5
                elegido = alias[0] if es_diagonal else (
                    alias[1] if len(alias) > 1 else alias[0])
                (diagonales if es_diagonal else cardinales).append(elegido)
            if cardinales:
                lines.append(f"  • {' / '.join(cardinales)} — "
                             f"{textos.t('direcciones_cardinales')}")
            if diagonales:
                lines.append(f"  • {' / '.join(diagonales)} — "
                             f"{textos.t('direcciones_diagonales')}")

        # nombre de comando -> titulo de su grupo. Se arma aqui y no como
        # constante porque _GRUPOS_AYUDA se lee mejor por grupos.
        grupo_de = {n: titulo for titulo, nombres in self._GRUPOS_AYUDA
                    for n in nombres}
        agrupados = {}

        for section_name, idle_only in self._HELP_SECTIONS:
            if idle_only and state != "IDLE":
                continue
            for name, entry in self.cfg.get(section_name, {}).items():
                if name.startswith("_") or not isinstance(entry, dict):
                    continue
                scope = entry.get("scope", "any")
                if scope not in (wanted, "any"):
                    continue
                # El texto en la lengua materna. Si no está traducido se
                # usa el español: una ayuda a medio traducir es incómoda,
                # una ayuda vacía es inservible.
                help_text = entry.get("help")
                if textos.idioma() != "es":
                    help_text = entry.get(f"help_{textos.idioma()}") or help_text
                if not help_text:
                    undocumented += 1
                    continue
                # Si va en un grupo, no se pinta su linea: se apunta y se
                # resume abajo. Se guarda el PRIMER alias, que es como se
                # dice de verdad ("copiar", no "copiar_al_portapapeles").
                # COMO SE LLAMA EL COMANDO en la lengua materna.
                #
                # Todos los alias siguen valiendo al hablar, en los dos
                # idiomas: esto es solo con cuál se presenta. Enseñarle
                # "scroll arriba" a un inglés en su propia ayuda es
                # enseñarle algo que no va a decir nunca.
                #
                # `alias_en` está comprobado contra la lista de alias al
                # generarlo: no puede anunciar un nombre que luego no
                # funcione. Y si un comando no tiene alias inglés, sale el
                # español, que es lo correcto -- así se dice de verdad.
                aliases = list(entry.get("aliases", [name]))
                propio = entry.get(f"alias_{textos.idioma()}")
                if propio and propio in aliases:
                    aliases.remove(propio)
                    aliases.insert(0, propio)

                grupo = grupo_de.get(name)
                if grupo is not None:
                    agrupados.setdefault(grupo, []).append(
                        aliases[0] if aliases else name)
                    continue
                lines.append(f"  • {' / '.join(aliases[:3])} — {help_text}")

        # Los grupos, al final y en el orden declarado: lo propio del
        # programa arriba, lo mecanico abajo.
        for clave, _nombres in self._GRUPOS_AYUDA:
            ejemplos = agrupados.get(clave)
            if not ejemplos:
                continue
            n = self._EJEMPLOS_POR_GRUPO
            muestra = ", ".join(ejemplos[:n])
            resto = len(ejemplos) - n
            titulo = textos.t(clave)
            if resto > 0:
                cola = textos.t("grupo_y_mas", muestra=muestra, resto=resto)
            else:
                cola = muestra
            lines.append(f"  • {titulo} — {cola}")
        return lines, undocumented

    # ------------------------------------------------------------------
    # DONDE ESTOY: la ayuda depende de eso y de nada mas
    # ------------------------------------------------------------------
    #
    # "No me sirve como ayuda lo que no puedo hacer en el estado en que
    # estoy, porque ese comando no lo voy a poder usar." Dicho asi, la
    # ayuda deja de ser un catalogo y pasa a ser una respuesta.
    #
    # El estado no es solo IDLE/DICTATING: es lo que dicen los LED mas la
    # vista del tablero. Estar en escucha con una casilla abierta y estar en
    # escucha sin nada abierto son dos sitios distintos, y lo que se puede
    # hacer en cada uno tambien.

    def _situacion(self) -> str:
        """Donde estamos AHORA, con el detalle que le importa al usuario."""
        if getattr(self, "_standby", False):
            return "dormido"
        if self._voice_login_pending():
            return "login"
        if getattr(self, "_intruder_locked_until", 0):
            return "bloqueado"
        if self.state == "DICTATING":
            return "formulas" if self.formuling else "dictando"
        if getattr(self, "_foco_activo", False):
            return "foco"
        if getattr(self, "_zoom_out_active_cell", None):
            return "zoom_out"
        if self.board_selected_cell:
            return "casilla_con_zonas" if self.board_zones else "casilla"
        return "escucha"

    # Lo que se DICE en cada sitio. Escrito a mano y a proposito.
    #
    # Antes se leia la lista pelada de comandos: en escucha son unos
    # cuarenta nombres seguidos. Eso no es ayuda, es un inventario -- se
    # hace eterno y no se retiene nada.
    #
    # Aqui se cuenta QUE SE PUEDE HACER, en dos o tres frases, y sobre todo
    # COMO SEGUIR o COMO SALIR. Quien pide ayuda casi nunca quiere la lista:
    # quiere saber que hace ahora.
    #
    # La lista completa sigue estando, en la ventana, que sale a la vez.
    # Los textos viven en textos.py, con sus dos idiomas. Aqui solo se
    # piden. Ver textos.AYUDA_HABLADA y textos.TITULOS_AYUDA.

    def _ayuda_hablada(self) -> str:
        """Lo que se dice en alto: breve, y sobre DONDE ESTAS."""
        return textos.ayuda_hablada(
            self._situacion(),
            "Te escucho. Di tablero para ver las casillas, o dictar para "
            "empezar a escribir.")


    # Donde tienen sentido las direcciones del compas. En cualquier otro
    # sitio no hacen nada, asi que listarlas seria ensenar un comando que no
    # se puede usar -- justo lo que la ayuda no debe hacer.
    _SITUACIONES_CON_DIRECCIONES = ("casilla", "casilla_con_zonas",
                                    "zoom_out", "foco")

    # Los alias en ingles de las direcciones. Se filtran para que la ayuda
    # no salga mezclando idiomas ("nordeste / northwest / sudeste"), que fue
    # lo primero que salio al probarla. Funcionan igual al decirlos: esto es
    # solo para lo que se ENSENA.
    _DIRECCIONES_EN_INGLES = frozenset({
        "west", "east", "north", "south", "left", "right", "up", "down",
        "northeast", "northwest", "southeast", "southwest",
        "ne", "nw", "se", "sw",
    })

    def _help_spoken_text(self, state: str) -> str:
        """La misma ayuda, redactada para OÍRSE: "Puedes decir:" y la
        lista pelada de comandos, sin descripciones.

        Leer las descripciones era insufrible -- "tab, tecla Tabulador.
        espacio, barra espaciadora..." se hacía eterno y encima no se
        retenía nada. Dicha solo la palabra, la lista entera cabe en unos
        segundos y sirve para lo que sirve: recordar QUÉ se puede decir.
        Para el detalle está la ventana, que sale a la vez.

        Se dice el primer alias de cada comando, que en commands.json es
        siempre el más natural de los suyos."""
        wanted = "idle" if state == "IDLE" else "dictating"
        nombres = []
        for section_name, idle_only in self._HELP_SECTIONS:
            if idle_only and state != "IDLE":
                continue
            for name, entry in self.cfg.get(section_name, {}).items():
                if name.startswith("_") or not isinstance(entry, dict):
                    continue
                if entry.get("scope", "any") not in (wanted, "any"):
                    continue
                alias = entry.get("aliases", [name])[0]
                if alias not in nombres:      # varios comandos comparten alias
                    nombres.append(alias)
        if not nombres:
            return "No hay comandos disponibles aquí."
        # separados por comas: una enumeración se entiende mucho mejor
        # dicha de corrido que troceada en frases sueltas
        return "Puedes decir: " + ", ".join(nombres) + "."

    def _decir_codigo_emparejamiento(self) -> None:
        """Dice el código de emparejamiento de este ordenador.

        Sale del certificado de la webapp, así que no hay nada que generar ni
        que caducar: mientras el certificado no cambie, el código es el mismo.
        La misma cuenta está en la app de Android (Emparejamiento.java).
        """
        try:
            import hashlib
            import ssl as _ssl
            from pathlib import Path as _Path

            pem = _Path(config.PROJECT_ROOT) / "webapp_cert.pem"
            if not pem.exists():
                texto = ("Este ordenador todavía no tiene certificado, así que no "
                         "hay código. Se crea al configurar el acceso desde el móvil.")
                print("[command_router] código de emparejamiento: falta webapp_cert.pem")
            else:
                der = _ssl.PEM_cert_to_DER_cert(pem.read_text())
                huella = hashlib.sha256(der).hexdigest()
                doce = str(int(huella[:16], 16) % 10**12).zfill(12)
                # Se dicta de tres en tres, con pausas: doce cifras seguidas
                # no hay quien las siga, y menos para compararlas con otras.
                grupos = [doce[0:3], doce[3:6], doce[6:9], doce[9:12]]
                texto = ("El código de emparejamiento es: "
                         + ". ".join(" ".join(g) for g in grupos)
                         + ". Repito: " + ". ".join(" ".join(g) for g in grupos))
                print("[command_router] código de emparejamiento: "
                      + " ".join(grupos))
                if self.gui is not None:
                    try:
                        self.gui.update_suggestion(textos.t("codigo") + " ".join(grupos))
                    except Exception:
                        pass
        except Exception as exc:
            texto = "No he podido leer el código de emparejamiento."
            print(f"[command_router] no se pudo calcular el código: {exc!r}")

        try:
            tts.get_speaker().say(texto, tts.HELP)
        except Exception as exc:
            print(f"[command_router] no se pudo decir el código: {exc!r}")

    def _show_help(self, speak: bool = False):
        """Ventana flotante de ayuda (comando "ayuda"/"help", scope
        "any"): lista los comandos del estado actual y se cierra sola
        pasados config.HELP_POPUP_MS milisegundos.

        Con `speak=True` ("ayuda audio") además se lee en alto, con la
        redacción de _help_spoken_text()."""
        state = self.state
        situacion = self._situacion()
        lines, undocumented = self._help_lines(state, situacion)
        if undocumented:
            lines.append("")
            lines.append(f"  (+{undocumented} comandos más sin descripción — "
                         f'añádeles un campo "help" en commands.json)')
        # El titulo dice DONDE ESTAS, no solo el modo. "Escucha" y "Dentro
        # de una casilla" son sitios distintos y lo que se puede hacer en
        # cada uno tambien.
        title = textos.titulo_ayuda(
            situacion,
            "🎧 Escucha — puedes decir:" if state == "IDLE"
            else "✍ Dictando — puedes decir:")
        if DEBUG:
            print(f"[command_router] ayuda pedida en estado {state}: {len(lines)} líneas")
        try:
            self.gui.show_help(title, lines, config.HELP_POPUP_MS)
        except Exception as exc:
            print(f"[command_router] no se pudo mostrar la ayuda: {exc!r}")
        if speak:
            try:
                # LA NUEVA: breve, descriptiva y sobre DONDE ESTAS.
                # _help_spoken_text (la lista pelada de nombres) se conserva
                # justo debajo por si alguna vez se quiere volver a ella,
                # pero leer cuarenta nombres seguidos no es ayudar.
                hablado = self._ayuda_hablada()
                if not tts.get_speaker().say(hablado, tts.HELP):
                    print("[command_router] no hay voz disponible para la ayuda hablada "
                          "-- la ventana sí se ha mostrado")
            except Exception as exc:
                print(f"[command_router] no se pudo leer la ayuda en alto: {exc!r}")

    # ---------- enrolado del micrófono del móvil ----------

    def start_mobile_enrollment(self, force=False):
        """Graba el perfil de voz DEL MÓVIL, guiando las frases en alto.

        Hace falta uno propio porque el perfil del PC no sirve ahí:
        medido, la misma frase daba "CORRECTO" por el micro del PC y
        **0,111** por el del móvil -- la compresión Opus y el remuestreo
        mueven demasiado el x-vector.

        Vive dentro de la aplicación y no en un script aparte porque el
        audio del móvil llega por la webapp, que corre en ESTE mismo
        proceso: un script externo no tendría forma de verlo.

        Se dispara solo la primera vez que se conecta el móvil (ver
        on_network_connected). `force=True` lo repite aunque ya exista."""
        if self._enroll_state is not None:
            return
        verificador = speaker_id.SpeakerVerifier("network")
        if verificador.enabled and not force:
            return   # ya hay perfil del móvil
        frases = list(getattr(config, "MOBILE_ENROLL_PHRASES", []))
        if not frases:
            return
        self._enroll_state = {"frases": frases, "i": 0, "vectores": [],
                              "descartadas": 0}
        print(f"[command_router] enrolando el micrófono del móvil "
              f"({len(frases)} frases)")
        fn = self._enrollment_callback
        if fn is not None:
            fn("network", self._on_enroll_sample)
        self._ask_enroll_phrase()

    def _ask_enroll_phrase(self):
        e = self._enroll_state
        if e is None:
            return
        frase = e["frases"][e["i"]]
        texto = f"Frase {e['i'] + 1} de {len(e['frases'])}. Repite: {frase}"
        try:
            self.gui.update_suggestion(
                textos.t("enrolando_movil", n=e["i"] + 1,
                         total=len(e["frases"]), frase=frase))
        except Exception:
            pass
        try:
            tts.get_speaker().say(texto, tts.HELP)
        except Exception:
            pass

    def _on_enroll_sample(self, vector, text):
        """Una frase del móvil durante el enrolado. La llama
        voice_recognizer con el x-vector ya calculado."""
        e = self._enroll_state
        if e is None:
            return
        if not vector:
            # Sin x-vector la frase no sirve, pero NO se avanza: se pide
            # otra vez la misma. Avanzar con menos muestras de las
            # previstas daría un perfil peor sin que se notara.
            e["descartadas"] += 1
            print(f"[command_router] muestra sin x-vector ({text!r}): se repite")
            try:
                tts.get_speaker().say(textos.t("no_te_he_oido"),
                                      tts.HELP)
            except Exception:
                pass
            return
        e["vectores"].append(list(vector))
        e["i"] += 1
        print(f"[command_router] muestra {len(e['vectores'])}/{len(e['frases'])} "
              f"recogida ({text[:40]!r})")
        if e["i"] < len(e["frases"]):
            self._ask_enroll_phrase()
        else:
            self._finish_mobile_enrollment()

    def _finish_mobile_enrollment(self):
        """Promedia las muestras y guarda el perfil del móvil."""
        e = self._enroll_state
        self._enroll_state = None
        fn = self._enrollment_callback
        if fn is not None:
            fn("network", None)      # se acaba el modo enrolado
        if e is None or len(e["vectores"]) < 3:
            print("[command_router] enrolado del móvil cancelado: muy pocas muestras")
            return

        import json as _json
        import math as _math
        normalizados = []
        for v in e["vectores"]:
            n = _math.sqrt(sum(x * x for x in v))
            if n:
                normalizados.append([x / n for x in v])
        if not normalizados:
            print("[command_router] enrolado del móvil cancelado: muestras inválidas")
            return
        dim = len(normalizados[0])
        media = [sum(v[i] for v in normalizados) / len(normalizados) for i in range(dim)]
        n = _math.sqrt(sum(x * x for x in media))
        perfil = [x / n for x in media] if n else media

        # coherencia interna: si sale baja, el perfil no va a servir de
        # nada y es mejor decirlo ahora que descubrirlo fallando después
        sims = [sum(a * b for a, b in zip(perfil, v)) for v in normalizados]
        peor = min(sims)

        destino = Path(config.SPEAKER_PROFILE_FILE_NETWORK)
        destino.parent.mkdir(parents=True, exist_ok=True)
        _guardar_perfil_con_copia(destino, _json.dumps({
            "profile": perfil,
            "meta": {"muestras": len(normalizados),
                     "descartadas": e["descartadas"],
                     "coherencia_min": round(peor, 3),
                     "coherencia_media": round(sum(sims) / len(sims), 3)},
        }, ensure_ascii=False, indent=2))
        print(f"[command_router] perfil del móvil guardado en {destino} "
              f"({len(normalizados)} muestras, coherencia mín {peor:.3f})")

        recargar = self._reload_profiles_callback
        if recargar is not None:
            try:
                recargar()
            except Exception as exc:
                print(f"[command_router] no se pudieron recargar los perfiles: {exc!r}")
        # Que el móvil se recargue: acaba de pasar a necesitar el santo y
        # seña, y su ciclo de grabación ya estaba en marcha con la
        # configuración anterior. Sin esto hay que cerrarlo y abrirlo a
        # mano, que es lo que pasaba al probarlo.
        self._client_reload_id += 1

        try:
            self.gui.update_suggestion(textos.t("voz_movil_aprendida"))
            tts.get_speaker().say(textos.t("voz_movil_aprendida_voz"), tts.HELP)
        except Exception:
            pass

    def on_network_connected(self):
        """La webapp avisa de que ya llega audio DECODIFICADO del móvil:
        la prueba de que su micrófono está abierto, igual que el primer
        bloque de `audio_level` lo es para el del PC (ver main.py).

        Dos casos, en este orden: si no hay perfil de ese micrófono se
        graba ahora -- única ocasión con audio suyo --; y si ya lo hay
        pero falta identificarse, se pide el santo y seña, ahora que sí
        puede oírse la respuesta."""
        if getattr(config, "MOBILE_ENROLL_ON_FIRST_CONNECT", True):
            self.start_mobile_enrollment()
            if self.is_enrolling():
                return      # el enrolado ya está hablando: no se solapa

        # Con perfil ya grabado, este es el momento correcto para pedir el
        # santo y seña: hay audio decodificado del móvil llegando, o sea
        # que su micrófono está abierto. Antes no se pedía en alto -- la
        # página mostraba el aviso, pero el ordenador no decía nada y no
        # había forma de saber desde cuándo escuchaba.
        origen_previo = self._source
        self._source = "network"
        try:
            if self._voice_login_pending():
                print("[command_router] micrófono del móvil listo: pidiendo santo y seña")
                self._ask_voice_login()
            else:
                self._source = origen_previo
        except Exception as exc:
            self._source = origen_previo
            print(f"[command_router] error pidiendo el santo y seña al móvil: {exc!r}")

    def set_enrollment_callback(self, fn):
        """fn(source, callback) -- normalmente
        recognizer_worker.set_enrollment."""
        self._enrollment_callback = fn

    def set_reload_profiles_callback(self, fn):
        self._reload_profiles_callback = fn

    def is_enrolling(self) -> bool:
        return self._enroll_state is not None

    # ---------- standby (ver config.STANDBY_AFTER_IDLE_S) ----------

    def _enter_standby(self, motivo="a petición"):
        """Deja de obedecer. Se vuelve diciendo el santo y sena, sin mas.

        La espera ES el cierre de sesion, y el santo y sena es la llave --
        no hacen falta dos pasos. Antes habia que decir "revive" y DESPUES
        el santo y sena; ademas de sobrar, era menos seguro: "revive" la
        puede decir cualquiera, y el santo y sena se valida por la voz.

        Por eso al entrar en espera se sube el liston de la voz al de login
        (config.VOICE_LOGIN_THRESHOLD). Sin eso, cualquier frase suya
        valdria con el umbral bajo de los comandos normales, y la espera
        dejaria de proteger nada.
        """
        if self._standby:
            return
        self._standby = True
        self._pintar_escucha()
        self._sesion()["ok"] = False
        # El liston alto, pero SIN pedir nada: no hace falta un aviso para
        # algo que se hace solo -- se dice el santo y sena y se entra.
        self._set_awaiting_login(True)
        print(f"[command_router] STANDBY ({motivo}): se vuelve con el santo y sena")
        try:
            self.gui.update_suggestion(textos.t("en_espera_sugerencia"))
        except Exception:
            pass
        try:
            tts.get_speaker().say(textos.t("me_pongo_en_espera"), tts.HELP)
        except Exception:
            pass

    def leave_standby(self):
        """Sale de standby desde fuera de la voz (bandeja del sistema).
        Sigue pidiendo el santo y seña: la bandeja despierta, no
        identifica."""
        if not self._standby:
            return
        self._standby = False
        self._sesion()["ok"] = False
        self._sesion()["fallos"] = 0
        self._ask_voice_login()

    def get_session_state(self) -> dict:
        """Estado de la sesión, para la webapp (ver
        webapp.set_session_state_bridge). Con esto el móvil sabe que NO
        debe pedir capturas ni refrescar nada mientras el PC no esté
        identificado -- y el servidor se niega a servirlas aunque las
        pida."""
        # Los dos estados son DISTINTOS y el móvil los usa para cosas
        # distintas, así que no pueden solaparse:
        #   - "standby": en espera. Al móvil le sirve para decirlo en su
        #     pantalla y dejar de pedir imágenes.
        #   - "awaiting_login": se espera el santo y seña, una frase
        #     larga. Ahí el móvil necesita trozos LARGOS para que no se
        #     parta.
        # Desde el 14-sep-2026 de la espera se sale con el santo y seña (ya
        # no hay "revive"), así que en espera también hacen falta los trozos
        # largos: con los de 5 s la frase podía quedar partida entre dos y
        # no reconocerse. Con "revive", una palabra, en espera se usaban los
        # cortos a propósito.
        en_standby = bool(self._standby)
        # Se informa de la sesión del MÓVIL, que es quien pregunta: su
        # identificación es independiente de la del PC (ver _sesion).
        # El móvil solo tiene que dar el santo y seña si su micrófono está
        # entre los que se verifican por voz; si no, le basta con la
        # contraseña de la webapp (ver config.SPEAKER_ID_SOURCES).
        # El móvil solo tiene que dar el santo y seña si (a) su micrófono
        # está entre los que se verifican por voz Y (b) ya existe un
        # perfil suyo contra el que comparar. Sin perfil no se le puede
        # pedir: se quedaría esperando una frase que nunca podría darse
        # por buena, en trozos de 15 s y sin imágenes.
        verifica_movil = ("network" in getattr(config, "SPEAKER_ID_SOURCES", ("device",))
                          and self._verifier_available("network"))
        pendiente = verifica_movil and not self._sesiones["network"]["ok"]
        return {
            # En espera, tambien: lo que despierta es el santo y seña.
            "awaiting_login": bool(pendiente or (en_standby and verifica_movil)),
            "standby": en_standby,
            # Si este número cambia, el móvil se recarga entero (ver
            # index.html). Hace falta porque hay cambios que su ciclo de
            # grabación no puede asumir a mitad: al terminar el enrolado
            # pasa a hacerle falta el santo y seña, con trozos de audio de
            # otra duración y con la petición de por medio. Recargar deja
            # la página en el estado nuevo desde cero.
            "reload_id": self._client_reload_id,
        }

    def is_standby(self) -> bool:
        return self._standby

    def check_idle_standby(self):
        """Entra en standby solo tras un rato sin oír nada reconocible.
        La llama el GUI con su temporizador de pausas.

        Distingue de verdad "sigue aquí" de "se ha ido", que es lo que un
        temporizador periódico no sabe hacer: preguntar cada quince
        minutos interrumpe estés o no, y no protege nada si te has ido a
        los dos minutos."""
        segundos = getattr(config, "STANDBY_AFTER_IDLE_S", 0)
        if not segundos or self._standby or self.state != "IDLE":
            return
        if not getattr(config, "VOICE_LOGIN_ENABLED", False):
            return
        if time.monotonic() - self._last_heard_ts >= segundos:
            self._enter_standby(f"{segundos/60:.0f} min sin actividad")

    # ---------- santo y seña (ver config.VOICE_LOGIN_*) ----------

    def _sesion(self, source=None) -> dict:
        """Estado de identificación del micrófono indicado (por defecto,
        el de la última frase). Cada micrófono lleva el suyo: ver
        __init__."""
        return self._sesiones[source or self._source]

    def _voice_login_pending(self) -> bool:
        """True mientras haya que identificarse y no se haya hecho.

        Se comprueba también si toca renovarlo (cada
        config.VOICE_LOGIN_INTERVAL_S), pero **nunca en mitad de un
        dictado**: interrumpir una frase a medias para pedir el santo y
        seña perdería lo dictado y sería insufrible. Se pospone hasta
        volver a escucha."""
        if not getattr(config, "VOICE_LOGIN_ENABLED", False):
            return False
        if not self._verifier_available():
            return False   # sin perfil de voz no se puede verificar a nadie
        if self._source not in getattr(config, "SPEAKER_ID_SOURCES", ("device",)):
            # Este micrófono no se verifica por voz (ver
            # config.SPEAKER_ID_SOURCES): el del móvil ya se ha
            # autenticado con la contraseña de la webapp, y pedirle
            # además el santo y seña sería pedirle algo que su audio no
            # puede demostrar.
            return False
        if not self._sesion()["ok"]:
            return True
        intervalo = getattr(config, "VOICE_LOGIN_INTERVAL_S", 0)
        if intervalo and self.state == "IDLE":
            if time.monotonic() - self._sesion()["ts"] >= intervalo:
                print("[command_router] toca renovar el santo y seña")
                self._sesion()["ok"] = False
                self._ask_voice_login()
                return True
        return False

    def _verifier_available(self, source=None) -> bool:
        """¿Hay perfil de voz para ESTE micrófono?

        Se mira el del origen actual y no siempre el del PC: sin perfil
        del móvil no se le puede pedir el santo y seña, porque no habría
        nada contra lo que comparar su respuesta -- se quedaría pidiendo
        una frase que jamás podría dar por buena."""
        try:
            return speaker_id.SpeakerVerifier(source or self._source).enabled
        except Exception:
            return False

    def set_awaiting_login_callback(self, fn):
        """fn(esperando: bool) -- normalmente
        recognizer_worker.set_awaiting_login. Sirve para que la
        verificación use el umbral del santo y seña (más exigente) en vez
        del de comandos mientras se está pidiendo."""
        self._awaiting_login_callback = fn

    def _set_awaiting_login(self, esperando: bool):
        fn = self._awaiting_login_callback
        if fn is None:
            return
        try:
            fn(bool(esperando))
        except Exception as exc:
            print(f"[command_router] no se pudo avisar del estado de login: {exc!r}")

    def _ask_voice_login(self):
        """Pide el santo y seña, en alto y por pantalla, y avisa al
        reconocedor para que suba el listón (umbral de login).

        NO se pide estando en espera: ahi el santo y sena entra solo (ver
        _enter_standby). Antes, en espera solo se atendia a "revive", asi que
        pedir el santo y sena era pedir algo que nadie iba a mirar: el
        usuario lo decia, el registro lo reconocia, y salia
        "en standby, ignorado". Bloqueo perfecto, y ademas invisible --
        la pantalla decia una cosa y el programa esperaba otra.

        Le paso de verdad, y fuera de casa, donde no podia reiniciar nada:
        estuvo diciendo el santo y sena contra una pantalla que se lo pedia
        mientras el programa lo tiraba. Y sin sesion abierta tampoco se
        servian las capturas (403), asi que no veia nada.
        """
        if self._standby:
            # En espera no se pide nada: el liston ya esta alto y basta con
            # decir el santo y sena (ver _enter_standby). Pedirlo aqui era
            # justo el bloqueo que le dejo tirado fuera de casa -- se lo
            # pedia y luego lo ignoraba.
            print("[command_router] en espera: el santo y sena entra solo")
            return
        self._set_awaiting_login(True)
        # NO se escribe la frase en pantalla: es su ordenador y se la sabe,
        # y dejarla puesta ahí solo serviría para que la leyera quien pasara
        # por delante. La frase de ejemplo (config.VOICE_LOGIN_HINT) se
        # queda para la calibración, que es donde hace falta.
        try:
            # urgente=True: letra grande y parpadeando. Aquí el programa
            # está ESPERANDO que el usuario hable, y si no se oye la
            # petición esta línea es lo único que lo dice.
            self.gui.update_suggestion(textos.t("pide_santo_y_sena"), urgente=True)
        except Exception:
            pass
        # La voz espera a que el microfono este ABIERTO.
        #
        # Sin esto el programa decia "santo y sena" mientras todavia cargaba
        # el modelo, y quien contestaba entonces hablaba al vacio. Por
        # pantalla ya se avisaba ("Espera, estoy arrancando"), pero quien no
        # ve la pantalla solo tiene la voz: para esa persona el programa
        # pedia algo que no podia oir.
        #
        # Va en un hilo aparte para no bloquear el arranque, y con tope: mas
        # vale un aviso tarde que un programa callado para siempre.
        def _pedir_cuando_escuche():
            try:
                import voice_recognizer as _vr
                _vr.esperar_microfono(90)
            except Exception:
                pass
            try:
                tts.get_speaker().say(textos.de_config("VOICE_LOGIN_PROMPT"), tts.HELP)
            except Exception as exc:
                print(f"[command_router] no se pudo pedir el santo y sena: {exc!r}")

        try:
            threading.Thread(target=_pedir_cuando_escuche,
                             name="pedir-santo-y-sena", daemon=True).start()
        except Exception:
            pass

    def _handle_voice_login(self, text: str, speaker_verdict: str):
        """Procesa una frase mientras se está esperando el santo y seña.

        Solo se mira LA VOZ, no lo que se diga (ver el bloque
        VOICE_LOGIN_* de config.py): la frase está para garantizar audio
        suficiente, que es lo que hace fiable al x-vector.

        Los tres veredictos se tratan MUY distinto, y ahí está la clave
        de que esto no acabe dejándole fuera:

          - "him"     -> dentro.
          - "unknown" -> la frase era demasiado corta para verificar: NO
            es un fallo, no cuenta. Se vuelve a pedir.
          - "other"   -> intento fallido de verdad. Estos sí cuentan, y a
            los config.VOICE_LOGIN_MAX_FAILURES se aborta.

        El silencio tampoco cuenta, por construcción: si nadie dice nada,
        aquí no entra nada y el contador no se mueve. Irse quince minutos
        no bloquea el ordenador, solo lo deja esperando.
        """
        if speaker_verdict == _HIM:
            self._sesion()["ok"] = True
            self._sesion()["ts"] = time.monotonic()
            self._sesion()["fallos"] = 0
            self._set_awaiting_login(False)
            print(f"[command_router] santo y seña CORRECTO: {text!r}")
            # Confirmación EXPLÍCITA, hablada y en pantalla. Antes la única
            # señal era que el aviso desapareciera, que es una señal muda:
            # trabajando sin mirar el monitor no había forma de saber
            # cuándo se podía empezar a dar órdenes.
            try:
                self.gui.update_suggestion(textos.t("te_escucho_ordenes"))
                # el mensaje se va solo al rato, como el resto de sugerencias
                self.gui.run_on_main_thread_delayed(self.gui.clear_suggestion, 4000)
            except Exception:
                pass
            try:
                texto = getattr(config, "VOICE_LOGIN_OK_TEXT", "")
                if texto:
                    tts.get_speaker().say(texto, tts.HELP)
            except Exception:
                pass
            return

        if speaker_verdict == _UNKNOWN:
            # ni acierto ni fallo: no había suficiente voz que analizar
            print(f"[command_router] santo y seña: frase demasiado corta "
                  f"para verificar ({text!r}) -- no cuenta")
            try:
                self.gui.update_suggestion(
                    "🔐 No he podido verificar tu voz: di una frase MÁS LARGA.")
            except Exception:
                pass
            return

        self._sesion()["fallos"] += 1
        maximo = getattr(config, "VOICE_LOGIN_MAX_FAILURES", 3)
        print(f"[command_router] santo y seña INCORRECTO "
              f"({self._sesion()["fallos"]}/{maximo}): {text!r}")
        if self._sesion()["fallos"] >= maximo:
            print("[command_router] *** demasiados santos y señas fallidos ***")
            self._trigger_intruder_abort()
            self._sesion()["fallos"] = 0
            return
        try:
            self.gui.update_suggestion(
                textos.t("esa_no_es_tu_voz",
                         fallos=self._sesion()["fallos"], maximo=maximo))
        except Exception:
            pass

    def start_voice_login(self):
        """Arranca la sesión pidiendo el santo y seña. La llama main.py
        una vez montado todo."""
        if not getattr(config, "VOICE_LOGIN_ENABLED", False):
            return
        if not self._verifier_available():
            print("[command_router] santo y seña desactivado: no hay perfil de voz "
                  "(créalo con tools/speaker_calibration.py)")
            return
        self._source = "device"
        self._sesion()["ok"] = False
        self._sesion()["fallos"] = 0
        self._ask_voice_login()

    # ---------- detección de intrusos y aborto (ver config.INTRUDER_*) ----------

    def _es_eco_del_otro_motor(self, norm: str, language: str) -> bool:
        """¿Es este comando el ECO del mismo, oído por el OTRO motor?

        Los dos motores transcriben el mismo audio, así que una sola
        palabra puede llegar dos veces como comando ("click" del inglés y
        "clic" del español). Sin filtrarlo, la acción se ejecuta dos
        veces por haber hablado una sola: dos flechas, dos clics.

        La condición es **mismo comando Y motor distinto**, no solo
        "mismo comando hace poco". Esa diferencia es la que importa:
        decir "arriba arriba" seguido para subir dos líneas es algo
        perfectamente normal, y con un filtro a ciegas se perdería la
        segunda. Dos repeticiones tuyas llegan siempre por el MISMO
        motor; el eco llega siempre por el otro.

        Se compara el COMANDO al que apunta el alias, no el texto: "up" y
        "arriba" son alias distintos del mismo comando y por tanto un
        eco."""
        objetivo = (self._any_control_map.get(norm)
                    or self._idle_control_map.get(norm)
                    or self._vc_action_alias_map.get(norm)
                    or self._app_command_alias_map.get(norm)
                    or norm)
        ventana = getattr(config, "DUPLICATE_COMMAND_WINDOW_S", 0)
        ahora = time.monotonic()
        eco = (ventana > 0
               and objetivo == self._ultimo_comando
               and language != self._ultimo_comando_lang
               and (ahora - self._ultimo_comando_ts) < ventana)
        # El registro se actualiza SIEMPRE, también al detectar un eco. Si
        # solo se actualizara al no haberlo, quedaría anclado al primer
        # comando y se comería todo lo que llegara después dentro de la
        # ventana: en la prueba, un "arriba" repetido a propósito dejaba
        # de funcionar porque seguía comparándose contra un "up" ya viejo.
        self._ultimo_comando = objetivo
        self._ultimo_comando_ts = ahora
        self._ultimo_comando_lang = language
        return eco

    def _looks_like_command(self, norm: str) -> bool:
        """¿Lo dicho es un comando DE VERDAD, y no una frase suelta?

        Es la cuarta condición del detector de intrusos, y la que de
        verdad separa "hay una tele puesta" de "hay alguien dándole
        órdenes a mi ordenador": el ruido de un telediario casi nunca cae
        justo en un alias de commands.json, mientras que quien intenta
        mandar en la máquina cumple esto por definición.

        Se comprueba contra TODAS las formas de comando que la aplicación
        acepta, no solo las palabras de control: un intruso que diga
        "click cuarenta y uno" o "terminal" está mandando igual."""
        if not norm:
            return False
        if (norm in self._any_control_map
                or norm in self._idle_control_map
                or norm in self._dictating_control_map):
            return True
        if norm in self._vc_action_alias_map or norm in self._app_command_alias_map:
            return True
        if self._try_parse_direct_vc(norm) or self._try_parse_bare_cell(norm) is not None:
            return True
        # "<accion> verde"/"green": es un comando reconocible aunque en este
        # instante no pueda ejecutarse (hace falta una posición del puntero
        # ya rastreada). _try_parse_board_action_green devuelve None en ese
        # caso, así que aquí se mira solo la FORMA de la frase.
        tokens = norm.split()
        if len(tokens) >= 2 and tokens[-1] in self._GREEN_WORDS:
            if " ".join(tokens[:-1]) in self._vc_action_alias_map:
                return True
        if len(tokens) >= 2 and tokens[-1] in self._RED_WORDS:
            if " ".join(tokens[:-1]) in self._vc_action_alias_map:
                return True
        # frases de desbloqueo: solo hacen algo estando bloqueado, pero
        # decirlas fuera de ese momento no es "no te entiendo"
        if norm in self._INTRUDER_UNLOCK_PHRASES:
            return True
        return False

    def _register_intruder_strike(self, text: str, confidence: float, peak_rms: float):
        """Suma un intento de intrusión si se cumplen las CUATRO
        condiciones (ver el bloque INTRUDER_* de config.py). Quien llama
        ya ha comprobado las dos primeras (no es su voz, y es un comando
        de verdad); aquí se miran la cercanía y la confianza.

        SIEMPRE se anota en el log, se cuente o no, con el rms y la
        confianza reales: son los números que hacen falta para calibrar
        INTRUDER_MIN_RMS, igual que el modo aviso del filtro por voz.

        DEVUELVE True solo si la prueba era SOLIDA (se ha contado). Ese
        valor es el que decide si se le corta la palabra a quien habla, y
        por eso importa tanto: una frase lejana o mal entendida no sirve
        para acusar a nadie, y tampoco debe servir para dejar a nadie sin
        obedecer. El 5-sep-2026 SI servia, y le paso a el: dijo "click"
        por el movil, lejos y flojo (rms 812 de 1500), el detector lo
        descarto por poco fiable... y el corte se aplico igualmente,
        dejandole con un aviso fijo en pantalla."""
        if not getattr(config, "INTRUDER_DETECTION_ENABLED", False):
            return False

        cerca = peak_rms >= config.INTRUDER_MIN_RMS
        claro = confidence >= config.INTRUDER_MIN_CONFIDENCE
        if not (cerca and claro):
            print(f"[command_router] comando de voz ajena NO contado "
                  f"({'lejos' if not cerca else 'confianza baja'}): {text!r} "
                  f"rms={peak_rms:.0f}/{config.INTRUDER_MIN_RMS} "
                  f"conf={confidence:.2f}/{config.INTRUDER_MIN_CONFIDENCE}")
            return False

        self._intruder_strikes += 1
        faltan = config.INTRUDER_STRIKES_TO_ABORT - self._intruder_strikes
        print(f"[command_router] INTRUSO {self._intruder_strikes}/"
              f"{config.INTRUDER_STRIKES_TO_ABORT}: {text!r} "
              f"rms={peak_rms:.0f} conf={confidence:.2f}")

        if faltan > 0:
            # aviso hablado espaciado (60 s por defecto): que se entere de
            # que alguien le está hablando al ordenador, sin convertirlo
            # en una alarma insoportable
            try:
                tts.get_speaker().say(textos.t("no_reconozco_tu_voz"), tts.INTRUDER)
            except Exception:
                pass
            return True

        self._trigger_intruder_abort()
        return True

    def _por_que_no_puedo_actuar(self):
        """Devuelve el motivo por el que AHORA no se debe actuar, o None.

        Un solo sitio con los tres estados en que el programa no obedece,
        para que no puedan discrepar el camino de la voz y el del movil.
        La voz ya los respetaba (cada uno con su `return` en on_final); los
        toques del movil no los miraban en absoluto.

        El orden importa poco, pero el texto si: va a llegar al movil tal
        cual, y tiene que decir QUE HACER, no solo que no se puede.
        """
        if getattr(self, "_standby", False):
            return "El ordenador está en espera. Di tu santo y seña."
        if self._voice_login_pending():
            return "Identifícate primero: di tu santo y seña."
        if getattr(self, "_intruder_locked_until", 0):
            return "Bloqueado por voz no reconocida. Di: soy yo."
        return None

    def _pintar_escucha(self):
        """Refresca el LED de escucha del GUI (activo / duda / dormido).

        Un solo sitio decide el estado, para que no puedan discrepar la
        pantalla y la realidad. Se llama en los tres momentos en que eso
        cambia: al dormirse, al despertar y al dudar de la voz.
        """
        if getattr(self, "_standby", False):
            estado = "dormido"
        elif getattr(self, "_dudando", False):
            estado = "duda"
        else:
            estado = "activo"
        try:
            self.gui.update_escucha(estado)
        except Exception:
            pass

    def _preguntar_si_eres_tu(self, text: str):
        """Voz no reconocida: preguntar, y NADA MAS.

        No se ejecuta la orden, no se bloquea el programa, no se castiga
        a nadie. Solo se pregunta en alto, espaciado, y se deja constancia
        por escrito.

        La pregunta VA con voz porque va dirigida a quien esta hablando:
        si el filtro se ha equivocado y eres tu, tienes que enterarte de
        que no te reconoce y de que puedes decir "soy yo".

        El aviso de posible intrusion, en cambio, va SIN VOZ: es para el
        dueno, no para quien esta delante. Sale por pantalla (parpadeando,
        urgente=True) y al log, que ahora sobrevive al reinicio. Decirlo en
        alto tendria dos problemas: avisa al intruso de que ha sido
        detectado, y si el dueno no esta delante no lo oye nadie.
        """
        self._dudando = True
        print(f"[command_router] voz no reconocida, NO se actua: {text!r}")
        self._pintar_escucha()
        try:
            tts.get_speaker().say(
                textos.de_config("VOZ_AJENA_PREGUNTA"),
                tts.INTRUDER)
        except Exception:
            pass
        try:
            self.gui.update_suggestion(
                textos.t("voz_no_reconocida_nada"), True)
        except Exception:
            pass

    def _trigger_intruder_abort(self):
        """Deja de obedecer TODA orden de voz hasta desbloquear."""
        if not getattr(config, "INTRUDER_ABORT_ENABLED", False):
            print("[command_router] se habría abortado por intrusión "
                  "(INTRUDER_ABORT_ENABLED=False: solo aviso)")
            self._intruder_strikes = 0
            return

        segundos = getattr(config, "INTRUDER_LOCK_SECONDS", 0)
        # `_intruder_locked_until` guarda el instante de caducidad, o
        # `math.inf` si no caduca sola. Un solo campo hace de interruptor
        # y de reloj: así no puede quedarse "bloqueado" con el reloj
        # caducado, ni al revés.
        self._intruder_locked_until = (time.monotonic() + segundos) if segundos else math.inf
        self._intruder_strikes = 0
        cuanto = f"{segundos:.0f}s" if segundos else "hasta desbloquear a mano"
        print(f"[command_router] *** ABORTO POR INTRUSIÓN *** "
              f"no se obedecerá ninguna orden ({cuanto})")
        try:
            self.gui.update_suggestion(textos.t("bloqueado_sugerencia"))
        except Exception:
            pass
        try:
            tts.get_speaker().say(textos.de_config("INTRUDER_ABORT_TEXT"), tts.HELP)
        except Exception:
            pass

    def _try_intruder_unlock(self, norm: str, speaker_ok: bool) -> bool:
        """Mientras está bloqueado, lo ÚNICO que se escucha. Devuelve True
        si se ha desbloqueado (o si el bloqueo ya había caducado).

        Tres vías de salida, a propósito:
          - **Caducidad** (config.INTRUDER_LOCK_SECONDS): red de seguridad
            deliberada. Si alguien consigue disparar el bloqueo a
            propósito, el daño queda acotado en el tiempo en vez de
            dejarte fuera de tu propio ordenador para siempre.
          - **Tu voz + la frase de desbloqueo**: solo cuenta si el filtro
            dice que eres tú (`speaker_ok`); si no, cualquiera podría
            decir "soy yo" y entrar.
          - **La bandeja del sistema** (ver gui), que no depende de la voz
            para nada -- imprescindible si el filtro se calibra mal.
        """
        if self._intruder_locked_until and time.monotonic() >= self._intruder_locked_until:
            print("[command_router] bloqueo por intrusión caducado")
            self.clear_intruder_lock()
            return True
        if speaker_ok and norm in self._INTRUDER_UNLOCK_PHRASES:
            print("[command_router] desbloqueado por voz reconocida")
            self.clear_intruder_lock()
            return True
        return False

    # Frases para desbloquear a viva voz. Solo funcionan si el filtro por
    # voz confirma que eres tú (ver _try_intruder_unlock).
    # LOS DOS IDIOMAS SIEMPRE, y no es descuido.
    #
    # Esto SÍ se compara como texto (al revés que el santo y seña, que solo
    # mira la voz). Con la lengua materna en inglés, el motor transcribe
    # "it's me" y no "soy yo": la salida por voz del bloqueo se quedaba
    # muerta, y peor aún, la propia ayuda inglesa te dice que digas
    # "it's me". Anunciar una salida que no funciona es peor que no
    # anunciarla.
    #
    # Se aceptan las dos listas SIEMPRE, en vez de cambiarlas con el idioma,
    # por una razón concreta: si alguien se bloquea justo después de cambiar
    # de idioma, o el idioma no es el que cree, la frase que le salga
    # naturalmente tiene que valer. Quedarse fuera es mucho peor que aceptar
    # de más.
    #
    # Y aceptar de más aquí NO abre nada: el desbloqueo exige `speaker_ok`
    # (ver _try_intruder_unlock). Un intruso diciendo "unlock" sigue
    # fallando la comprobación de voz. Lo único que hace esta lista es
    # decidir QUÉ PALABRAS se escuchan, no a quién se le hace caso.
    #
    # Aparte queda la bandeja del sistema, que no depende de la voz para
    # nada -- ver bandeja.py, "Desbloquear (intruso)".
    _INTRUDER_UNLOCK_PHRASES = frozenset({
        # español
        "soy yo", "desbloquear", "desbloquea", "continuar", "sigue",
        # inglés. Se meten las variantes que de verdad salen del motor:
        # _normalize NO quita el apóstrofo, así que "it's me" e "its me"
        # son dos cadenas distintas y hacen falta las dos.
        "it's me", "its me", "it is me", "unlock", "continue", "carry on",
        "go on",
    })

    def clear_intruder_lock(self):
        """Levanta el bloqueo y pone el contador a cero. Pública porque la
        llama también el menú de la bandeja (ver gui), que es la salida
        que NO depende de la voz."""
        self._intruder_locked_until = 0.0
        self._intruder_strikes = 0
        try:
            self.gui.clear_suggestion()
        except Exception:
            pass

    def is_intruder_locked(self) -> bool:
        return bool(self._intruder_locked_until)

    def _maybe_say_not_understood(self, text: str, norm: str, speaker_ok: bool,
                                  language: str = ""):
        """Dice "no te entiendo" en alto cuando el usuario le habla y no
        se le ha entendido.

        La condición importante es `speaker_ok`: **solo se le contesta a
        él**. En la prueba con las noticias puestas, el reconocedor cerró
        más de 150 frases ajenas en un rato, y ninguna encajaba con un
        comando -- sin esta condición, la aplicación estaría diciendo "no
        te entiendo" sin parar mientras hubiera una tele encendida.

        Con el filtro por voz apagado o sin perfil, `speaker_ok` es
        siempre True y entonces manda el límite de tiempo por categoría
        (config.TTS_MIN_INTERVAL_S) para que al menos no se solape.

        El resto de condiciones (dictando no, mínimo entre avisos) las
        aplica tts.Speaker.say() y son comunes a todos los avisos.
        """
        if not getattr(config, "TTS_NOT_UNDERSTOOD_ENABLED", False):
            return
        if not text or not speaker_ok:
            return

        # SOLO el idioma primario. Los dos motores (es y en) escuchan el
        # MISMO audio, así que una frase dicha en español genera además una
        # transcripción inglesa disparatada ("click verde" -> "click
        # berlin", "mover pie" -> "mobility f"). Contarlas -- y peor, decir
        # "no te entiendo" por ellas -- era contar dos veces el mismo
        # fallo: en la prueba real, la mayoría de los 34 "no entendidos" de
        # una sesión corta eran justo eso.
        if language and language != self.primary_language:
            return

        # Si lo dicho SÍ es un comando reconocible, no se avisa aunque no
        # haya podido ejecutarse: "click verde" sin puntero rastreado se
        # entendió perfectamente, lo que pasa es que ahora mismo no
        # procede. Decir "no te entiendo" ahí es sencillamente falso.
        if self._looks_like_command(norm):
            return

        # Las frases CORTAS avisan mucho menos (o nada, ver
        # config.TTS_MIN_INTERVAL_S). Con palabras de una sílaba el
        # reconocedor falla a menudo con algo parecido a lo dicho ("tab"
        # -> "adulador"), no encaja con ningún comando, y el aviso saltaba
        # tan seguido que molestaba más que ayudaba -- encima en los
        # casos en los que el comando suele acabar ejecutándose bien al
        # segundo intento.
        corta = len(text.split()) <= getattr(config, "TTS_NOT_UNDERSTOOD_SHORT_WORDS", 2)
        categoria = tts.NOT_UNDERSTOOD_SHORT if corta else tts.NOT_UNDERSTOOD
        try:
            said = tts.get_speaker().say(
            textos.de_config("TTS_NOT_UNDERSTOOD_TEXT"), categoria)
        except Exception as exc:
            print(f"[command_router] no se pudo avisar en alto: {exc!r}")
            return

        # Se anota SIEMPRE, se haya dicho en alto o no: son los fallos
        # reales de reconocimiento, y siguen interesando para ver qué
        # palabras se atragantan aunque la voz se haya callado.
        self._not_understood_count += 1
        print(f"[command_router] no entendido ({self._not_understood_count}): {text!r} "
              f"[{'corta' if corta else 'larga'}, "
              f"{'dicho en alto' if said else 'callado'}]")
        self._sugerir_pulsa_si_toca(text)

    # Cada cuanto, como poco, se vuelve a sugerir "pulsa" (segundos).
    _SUGERENCIA_PULSA_CADA_S = 120
    _PALABRAS_CLIC_FALLIDAS = frozenset({
        "clip", "lit", "mit", "jeep", "quit", "kit", "click", "clic", "clica",
    })

    def _sugerir_pulsa_si_toca(self, text: str) -> None:
        """Cuando falla un intento de clic sobre el puntero verde, sugerir
        "pulsa" -- SOLO por pantalla y de vez en cuando.

        El motor espanol no oye bien "click": se le atraganta el final, y lo
        transcribe como "clip", "lit", "mit", "jeep". Medido en una sesion
        real: 8 intentos perdidos contra 3 que llegaron, ninguno por la
        posicion. "Pulsa" no tiene ese problema.

        Se dice AQUI, cuando acaba de fallar, que es cuando sirve de algo. Y
        no se dice en alto: un aviso hablado cada vez que alguien dice "clic"
        acabaria siendo una regañina, y ademas interrumpe.
        """
        if self.gui is None:
            return
        tokens = _normalize(text).split()
        # Solo si parecia un intento de accion sobre el puntero verde: la
        # ultima palabra es "verde"/"green" y la anterior suena a clic.
        if len(tokens) < 2 or tokens[-1] not in self._GREEN_WORDS:
            return
        if tokens[-2] not in self._PALABRAS_CLIC_FALLIDAS:
            return
        ahora = time.monotonic()
        ultima = getattr(self, "_ultima_sugerencia_pulsa", 0.0)
        if ahora - ultima < self._SUGERENCIA_PULSA_CADA_S:
            return
        self._ultima_sugerencia_pulsa = ahora
        try:
            self.gui.update_suggestion(textos.t("prueba_pulsa_verde"))
        except Exception:
            pass

    def _recordar_desplazamiento(self, kind, repetir) -> None:
        """Si `kind` es un desplazamiento ("scroll_up"...), guarda `repetir`
        para "otra"/"again". Lo demas (clics, movimientos) no lo toca: "otra"
        repite el ultimo DESPLAZAMIENTO aunque entre medias se haya hecho
        otra cosa."""
        if isinstance(kind, str) and kind.startswith("scroll"):
            self._ultimo_desplazamiento = repetir

    def _repetir_desplazamiento(self) -> None:
        """"otra" / "otro" / "otra vez" / "again": repite el ultimo
        desplazamiento, sea cual sea, en el mismo sitio. Existe para acortar
        la orden cuando se baja por una lista o un menu (idea de pipataki,
        12-sep-2026)."""
        if self._ultimo_desplazamiento is None:
            try:
                self.gui.update_suggestion(textos.t("nada_que_repetir"))
            except Exception:
                pass
            try:
                tts.get_speaker().say(textos.t("nada_que_repetir"), tts.HELP)
            except Exception:
                pass
            return
        print("[command_router] otra: se repite el ultimo desplazamiento")
        self._ultimo_desplazamiento()

    def _fire_keyboard_shortcut(self, shortcut_name: str):
        """Dispara una tecla/atajo predefinido (ver
        input_action.PREDEFINED_ACTIONS) desde una entrada
        `"action": "keyboard:<nombre>"` de commands.json.

        Normalmente NO se toca la ventana: el GUI se crea con
        Qt.WA_ShowWithoutActivating (ver gui.py __init__), así que
        VoiceController nunca se lleva el foco del teclado POR SÍ SOLO --
        la tecla la recibe la aplicación que ya lo tuviera, que es lo que
        se espera al decir "tabulador" o "intro" mientras se trabaja en
        otra ventana.

        Pero el usuario PUEDE subirlo a propósito ("trae control", para ver
        el GUI mientras trabaja con la vista de foco). Entonces el foco sí
        es nuestro, y la tecla se la comía VoiceController en silencio. En
        ese caso -- y solo en ese -- se hace el mismo baile que el dictado:
        apartar, asegurar la ventana buena, actuar, y volver a subir. Lo
        decide actions.apartar_gui_si_estorba().

        Es distinto del clic del tablero, que siempre necesita apartar la
        ventana porque ahí lo que estorba es el TAPADO físico de la
        posición, no el foco.
        """
        # Si el GUI estaba delante, se aparta para la tecla y se vuelve a
        # subir despues: al_volver hace que al subir traiga las capturas
        # nuevas, tomadas con VC todavia apartado.
        ok = actions.execute_keyboard_shortcut(
            self.gui, shortcut_name,
            al_volver=lambda: self._refrescar(ya_apartada=True))
        if DEBUG:
            print(f"[command_router] tecla especial {shortcut_name!r}: "
                  f"{'OK' if ok else 'FALLÓ'}")

    # palabras que indican "usa la posición real del puntero" en vez del
    # ajuste fino acumulado por voz/compás -- ver
    # _try_parse_board_action_green / gui.get_touch_offset()
    _GREEN_WORDS = frozenset({"verde", "green"})
    # El puntero del MOVIL es rojo, y decir "rojo" es lo que sale solo
    # al usarlo -- lo dijo el en la primera prueba, antes de que
    # existiera el comando.
    _RED_WORDS = frozenset({"rojo", "red"})

    def _try_parse_board_action_green(self, norm_text: str):
        """'<accion> verde'/'<accion> green' (ej. 'click verde', 'mueve
        verde', 'doble click green'): ejecuta esa acción en la posición
        ACTUAL del círculo verde -- el puntero real, seguido en vivo por
        gui.py mientras haya una casilla ampliada visible (ver
        gui.get_touch_offset(), gui._do_touch_track()) -- en vez de en
        el ajuste fino acumulado por voz/compás (self.board_offset_x/y,
        que esta variante NO toca). Solo tiene sentido con una casilla
        ya seleccionada (se comprueba en el mismo bloque que
        _try_parse_board_zone_action, ver on_final).

        Devuelve (handler_name, (touch_offset_x, touch_offset_y)), o
        None si: el texto no encaja con el patrón, la acción (prefijo
        antes de "verde"/"green") no se reconoce, o no hay ninguna
        posición táctil rastreada ahora mismo (casilla no ampliada,
        seguimiento desactivado -- modo "cara" -- o puntero aún no
        visto)."""
        tokens = norm_text.split()
        if len(tokens) < 2 or tokens[-1] not in self._GREEN_WORDS:
            return None
        prefix = " ".join(tokens[:-1])
        handler_name = self._vc_action_alias_map.get(prefix)
        if handler_name is None:
            return None
        try:
            touch_offset = self.gui.get_touch_offset()
        except Exception as exc:
            if DEBUG:
                print(f"[command_router] error leyendo get_touch_offset(): {exc!r}")
            touch_offset = None
        if touch_offset is None:
            # El puntero solo se rastrea mientras el ratón está FÍSICAMENTE
            # encima de la miniatura del tablero, dentro de la ventana de
            # VoiceController (ver gui._do_touch_track). Trabajando solo
            # por voz eso no pasa nunca, así que "<accion> verde" no tiene
            # ninguna posición que usar y no hace nada.
            #
            # Antes esto solo se veía en la consola (y solo con DEBUG):
            # desde el GUI, el comando simplemente no respondía, sin
            # explicación. Se avisa en el campo Sugerencias con la
            # alternativa concreta, que es lo que de verdad hace falta
            # saber: la misma acción SIN "verde" usa el ajuste por voz.
            accion = prefix or "click"
            print(f"[command_router] '{norm_text}': sin posición táctil rastreada "
                  f"(el ratón no está sobre la miniatura) -- usa '{accion}' a secas")
            try:
                self.gui.update_suggestion(
                    f'💡 "{norm_text}" necesita el ratón sobre la miniatura del '
                    f'tablero. Por voz, di solo "{accion}".'
                )
                self._active_suggestion = {"type": "hint_green"}
            except Exception:
                pass
            return None
        return handler_name, touch_offset

    def _fire_board_action(self, handler_name: str, offset: tuple | None = None):
        if self.board_selected_cell is None:
            return
        kind = actions.VC_HANDLER_KIND.get(handler_name)
        if kind is None:
            return
        cell = self.board_selected_cell
        ox, oy = offset if offset is not None else (self.board_offset_x, self.board_offset_y)
        if DEBUG:
            origen = "verde/táctil" if offset is not None else "ajuste fino"
            print(f"[command_router] acción de tablero ({origen}): {kind} en casilla {cell} offset=({ox},{oy})")
        actions.fire_board_action(self.gui, cell, ox, oy, kind)
        self._recordar_desplazamiento(kind, lambda: actions.fire_board_action(
            self.gui, cell, ox, oy, kind))
        self._deselect_board_cell()

    def _fire_board_zone_action(self, handler_name: str, zone_num: int):
        """Ejecuta la acción `handler_name` directamente sobre la zona
        clicable autodetectada número `zone_num` (1-based), ignorando el
        ajuste fino manual acumulado hasta ahora -- ver
        _try_parse_board_zone_action / board.detect_zones."""
        if self.board_selected_cell is None:
            return
        if not (1 <= zone_num <= len(self.board_zones)):
            return
        kind = actions.VC_HANDLER_KIND.get(handler_name)
        if kind is None:
            return
        cell = self.board_selected_cell
        ox, oy = self.board_zones[zone_num - 1]
        if DEBUG:
            print(f"[command_router] acción sobre zona {zone_num}: {kind} en casilla {cell} offset=({ox},{oy})")
        actions.fire_board_action(self.gui, cell, ox, oy, kind)
        self._recordar_desplazamiento(kind, lambda: actions.fire_board_action(
            self.gui, cell, ox, oy, kind))
        self._deselect_board_cell()

    def handle_touch(self, text: str):
        """Entrada táctil (tablero del GUI de escritorio o de la webapp):
        el mismo texto que reconocería la voz (un número, una dirección,
        una acción...), procesado por la MISMA máquina de estados que
        on_final, con confianza máxima. Así el tablero "acepta entrada
        táctil" tal cual describe el manual, sin duplicar la lógica."""
        self.on_final(text, confidence=1.0, language=self.primary_language, sentence_type="statement")

    # ---------- entrada principal ----------

    def on_partial(self, text: str, language: str = "es"):
        if language == self.primary_language:
            if self.state == "DICTATING":
                if self.formuling:
                    # show concatenated live preview without spaces
                    try:
                        self.gui.update_pretexto_formuling(self.primary_buffer, text)
                    except Exception:
                        self.gui.update_pretexto(self.primary_buffer, preview=text)
                else:
                    self.gui.update_pretexto(self.primary_buffer, preview=text)
        # El idioma secundario mientras se dicta es solo para palabras de
        # control (ver on_final); no tiene campo propio en el GUI, así que
        # su texto parcial no se muestra en ningún sitio.

    def on_final(self, text: str, confidence: float = 1.0, language: str = "es",
                 sentence_type: str = "statement", speaker_verdict: str = "him",
                 peak_rms: float = 0.0, source: str = "device"):
        """`speaker_verdict`: "him" | "other" | "unknown" (ver
        speaker_id.verdict). "unknown" significa que la frase no dio
        x-vector y NO se ha podido verificar -- que no es lo mismo que
        "es otra persona", y confundirlos hacía que un comando corto suyo
        contara como intento de intrusión.

        `source`: de qué micrófono vino, "device" (el del PC) o "network"
        (el del móvil). La identificación va POR SEPARADO para cada uno:
        ver _sesion().

        `peak_rms`: pico de energía de la frase -- la señal de "esto se
        ha dicho cerca del micrófono" (ver _register_intruder_strike)."""
        norm = _normalize(text)

        # --- Idioma secundario en ESCUCHA ---
        # Ver config.SECONDARY_LANGUAGE_IN_IDLE. Los dos motores oyen el
        # MISMO audio, así que hablando en español el inglés transcribe
        # disparates en paralelo. Pero tirarlo entero era pasarse: el
        # léxico inglés tiene `firefox`, `inkscape`, `konsole`,
        # `backspace`, `listen`, `undo`... que el español NO tiene, y los
        # alias ingleses de commands.json funcionan justo gracias a él.
        #
        # Por defecto ("commands") se acepta solo lo que encaje con un
        # comando de verdad: los disparates no coinciden nunca con un
        # alias, así que se van solos.
        modo_secundario = getattr(config, "SECONDARY_LANGUAGE_IN_IDLE", "commands")
        if self.state == "IDLE":
            if language != self.primary_language and (
                    modo_secundario == "none"
                    or (modo_secundario == "commands"
                        and not self._looks_like_command(norm))):
                if DEBUG:
                    print(f"[command_router]   -> descartado (idioma secundario "
                          f"en escucha, no es comando): {text!r}")
                return
            # El eco del otro motor se filtra mire el idioma que mire:
            # da igual cuál de los dos llegue primero (ver
            # _es_eco_del_otro_motor).
            if self._looks_like_command(norm) and self._es_eco_del_otro_motor(norm, language):
                print(f"[command_router] eco del otro motor, ignorado: {text!r}")
                return

        # De qué micrófono viene esta frase, LO PRIMERO: todo lo que
        # viene detrás (standby, santo y seña, intrusos) consulta la
        # sesión de ESTE micrófono, y van por separado -- ver _sesion().
        # El móvil y el PC son dos sitios físicos distintos, con
        # condiciones de audio distintas; compartir el estado hacía que
        # un fallo en uno bloqueara el otro.
        self._source = source if source in self._sesiones else "device"

        # --- Standby ---
        # Lo primero de todo: en espera no se obedece NADA. Se sale diciendo
        # el santo y seña, que se valida por la voz, así que dejar el
        # ordenador solo no lo deja abierto a cualquiera.
        self._last_heard_ts = time.monotonic()
        control_previo = self._any_control_map.get(norm) or (
            self._idle_control_map.get(norm) if self.state == "IDLE"
            else self._dictating_control_map.get(norm))
        if self._standby:
            # El santo y sena entra directamente, sin decir "revive" antes.
            # El liston de la voz ya es el de login (ver _enter_standby), asi
            # que esto es exactamente la misma comprobacion que hace el
            # arranque -- ni mas floja ni mas dura.
            if speaker_verdict == _HIM:
                print(f"[command_router] santo y sena en espera: {text!r}")
                self._standby = False
                self._dudando = False
                self._pintar_escucha()
                self._set_awaiting_login(False)
                self._sesion()["ok"] = True
                self._sesion()["ts"] = time.monotonic()
                self._sesion()["fallos"] = 0
                if self.gui is not None:
                    try:
                        self.gui.update_suggestion(textos.t("te_escucho"))
                    except Exception:
                        pass
                try:
                    tts.get_speaker().say(textos.t("te_escucho_voz"), tts.HELP)
                except Exception:
                    pass
                return
            # Ya no hay "revive" (14-sep-2026): era un paso de mas antes del
            # santo y sena, que es lo unico que despierta.
            if DEBUG:
                print(f"[command_router] en standby, ignorado: {text!r}")
            return
        if control_previo == "standby":
            self._enter_standby()
            return

        # --- Santo y seña (ver _check_voice_login) ---
        # Lo PRIMERO: mientras no se haya identificado no se obedece nada.
        if self._voice_login_pending():
            self._handle_voice_login(text, speaker_verdict)
            return

        # --- Bloqueo por intrusión (ver _register_intruder_strike) ---
        # Lo primero de todo: mientras está bloqueado no se obedece NADA,
        # ni comandos ni dictado. Lo único que se sigue mirando es la
        # frase de desbloqueo, y solo si la dice él.
        if self._intruder_locked_until:
            if self._try_intruder_unlock(norm, speaker_verdict == _HIM):
                return
            if DEBUG:
                print(f"[command_router] bloqueado por intrusión, ignorado: {text!r}")
            return

        # --- "soy yo": pedir el santo y sena, DIGA QUIEN LO DIGA ---
        # Va aqui arriba, ANTES del filtro de voz, y esa colocacion es el
        # arreglo del 5-sep-2026. Antes vivia dentro del "si no te
        # reconozco", asi que solo funcionaba cuando el filtro fallaba...
        # y en el momento en que volvia a reconocerle, dejaba de existir.
        # Resultado: aviso fijo en pantalla, "soy yo" dicho once veces
        # seguidas, y ninguna respuesta. "soy yo" no es un comando de
        # commands.json, asi que caia en "no entendido" y ahi moria.
        #
        # Que lo acepte de CUALQUIER voz es deliberado: lo unico que
        # consigue es que el programa PIDA la contrasena hablada, y esa si
        # exige su voz al liston de login. No abre nada.
        if (getattr(config, "VOZ_AJENA_NO_ACTUA", True)
                and norm in self._INTRUDER_UNLOCK_PHRASES):
            print(f"[command_router] \"{norm}\": pido el santo y sena")
            self._dudando = False
            self._pintar_escucha()
            # CADUCAR LA SESION ANTES DE PEDIR NADA. _ask_voice_login() solo
            # avisa y sube el liston del reconocedor al umbral de login: no
            # marca la sesion como caducada. Eso lo hace quien llama, igual
            # que leave_standby() al salir de la espera desde la bandeja.
            #
            # Sin estas dos lineas queda un callejon sin salida perfecto: el
            # programa pide el santo y sena por pantalla y en alto, sube el
            # liston a 0,44... y _voice_login_pending() sigue diciendo que
            # no hay nada pendiente, porque la sesion seguia siendo valida.
            # La frase llega, no la mira nadie, y cae en "no entendido".
            # Encima el liston alto hace que sus propias frases parezcan de
            # un desconocido. Paso el 5-sep-2026: "soy yo" respondia, y el
            # santo y sena no entraba de ninguna manera.
            self._sesion()["ok"] = False
            self._sesion()["fallos"] = 0
            self._ask_voice_login()
            return

        # --- Voz que NO es la suya ---
        # El reconocedor ya ha anotado el veredicto; aquí se decide qué
        # hacer con él: si lo dicho es un comando de verdad, si la prueba
        # es lo bastante solida para cortarle la palabra a quien habla, y
        # por ultimo, si el filtro está en modo "block", si se descarta.
        if speaker_verdict != _HIM:
            # SOLO cuenta como intrusión una voz VERIFICADA como ajena.
            # "unknown" (sin x-vector) no acusa a nadie: es justo lo que
            # producen los comandos cortos, también los suyos.
            prueba_solida = False
            if speaker_verdict == _OTHER and self._looks_like_command(norm):
                prueba_solida = self._register_intruder_strike(
                    text, confidence, peak_rms)

            # --- No actuar (ver config.VOZ_AJENA_NO_ACTUA) ---
            # Antes de esto, una voz ajena EJECUTABA sus ordenes mientras el
            # filtro estuviera en modo "warn", y lo unico que la paraba era el
            # bloqueo, que llegaba al tercer intento. Ahora no se ejecuta nada
            # desde el primero: ni comandos, ni dictado, ni nada.
            #
            # PERO solo con PRUEBA SOLIDA -- las cuatro condiciones del
            # detector de intrusos, no solo el veredicto del filtro. Esa
            # distincion no estaba el 4-sep y le mordio al dia siguiente:
            # basto un "click" dicho por el movil, lejos y flojo (rms 812 de
            # 1500), para dejarle sin obedecer. El propio detector habia
            # escrito en el log "NO contado (lejos)" -- es decir, esta medida
            # no vale para acusar a nadie -- y el corte se aplicaba igual.
            #
            # Si la prueba no es solida se sigue adelante como siempre. Es la
            # eleccion correcta: en la duda, obedecer a quien probablemente
            # es el dueno. Lo contrario es dejarle tirado con un aviso fijo,
            # que es exactamente lo que paso.
            if (getattr(config, "VOZ_AJENA_NO_ACTUA", True)
                    and speaker_verdict == _OTHER and prueba_solida):
                self._preguntar_si_eres_tu(text)
                try:
                    self.gui.update_pretexto(self.primary_buffer, preview="")
                except Exception:
                    pass
                return

            if speaker_id.is_blocking() and speaker_verdict == _OTHER:
                # la previsualización en vivo del GUI ya muestra este
                # texto (llegó como parcial antes de cerrarse la frase);
                # si no se limpia se queda colgada, descartada pero visible
                try:
                    self.gui.update_pretexto(self.primary_buffer, preview="")
                except Exception:
                    pass
                return
        elif self._intruder_strikes or self._dudando:
            # Las dos cosas, y por separado: la racha se pone a cero sola al
            # llegar a tres, asi que mirar solo la racha dejaba el aviso
            # colgado justo en el caso peor -- despues de tres frases ajenas.
            #
            # Basta con que hables TÚ para romper la racha: los intentos
            # que cuentan son SEGUIDOS, no un total acumulado a lo largo
            # del día. Si no se reiniciara, tres frases ajenas sueltas en
            # horas distintas acabarían bloqueándote sin que haya pasado
            # nada raro.
            if self._intruder_strikes:
                print(f"[command_router] contador de intrusión a cero "
                      f"(estabas {self._intruder_strikes}/"
                      f"{config.INTRUDER_STRIKES_TO_ABORT}): te he reconocido")
            self._intruder_strikes = 0
            if self._dudando:
                self._dudando = False
                self._pintar_escucha()
                # Y BORRAR EL AVISO. Se quedaba puesto para siempre: el LED
                # volvia a verde, el programa te obedecia otra vez, y la
                # pantalla seguia diciendo "voz no reconocida" parpadeando.
                # Un aviso que no se apaga cuando el motivo desaparece es
                # peor que no tenerlo: deja de significar nada y encima hace
                # dudar de si el programa esta bien.
                try:
                    self.gui.update_suggestion(textos.t("te_escucho"))
                except Exception:
                    pass
        if DEBUG:
            print(
                f"[command_router] final reconocido: {text!r} "
                f"(lang={language}, conf={confidence:.2f}, estado={self.state}, "
                f"micro={source})"
            )

        state_map = self._idle_control_map if self.state == "IDLE" else self._dictating_control_map

        # 1) coincidencia EXACTA con toda la frase, dentro del scope del estado actual
        # --- Habilidades (ver habilidades/__init__.py) -------------------
        #
        # Lo especifico de CADA programa -- narrar un PDF, las herramientas
        # de un editor de dibujo, dictar codigo -- vive en modulos aparte que
        # se activan solo cuando esa ventana esta delante. Se les ofrece la
        # frase ANTES que al nucleo, para que puedan quedarsela.
        #
        # Hoy no hay ninguna activa y esto sale en 0,0002 ms: el programa se
        # comporta exactamente igual que si no existiera. El enganche esta
        # puesto para que anadir una habilidad sea escribir un fichero, sin
        # tocar este.
        try:
            if habilidades.ofrecer(text, norm, {"gui": self.gui, "router": self}):
                return
        except Exception as exc:
            # Una habilidad rota no puede dejar sordo al programa.
            print(f"[command_router] fallo en habilidades: {exc!r}")

        control_action = self._any_control_map.get(norm) or state_map.get(norm)
        leftover_text = ""

        # "ayuda"/"help" (scope "any"): ventana flotante con los comandos
        # disponibles en el estado ACTUAL, unos segundos y se cierra sola.
        # Se comprueba aquí, con la frase COMPLETA ya reconocida y ANTES
        # del rescate por palabra final de abajo, a propósito: mientras se
        # dicta, "ayuda" es una palabra perfectamente normal dentro de una
        # frase ("necesito ayuda"), y no queremos que se coma el dictado
        # por aparecer al final. Solo la frase entera "ayuda" abre la
        # ventana; el resto se dicta como texto normal.
        if control_action == "show_help":
            self._show_help()
            return
        if control_action == "show_help_audio":
            # el pop-up SIEMPRE, y además leído en alto: son dos formas de
            # la misma ayuda, no una alternativa a la otra
            self._show_help(speak=True)
            return

        # "código de emparejamiento": el número que hay que comparar con el
        # que enseña el móvil la primera vez que se conecta.
        #
        # Se dice EN ALTO a propósito. La forma habitual de emparejar dos
        # aparatos es un código QR en la pantalla, y aquí no vale: buena
        # parte de quien usa esto no ve la pantalla del ordenador. Dicho en
        # voz alta, el emparejamiento entero se puede hacer escuchando.
        if control_action == "pairing_code":
            self._decir_codigo_emparejamiento()
            return

        # "foco": ensena LA VENTANA en la que se estaba trabajando, en vez de
        # un trozo de escritorio elegido por casilla. Es lo comodo cuando se
        # esta usando un programa concreto: el navegador, un editor.
        if control_action == "board_focus":
            self._entrar_en_foco()
            return

        # 2) si no hay coincidencia exacta y estamos dictando, prueba si la
        #    ÚLTIMA palabra del resultado es una palabra de control válida
        #    aquí (Vosk juntó tu dictado con la palabra de control por
        #    falta de pausa). Esto puede pasar tanto si la frase completa la
        #    transcribió el motor primario como el secundario, así que no se
        #    filtra por idioma.
        if control_action is None and self.state == "DICTATING":
            tokens = norm.split()
            if tokens:
                last_tok = tokens[-1]
                last_action = self._any_control_map.get(last_tok) or state_map.get(last_tok)
                # "ayuda" al final de una frase dictada es una palabra
                # normal ("necesito ayuda"), no una petición de ayuda:
                # solo la frase entera abre la ventana (ver arriba).
                if last_action == "show_help":
                    last_action = None
                if last_action is not None:
                    control_action = last_action
                    leftover_tokens = text.split()[:-1]  # texto original, sin normalizar, para conservar acentos
                    leftover_text = " ".join(leftover_tokens)
                    if DEBUG:
                        print(f"[command_router]   -> palabra de control detectada al final: "
                              f"{last_tok!r} ({control_action}); resto: {leftover_text!r}")

        if self.state == "IDLE":
            if self._try_parse_guardar_como(text, norm):
                return
            if self._try_parse_foco_window(text, norm):
                return
            if self._try_parse_carpeta(text, norm):
                return
            if self._try_parse_bring_window(text, norm):
                return
            if self._try_parse_input_mode(norm):
                return
            if control_action == "quit":
                self.gui.quit_app()
                return
            if control_action == "toggle_monitor":
                # El panel de estado del modo servicio. En el modo con
                # ventana no hace falta -- todo eso ya se ve -- asi que
                # alli no hace nada y se dice por que, en vez de callar.
                fn = getattr(self.gui, "alternar_monitor", None)
                if fn is None:
                    self.gui.update_suggestion(
                        "El panel de estado es del modo servicio: "
                        "aqui ya lo tienes todo a la vista.")
                else:
                    fn()
                return

            if control_action == "seleccion_origen":
                self._seleccion_fijar_origen()
                return
            if control_action == "seleccion_fin":
                self._seleccion_terminar("texto")
                return
            if control_action == "seleccion_arrastre":
                self._seleccion_terminar("area")
                return
            if control_action == "seleccion_cancelar":
                self._seleccion_cancelar()
                return
            if control_action == "show_board_grid":
                # La rejilla numerada DENTRO del GUI, no a pantalla completa.
                #
                # La vista general ya la dibuja, asi que esto es volver ahi:
                # se apagan los otros modos y se ensena el tablero con sus
                # numeros, que es lo que hace falta para nombrar una casilla.
                #
                # La rejilla A PANTALLA COMPLETA (accion "show_grid", que
                # se dice "rejilla") era de la epoca ANTERIOR al tablero de
                # 100 casillas, y ya no existe. Esto no es aquello.
                self._foco_activo = False
                self._zoom_out_active_cell = None
                self._deselect_board_cell()
                actions.refresh_board_overview(self.gui)
                return
            if control_action == "refresh_captures":
                # "refrescar": vuelve a capturar lo que se esta mirando. Si la
                # ventana esta oculta (modo servicio, o se esta usando el
                # movil) NO se saca: se refresca por detras y ya.
                visible = bool(getattr(self.gui, "isVisible", lambda: True)())
                self._refrescar(volver=self.gui.traer_al_frente_suave if visible else False,
                                ya_apartada=not visible)
                try:
                    self.gui.update_suggestion(textos.t("capturas_actualizadas"))
                except Exception:
                    pass
                return
            if control_action == "repeat_scroll":
                # Aqui, ANTES del bloque de la casilla: con una casilla
                # seleccionada, "otra" no es un ajuste fino ni una zona.
                self._repetir_desplazamiento()
                return
            if control_action == "raise_gui":
                # "subir": trae la ventana al frente si quedó tapada (ver
                # manual, Sección 1 Paso 3)
                try:
                    self.gui.subir_ventana()
                except Exception:
                    pass
                return
            if control_action == "switch_to_local_mic":
                # "micrófono local"/"mic local": vuelve a escuchar el
                # micrófono físico del escritorio tras haber usado el del
                # móvil (ver main.py, set_switch_to_local_mic_callback)
                try:
                    self._switch_to_local_mic()
                except Exception:
                    pass
                return
            if control_action == "start_dictation":
                self._deselect_board_cell()
                self._set_state("DICTATING")
                self.formuling = False
                self.primary_buffer = ""
                self._word_origins = []
                self.secondary_buffer = ""
                self.gui.clear_pretexto()
                self._clear_suggestion()
                return
            if control_action == "start_formuling":
                # enter dictation + formuling (math / science) submode
                self._deselect_board_cell()
                self._set_state("DICTATING")
                self.formuling = True
                self.primary_buffer = ""
                self._word_origins = []
                self.secondary_buffer = ""
                self.gui.clear_pretexto()
                self._clear_suggestion()
                try:
                    self.gui.update_formuling_indicator(True)
                except Exception:
                    pass
                return

            # --- Tablero de 100 casillas: mientras hay una casilla YA
            # seleccionada, las direcciones y las acciones-solas tienen
            # prioridad (ver docstring del módulo) ---
            if self.board_selected_cell is not None:
                direction_match = self._try_parse_board_direction(norm)
                if direction_match:
                    vector, pixels = direction_match
                    self._nudge_board(vector, pixels)
                    return
                # "<accion> <numero>" sobre una zona clicable autodetectada
                # (ej. "click 1"): se comprueba ANTES del formato directo
                # "<accion> <casilla>" para que, mientras haya zonas
                # detectadas, el número se interprete como zona y no como
                # otra casilla del tablero.
                zone_match = self._try_parse_board_zone_action(norm)
                if zone_match:
                    handler_name, zone_num = zone_match
                    self._fire_board_zone_action(handler_name, zone_num)
                    return
                # "menos zoom"/"zoom out": cuarto de escritorio (5x5
                # casillas) donde cae la casilla seleccionada, sin
                # numerar -- ver board.capture_zoom_out. Pasa del modo
                # "cell" al modo zoom_out interactivo (Fase 2); el
                # puntero verde arranca centrado (ver
                # _enter_zoom_out_interactive) igual que con "mover <n>".
                if norm in ("menos zoom", "zoom out"):
                    cell = self.board_selected_cell
                    self._deselect_board_cell()
                    self._enter_zoom_out_interactive(cell)
                    return
                # "<accion> verde"/"<accion> green" (ej. "click verde",
                # "mueve verde"): actúa en la posición real del puntero
                # (seguida en vivo por el círculo verde, ver
                # gui.get_touch_offset), no en el ajuste fino acumulado
                # por voz/compás -- se comprueba ANTES del disparo normal
                # para que "verde"/"green" no se trate como ruido de más.
                green_match = self._try_parse_board_action_green(norm)
                if green_match:
                    handler_name, touch_offset = green_match
                    self._fire_board_action(handler_name, offset=touch_offset)
                    return
                handler_name = self._vc_action_alias_map.get(norm)
                if handler_name:
                    self._fire_board_action(handler_name)
                    return

            # --- Fase 2 (PDF NuevoGUI): modo zoom_out interactivo activo
            # -- mismo criterio de prioridad que el bloque de casilla
            # seleccionada de arriba (mutuamente excluyentes: nunca hay
            # una casilla "cell" seleccionada A LA VEZ que un zoom_out
            # activo). Solo direcciones (ajuste fino del puntero verde)
            # y palabras de acción -- nada de selección de casilla ni
            # zonas numeradas aquí (el PDF no las contempla en este modo).
            # "<accion> rojo": actua donde el MOVIL tiene su punto rojo.
            #
            # Va ANTES que todo lo demas y no depende de la vista: el puntero rojo
            # existe siempre que haya un movil conectado, se este mirando el tablero,
            # una casilla o la ventana enfocada.
            #
            # Hace falta para el modo cara, donde no se pueden pulsar botones. Y es lo
            # que el pidio sin saberlo: en la primera prueba dijo "pulsa rojo" tres
            # veces antes de que el comando existiera.
            # Una accion A SECAS ("pulsa", "click derecho") con un movil conectado
            # actua donde este SU puntero.
            #
            # Al principio se pedia decir "pulsa rojo". Pero al usarlo le salio decirlo
            # sin color, una y otra vez -- y tiene razon: si estas mirando el punto rojo
            # en la pantalla del movil, no hay ningun otro sitio donde puedas querer
            # pulsar. Exigir la palabra era friccion sin motivo.
            #
            # La forma con "rojo" se queda igualmente, por si algun dia hay ambiguedad.
            # CONDICION IMPORTANTE: solo si no hay ningun modo del PC activo. Con
            # zoom_out, una casilla o la vista foco en marcha, el puntero que manda
            # es el VERDE -- si no, con el movil conectado se secuestrarian esos
            # flujos del escritorio.
            if (self._rojo_fx is not None
                    and not self._foco_activo
                    and self._zoom_out_active_cell is None
                    and self.board_selected_cell is None):
                solo_accion = self._vc_action_alias_map.get(norm)
                if solo_accion and solo_accion != "vc_move":
                    self._actuar_en_puntero_rojo(solo_accion)
                    return

            tokens_rojo = norm.split()
            if len(tokens_rojo) >= 2 and tokens_rojo[-1] in self._RED_WORDS:
                handler_rojo = self._vc_action_alias_map.get(" ".join(tokens_rojo[:-1]))
                if handler_rojo and handler_rojo != "vc_move":
                    self._actuar_en_puntero_rojo(handler_rojo)
                    return

            # Vista "foco": mismas reglas que zoom_out -- direcciones para el
            # ajuste fino del puntero verde y palabras de accion. La
            # diferencia es que aqui no hay casilla: la region es la ventana.
            if self._foco_activo:
                direction_match = self._try_parse_board_direction(norm)
                if direction_match:
                    vector, pixels = direction_match
                    self._nudge_foco(vector, pixels)
                    return
                green_match = self._try_parse_board_action_green(norm)
                if green_match:
                    handler_name, touch_offset = green_match
                    self._fire_foco_action(handler_name, offset=touch_offset)
                    return
                handler_name = self._vc_action_alias_map.get(norm)
                if handler_name and handler_name != "vc_move":
                    self._fire_foco_action(handler_name)
                    return

            if self._zoom_out_active_cell is not None:
                direction_match = self._try_parse_board_direction(norm)
                if direction_match:
                    vector, pixels = direction_match
                    self._nudge_zoom_out(vector, pixels)
                    return
                # "<accion> verde"/"<accion> green": actúa en la posición
                # ACTUAL del puntero verde tal como lo sigue en vivo el
                # ratón/táctil (gui.get_touch_offset()) -- SIN esto, el
                # arrastre por touchpad solo movía el dibujo, pero la
                # acción seguía usando self._zoom_out_offset_x/y (que
                # solo tocan las palabras del compás), así que un "click"
                # a secas parecía "no llegar" a donde se había arrastrado
                # -- mismo mecanismo que ya existe para el modo "cell"
                # (ver _try_parse_board_action_green más abajo).
                green_match = self._try_parse_board_action_green(norm)
                if green_match:
                    handler_name, touch_offset = green_match
                    self._fire_zoom_out_action(handler_name, offset=touch_offset)
                    return
                handler_name = self._vc_action_alias_map.get(norm)
                if handler_name and handler_name != "vc_move":
                    self._fire_zoom_out_action(handler_name)
                    return

            # comando del tablero DIRECTO de un solo tiro ("<accion> <casilla>")
            direct_vc = self._try_parse_direct_vc(norm)
            if direct_vc:
                handler_name, cell = direct_vc
                if DEBUG:
                    print(f"[command_router]   -> vc directo OK: "
                          f"handler={handler_name} casilla={cell}")
                # "mover <casilla n>" (Fase 2, PDF NuevoGUI): YA NO mueve
                # el cursor real al instante -- entra en modo zoom_out
                # interactivo, con el puntero verde extrapolado desde la
                # última posición real conocida (nunca desde donde
                # estuviera "cell" seleccionada, que se deselecciona
                # igual que antes por si acaso).
                if handler_name == "vc_move":
                    self._deselect_board_cell()
                    self._enter_zoom_out_interactive(cell)
                    return
                self._deselect_board_cell()
                handler = actions.VC_HANDLERS.get(handler_name)
                if handler:
                    handler(self.gui, cell)
                    self._recordar_desplazamiento(
                        actions.VC_HANDLER_KIND.get(handler_name),
                        lambda: handler(self.gui, cell))
                return

            # número SOLO (1-100) -> selecciona casilla (Paso 1 del manual)
            bare_cell = self._try_parse_bare_cell(norm)
            if bare_cell is not None:
                self._select_board_cell(bare_cell)
                return

            # comando de app DIRECTO, sin pasar por "dictar"
            exec_cmd = self._app_command_alias_map.get(norm)
            if exec_cmd:
                if DEBUG:
                    print(f"[command_router]   -> abriendo app: {exec_cmd!r}")
                actions.launch_app(exec_cmd)
                return

            # --- Teclas especiales del teclado (commands.json ->
            # control_words con "action": "keyboard:<nombre>", scope
            # "idle"): "tabulador", "espacio", "intro", "escape",
            # "scroll derecha"... Se comprueba AQUÍ, DESPUÉS de todo lo
            # del tablero, a propósito: mientras hay una casilla
            # seleccionada o un zoom_out activo, "arriba"/"abajo"/
            # "izquierda"/"derecha" y "scroll <dirección>" significan
            # ajuste fino del puntero / acción sobre la casilla, y esos
            # bloques ya han hecho return mucho antes de llegar aquí.
            # Sin casilla ni zoom_out, esas mismas palabras son las
            # teclas del teclado -- que es justo lo que dice el
            # comentario de board_directions en commands.json.
            if isinstance(control_action, str) and control_action.startswith("keyboard:"):
                tecla = control_action[len("keyboard:"):]
                if norm in self._alias_desplazamiento_teclado:
                    self._ultimo_desplazamiento = lambda: self._fire_keyboard_shortcut(tecla)
                self._fire_keyboard_shortcut(tecla)
                return

            # --- Ventanas de OTRAS aplicaciones (minimizar, maximizar,
            # cerrar...). Van por kdotool y no por atajo de teclado
            # porque minimizar/maximizar no tienen atajo estándar: cada
            # escritorio usa el suyo y muchos vienen sin asignar. Ver
            # actions.window_action, que además se niega a actuar si la
            # ventana con foco resulta ser el propio VoiceController.
            if isinstance(control_action, str) and control_action.startswith("window:"):
                actions.window_action(control_action[len("window:"):])
                return

            # acciones sobre el campo "Texto" (confirmado), disponibles en IDLE
            if control_action == "copy_confirmed":
                self._copy_confirmed()
                return
            if control_action == "paste_confirmed":
                self._paste_confirmed()
                return
            if control_action == "select_confirmed":
                self._select_confirmed()
                return
            if control_action == "clear_confirmed":
                self._clear_confirmed()
                return

            # Nada ha encajado. Si la voz era la SUYA (y no la tele), se
            # le avisa en alto de que no se le ha entendido -- ver
            # _maybe_say_not_understood para las condiciones exactas.
            # Aquí NO se registra intento de intrusión: no encajar con
            # ningún comando es justo lo que hace todo el rato una tele
            # de fondo (condición 4, ver _register_intruder_strike).
            # "no te entiendo" se dice a quien NO esté verificado como
            # ajeno: si no se pudo verificar, lo más probable es que sea
            # él y merece la respuesta.
            self._maybe_say_not_understood(text, norm, speaker_verdict != _OTHER, language)
            return

        # state == DICTATING
        # Las palabras de control (confirmar/borrar/salir/idle) se comprueban
        # sin importar qué motor (primario o secundario) las transcribió: en
        # commands.json están pensadas como palabras poco probables en una
        # frase normal, así que da igual si dijiste "borra" en español (lo
        # oye el motor primario) o "reset" en inglés (lo oye el secundario).

        # Si hay una pregunta ambigua pendiente (ver _check_ambiguous_suggestion)
        # y lo que se acaba de reconocer es exactamente el nombre de una de
        # sus opciones (ej. "siglas"), se resuelve aquí y no se trata como
        # texto dictado. Se comprueba ANTES que nada más para que tenga
        # prioridad incluso sobre las palabras de control.
        if self._try_resolve_ambiguous_choice(norm):
            return

        # "corrige/corregir/correct/fix <numero> <modificador>" (ej. "corregir
        # 4 mayuscula", "corrige 5 siglas"): corrige UNA palabra concreta del
        # Pre-Texto por su posición, sin tocar el resto. Se comprueba ANTES
        # que "control_action == 'correct_last_word'" porque ese solo
        # dispara con el disparador SOLO (coincidencia exacta de toda la
        # frase); aquí el disparador va seguido de más tokens, así que
        # control_action ya habrá salido None para esta frase.
        correct_word_match = self._try_parse_correct_word(norm)
        if correct_word_match:
            index, modifier, ambiguous = correct_word_match
            self._correct_word(index, modifier, ambiguous=ambiguous)
            return

        if control_action == "quit":
            self.gui.quit_app()
            return
        if control_action == "refresh_captures":
            visible = bool(getattr(self.gui, "isVisible", lambda: True)())
            self._refrescar(volver=self.gui.traer_al_frente_suave if visible else False,
                            ya_apartada=not visible)
            return
        if control_action == "raise_gui":
            try:
                self.gui.subir_ventana()
            except Exception:
                pass
            return
        if control_action == "switch_to_local_mic":
            try:
                self._switch_to_local_mic()
            except Exception:
                pass
            return
        if control_action == "reset":
            # borra el Pre-Texto pero se queda dictando (no cambia de estado),
            # para poder corregir y seguir sin decir "dictar" otra vez.
            # El campo Texto (confirmado) NO se toca -- para vaciarlo se usa
            # "vaciar texto" desde IDLE.
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            self._arm_text_suppression(0.7)
            return
        if control_action == "correct_last_word":
            # como "reset" pero borra SOLO la última palabra del
            # Pre-Texto, para corregir un fallo puntual sin tener que
            # volver a dictar todo el fragmento.
            self._correct_last_word()
            return
        if control_action == "go_idle":
            # vuelve a reposo descartando lo que hubiera en el Pre-Texto
            # (el campo Texto confirmado persiste)
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            self._set_state("IDLE")
            self._arm_text_suppression(0.7)
            return
        if control_action == "apply_suggestion":
            # acepta la sugerencia activa de tipo "to_math" (pasar a dígitos/
            # notación matemática), sin salir de dictado ni cambiar el modo
            # formuling. Las preguntas ambiguas (ver _check_ambiguous_suggestion)
            # NO pasan por aquí -- se resuelven diciendo directamente el
            # nombre de la opción elegida (ver _try_resolve_ambiguous_choice,
            # comprobado al principio del bloque DICTATING), no con "vale".
            if self._active_suggestion and self._active_suggestion.get("type") == "to_math":
                self.primary_buffer = self._active_suggestion["text"]
                self.gui.update_pretexto(self.primary_buffer, preview="")
                if DEBUG:
                    print(f"[command_router] sugerencia aplicada: {self.primary_buffer!r}")
            self._clear_suggestion()
            return
        if control_action == "dismiss_suggestion":
            self._clear_suggestion()
            return
        if control_action == "confirm":
            if leftover_text:
                if self.formuling:
                    chunk = _mathematize_chunk(leftover_text, sentence_type)
                    self.primary_buffer = (
                        (self.primary_buffer + " " + chunk).strip() if self.primary_buffer else chunk
                    )
                else:
                    self.primary_buffer = (
                        (self.primary_buffer + " " + leftover_text).strip() if self.primary_buffer else leftover_text
                    )
            self._confirm_and_route()
            return

        # no es palabra de control: es texto dictado normal, se añade al buffer primario
        if time.monotonic() < self._ignore_text_until:
            return

        if language == self.primary_language and self.state == "DICTATING" and not self.formuling and confidence < 0.65:
            # las frases dudosas suelen aparecer tras pausas/silencios; mejor ignorarlas
            if DEBUG:
                print(f"[command_router] descartado por baja confianza: {confidence:.2f}")
            return

        if language == self.primary_language:
            # cualquier texto nuevo deja obsoleta la sugerencia anterior;
            # si sigue siendo pertinente, check_pause_suggestion() la
            # volverá a mostrar tras la siguiente pausa
            self._clear_suggestion()
            if self.formuling:
                chunk = _mathematize_chunk(text, sentence_type)
                self.primary_buffer = (self.primary_buffer + " " + chunk).strip() if self.primary_buffer else chunk
                # en modo fórmula no hay normalización de números/aprendizaje
                # de correcciones (ver docstring del módulo), pero
                # self._word_origins debe seguir teniendo una entrada por
                # cada palabra de primary_buffer para que los índices de
                # "corregir <numero> ..." sigan cuadrando si se usa aquí
                self._word_origins.extend(chunk.split(" ") if chunk else [])
                try:
                    self.gui.update_pretexto_formuling(self.primary_buffer, preview="")
                except Exception:
                    self.gui.update_pretexto(self.primary_buffer, preview="")
            else:
                # por defecto, cualquier cantidad dictada como palabras se
                # normaliza sola a cifra (ej. "treinta y cinco" -> "35"),
                # salvo que esa palabra ya tenga una corrección aprendida
                # (ver _apply_default_number_normalization) -- se hace
                # sobre el texto en crudo, antes de humanizar, para no
                # tener que lidiar con puntuación pegada a las palabras
                text, number_origins = self._apply_default_number_normalization(text)
                # "formato humano": mayúscula inicial + puntuación según la
                # entonación estimada por prosody.py (solo llega aquí si
                # estamos en DICTATING, que es cuando voice_recognizer
                # realmente calcula sentence_type; fuera de aquí siempre
                # sería "statement" por defecto y no se aplicaría nada raro)
                chunk = _humanize_chunk(text, sentence_type)
                chunk = self._apply_strict_corrections(chunk)
                self.primary_buffer = (self.primary_buffer + " " + chunk).strip() if self.primary_buffer else chunk
                self.gui.update_pretexto(self.primary_buffer, preview="")
                # _humanize_chunk/_apply_strict_corrections no cambian el
                # número de palabras del chunk, así que number_origins
                # sigue teniendo la misma cantidad de entradas
                self._word_origins.extend(number_origins)
                self._check_ambiguous_suggestion(chunk)
        else:
            # Este punto solo se alcanza en DICTATING (en IDLE se retorna
            # antes). El idioma secundario, mientras dictamos, es
            # exclusivamente para palabras de control (ver más arriba);
            # cualquier otra cosa que reconozca aquí es al mismo audio que
            # ya se transcribió/escribe en el idioma primario, así que se
            # descarta en vez de mostrarse como si fuera texto nuevo.
            if DEBUG:
                print(f"[command_router]   -> descartado (idioma secundario en dictado, no es comando): {text!r}")
            return

    def manual_action(self, action: str):
        """Acciones manuales desde GUI/tray, sin depender del idioma."""
        if action == "confirm":
            self._confirm_and_route()
            return
        if action == "reset":
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            self._arm_text_suppression(0.7)
            return
        if action == "correct_last_word":
            self._correct_last_word()
            return
        if action == "idle":
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            self._set_state("IDLE")
            # trae el GUI al frente si quedó detrás de otra ventana o se
            # ocultó (ver gui.bring_to_front) -- "idle" es un buen momento
            # neutro para hacerlo, ya que no interrumpe ningún dictado en curso
            try:
                self.gui.bring_to_front()
            except Exception as exc:
                if DEBUG:
                    print(f"[command_router] error en bring_to_front: {exc!r}")
            self._arm_text_suppression(0.7)
            return
        if action == "quit":
            self.gui.quit_app()
            return
        if action == "start_dictation":
            self._set_state("DICTATING")
            self.formuling = False
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            return
        if action == "start_formuling":
            self._set_state("DICTATING")
            self.formuling = True
            self.primary_buffer = ""
            self._word_origins = []
            self.secondary_buffer = ""
            self.gui.clear_pretexto()
            self._clear_suggestion()
            try:
                self.gui.update_formuling_indicator(True)
            except Exception:
                pass
            return
        if action == "copy_confirmed":
            self._copy_confirmed()
            return
        if action == "paste_confirmed":
            self._paste_confirmed()
            return
        if action == "select_confirmed":
            self._select_confirmed()
            return
        if action == "clear_confirmed":
            self._clear_confirmed()
            return

    def _sync_language_combo_ui(self):
        combo_label = f"{self.primary_language.upper()} > {self.secondary_language.upper()}"
        try:
            self.gui.set_ui_language(self.primary_language)
            self.gui.update_language_combo_label(combo_label)
        except Exception:
            pass

    # ---------- confirmación y enrutado (formato "posicion ... <accion>", legacy) ----------

    def _confirm_and_route(self):
        text = self.primary_buffer.strip()
        self.primary_buffer = ""
        self._word_origins = []
        self.secondary_buffer = ""
        self._set_state("IDLE")
        # ensure formuling indicator cleared
        try:
            self.gui.update_formuling_indicator(False)
        except Exception:
            pass
        self._clear_suggestion()
        self.gui.clear_pretexto()

        if not text:
            return

        norm = _normalize(text)
        if DEBUG:
            print(f"[command_router] confirmando texto: {text!r}")

        if norm.split() and norm.split()[0] in self._vc_trigger_aliases:
            vc_match = self._try_parse_vc(norm)
            if vc_match:
                handler_name, cell = vc_match
                if DEBUG:
                    print(f"[command_router]   -> vc OK: handler={handler_name} casilla={cell}")
                self._deselect_board_cell()
                handler = actions.VC_HANDLERS.get(handler_name)
                if handler:
                    handler(self.gui, cell)
            elif DEBUG:
                print(f"[command_router]   -> empezaba por 'vc'/'posicion' pero no se pudo parsear "
                      f"(número o acción no reconocidos): {norm!r}")
            return

        terminal_cmd = self._terminal_alias_map.get(norm)
        if terminal_cmd:
            actions.run_terminal_command(terminal_cmd)
            return

        # ruta por defecto (ver manual, Sección 2 Paso 3): sube el texto al
        # campo "Texto"; si config.AUTO_PASTE_ON_CONFIRM está activo (por
        # defecto SÍ), se pega automáticamente ahí mismo en la ventana
        # externa que tenga el foco (mismo mecanismo que decir "pegar
        # texto" a mano, ver _paste_confirmed) -- así no hace falta un
        # segundo comando tras "entra". Si está desactivado, se queda
        # acumulado en Texto hasta pedir "pegar texto"/"copiar texto"
        # explícitamente (para poder juntar varias frases antes de mandarlas).
        self.confirmed_text = (self.confirmed_text + "\n" + text) if self.confirmed_text else text
        self.gui.update_texto(self.confirmed_text)
        if DEBUG:
            print(f"[command_router]   -> subido a Texto (pendiente de copiar/pegar): {text!r}")
        if config.AUTO_PASTE_ON_CONFIRM:
            # clear_display: ver config.CLEAR_TEXT_FIELD_AFTER_AUTO_PASTE
            # -- por defecto True, así el campo "Texto" queda limpio en
            # cuanto el texto ya se ha escrito en la aplicación de
            # destino, listo para el siguiente dictado.
            self._paste_confirmed(
                clear_display=getattr(config, "CLEAR_TEXT_FIELD_AFTER_AUTO_PASTE", False)
            )

    def _append_formuling_text(self, text: str):
        """Append text interpreted as spelled letters to the buffer.
        formuling mode is literal: concatenate what the recognizer heard,
        without predictive mapping.
        """
        if not text:
            return
        tokens = text.split()
        for tok in tokens:
            norm = _normalize(tok)
            if not norm:
                continue
            self.primary_buffer = (self.primary_buffer + norm) if self.primary_buffer else norm
