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
speaker_id: filtra por VOZ lo que llega del reconocedor.

Idea
----
Vosk puede devolver, junto al texto de cada frase, un "x-vector" de 128
dimensiones: un resumen numérico de CÓMO suena la voz, independiente de
lo que se diga. Comparándolo con un PERFIL grabado antes (ver
tools/speaker_calibration.py) se obtiene una similitud de 0 a 1, y con
un umbral se decide si esa frase la ha dicho el dueño del perfil o
viene de la tele, la radio o de otra persona en la habitación.

DOS UMBRALES, no uno -- medido, no supuesto
-------------------------------------------
La calibración en la máquina del usuario (29-08-2026, 14 comandos + 17
frases de un telediario) dejó claro que la fiabilidad depende de la
DURACIÓN de la frase, porque los x-vectores necesitan varios segundos
de habla para estabilizarse:

  - Frases largas (dictado): su voz 0,684-0,811 contra 0,199-0,346 de
    las ajenas. Un hueco de +0,338, con toda la banda 0,45-0,60 dando
    cero errores en ambos sentidos. Por eso el umbral de dictado (0,50)
    va en el centro de esa banda: no es un equilibrio delicado.
  - Palabras sueltas (comandos): su voz 0,292-0,577, ajenas hasta
    0,346. Aquí SÍ se solapan. El umbral de comandos (0,25) se eligió a
    propósito por debajo de su peor comando observado (0,292) en vez de
    pegado a él: la prioridad es no rechazarle nunca un comando, aunque
    eso deje pasar alguna voz ajena. Aun así bloquea ~70% del ruido,
    porque las frases que NO dan x-vector también se descartan (8 de
    las 17 ajenas no daban ninguno: la tele lejana muchas veces ni se
    puede caracterizar).

MODO AVISO
----------
Por defecto (config.SPEAKER_ID_MODE = "warn") NO se descarta nada: solo
se anota por consola lo que se HABRÍA descartado. Los umbrales salen de
una muestra pequeña, y en una aplicación de accesibilidad un rechazo
equivocado significa tener que repetirlo todo. Primero se mira qué
haría durante unos días de uso real, y con esos datos se afinan los
umbrales antes de pasar a "block".

