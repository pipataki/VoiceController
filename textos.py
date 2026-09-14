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
textos: lo que el programa DICE y MUESTRA, en cada idioma.

POR QUE EXISTE
--------------
El 5-sep-2026 se replanteó el bilingüismo: hay una LENGUA MATERNA que
domina y otra que se maneja (ver config.LENGUA_MATERNA). Con eso, poner
`LENGUA_MATERNA = "en"` hace que el programa FUNCIONE en inglés -- dictado,
comandos, casillas -- pero seguía HABLÁNDOTE en español, porque no existía
ninguna capa de traducción: `gui.set_ui_language()` estaba ahí desde
siempre sin ninguna tabla detrás.

Esto es esa tabla. Hace falta para que lo usen en Estados Unidos, Reino
Unido y la Commonwealth, que es hacia donde va el proyecto.

DOS REGLAS QUE NO SE SALTAN
---------------------------
1. **Con la materna en español, nada cambia.** Los textos españoles son
   los que ya había, palabra por palabra. Lo inglés es estrictamente
   añadido. Si algún día alguien duda, que compare: el español de aquí
   tiene que ser idéntico al que estaba escrito en command_router.

2. **Nunca reventar por un texto que falte.** Si una clave no está
   traducida, sale la española. Un programa a medio traducir es incómodo;
   uno que se cae por una cadena que falta es inservible. Y en un programa
   de accesibilidad, quedarse mudo es lo peor que puede pasar.

