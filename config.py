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
config.py: Configuración centralizada de VoiceController.

Todos los parámetros en un solo lugar, fácil de ajustar.
"""

import os
from pathlib import Path

# ==============================================================================
# AUDIO
# ==============================================================================

# Dispositivo de entrada de audio
# None = dispositivo por defecto
# O bien un índice numérico (0, 1, 2...) o nombre de dispositivo
# None = el que diga el sistema. Por defecto se deja así porque el índice
# correcto depende de CADA máquina: aquí el del usuario es el 5 y el del
# sistema es otro distinto, así que un número fijo en este fichero sería
# válido solo para él. El suyo va en config_local.py.
# Capa que toca el sistema (teclado, ratón, capturas, ventanas). Ver
# backends/. "auto" elige por sí misma según el sistema operativo;
# "linux" o "windows" lo fuerzan, sobre todo para probar.
BACKEND = "auto"

INPUT_DEVICE = None

# Ceder el micrófono a otra aplicación (Pipe-Logic) cuando lo pida, y
# recuperarlo cuando lo suelte. Ver cesion_microfono.py para el protocolo.
# CEDER_MICROFONO_SOCKET = None usa $XDG_RUNTIME_DIR/voicecontroller/microfono.sock
CEDER_MICROFONO_ENABLED = True
CEDER_MICROFONO_SOCKET = None

# Sample rate (Hz)
SAMPLE_RATE = 16000

# Tamaño de bloque de audio (muestras por callback)
AUDIO_BLOCKSIZE = 4096

# Tope de bloques de audio esperando a ser reconocidos (ver
# voice_recognizer._audio_callback). Con el micro local a 48000 Hz y bloques
# de 4096 muestras, cada bloque son ~85ms: 120 bloques son ~10s de margen.
# Si el reconocimiento se queda más atrás que esto se descarta lo más viejo
# en vez de dejar crecer la cola sin fin (una cola sin tope no se recupera
# nunca: el retraso solo se acumula, y lo reconocido acaba llegando minutos
# tarde). Si ves el aviso "cola de audio llena" a menudo, el cuello de
# botella es la CPU con los dos modelos grandes a la vez, no este número.
AUDIO_QUEUE_MAX_BLOCKS = 120

# ==============================================================================
# VOSK (MODELOS DE LENGUAJE OFFLINE)
# ==============================================================================

# Detectar si estamos en desarrollo o instalación
PROJECT_ROOT = Path(__file__).parent.absolute()

# Carpeta de modelos (se descarga en primera instalación)
VOSK_MODELS_DIR = PROJECT_ROOT / "vosk_models"
VOSK_MODELS_DIR.mkdir(exist_ok=True)

VOSK_MODEL_ES = str(VOSK_MODELS_DIR / "vosk-model-es-0.42")
VOSK_MODEL_EN = str(VOSK_MODELS_DIR / "vosk-model-en-us-0.42")

# EN CUANTOS PASOS SE HACE UN ARRASTRE
# -------------------------------------
# El comando "arrastra aqui" mantiene el boton pulsado y mueve el raton del
# origen al destino. Si ese movimiento se hiciera de un salto, muchos
# programas -- Inkscape, los gestores de archivos -- no dibujarian el
# recuadro de seleccion: solo lo empiezan cuando VEN el raton moverse con el
# boton pulsado.
#
# Doce pasos son movimiento de sobra y siguen siendo casi instantaneos
# (unos 0,25 s). Subirlo si algun programa se resiste.
ARRASTRE_PASOS = 12

# LA LENGUA MATERNA
# ------------------
# El proyecto nació como una aplicación bilingüe simétrica, y el 5-sep-2026
# quedó claro que eso no era cierto ni podía serlo. Tres pruebas:
#
#   - numbers_es era el ÚNICO parser de números. Las casillas, las zonas,
#     "corrige <nº>"... toda la estructura numérica hablaba solo español.
#     Con el inglés de principal, esa mitad de la aplicación no respondía.
#   - gui.set_dictation_language_callback() no la llamaba NADIE: el camino
#     del cambio de idioma no se había ejecutado nunca en producción.
#   - Dictando, todo lo del idioma secundario sale como "descartado
#     (idioma secundario en dictado, no es comando)".
#
# O sea que el secundario ya era, de hecho, un cazador de comandos y nada
# más. Esto no lo degrada: lo nombra.
#
# La idea, de pipataki: una LENGUA MATERNA que domina -- dicta, cuenta,
# puntúa, estructura -- y OTRA LENGUA que se maneja como una habilidad,
# reconociendo órdenes. Como una persona: nativa en una, competente en
# otra. Y cambiar de lengua materna es como cambiar el idioma del sistema:
# se elige, se reinicia. Nadie espera hacerlo a media frase.
#
# PENDIENTE (etapa 2): con LENGUA_MATERNA = "en" el programa FUNCIONA en
# inglés -- dictado, comandos, casillas -- pero te sigue HABLANDO en
# español: la ayuda, los avisos y la voz de Piper están en español, y no
# existe math_notation_en. Hace falta para que lo usen en Estados Unidos,
# Reino Unido y la Commonwealth, y está apuntado como trabajo propio.
LENGUA_MATERNA = "es"          # "es" | "en"
OTRA_LENGUA = "en" if LENGUA_MATERNA == "es" else "es"

# LOS MODELOS PEQUEÑOS, PARA EL IDIOMA SECUNDARIO
# -----------------------------------------------
# El idioma secundario NO dicta nunca. Solo se le pregunta si lo que se ha
# oído es uno de los comandos de su lista, que es corta y cerrada. Para eso
# el modelo pequeño no es un apaño: es la herramienta que toca.
#
# Y la diferencia es brutal. Medido el 5-sep-2026 en esta misma máquina,
# cargando los modelos uno a uno:
#
#     español grande ....... 3.377 MB      (4,1 s en cargar)
#     inglés  grande ....... 6.686 MB      (6,9 s en cargar)
#     inglés  pequeño .........155 MB      (0,2 s)  decodificando de verdad
#     español pequeño ......... 54 MB      (0,2 s)
#
# Con los dos grandes cargados a la vez -- que es como estaba hasta hoy --
# la aplicación pedía 10.260 MB solo de modelos, y el pico medido en una
# sesión real fue de 12.746 MB. Con el grande de principal y el pequeño de
# secundario: 3.530 MB. Casi 6,7 GB menos, y la mitad de CPU, porque cada
# trozo de audio se decodifica dos veces y una de las dos pasa a ser barata.
#
# De ahí venían los ventiladores al arrancar.
VOSK_MODEL_ES_SMALL = str(VOSK_MODELS_DIR / "vosk-model-small-es-0.42")
VOSK_MODEL_EN_SMALL = str(VOSK_MODELS_DIR / "vosk-model-small-en-us-0.15")

# Si el pequeño del secundario no está descargado, se usa el grande y todo
# sigue funcionando como siempre: esto no puede dejar a nadie sin idioma.
# Ponlo en False para volver al comportamiento antiguo (los dos grandes).
SECONDARY_SMALL_MODEL = True


# ==============================================================================
# WEBAPP (micrófono remoto / streaming de escritorio)
# ==============================================================================

# Si está activo, main.py arranca el servidor Flask (webapp/app.py) en un
# hilo en segundo plano al iniciar VoiceController, y lo detiene al cerrar.
ENABLE_WEBAPP = os.environ.get("VOICECONTROLLER_ENABLE_WEBAPP", "1") == "1"

# ==============================================================================
# DETECCIÓN DE SILENCIO (VAD ligero por energía RMS)
# ==============================================================================

# Nivel RMS (sobre audio int16, rango 0-32767) por debajo del cual un bloque
# de audio se considera "silencio". Depende del micrófono/ganancia: si el LED
# de voz se queda siempre encendido con ruido de fondo, sube este valor; si
# se queda apagado incluso hablando, bájalo. Se puede afinar viendo el nivel
# numérico que muestra la GUI mientras hablas y en silencio.
SILENCE_RMS_THRESHOLD = 300

# Nº de bloques consecutivos por debajo del umbral para pasar a "silencio".
# El ataque (silencio -> voz) es inmediato; solo la vuelta a silencio tiene
# este pequeño retardo, para no parpadear entre palabras de una misma frase.
SILENCE_HANGOVER_BLOCKS = 4

# ==============================================================================
# SUGERENCIAS EN PAUSA (campo "Sugerencias" del GUI)
# ==============================================================================

# Milisegundos sin actividad de texto (mientras se dicta) tras los que se
# evalúa si hay algo que sugerir (p.ej. "esto que acabas de decir parece una
# expresión numérica, ¿la paso a modo fórmula?"). No confundir con
# SILENCE_RMS_THRESHOLD (ese es a nivel de audio/VAD; este es a nivel de
# texto ya reconocido, para no interrumpir mientras la persona sigue hablando).
PAUSE_SUGGESTION_MS = 900

# Cada cuánto se comprueba si ha pasado PAUSE_SUGGESTION_MS sin actividad.
PAUSE_POLL_MS = 250

# Cada cuánto se comprueba si la ventana del GUI ha cambiado visualmente
# para volcarla a vc.png (ver GUI._maybe_capture_vc_snapshot() en gui.py y
# VC_FILE en paths.py) -- la webapp la usa como "espejo" del GUI en vez de
# mostrar el escritorio completo (tablero.png). Solo se escribe a disco
# cuando el contenido cambia de verdad (comparación de imagen), así que un
# intervalo bajo no genera escrituras innecesarias si la ventana está
# quieta.
VC_SNAPSHOT_POLL_MS = 400

# Cada cuánto (ms) se comprueba la posición real del puntero para que el
# círculo verde de la casilla ampliada la siga en vivo (ver
# gui.GUI._do_touch_track / config del tablero, comando de voz "click
# verde"/"mueve verde" en command_router.py). Un intervalo bajo da un
# seguimiento más fluido a costa de más CPU -- 33ms es ~30 actualizaciones
# por segundo, de sobra para una indicación visual.
TOUCH_TRACK_POLL_MS = 33

# ==============================================================================
# PEGADO DEL TEXTO CONFIRMADO EN VENTANA EXTERNA ("pegar texto")
# ==============================================================================

# Antes de "pegar texto" (ver command_router._paste_confirmed), el GUI se
# manda solo detrás/oculto un momento y se restaura al frente justo
# después -- eso ya basta en la mayoría de los casos para que la ventana
# externa (cualquiera que sea) recupere el foco de forma natural, SIN
# necesitar saber cuál es. Lo de abajo es solo un extra opcional para
# casos raros donde eso no baste y quieras forzar una ventana concreta.
#
# OPCIONAL/AVANZADO. Expresión regular que debe coincidir con el TÍTULO
# de una ventana externa concreta -- si la rellenas, además de lo de
# arriba se intenta activar ESA ventana en concreto con `kdotool`
# (https://github.com/jinliu/kdotool -- ver actions.activate_target_window();
# instálalo descargando el binario desde sus releases de GitHub, como
# explica install.sh). NOTA: `kstart`/kde-cli-tools NO sirve para
# esto en KDE Frameworks 6 -- perdió las opciones --window/--activate en
# la reescritura para KF6, comprobado directamente en su código fuente.
# Vacío ("") por defecto = desactivado (recomendado, no hace falta para
# el caso normal).
PASTE_TARGET_WINDOW_REGEX = ""

# Milisegundos de espera tras mandar el GUI detrás (y tras
# activate_target_window() si se usa) y antes de escribir el texto, para
# dar tiempo a que el compositor complete el cambio de foco.
PASTE_ACTIVATE_DELAY_MS = 200

# Si es True, en cuanto se confirma un dictado ("entra") y el texto sube
# al campo "Texto", se pega automáticamente en la ventana externa (mismo
# mecanismo que decir "pegar texto" a mano -- ver
# command_router._paste_confirmed()), sin esperar a un comando aparte.
# Si es False (comportamiento de antes), el texto se queda acumulado en
# "Texto" hasta que digas "pegar texto"/"copiar texto" explícitamente
# (útil si quieres juntar varias frases confirmadas antes de mandarlas
# todas juntas).
AUTO_PASTE_ON_CONFIRM = True

# Si es True, cuando el auto-pegado de arriba ya ha mandado el texto a la
# aplicación de destino, el campo "Texto" del GUI se VACÍA -- el texto ya
# ha cumplido su función (está escrito en la otra ventana) y dejarlo ahí
# solo confunde: parece pendiente de enviar cuando ya se envió, y hacía
# falta decir "vaciar texto" a mano antes del siguiente dictado. Ponlo a
# False para volver al comportamiento anterior (el campo se queda
# mostrando la última frase enviada, como registro de lo que se mandó).
# Solo afecta al auto-pegado: sin AUTO_PASTE_ON_CONFIRM el texto sigue
# acumulándose en "Texto" hasta que se pida pegar/copiar/vaciar.
CLEAR_TEXT_FIELD_AFTER_AUTO_PASTE = True

# Si es True, justo después de escribir el texto (type_text) y ANTES de
# devolver el foco a VoiceController, se envía una pulsación de Enter
# (actions.press_enter()) -- pensado para cuando el texto se pega en un
# buscador o barra de direcciones: sin esto, la búsqueda/navegación no
# se disparaba sola porque el foco volvía a VoiceController antes de que
# el usuario pudiera pulsar Enter a mano. En un editor de texto normal,
# el efecto es simplemente una línea nueva -- razonable si se sigue
# escribiendo ahí después. Si prefieres que NUNCA se envíe Enter
# automáticamente (por ejemplo si pegas a menudo dentro de una palabra u
# oración ya empezada), ponlo a False.
AUTO_ENTER_AFTER_PASTE = True

# Milisegundos de espera entre escribir el texto y enviar el Enter (si
# AUTO_ENTER_AFTER_PASTE está activo), para dar tiempo a que la app
# destino procese el texto recién escrito antes de la tecla.
PASTE_ENTER_DELAY_MS = 100

# ==============================================================================
# VOZ DEL PROPIO VOICECONTROLLER (Piper-TTS)
# ==============================================================================
# Ver tts.py. Se usa para leer la ayuda ("ayuda audio") y para el aviso
# "no te entiendo".

TTS_ENABLED = True

# "piper"  -> voz neuronal local, la que suena bien (paquete piper-tts).
# "espeak" -> fuerza el respaldo robótico. Si se pide "piper" y no está
#             disponible, se cae a espeak solo, sin quedarse mudo.
TTS_ENGINE = "piper"

# UNA VOZ POR IDIOMA. Si el programa te habla en inglés, tiene que sonar
# en inglés: una voz española leyendo texto inglés es ininteligible, porque
# Piper pronuncia con la fonética de su idioma ("the window" sale como
# "te uindou"). Y en accesibilidad, una voz que no se entiende es lo mismo
# que no tener voz.
#
# La que toque se elige por config.LENGUA_MATERNA (ver tts._voz_del_idioma).
TTS_PIPER_VOICES = {
    "es": str(PROJECT_ROOT / "piper_voices" / "es_ES-sharvard-medium.onnx"),
    "en": str(PROJECT_ROOT / "piper_voices" / "en_US-lessac-medium.onnx"),
}

# Se conserva por compatibilidad: es la que se usa si el idioma no tiene
# voz propia. Nunca se queda sin voz por esto.
TTS_PIPER_VOICE = TTS_PIPER_VOICES["es"]

# "femenina" | "masculina". SOLO tiene efecto en modelos con más de un
# hablante: es_ES-sharvard-medium trae los dos en el mismo fichero
# (speaker_id_map = {"M": 0, "F": 1}), así que cambiar esto no requiere
# descargar nada. En un modelo de un solo hablante se ignora, con aviso.
#
# Pensado también para la DISTRIBUCIÓN: es la única opción que hay que
# ofrecer en una instalación limpia para que cada persona elija el sexo
# de la voz del asistente. Ver tools/probar_voces.py para escucharlas.
TTS_VOICE_GENDER = "femenina"

# Velocidad del habla, y significa lo que parece: 1.0 es el ritmo normal
# del modelo, **MENOS de 1.0 habla más DESPACIO** (0.85 = un 15% más
# lenta) y más de 1.0 más deprisa.
#
# (Por dentro, Piper no usa velocidad sino `length_scale`, que es un
# multiplicador de DURACIÓN y por tanto va al revés. Antes este ajuste
# exponía ese número tal cual, llamándolo "SPEED": una trampa, porque
# bajarlo aceleraba la voz. Ahora se invierte en tts.py y aquí el número
# se lee como cualquiera esperaría.)
TTS_SPEED = 1.09

# Frase del aviso cuando no se entiende algo dirigido a la aplicación.
TTS_NOT_UNDERSTOOD_TEXT = "No te entiendo. ¿Me lo repites?"

# Segundos de SILENCIO del micrófono después de que la voz termine de
# sonar. Sin esto, VoiceController se oiría a sí mismo y transcribiría su
# propio "no te entiendo" como si fuera una orden.
TTS_MIC_MUTE_TAIL_MS = 400

# Mínimo entre avisos hablados de la MISMA categoría (segundos). Es lo que
# evita que la aplicación se vuelva insoportable: en la prueba con las
# noticias puestas, el reconocedor cerró más de 150 frases ajenas en un
# rato -- decir algo en cada una sería insufrible. Si un aviso llega
# demasiado pronto se DESCARTA, no se encola.
#   "help"           -> lo ha pedido el usuario a propósito: sin límite.
#   "not_understood" -> es él, pero no se le ha entendido el comando.
#   "intruder"       -> voz ajena que suena dirigida a la máquina; el más
#                       espaciado de los tres, porque es el que puede
#                       dispararse solo con la tele puesta.
# Avisar en alto ("no te entiendo") cuando SÍ es su voz pero no se ha
# entendido el comando. Ponlo a False si prefieres que la aplicación
# solo hable cuando se le pide la ayuda.
TTS_NOT_UNDERSTOOD_ENABLED = True

# Mandar también al móvil (webapp) lo que dice la aplicación. El móvil lo
# reproduce en el HUECO ENTRE TROZOS de grabación, que es cuando su
# micrófono está parado -- si sonara con el micrófono abierto, se grabaría
# a sí mismo y mandaría la voz de vuelta al PC como si fuera una orden.
TTS_SEND_TO_MOBILE = True

# Con el micrófono del móvil en uso, ¿debe CALLARSE el altavoz del PC?
#
# Lo que pasaba con los dos sonando: la misma frase se oye dos veces, y la
# del móvil llega DETRÁS (tiene que subir el audio, decodificarse y bajar).
# Al pedir el santo y seña eso despista de verdad -- oyes el principio por
# el ordenador y el final por el teléfono, desfasados.
#
# Y la que vale es la del móvil, porque es la que se oye estando lejos.
#
# Solo se aplica en modo red. Con el micrófono del PC, el ordenador habla
# como siempre. Y si el envío al móvil está apagado, tampoco se calla: más
# vale oírlo dos veces que no oírlo.
TTS_SOLO_MOVIL_EN_RED = True

# Cuántos comandos se LEEN como mucho en "ayuda audio". La lista de idle
# pasa de cuarenta y leerla entera serían varios minutos de voz que no
# hay quien aguante ni recuerde; el resto se remite a la ventana, que sí
# los muestra todos.
TTS_HELP_MAX_ITEMS = 12

# Cuántas palabras o menos cuentan como "frase corta". Un comando suelto
# ("tab", "espacio", "click derecho") entra aquí; una frase hablada, no.
TTS_NOT_UNDERSTOOD_SHORT_WORDS = 2

TTS_MIN_INTERVAL_S = {
    "help": 0,
    "not_understood": 12,
    # Frases CORTAS: mucho más espaciado. Con palabras de una sílaba el
    # reconocedor falla a menudo con algo parecido ("tab" -> "adulador"),
    # no encaja con ningún comando y saltaba el aviso una y otra vez. El
    # fallo se sigue anotando en el log igual; lo que cambia es cuánto se
    # dice en alto. Pon None para que en frases cortas no diga NADA.
    "not_understood_short": 120,
    "intruder": 60,
}

# Números que el reconocedor confunde a menudo, y con qué se confunden.
#
# Solo se aplica al ARGUMENTO NUMÉRICO de un comando ("mover <n>",
# "click <n>"...), nunca al texto dictado: "pie" es una palabra normal y
# en un dictado debe seguir siendo "pie", no un 10. Por eso la
# sustitución vive en el parseo de comandos y no en numbers_es.
#
# Sale de su log real: diciendo "mover diez" 11 veces, 5 se oyeron como
# "mover tie", "mover tier" o "mover pie" -- las palabras de una sílaba
# son justo las que peor reconoce Vosk. Es la misma convención que ya usa
# commands.json con "idel", "oquei" o "faierfox": añadir la transcripción
# equivocada como alias de lo que se quería decir.
#
# Amplíalo con lo que veas en tu propio log.
NUMBER_MISHEARD = {
    "tie": "diez",
    "tier": "diez",
    "tie r": "diez",
    "pie": "diez",
    "quier": "diez",
    "dies": "diez",
}

# En estado de ESCUCHA, ¿qué se hace con el idioma SECUNDARIO?
#
# Los dos motores oyen el MISMO audio, así que hablando en español el
# motor inglés transcribe disparates en paralelo ('mover diez' ->
# 'moreover viet', 'mover' -> 'mobility'). Pero NO todo lo suyo es
# basura: el léxico inglés contiene `firefox`, `inkscape`, `konsole`,
# `backspace`, `listen`, `undo`, `redo`, `insert`, `delete`... que el
# español NO tiene. Los alias ingleses de commands.json funcionan
# gracias a ese motor, y son de uso diario.
#
#   "commands" (por defecto) -> del secundario se acepta SOLO lo que
#       encaje con un comando existente; el resto se tira sin más. Así
#       siguen funcionando "firefox", "undo" o "select all", y a la vez
#       desaparecen los disparates, que nunca coinciden con un alias.
#   "all"  -> se acepta todo (comportamiento antiguo: ensuciaba el
#       contador de "no entendido" y contaba intrusos falsos).
#   "none" -> se ignora entero. Pierdes todos los alias ingleses.
SECONDARY_LANGUAGE_IN_IDLE = "commands"

# Ventana (segundos) para no ejecutar DOS VECES el mismo comando cuando
# los dos motores transcriben la misma voz ("click" en inglés y "clic" en
# español a la vez). El segundo se descarta.
DUPLICATE_COMMAND_WINDOW_S = 1.5

# ==============================================================================
# SANTO Y SEÑA: identificarse por voz al arrancar y cada cierto tiempo
# ==============================================================================
# Idea suya, y la medida la respalda: la verificación por voz funciona muy
# bien con frases LARGAS (su voz 0,684-0,811 contra 0,199-0,346 de las
# ajenas, un hueco de +0,338) y es inútil con palabras sueltas (0,292-0,577
# frente a ajenas de hasta 0,346: se solapan).
#
# Así que en vez de pelearse con la debilidad, se apoya en la fuerza:
# verificar UNA VEZ bien, con una frase larga, y confiar en la sesión.
#
# Se comprueba SOLO LA VOZ, no lo que se diga: la frase está para
# garantizar audio suficiente, que es lo que hace fiable al x-vector.
# Como secreto valdría poco de todas formas (quien esté en la habitación
# lo oye), y exigir el texto exacto solo añadiría una forma más de
# quedarse fuera si el reconocedor falla una palabra.

VOICE_LOGIN_ENABLED = True

# Lo que dice el ordenador al pedirlo. La frase de ejemplo se usa SOLO en
# la calibración (`speaker_calibration.py login`): en el GUI no se escribe
# nunca, para no dejarla puesta en pantalla a la vista de cualquiera que
# pase por delante. Vale cualquier frase de duración parecida: no se
# comprueba el texto, solo la voz.
VOICE_LOGIN_PROMPT = "Santo y seña."

# Lo que dice al RECONOCERTE. Sin esto, la única señal de que ya estás
# dentro era que desapareciera el aviso de la pantalla -- una señal muda,
# y encima solo visible: trabajando sin mirar el monitor no había forma de
# saber cuándo se podía empezar a dar órdenes.
VOICE_LOGIN_OK_TEXT = "Te escucho."
VOICE_LOGIN_HINT = "La lluvia en Sevilla es una maravilla"

# Umbral propio, MEDIDO con la frase real (5 repeticiones, 29-08-2026):
#
#   su santo y seña : 0,542 - 0,616  (media 0,581, muy estable)
#   voces ajenas    : 0,199 - 0,346
#   banda segura    : 0,346 .. 0,542  (anchura 0,196)
#
# 0,44 es el punto equidistante: +0,102 por debajo de su peor intento y
# +0,094 por encima de la peor voz ajena. Se eligió el centro y no algo
# más alto porque la asimetría de costes va en esa dirección: quedarse
# fuera de tu propia herramienta de accesibilidad es peor que colar a
# alguien, sobre todo cuando esto NO es autenticación (una grabación
# pasaría igual) sino un filtro. Y con solo 5 muestras, un catarro o
# hablar más lejos del micro se comen un margen estrecho.
#
# Confirma la duración como factor: esta frase (~2,5 s) puntúa 0,58 de
# media, contra 0,68-0,81 de las frases de enrolado (6 s). Por eso NO se
# podía heredar el umbral de dictado.
VOICE_LOGIN_THRESHOLD = 0.44

# El mismo umbral, pero para el santo y seña dicho al MÓVIL. Aparte desde el
# 14-sep-2026: el micro del móvil puntúa bastante más bajo que el del PC, y
# con uno solo para los dos, lo que calibre el PC deja fuera al móvil. En la
# VM de pruebas la calibración puso 0,60 (con su micro) y el santo y seña del
# móvil daba 0,566: ni se identificaba a la primera ni podía despertar de la
# espera. 0,44 queda, como el del PC, por encima de la peor voz ajena medida
# (0,346). Pon None para que el móvil use el mismo que el PC.
VOICE_LOGIN_THRESHOLD_NETWORK = 0.44

# Intentos FALLIDOS seguidos antes de abortar. Solo cuentan los intentos
# REALES: alguien contesta con una frase verificable y no es él. El
# silencio NO cuenta -- si no, irse quince minutos dejaría el ordenador
# bloqueado al volver. Una frase demasiado corta para verificar tampoco
# cuenta: no es un fallo, es que no se ha podido saber.
VOICE_LOGIN_MAX_FAILURES = 3

# Cada cuánto se vuelve a pedir por reloj, en segundos. 0 = nunca.
#
# DESACTIVADO por defecto a propósito: preguntar cada X minutos
# interrumpe trabajes o no, y no distingue "sigue aquí" de "se ha ido".
# En su lugar está el STANDBY de abajo, que es lo que él pidió: se pone
# en espera cuando tú quieres (o solo al dejar de usarlo), y para salir
# hace falta el santo y seña. Súbelo de 0 si además quieres el reloj.
VOICE_LOGIN_INTERVAL_S = 0

# ==============================================================================
# STANDBY: dejar de escuchar hasta decir el santo y seña
# ==============================================================================
# Di "standby" (o "duerme", "en espera", "pausa") y el sistema deja de
# obedecer NADA. Se vuelve diciendo el santo y seña, sin más: la voz se
# valida con el listón de login, así que dejar el ordenador solo no lo deja
# abierto a cualquiera. ("revive" se quitó el 14-sep-2026: era un paso de más.)
#
# Es mejor que un temporizador porque no interrumpe mientras trabajas y
# porque distingue de verdad "sigue aquí" de "se ha ido".

# Segundos sin oír NADA reconocible tras los cuales se entra en standby
# solo. 0 = solo manual.
#
# Diez minutos de fábrica. Es un ajuste PERSONAL: cada uno trabaja a su
# ritmo, y lo que a uno le parece "ya no está" a otro le corta a mitad de
# pensar. Quien quiera otro valor lo pone en config_local.py, que no se pisa
# al actualizar:
#
#     STANDBY_AFTER_IDLE_S = 420   # siete minutos
STANDBY_AFTER_IDLE_S = 600

# ==============================================================================
# DETECCIÓN DE INTRUSOS Y ABORTO POR SEGURIDAD
# ==============================================================================
# Ver command_router._register_intruder_strike(). El contador NO sube con
# cualquier voz ajena: si lo hiciera, la tele o alguien con mala idea
# podrían PROVOCAR EL BLOQUEO a propósito y dejarte fuera de tu propio
# ordenador -- justo lo contrario de lo que se busca. Solo cuenta cuando
# se cumplen LAS CUATRO condiciones a la vez:
#
#   1. No es tu voz          -> veredicto del filtro (speaker_id.py)
#   2. Está CERCA            -> pico de energía por encima de INTRUDER_MIN_RMS
#   3. Se le entiende bien   -> confianza por encima de INTRUDER_MIN_CONFIDENCE
#   4. Es un comando de VERDAD -> la frase encaja con un alias existente
#
# La cuarta es la que de verdad separa "hay una tele puesta" de "hay
# alguien dándole órdenes a mi ordenador": el ruido de un telediario casi
# nunca cae justo en un alias, mientras que quien intenta mandar en la
# máquina cumple las cuatro por definición.

INTRUDER_DETECTION_ENABLED = True

# Margen EXTRA por debajo del umbral para contar un intento de intrusión.
# El umbral de comandos (0,18) está puesto bajo a propósito para no
# rechazarle nunca; acusar a alguien de intrusión merece más certeza que
# filtrar una frase. Con 0,05, una voz tiene que puntuar por debajo de
# 0,13 para contar.
INTRUDER_SCORE_MARGIN = 0.05

# Pico de energía mínimo para considerar que se dijo CERCA del micrófono.
# SILENCE_RMS_THRESHOLD (=300) es solo el umbral de "aquí hay algo"; para
# "esto se ha dicho delante del ordenador" hace falta bastante más. Este
# número es el que hay que calibrar con el log: cada intento se anota con
# su rms real aunque no llegue a contar.
INTRUDER_MIN_RMS = 1500

# Confianza mínima del reconocedor. El habla lejana y reverberante puntúa
# bajo; quien habla de cerca, alto.
INTRUDER_MIN_CONFIDENCE = 0.70

# Cuántos intentos seguidos hacen falta para abortar. El contador se pone
# a CERO en cuanto se reconoce un comando tuyo: son intentos SEGUIDOS de
# alguien que no eres tú, no un total acumulado a lo largo del día.
INTRUDER_STRIKES_TO_ABORT = 3

# Si es True, al llegar a los intentos de arriba se dejan de obedecer TODOS
# los comandos de voz hasta desbloquear. Ponlo a False para que solo avise
# de viva voz y en el log sin llegar a bloquear nunca -- recomendable hasta
# haber visto en el log real que INTRUDER_MIN_RMS está bien calibrado.
# Desde que VOZ_AJENA_NO_ACTUA existe, esto va a False por defecto. El bloqueo
# tenia sentido cuando una voz ajena SI ejecutaba ordenes: era lo unico que la
# paraba. Ahora no ejecuta ninguna, asi que bloquear no anade seguridad -- solo
# anade la posibilidad de que alguien te deje fuera de tu propio ordenador a
# proposito, diciendo tres tonterias delante del microfono.
INTRUDER_ABORT_ENABLED = False

# El bloqueo se levanta solo pasados estos segundos. Es una red de
# seguridad DELIBERADA: si alguien consigue disparar el bloqueo a
# propósito, el daño está acotado en el tiempo y no te deja fuera para
# siempre. Ponlo a 0 para que solo se pueda desbloquear a mano.
INTRUDER_LOCK_SECONDS = 300

# Aviso hablado al bloquear (ver tts.py, categoría "intruder").
INTRUDER_ABORT_TEXT = ("He detectado órdenes de una voz que no reconozco. "
                       "Dejo de obedecer por seguridad. "
                       "Di: soy yo, para continuar.")

# ------------------------------------------------------------------------------
# VOZ AJENA: NO ACTUAR, EN VEZ DE ACTUAR Y LUEGO BLOQUEAR
# ------------------------------------------------------------------------------
# Con True, una voz VERIFICADA como ajena no ejecuta NADA: ni comandos, ni
# dictado, ni nada que pueda comprometer algo. No se bloquea el programa, no
# se castiga a nadie, no pasa nada de nada. Solo se pregunta en alto
# VOZ_AJENA_PREGUNTA, espaciado, y si quien esta delante dice "soy yo" se le
# pide el santo y sena igual que en el arranque.
#
# Antes esto NO era asi, y es importante entender por que se cambia. El filtro
# de voz nacio en modo "warn" (SPEAKER_ID_MODE), que por diseno NO descarta
# nada: solo anota en el log lo que HABRIA descartado. La idea era mirar unos
# dias que tal acertaba antes de dejarle actuar. El efecto lateral es que una
# voz ajena SI ejecutaba sus ordenes, y lo unico que la paraba era el bloqueo,
# que llegaba al TERCER intento. O sea, lo peor de las dos cosas: dos ordenes
# ajenas se ejecutaban, y ademas acababas bloqueado.
#
# Esta opcion separa las dos decisiones, que nunca debieron ir juntas:
#
#   - "no te reconozco, no hago nada"  -> siempre, sin coste ninguno
#   - "me bloqueo"                     -> ya no hace falta (ver abajo)
#
# Y no puede dejarte fuera: si el filtro se equivoca y no te reconoce a TI,
# dices "soy yo", te pide el santo y sena, y entras. Igual que el primer dia.
VOZ_AJENA_NO_ACTUA = True

# Lo que se dice a quien no se reconoce. Va espaciado (categoria "intruder" de
# tts.py, 60 s por defecto), no en cada frase: sonar sin parar seria
# insoportable y ademas delataria que el ordenador esta escuchando.
VOZ_AJENA_PREGUNTA = "¿Eres tú realmente? No te reconozco."

# ==============================================================================
# RECONOCIMIENTO DE LOCUTOR (filtrar voces ajenas: tele, radio, otra gente)
# ==============================================================================
# Ver speaker_id.py para el porqué de CADA número de aquí: todos salen de
# la calibración hecha en esta misma máquina con
# tools/speaker_calibration.py, no de valores por defecto de nadie.

# Interruptor general. Con el perfil creado, ponerlo a False es la forma
# de desactivarlo del todo sin desinstalar nada (la otra salida de
# emergencia, sin tocar ficheros, está en el menú de la bandeja del
# sistema: "Filtrar por mi voz").
SPEAKER_ID_ENABLED = True

# De QUÉ micrófonos se verifica la voz. Medido el 30-08-2026: el perfil
# se enroló con el micrófono del PC y NO sirve para el del móvil. La
# misma frase, dicha seguida:
#
#     micro=device   -> santo y seña CORRECTO
#     micro=network  -> 0,111  (umbral 0,44)
#     "click" suyo   -> -0,012 (contó como INTRUSO)
#
# No es un umbral mal puesto: el micrófono del teléfono, la compresión
# Opus y el remuestreo mueven tanto el x-vector que el perfil deja de
# valer. Bajar el umbral hasta ahí dejaría entrar a cualquiera.
#
# Así que cada canal usa la autenticación que SÍ puede hacer:
#   - el micrófono del PC, por voz (no tiene contraseña que dar);
#   - el del móvil, por la contraseña de la webapp sobre HTTPS, que es
#     un secreto de verdad y no depende del acústica.
#
# Si algún día se enrola un perfil aparte grabado CON el móvil, se puede
# añadir "network" aquí.
SPEAKER_ID_SOURCES = ("device", "network")

# Grabar el perfil del móvil automáticamente la PRIMERA vez que se
# conecta. Es la única ocasión en que se tiene audio suyo, así que se
# aprovecha; después no vuelve a pedirse. Para repetirlo, borra
# config/speaker_profile_network.json.
MOBILE_ENROLL_ON_FIRST_CONNECT = True

# "warn"  -> NO descarta nada: solo anota por consola lo que HABRÍA
#            descartado. Es el modo con el que se empieza, para ver qué
#            haría durante unos días de uso real antes de dejarle actuar.
# "block" -> descarta de verdad las frases que no superen el umbral.
SPEAKER_ID_MODE = "warn"

# Umbral para el DICTADO (frases largas). Medido: su voz 0,684-0,811 y
# las voces ajenas 0,199-0,346, con toda la banda 0,45-0,60 dando cero
# errores en ambos sentidos. 0,50 va en el centro de esa banda, no en su
# borde.
SPEAKER_ID_THRESHOLD_DICTATION = 0.50

# Umbral para los COMANDOS (palabras sueltas). Aquí las distribuciones SÍ
# se solapan (su voz 0,292-0,577, ajenas hasta 0,346), así que este
# número está elegido a propósito por DEBAJO de su peor comando medido,
# no pegado a él: más vale colar alguna voz ajena que rechazarle un
# comando propio, que en una aplicación de accesibilidad significa tener
# que repetirlo todo.
#
# 0,18 es la RODILLA de la curva, medida con sus datos reales
# (14 comandos suyos, 17 frases de un telediario):
#
#     umbral   margen bajo tu peor comando   te rechaza   bloquea tele
#      0.25            -0.002                 0/14          71%
#      0.22            +0.028                 0/14          59%
#      0.20            +0.048                 0/14          53%
#      0.18            +0.068                 0/14          47%
#      0.15            +0.098                 0/14          47%   <- ya no mejora
#
# Se bajó de 0,25 porque su peor comando conocido ('ayudas', que era él
# diciendo "ayuda") puntuó 0,248: se le habría rechazado por 0,002. Con
# 0,18 quedan 0,068 de margen por debajo de ese caso.
#
# Por debajo de 0,18 la protección ya no baja... pero tampoco sube: ese
# 47% son las frases que NO dan x-vector, que se descartan siempre pase
# lo que pase (8 de las 17 ajenas; la tele lejana muchas veces ni se
# puede caracterizar). O sea que en los comandos cortos quien protege de
# verdad es esa regla, no el umbral.
SPEAKER_ID_THRESHOLD_COMMAND = 0.15
#
# BAJADO DE 0,18 A 0,15 el 5-sep-2026, con datos de uso real. En dos
# sesiones seguidas, la palabra "uno" (para entrar en la casilla 1, que es
# de lo primero que se dice) puntuo 0,173 y 0,174: rechazada por dos
# milesimas. El era el que hablaba.
#
# Ese caso NO estaba en la calibracion original -- el peor comando medido
# entonces fue 'ayudas' con 0,248 -- porque "uno" es mas corta todavia.
#
# Y bajar no cuesta proteccion NINGUNA: en la tabla de arriba, 0,18 y 0,15
# bloquean exactamente el mismo 47% de la television. Ese 47% son las
# frases que no dan x-vector, que se descartan siempre pase lo que pase.
# Por debajo de 0,18 la curva ya estaba plana; solo se gana margen.

# CUANTAS PALABRAS son "corto" para elegir umbral.
#
# El umbral NO se elige por el estado (dictando o no) sino por LO QUE SE HA
# DICHO, y esto no es una politica discutible: es corregir una comparacion
# mal hecha. La puntuacion del x-vector BAJA con la duracion del audio, asi
# que medir una palabra suelta con el liston de las frases largas es
# comparar peras con manzanas. Con los numeros de arriba:
#
#     sus frases largas    0,684 - 0,811     liston 0,50   holgado
#     sus palabras sueltas 0,292 - 0,577     liston 0,50   FALLA casi siempre
#
# El 5-sep-2026 eso monto una trampa cerrada. Dictando, el liston es 0,50;
# el dice "cerrar" (0,470) y se le rechaza por voz ajena; al rechazarse, NO
# se sale del dictado; y al seguir dictando, el liston sigue en 0,50. Es
# decir: EL LISTON ALTO IMPIDE JUSTO EL COMANDO QUE SACARIA DEL LISTON ALTO.
# Estuvo dando vueltas con el santo y sena correcto cuatro veces seguidas.
#
# Pasa igual en el modo con ventana: no es del modo servicio.
#
# 3 palabras cubre "entra", "soy yo", "cerrar ventana", "doble clic uno".
# Subirlo mucho haria que frases dictadas cortas se midieran con el liston
# flojo; bajarlo dejaria fuera "cerrar ventana".
SPEAKER_ID_PALABRAS_CORTO = 3

# Modelo de locutor de Vosk (descargable de
# https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip) y perfil de
# voz generado con `python tools/speaker_calibration.py export`.
SPEAKER_ID_MODEL = str(VOSK_MODELS_DIR / "vosk-model-spk-0.4")
SPEAKER_PROFILE_FILE = str(PROJECT_ROOT / "config" / "speaker_profile.json")

# Perfil APARTE para el micrófono del móvil. Hace falta uno propio porque
# el mismo perfil no vale para los dos: medido, la misma frase daba
# "CORRECTO" por el micro del PC y 0,111 por el del móvil. La compresión
# Opus y el remuestreo mueven demasiado el x-vector.
#
# Se graba la primera vez que se conecta el móvil (ver
# command_router.start_mobile_enrollment). Mientras no exista, el móvil se
# autentica solo con la contraseña de la webapp.
SPEAKER_PROFILE_FILE_NETWORK = str(PROJECT_ROOT / "config" / "speaker_profile_network.json")

# Frases del enrolado por el móvil. Menos que las del PC (allí son 6)
# porque cada una cuesta un ciclo de grabación completo por red, con su
# subida: seis serían varios minutos de ida y vuelta.
MOBILE_ENROLL_PHRASES = [
    "Hola, soy yo, y esta es mi voz a través del móvil.",
    "Quiero manejar el ordenador desde el teléfono cuando no estoy delante.",
    "El tablero tiene cien casillas numeradas de izquierda a derecha.",
    "La lluvia en Sevilla es una maravilla, y esta es mi frase de siempre.",
]

# Milisegundos que permanece abierta la ventana de ayuda ("ayuda"/"help",
# ver command_router._show_help): se cierra sola pasado este tiempo, sin
# necesidad de decir nada más. Súbelo si la lista te da tiempo justo a
# leerla.
HELP_POPUP_MS = 9000

# ==============================================================================
# TABLERO DE 100 CASILLAS (Sección 1 del manual)
# ==============================================================================

# Píxeles (reales, los de tablero.png/casilla.png) que se mueve el
# marcador de ajuste fino con una palabra de dirección SIN número detrás
# (p.ej. "oeste" a secas). Con número ("oeste 3") se usa ese valor exacto.
BOARD_NUDGE_STEP_PX = 8

# ==============================================================================
# GUI (PySide6)
# ==============================================================================

# Tamaño de ventana inicial
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 300

# Fuente de la ventana
FONT_FAMILY = "Monospace"
FONT_SIZE = 11

# ==============================================================================
# DEBUG
# ==============================================================================

DEBUG = os.environ.get("VOICECONTROLLER_DEBUG", "0") == "1"
VERBOSE = os.environ.get("VOICECONTROLLER_VERBOSE", "0") == "1"

# ==============================================================================
# LOGGING
# ==============================================================================

LOG_FILE = PROJECT_ROOT / "voicecontroller.log"
ENABLE_LOG_FILE = True

# Tamano a partir del cual se tira el log viejo si no se pudo rotar.
# El log del arranque anterior se guarda siempre como voicecontroller.log.1:
# cuando algo se cuelga, el que interesa leer es el de la sesion que se
# murio, no el de la que acabas de arrancar para mirarlo.
LOG_MAX_MB = 5



# Cuanto se espera a que aparezca el dialogo de "guardar como" antes de
# escribir el nombre. Escribir antes de tiempo manda el texto a la ventana
# que estaba debajo -- justo el documento que se queria guardar.
#
# Un segundo va sobrado en un equipo normal. En uno lento, o con un dialogo
# que tarde (red, unidades montadas), subirlo en config_local.py.
GUARDAR_COMO_ESPERA_S = 1.0

# Cuantas lineas mueve cada "scroll arriba"/"scroll abajo".
#
# Una sola se queda muy corta: para bajar por un documento hay que repetir el
# comando media docena de veces, y dictando eso cansa. Tres es un termino
# medio razonable.
#
# Es un ajuste de GUSTO, como el tiempo de espera: quien lea rapido querra
# mas. Se cambia en config_local.py, que no se pisa al actualizar.
SCROLL_LINEAS = 3

# ==============================================================================
# LA DIANA SIGUIENDO AL RATON (solo en modo servicio)
# ==============================================================================
# Cada cuantos milisegundos se mira donde esta el raton para arrastrar la
# diana con el, mientras el cursor esta DENTRO de la region de trabajo.
#
# Mas suelto que los 33 ms del GUI (TOUCH_TRACK_POLL_MS) y por un motivo
# concreto: alli la comprobacion es interna y gratis. En Wayland,
# QCursor.pos() NO FUNCIONA -- el protocolo no deja que un cliente pregunte
# donde esta el cursor global -- asi que hay que preguntarselo al compositor
# con `kdotool getmouselocation`, y eso lanza un proceso cada vez.
#
# Medido: cada consulta tarda 4 ms de mediana. A 60 ms son ~16 por segundo,
# de sobra para colocar una marca con la mano y sin cargar la maquina.
#
# Y solo se consulta cuando YA hay region de trabajo (una casilla, un cuarto
# de escritorio o la ventana del foco). En el tablero o en reposo, ni una.
DIANA_SEGUIR_MS = 60


# ==============================================================================
# ZONAS CLICABLES: CUANTO SE AFINA AL BUSCARLAS
# ==============================================================================
# Al entrar en una casilla, zones.py mira el recorte y busca donde hay
# "energia de borde" -- iconos, botones, texto -- para numerarlo y poder
# decir "click 1". Estos cuatro numeros deciden CUANTAS cosas encuentra.
#
# Se sacaron aqui el 5-sep-2026, al ver que en una casilla con dos iconos
# solo detectaba dos zonas cuando en realidad hay cuatro cosas utiles: el
# dibujo del icono y su nombre son elementos DISTINTOS, y a veces lo que se
# quiere es el nombre (renombrar) y no el icono.
#
# Van aqui como valores por defecto; lo de cada uno, en config_local.py.

# Lado del bloque con que se analiza la imagen. ES EL QUE MAS MANDA: bloques
# grandes funden en una sola zona cosas que estan cerca -- el icono y su
# nombre acaban siendo una -- y bloques pequenos las separan. El suelo real
# es 4: por debajo, cualquier textura del fondo cuenta como elemento.
#
# None = AUTOMATICO, calculado como ancho_de_casilla / ZONAS_BLOQUE_DIVISOR.
#
# Va relativo y no en pixeles fijos porque el valor bueno depende de la
# RESOLUCION. Medido el 5-sep-2026 en 1920x1080: 6 px es el que separa el
# icono de su nombre y saca los iconos justos de la barra de tareas. Pero en
# esa pantalla una casilla mide 192 px, asi que ese 6 es "un treintaidosavo
# de la casilla". En un monitor 4K la casilla mide 384 px y 6 px analizaria
# un detalle el doble de fino: donde aqui se ve "icono y nombre", alli se
# verian trozos del icono.
#
# Poniendole un numero se fija en pixeles y se ignora el divisor -- que es lo
# que conviene si uno ya ha calibrado su maquina midiendo.
ZONAS_BLOQUE_PX = None

# El divisor del calculo automatico.
ZONAS_BLOQUE_DIVISOR = 24

# ------------------------------------------------------------------------------
# ALGO QUE NO ES EVIDENTE Y CUESTA DESCUBRIR DOS VECES
# ------------------------------------------------------------------------------
# El numero de zonas NO baja de forma ordenada al agrandar el bloque. Medido
# el 5-sep-2026 sobre UNA MISMA captura de la casilla 1 (192x108 px):
#
#     bloque    4   5   6   7   8   9  10  11  12
#     zonas     6   9   8   3   4   2   2   3   3
#
# Con 7 salen TRES y con 8 salen CUATRO. No es ruido de medida: se repite.
#
# Salta porque el umbral se recalcula con los PROPIOS DATOS -- es
# `media + sigma * desviacion` de las energias de los bloques (ver
# zones.detect_zones). Al agrandar el bloque, cada uno promedia mas area, las
# energias se uniforman, la desviacion baja, y el umbral se mueve. A eso se
# suma que cambian las divisiones: un elemento partido entre dos bloques
# puede pasar a caber en uno.
#
# Consecuencia practica: NO vale suponer que "mas bloque = menos zonas". Hay
# que probarlo y MIRARLO:
#
#     ./venv/bin/python tools/calibrar_zonas.py 1        la tabla
#     ./venv/bin/python tools/calibrar_zonas.py 1 8      dibujadas en pantalla
#
# En 1920x1080, el valor que dio el resultado bueno fue 8: cuatro zonas en la
# casilla 1, en dos columnas y dos alturas -- los dos iconos con su dibujo y
# su nombre, separados, que es lo que hacia falta para poder renombrar.
# De ahi el divisor de arriba: 192 / 8 = 24.

# Bloques minimos para que una region cuente como zona. Sirve para descartar
# ruido de un solo bloque. Si al bajar ZONAS_BLOQUE_PX empiezan a salir zonas
# de la nada, subir esto antes que volver a subir el bloque.
ZONAS_MIN_BLOQUES = 2

# Cuantas zonas como mucho. NUEVE, Y ES UNA DECISION, no un valor de
# partida: son los digitos que se dicen de un tiron ("click 1" ...
# "click 9").
#
# NO SUBIR SIN LEER ESTO. Mientras hay una casilla seleccionada, un numero
# se interpreta como ZONA si cae dentro de las detectadas, y como CASILLA si
# no (ver command_router._try_parse_board_zone_action). Con el tope en 9 eso
# es predecible: 1-9 siempre son zonas. Con el tope en 15, "click 12" actua
# en la zona 12 si se detectaron 12 zonas, y salta a la CASILLA 12 si solo
# se detectaron 4. La misma frase, dos cosas distintas, segun lo que el
# analisis de imagen haya encontrado ese dia.
#
# El objetivo NO es tener mas zonas: es que esas nueve sean nueve cosas
# DISTINTAS y utiles, y no nueve trozos del mismo nombre. Eso se consigue
# con ZONAS_BLOQUE_PX, y se juzga mirandolo -- ver tools/calibrar_zonas.py,
# que ademas las dibuja en pantalla para poder decidir con los ojos.
ZONAS_MAX = 9

# Cuanto hay que destacar sobre la media para contar como "hay algo aqui",
# medido en desviaciones tipicas. Subirlo deja solo lo mas marcado y tiende a
# SEPARAR elementos que se tocaban; bajarlo detecta cosas mas tenues y tiende
# a unirlos. Es el ajuste fino cuando ZONAS_BLOQUE_PX ya esta donde se quiere.
ZONAS_UMBRAL_SIGMA = 1.0


# ==============================================================================
# QUE APARATOS PUEDEN CONECTARSE A LA WEBAPP (FILTRO POR IP)
# ==============================================================================
# VACIO DE FABRICA A PROPOSITO: sin esto, cualquier aparato de la red puede
# al menos INTENTAR autenticarse. Con esto, los que no esten en la lista ni
# llegan a la pantalla de contrasena.
#
# Es una capa MAS, nunca un sustituto de la contrasena: una IP se puede
# falsificar dentro de una red local. Sirve para que un aparato que no es el
# tuyo no llegue ni a probar.
#
# ESTO VA EN config_local.py, no aqui. Es de cada maquina: la IP del movil
# de uno no significa nada en el ordenador de otro, y una instalacion en
# Windows no tiene por que heredar la red de la de Linux.
#
#   WEBAPP_ALLOWED_IPS = ["10.8.0.2"]              una sola, fija
#   WEBAPP_ALLOWED_IPS = ["10.8.0.2", "10.8.0.7"]  varias sueltas
#   WEBAPP_ALLOWED_IPS = ["10.8.0.10-10.8.0.50"]   un rango, con guion
#   WEBAPP_ALLOWED_IPS = ["10.8.0.10-50"]            lo mismo, abreviado
#   WEBAPP_ALLOWED_IPS = ["10.8.0.0/24"]             un rango, en CIDR
#
# CUIDADO, y es un cuidado con historia: si se pone una IP fija y el router
# le da otra al movil, la aplicacion deja de responder SIN EXPLICACION
# APARENTE. El movil se conecta, no pasa nada, y no hay ni un mensaje. Por
# eso conviene la IP fija solo cuando la asigna la VPN por certificado (que
# es el caso de esta maquina) y no cuando la reparte un router por DHCP.
#
# Si esta lista tiene algo, SOLO esas pueden entrar. Si esta vacia, no se
# filtra nada. La lista de prohibidas se mira primero: prohibir gana.
WEBAPP_ALLOWED_IPS = []
WEBAPP_BLOCKED_IPS = []


# ==============================================================================
# YDOTOOL: CUANTO ESPERAR ANTES DE DARLO POR PERDIDO
# ==============================================================================
# Cada tecla, cada clic y cada movimiento del puntero salen por ydotool, que
# habla con su demonio a traves de un socket. Si el demonio deja de contestar
# -- se ha muerto, se ha quedado atascado, o el socket es de otro usuario --
# la llamada se queda esperando PARA SIEMPRE en el hilo que la hizo, y desde
# fuera parece que el programa te oye pero no obedece.
#
# Con un limite, la llamada falla, se avisa por el log y el programa sigue
# vivo para poder contarlo. Es preferible una tecla perdida a un cuelgue.
YDOTOOL_TIMEOUT_S = 5.0

# Escribir un texto largo tarda mas que pulsar una tecla: ydotool va caracter
# a caracter. El limite de escritura se calcula sobre la marcha
# (YDOTOOL_TIMEOUT_S + un margen por caracter) para no cortar un dictado
# largo por la mitad.
YDOTOOL_SEGUNDOS_POR_CARACTER = 0.05

# Reproducir audio dura lo que dura el audio, asi que aqui el limite es solo
# una red de seguridad contra un reproductor colgado: generoso a proposito,
# nunca debe cortar una frase de ayuda larga.
AUDIO_TIMEOUT_S = 120.0


# ==============================================================================
# AJUSTES PERSONALES -- SIEMPRE LO ULTIMO, Y ESTO VA EN SERIO
# ==============================================================================
# Todo lo de arriba son valores POR DEFECTO y se pisa en cada actualizacion.
# Lo que cada usuario mide para su maquina (microfono, umbrales de voz,
# velocidad del habla, que aparatos pueden conectarse...) vive en
# config_local.py, que NO se toca nunca al actualizar.
#
# ESTAS LINEAS TIENEN QUE SER LAS ULTIMAS DEL FICHERO. No es una manera de
# hablar: cualquier opcion escrita DEBAJO de este import se ejecuta DESPUES
# y machaca en silencio lo que el usuario haya puesto en config_local.py.
#
# Ya paso, y con siete opciones a la vez. Se fueron anadiendo secciones al
# final del fichero -- que es lo natural -- sin caer en que este import
# estaba mas arriba. Entre ellas SCROLL_LINEAS y GUARDAR_COMO_ESPERA_S,
# cuyos propios comentarios decian "se cambia en config_local.py" mientras
# el codigo garantizaba que no. Y no da ningun error: el usuario edita su
# fichero, guarda, reinicia, y no pasa nada. A buscarlo donde no esta.
#
# Asi que: si anades una opcion nueva, va ARRIBA de esto. Siempre.
try:
    from config_local import *      # noqa: F401,F403
except ImportError:
    pass

# ------------------------------------------------------------------------------
# DIAGNOSTICO DEL PUNTERO
# ------------------------------------------------------------------------------
# Con esto en True, cada movimiento del raton apunta en el log donde se pidio
# (en pixeles de la captura), donde se tradujo (en logicos) y donde acabo de
# verdad, con el desvio. Cuesta un proceso por movimiento, asi que va apagado.
#
# Sirve para lo que no se puede arreglar mirando: "el clic cae un poco
# desplazado". Con dos numeros se ve si el desvio es fijo o si crece con la
# distancia -- que son dos fallos distintos.
DEPURAR_PUNTERO = False

# ------------------------------------------------------------------------------
# DESDE DONDE SE ABREN LOS PROGRAMAS
# ------------------------------------------------------------------------------
# Un programa lanzado por voz ("editor", "navegar", "dibujar"...) hereda el
# directorio de trabajo de quien lo lanza, y ese era el de VoiceController. Al
# abrir Kate y decir "guardar como", el dialogo proponia guardar DENTRO de la
# instalacion -- un sitio que no es de nadie y que ademas desaparece al
# desinstalar. Le paso a pipataki el 12-sep-2026.
#
# Vacio o sin poner = tu carpeta personal, que es donde uno guarda sus cosas.
# NO hace falta escribir tu nombre de usuario: se resuelve solo, y funciona
# igual en Linux y en Windows.
#
# Si quieres otra, valen las tres formas:
#
#   CARPETA_INICIAL = "~/Documentos"            <- la mas corta
#   CARPETA_INICIAL = "$HOME/Documentos"
#   CARPETA_INICIAL = "/home/$USER/Documentos"
#
# Si la ruta que pongas no existe, se usa la personal igualmente en vez de
# fallar: un ajuste mal escrito no puede dejar sin funcionar el abrir
# programas.
CARPETA_INICIAL = ""

# ------------------------------------------------------------------------------
# REFRESCO DE LAS CAPTURAS
# ------------------------------------------------------------------------------
# Segundos que se espera, con VC apartado, antes de volver a capturar tras una
# accion: lo que esa accion abre -- un menu, una pagina, el texto pegado --
# tarda en pintarse, y una foto demasiado pronta ensena el ANTES. El movil ya
# esperaba medio segundo tras cada clic.
#
# Se usa en "refrescar", al volver VC a primer plano ("trae control", tras una
# tecla o tras pegar el dictado) y tras cada clic del tablero. Mas alto = fotos
# mas fiables en un equipo lento, a cambio de que cada accion tarde mas.
REFRESCO_ESPERA_S = 0.4