LO QUE ESTO NO ES
-----------------
No es autenticación. Una grabación de su voz pasaría el filtro igual.
Sirve para que la tele no escriba sola, no para impedir que otra
persona use el ordenador.
"""

import json
import math

import config


class SpeakerVerifier:
    """Compara el x-vector de cada frase con el perfil del usuario.

    Se construye siempre (aunque falte el perfil o esté desactivado);
    en ese caso `enabled` es False y check() acepta todo, para que el
    reconocedor no tenga que preguntar por nada antes de llamar."""

    def __init__(self, source="device"):
        """`source`: "device" (micrófono del PC) o "network" (el del
        móvil). Cada uno tiene su PROPIO perfil, y no son
        intercambiables: medido, el perfil del PC puntúa 0,111 sobre la
        misma frase dicha por el móvil. Sin un perfil propio para ese
        canal, la verificación por voz allí es imposible."""
        self.source = source
        self.profile = None
        self.reason = ""
        self._warned_missing_vector = False
        # contadores para el modo aviso, consultables desde fuera
        self.n_checked = 0
        self.n_would_reject = 0
        self.n_no_vector = 0

        if not getattr(config, "SPEAKER_ID_ENABLED", False):
            self.reason = "desactivado en config.SPEAKER_ID_ENABLED"
            return
        path = self.profile_path()
        if not path:
            self.reason = f"no hay ruta de perfil para {self.source!r}"
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            vector = data.get("profile")
            if not vector:
                raise ValueError('el fichero no tiene campo "profile"')
            self.profile = _normalize(vector)
            if self.profile is None:
                raise ValueError("el perfil tiene norma cero")
            self.meta = data.get("meta", {})
            self.reason = f"perfil cargado de {path}"
        except FileNotFoundError:
            self.reason = (f"no hay perfil todavía en {path}"
                           + (" -- se grabará al conectar el móvil"
                              if self.source == "network" else
                              " -- créalo con `python tools/speaker_calibration.py enroll`"
                              " y luego `export`"))
        except Exception as exc:
            self.reason = f"no se pudo leer el perfil ({exc!r})"

    def profile_path(self):
        """Fichero de perfil de este micrófono."""
        if self.source == "network":
            return getattr(config, "SPEAKER_PROFILE_FILE_NETWORK", None)
        return getattr(config, "SPEAKER_PROFILE_FILE", None)

    @property
    def enabled(self) -> bool:
        return self.profile is not None

    @property
    def blocking(self) -> bool:
        """True si además de avisar se descarta de verdad."""
        return (self.enabled
                and getattr(config, "SPEAKER_ID_MODE", "warn") == "block")

    # Modos de verificación. Cada uno tiene su umbral porque cada uno
    # trabaja con frases de duración muy distinta, y la puntuación baja
    # con la duración: no se puede usar el mismo número para una palabra
    # suelta que para una frase entera.
    DICTATION = "dictation"
    COMMAND = "command"
    LOGIN = "login"

    def threshold(self, mode) -> float:
        # `mode` admite el bool de antes (True = dictado) por compatibilidad
        if mode is True:
            mode = self.DICTATION
        elif mode is False:
            mode = self.COMMAND
        if mode == self.LOGIN:
            # El movil tiene su PROPIO minimo (14-sep-2026). Su micro puntua
            # bastante mas bajo que el del PC, y con uno solo para los dos, la
            # calibracion del PC (0,60 en la VM de pruebas) dejaba al movil sin
            # poder identificarse ni despertar de la espera: medido, su santo y
            # sena daba 0,566.
            if self.source == "network":
                propio = getattr(config, "VOICE_LOGIN_THRESHOLD_NETWORK", None)
                if propio is not None:
                    return propio
            return getattr(config, "VOICE_LOGIN_THRESHOLD",
                           config.SPEAKER_ID_THRESHOLD_DICTATION)
        if mode == self.DICTATION:
            return config.SPEAKER_ID_THRESHOLD_DICTATION
        return config.SPEAKER_ID_THRESHOLD_COMMAND

    # Veredictos posibles. La diferencia entre OTHER y UNKNOWN es la que
    # más importa y la que faltaba: "no se ha podido verificar" NO es
    # "es otra persona". Confundirlas hacía que un comando corto suyo
    # ('cerrar', confianza 1.00) contara como intento de intrusión.
    HIM = "him"          # hay vector y se parece al perfil
    OTHER = "other"      # hay vector y NO se parece: es otra voz
    UNKNOWN = "unknown"  # no hay vector: no se sabe, y no se puede saber

    def verdict(self, spk_vector, mode):
        """Devuelve (veredicto, similitud, umbral).

        Frases muy cortas a menudo no producen x-vector: medido, 8 de 17
        frases de tele no daban ninguno, pero también le pasa a sus
        propios comandos de una palabra. Por eso la ausencia de vector es
        su propio veredicto (UNKNOWN) y no se disfraza de OTHER: quien
        llame decide qué hacer con cada caso, que no es lo mismo para
        filtrar texto que para acusar a alguien de intrusión."""
        if not self.enabled:
            return self.HIM, None, None
        threshold = self.threshold(mode)
        vector = _normalize(spk_vector) if spk_vector else None
        if vector is None:
            return self.UNKNOWN, None, threshold
        score = sum(a * b for a, b in zip(self.profile, vector))
        return (self.HIM if score >= threshold else self.OTHER), score, threshold

    def check(self, spk_vector, is_dictating):
        """Devuelve (aceptar, similitud, umbral).

        `aceptar` es lo que debe hacer quien llama: en modo aviso
        SIEMPRE es True (solo se cuenta lo que se habría descartado).

        Una frase SIN x-vector se trata como no verificada -> se
        rechazaría en modo bloqueo. Es lo correcto y además sale gratis:
        en la calibración ninguna frase propia se quedó sin vector,
        mientras que 8 de 17 frases de la tele sí.
        """
        if not self.enabled:
            return True, None, None

        threshold = self.threshold(is_dictating)
        self.n_checked += 1

        vector = _normalize(spk_vector) if spk_vector else None
        if vector is None:
            self.n_no_vector += 1
            self.n_would_reject += 1
            return (not self.blocking), None, threshold

        score = sum(a * b for a, b in zip(self.profile, vector))
        if score >= threshold:
            return True, score, threshold

        self.n_would_reject += 1
        return (not self.blocking), score, threshold

    def stats(self) -> str:
        if not self.n_checked:
            return "sin frases comprobadas todavía"
        pct = 100.0 * self.n_would_reject / self.n_checked
        return (f"{self.n_would_reject}/{self.n_checked} frases "
                f"{'descartadas' if self.blocking else 'se habrían descartado'} "
                f"({pct:.0f}%), de ellas {self.n_no_vector} sin x-vector")


def is_blocking() -> bool:
    """True si el filtro por voz está en modo "block" (descarta de
    verdad) y no solo en "warn". Lo consulta command_router, que es quien
    aplica el descarte -- ver el porqué en su on_final()."""
    return (getattr(config, "SPEAKER_ID_ENABLED", False)
            and getattr(config, "SPEAKER_ID_MODE", "warn") == "block")


def _normalize(vector):
    """Normaliza a longitud 1 para que el producto escalar sea
    directamente el coseno. Sin esto las similitudes no serían
    comparables con los umbrales medidos en la calibración, que se
    calcularon sobre vectores normalizados."""
    try:
        values = [float(x) for x in vector]
    except (TypeError, ValueError):
        return None
    norm = math.sqrt(sum(v * v for v in values))
    if not norm:
        return None
    return [v / norm for v in values]