COMO SE TRADUJO LA AYUDA HABLADA
--------------------------------
No es traducción literal. Se dice en alto, así que lo que importa es que
suene natural dicho, no que calque la sintaxis. Se mantuvo lo que la hace
útil: qué puedes hacer aquí y, sobre todo, CÓMO SALIR.
"""

import config


def idioma() -> str:
    """La lengua materna vigente. Se lee cada vez a propósito.

    config.LENGUA_MATERNA puede cambiar en caliente (el menú de la
    bandeja), y una constante calculada al importar se quedaría con el
    valor del arranque -- el mismo fallo que ya costó una tarde con los
    umbrales de config_local.
    """
    return getattr(config, "LENGUA_MATERNA", "es")


def t(clave: str, **formato) -> str:
    """El texto de `clave` en la lengua materna.

    Si no está traducido, devuelve el español. Si la clave no existe
    devuelve la propia clave -- feo pero visible, que es justo lo que se
    quiere de un fallo así: que se note al probarlo y no en silencio.
    """
    entrada = TEXTOS.get(clave)
    if entrada is None:
        return clave
    texto = entrada.get(idioma()) or entrada.get("es") or clave
    if formato:
        try:
            return texto.format(**formato)
        except (KeyError, IndexError):
            return texto          # antes texto sin rellenar que una excepción
    return texto


# ---------------------------------------------------------------------------
# LA AYUDA HABLADA: breve, amable, y sobre DONDE ESTAS
# ---------------------------------------------------------------------------
# Antes se leía la lista pelada de comandos: en escucha son unos cuarenta
# nombres seguidos. Eso no es ayuda, es un inventario. Aquí se cuenta qué se
# puede hacer y cómo seguir o cómo salir.

AYUDA_HABLADA = {
    "dormido": {
        "es": "Estoy en espera. Di tu santo y seña cuando quieras seguir.",
        "en": "I'm on standby. Say your passphrase whenever you want to "
              "carry on.",
    },
    "login": {
        "es": "Estoy esperando que te identifiques. Di tu santo y seña. "
              "Si no te reconozco, di: soy yo, y te lo vuelvo a pedir.",
        "en": "I'm waiting for you to identify yourself. Say your "
              "passphrase. If I don't recognise you, say: it's me, and "
              "I'll ask again.",
    },
    "bloqueado": {
        "es": "He dejado de obedecer porque no reconocí una voz. "
              "Di: soy yo, para continuar.",
        "en": "I've stopped obeying because I didn't recognise a voice. "
              "Say: it's me, to carry on.",
    },
    "escucha": {
        "es": "Te escucho. Di un número del uno al cien para ir a esa casilla "
              "del tablero, o di tablero si quieres verlo. "
              "Di dictar para empezar a escribir, y foco para trabajar sobre "
              "la ventana que tienes delante.",
        "en": "I'm listening. Say a number from one to a hundred to go to "
              "that square on the board, or say board if you want to see it. "
              "Say type to start writing, and focus to work on the window "
              "in front of you.",
    },
    "casilla": {
        "es": "Estás dentro de una casilla. Muévete diciendo una dirección: "
              "arriba, abajo, izquierda o derecha. "
              "Cuando el punto verde esté donde quieres, di click, o doble "
              "click. Di tablero para volver a la vista general.",
        "en": "You're inside a square. Move by saying a direction: up, "
              "down, left or right. When the green dot is where you want "
              "it, say click, or double click. Say board to go back to the "
              "whole screen.",
    },
    "casilla_con_zonas": {
        "es": "Estás dentro de una casilla y he encontrado varios sitios donde "
              "pulsar, numerados. Di click y su número, por ejemplo: click uno. "
              "También puedes moverte con las direcciones. "
              "Di tablero para volver.",
        "en": "You're inside a square and I've found several places to "
              "click, numbered. Say click and its number, for example: "
              "click one. You can also move with the directions. Say board "
              "to go back.",
    },
    "zoom_out": {
        "es": "Estás viendo un cuarto de la pantalla. Mueve el punto verde con "
              "las direcciones y di click cuando esté en su sitio. "
              "Di tablero para volver a la vista general.",
        "en": "You're looking at a quarter of the screen. Move the green "
              "dot with the directions and say click when it's in place. "
              "Say board to go back to the whole screen.",
    },
    "foco": {
        "es": "Estás trabajando sobre una ventana. Mueve el punto verde con las "
              "direcciones, o dime qué tecla quieres: guardar, cerrar ventana, "
              "deshacer. Di tablero para volver al escritorio entero.",
        "en": "You're working on a window. Move the green dot with the "
              "directions, or tell me which key you want: save, close "
              "window, undo. Say board to go back to the whole desktop.",
    },
    "dictando": {
        "es": "Estoy escribiendo lo que digas. Habla con normalidad; los "
              "signos de interrogación y de exclamación los pongo yo. "
              "Cuando termines, di entra para enviarlo. "
              "Di escucha si quieres dejar de dictar.",
        "en": "I'm writing down whatever you say. Speak normally; I'll add "
              "the question marks and exclamation marks myself. When you're "
              "done, say enter to send it. Say listen if you want to stop "
              "typing.",
    },
    "formulas": {
        "es": "Estoy escribiendo letra a letra, para fórmulas. "
              "Di entra cuando termines, o escucha para salir de aquí.",
        "en": "I'm writing letter by letter, for formulas. Say enter when "
              "you're done, or listen to get out of here.",
    },
}


# Los títulos de la ventana de ayuda. Los emojis se quedan igual: dicen
# dónde estás de un vistazo y no son de ningún idioma.
TITULOS_AYUDA = {
    "dormido": {"es": "😴 En espera — puedes decir:",
                "en": "😴 On standby — you can say:"},
    "login": {"es": "🔐 Esperando tu santo y seña — puedes decir:",
              "en": "🔐 Waiting for your passphrase — you can say:"},
    "bloqueado": {"es": "🔒 Bloqueado — puedes decir:",
                  "en": "🔒 Locked — you can say:"},
    "escucha": {"es": "🎧 Escucha — puedes decir:",
                "en": "🎧 Listening — you can say:"},
    "casilla": {"es": "▣ Dentro de una casilla — puedes decir:",
                "en": "▣ Inside a square — you can say:"},
    "casilla_con_zonas": {
        "es": "▣ Dentro de una casilla, con zonas — puedes decir:",
        "en": "▣ Inside a square, with zones — you can say:"},
    "zoom_out": {"es": "🔍 Un cuarto de pantalla — puedes decir:",
                 "en": "🔍 A quarter of the screen — you can say:"},
    "foco": {"es": "🪟 Sobre una ventana — puedes decir:",
             "en": "🪟 On a window — you can say:"},
    "dictando": {"es": "✍ Dictando — puedes decir:",
                 "en": "✍ Typing — you can say:"},
    "formulas": {"es": "🔢 Fórmulas, letra a letra — puedes decir:",
                 "en": "🔢 Formulas, letter by letter — you can say:"},
}


def ayuda_hablada(situacion: str, por_defecto: str = None) -> str:
    """Lo que se dice en alto para esa situación, en la lengua materna."""
    entrada = AYUDA_HABLADA.get(situacion)
    if entrada is None:
        return por_defecto if por_defecto is not None else ""
    return entrada.get(idioma()) or entrada["es"]


def titulo_ayuda(situacion: str, por_defecto: str = None) -> str:
    """El título de la ventana de ayuda, en la lengua materna."""
    entrada = TITULOS_AYUDA.get(situacion)
    if entrada is None:
        return por_defecto if por_defecto is not None else ""
    return entrada.get(idioma()) or entrada["es"]


# ---------------------------------------------------------------------------
# MENSAJES SUELTOS: lo que se dice y lo que sale en la línea de sugerencias
# ---------------------------------------------------------------------------
# Las claves describen QUE pasa, no el texto, para que traducir no obligue a
# tocar el código. Los huecos {asi} se rellenan con t("clave", asi=valor).

TEXTOS = {
    # --- cambio de idioma -------------------------------------------------
    "cambiando_idioma": {
        "es": "Cambiando a {idioma}. Un momento, no te oigo mientras tanto.",
        "en": "Switching to {idioma}. One moment, I can't hear you "
              "meanwhile.",
    },
    "idioma_es": {"es": "español", "en": "Spanish"},
    "idioma_en": {"es": "inglés", "en": "English"},

    # --- identidad y seguridad -------------------------------------------
    "pide_santo_y_sena": {
        "es": "🔐 Di tu santo y seña ahora",
        "en": "🔐 Say your passphrase now",
    },
    "santo_y_sena_incorrecto": {
        "es": "Santo y seña incorrecto ({intentos} de {total}).",
        "en": "Wrong passphrase ({intentos} of {total}).",
    },
    "no_te_reconozco": {
        "es": "¿Eres tú realmente? No te reconozco.",
        "en": "Is that really you? I don't recognise you.",
    },
    "di_soy_yo": {
        "es": "Di: soy yo, si eres tú.",
        "en": "Say: it's me, if it's you.",
    },

    # --- dictado ----------------------------------------------------------
    "no_te_entiendo": {
        "es": "No te entiendo. ¿Puedes repetirlo?",
        "en": "I don't understand. Can you say that again?",
    },
    "no_hay_ventana_destino": {
        "es": "No hay ventana donde escribir: pon el cursor donde quieras "
              "el texto.",
        "en": "There's no window to write in: put the cursor where you "
              "want the text.",
    },

    # --- la ventana de ayuda ---------------------------------------------
    "grupo_portapapeles": {"es": "portapapeles y archivo",
                           "en": "clipboard and files"},
    "grupo_teclas": {"es": "teclas", "en": "keys"},
    "grupo_desplazar": {"es": "desplazar la vista", "en": "scrolling"},
    "grupo_ventanas": {"es": "ventanas y pestañas", "en": "windows and tabs"},
    "grupo_y_mas": {"es": "{muestra}… y {resto} más",
                    "en": "{muestra}… and {resto} more"},
    "direcciones_cardinales": {
        "es": "mueven el punto verde",
        "en": "move the green dot",
    },
    "direcciones_diagonales": {"es": "en diagonal", "en": "diagonally"},

    # --- tablero ----------------------------------------------------------
    "sin_zonas": {
        "es": "No he encontrado nada donde pulsar en esta casilla.",
        "en": "I haven't found anything to click on in this square.",
    },
    # --- mensajes de trabajo ---------------------------------------------
    "corregir_como": {
        "es": '❓ "{palabra}" ¿como {opciones}? Dilo para aplicarlo.',
        "en": '❓ "{palabra}" as {opciones}? Say it to apply.',
    },
    "parece_expresion": {
        "es": '💡 Parece una expresión numérica. Di "aplica sugerencia" '
              'para pasarla a dígitos: {simbolico}',
        "en": '💡 This looks like a numeric expression. Say "apply '
              'suggestion" to turn it into digits: {simbolico}',
    },
    "enrolando_movil": {
        "es": '🎙 Enrolando el móvil ({n}/{total}): "{frase}"',
        "en": '🎙 Enrolling the phone ({n}/{total}): "{frase}"',
    },
    "esa_no_es_tu_voz": {
        "es": "🔐 Esa no es tu voz ({fallos}/{maximo}). Repite el santo y seña.",
        "en": "🔐 That's not your voice ({fallos}/{maximo}). Say the "
              "passphrase again.",
    },
    "voz_no_reconocida_nada": {
        "es": "👤 Voz no reconocida: no se ha hecho nada. "
              'Di "soy yo" para identificarte.',
        "en": "👤 Voice not recognised: nothing was done. "
              'Say "it\'s me" to identify yourself.',
    },
    "o_enumeracion": {"es": "o", "en": "or"},
    # --- seleccionar -------------------------------------------------------
    "seleccion_origen": {
        "es": "🟡 Origen fijado. Mueve el punto y di \"fin de la selección\".",
        "en": "🟡 Start point set. Move the dot and say \"end of selection\".",
    },
    "seleccion_sin_mover": {
        "es": "El punto no se ha movido. Muévelo y repite \"fin de la selección\".",
        "en": "The dot hasn't moved. Move it and say \"end of selection\" again.",
    },
    "seleccion_hecha": {
        "es": "✅ Seleccionado.",
        "en": "✅ Selected.",
    },
    "seleccion_cancelada": {
        "es": "Selección cancelada.",
        "en": "Selection cancelled.",
    },
    "seleccion_sin_origen": {
        "es": "No hay origen fijado: di \"seleccionar\" donde quieras empezar.",
        "en": "No start point set: say \"select\" where you want to begin.",
    },
    "seleccion_sin_punto": {
        "es": "No hay punto que usar: entra en una casilla o pide foco.",
        "en": "There's no dot to use: go into a square or ask for focus.",
    },
    # --- carpetas del perfil ----------------------------------------------
    "carpeta_abierta": {
        "es": "📁 {nombre}: {motivo}.",
        "en": "📁 {nombre}: {motivo}.",
    },
    "carpeta_no_existe": {
        "es": "No tienes ninguna carpeta \"{nombre}\" en tu perfil. No la creo.",
        "en": "You have no folder called \"{nombre}\" in your profile. "
              "I won't create it.",
    },
    "carpeta_no_abre": {
        "es": "No se pudo abrir {nombre}: {motivo}",
        "en": "Couldn't open {nombre}: {motivo}",
    },
    "terminal_en": {
        "es": "🖥 Terminal en {nombre}.",
        "en": "🖥 Terminal in {nombre}.",
    },
    "carpeta_sin_nombre": {
        "es": "Dime también el nombre: \"crear carpeta borradores\".",
        "en": "Tell me the name too: \"create folder drafts\".",
    },
    # Dos textos y no uno con {que}: en español "archivo creada" chirría.
    # El inglés no distingue género, pero se mantienen separados para que
    # las dos tablas tengan las mismas claves.
    "carpeta_sin_saber_donde": {
        "es": "⚠️ No sé en qué carpeta estás. Abre el explorador donde lo "
              "quieras, o di \"carpeta <nombre>\" primero.",
        "en": "⚠️ I don't know which folder you're in. Open the file manager "
              "where you want it, or say \"folder <name>\" first.",
    },
    "extension_rara": {
        "es": "⚠️ No entiendo la extensión \"{trozo}\". Dila por su nombre "
              "(\"punto texto\") o deletréala (\"punto te equis te\").",
        "en": "⚠️ I don't understand the extension \"{trozo}\". Say its name "
              "(\"dot text\") or spell it (\"dot tee ex tee\").",
    },
    "carpeta_creada": {
        "es": "✅ Carpeta \"{nombre}\" creada donde tienes abierto Dolphin.",
        "en": "✅ Folder \"{nombre}\" created where Dolphin is showing.",
    },
    "archivo_creado": {
        "es": "✅ Archivo \"{nombre}\" creado donde tienes abierto Dolphin.",
        "en": "✅ File \"{nombre}\" created where Dolphin is showing.",
    },
    "carpeta_no_creada": {
        "es": "No se pudo crear: {motivo}",
        "en": "Couldn't create it: {motivo}",
    },
    "capturas_actualizadas": {
        "es": "Capturas actualizadas.",
        "en": "Captures updated.",
    },
    "nada_que_repetir": {
        # "otra" sin ningun desplazamiento antes: se dice por que no pasa
        # nada y que es lo que si se puede repetir.
        "es": "No hay ningún desplazamiento que repetir.",
        "en": "There's no scroll to repeat.",
    },
    "no_puedo_enfocarme": {
        # Negarse sin decir que hacer deja al usuario donde estaba. pipataki lo
        # dijo intentando traer el GUI con "foco control de voz": la orden
        # buena existe, y es lo que hay que contestarle.
        "es": "A mi misma no puedo enfocarme. Para verme delante, di trae control.",
        "en": "I can't focus on myself. To bring me to the front, say trae control.",
    },
    "sin_puntero_movil": {
        "es": "No se donde tienes el puntero del movil.",
        "en": "I don't know where your phone pointer is.",
    },
    "no_te_he_oido": {
        "es": "No te he oído bien. Repítelo, por favor.",
        "en": "I didn't hear you properly. Say it again, please.",
    },
    "voz_movil_aprendida_voz": {
        "es": "Ya reconozco tu voz por el móvil. "
              "Voy a reiniciar la sesión del teléfono.",
        "en": "I can recognise your voice on the phone now. "
              "I'm going to restart the phone session.",
    },
    "voz_movil_aprendida": {
        "es": "✅ Voz del móvil aprendida.",
        "en": "✅ Phone voice learned.",
    },
    "me_pongo_en_espera": {
        "es": "Me pongo en espera.",
        "en": "Going on standby.",
    },
    "en_espera_sugerencia": {
        "es": "😴 En espera. Di tu santo y seña.",
        "en": "😴 On standby. Say your passphrase.",
    },
    "no_reconozco_tu_voz": {
        "es": "No reconozco tu voz.",
        "en": "I don't recognise your voice.",
    },
    "te_escucho_voz": {"es": "Te escucho.", "en": "I'm listening."},
    "te_escucho": {"es": "✅ Te escucho.", "en": "✅ I'm listening."},
    "te_escucho_ordenes": {
        "es": "✅ Te escucho: ya puedes dar órdenes.",
        "en": "✅ I'm listening: you can give orders now.",
    },
    "bloqueado_sugerencia": {
        "es": "🔒 Bloqueado: voz no reconocida. "
              'Di "soy yo" o usa la bandeja del sistema.',
        "en": "🔒 Locked: voice not recognised. "
              'Say "it\'s me" or use the system tray.',
    },
    "codigo": {"es": "Código: ", "en": "Code: "},
    "guardar_como": {
        "es": 'Guardar como "{nombre}" — di "intro"',
        "en": 'Save as "{nombre}" — say "enter"',
    },
    "prueba_pulsa_verde": {
        "es": 'Prueba a decir "pulsa verde"',
        "en": 'Try saying "click green"',
    },
}


# ---------------------------------------------------------------------------
# TEXTOS QUE VIVEN EN config.py
# ---------------------------------------------------------------------------
# Tres avisos son configurables desde siempre (el santo y seña, el "no te
# entiendo" y el aviso de intruso), y alguien puede tenerlos personalizados
# en config_local.py.
#
# Por eso el español SIGUE SALIENDO DE config: si se lo hubiera llevado esta
# tabla, una personalización dejaría de aplicarse sin decir nada -- que es
# exactamente el fallo que ya nos costó una tarde con los umbrales. Los
# demás idiomas salen de aquí.

TEXTOS_DE_CONFIG = {
    "TTS_NOT_UNDERSTOOD_TEXT": {
        "en": "I don't understand. Could you say that again?",
    },
    "VOICE_LOGIN_PROMPT": {
        "en": "Passphrase.",
    },
    "VOICE_LOGIN_OK_TEXT": {
        "en": "I'm listening.",
    },
    "VOZ_AJENA_PREGUNTA": {
        "en": "Is that really you? I don't recognise you.",
    },
    # OJO: VOICE_LOGIN_HINT **NO SE TRADUCE**, y no es un olvido. No es un
    # texto de interfaz: es EL SANTO Y SEÑA, la frase que hay que decir.
    # Traducirla sería cambiarle la contraseña al usuario sin avisar.
    #
    # Y no hace falta traducirla: el santo y seña no se compara nunca como
    # texto -- solo se mira la voz (ver command_router._handle_voice_login).
    # La frase está para dar audio suficiente al x-vector, así que vale
    # dicha en cualquier idioma.
    "INTRUDER_ABORT_TEXT": {
        "en": "I've heard orders from a voice I don't recognise. "
              "I'm going to stop obeying, to be safe. "
              "Say: it's me, to carry on.",
    },
}


def de_config(nombre: str) -> str:
    """El aviso `nombre` de config.py, en la lengua materna.

    En español devuelve el de config TAL CUAL, para respetar cualquier
    personalización de config_local.py. En los demás idiomas, el de la
    tabla; y si ese idioma no está traducido, otra vez el de config --
    antes con acento que mudo.
    """
    valor = getattr(config, nombre, "")
    if idioma() == "es":
        return valor
    return (TEXTOS_DE_CONFIG.get(nombre, {}) or {}).get(idioma()) or valor
