"""Habilidades: lo que VoiceController sabe hacer SEGUN el programa que
tengas delante.

QUE ES ESTO
-----------
El nucleo del programa es deliberadamente generico: mueve el puntero, pulsa,
dicta texto, maneja ventanas. Eso vale para todo y no sabe nada de nadie.

Pero trabajar de verdad en un programa concreto pide cosas que solo tienen
sentido ahi:

  - En un lector de PDF: "leeme esta pagina", "salta al capitulo tres",
    y algun dia describir los esquemas y las tablas, para que un libro se
    pueda escuchar como lo leeria una persona.
  - En un programa de dibujo: "coge el pincel", "grosor cinco", "capa nueva".
  - Escribiendo codigo: dictar con su puntuacion y su sangrado, sin tener
    que decir "abre parentesis" cada dos palabras.

Cada una de esas cosas es una HABILIDAD: un modulo aparte que se activa solo
cuando la ventana que tienes delante es la suya, y que no existe para el
resto del programa mientras tanto.

POR QUE ASI Y NO METIENDOLO EN command_router
---------------------------------------------
command_router ya tiene 3000 lineas. Meter ahi lo especifico de cada
programa lo convertiria en un cajon de sastre imposible de mantener, y
obligaria a tocar el nucleo -- lo que usa todo el mundo -- cada vez que
alguien quiera anadir soporte para su editor favorito.

Asi, una habilidad nueva es un fichero nuevo. Ni se toca el nucleo ni se
puede romper lo que ya funciona: si una habilidad falla, se desactiva sola y
el programa sigue como si no existiera.

COMO SE ESCRIBE UNA
-------------------
Un fichero en esta carpeta con una clase que herede de `Habilidad`. Ver
`ejemplo_lector.py`, que esta comentado y DESACTIVADO a proposito.

ESTADO
------
Esto es el esqueleto. No hay ninguna habilidad activa todavia: el enganche
esta puesto y probado, y con la lista vacia el programa se comporta
exactamente igual que antes.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import time
from typing import Optional

# Cada cuanto se vuelve a preguntar cual es la ventana de delante. Preguntarlo
# en cada frase seria lanzar un proceso externo (kdotool) por cada cosa que se
# diga; a este ritmo es imperceptible y sobra para lo que hace falta.
_CADA_S = 3.0

_registro: list["Habilidad"] = []
_ultimo_titulo = ""
_ultimo_momento = 0.0


class Habilidad:
    """Base de toda habilidad. Heredar y rellenar lo que haga falta."""

    # Nombre corto, para los mensajes del registro.
    nombre = "sin nombre"

    # Expresiones regulares contra el TITULO de la ventana. Basta con que
    # encaje una. Se comparan sin distinguir mayusculas.
    patrones: tuple[str, ...] = ()

    # A False, el modulo esta ahi pero no se carga. Sirve para dejar
    # habilidades a medio escribir sin que molesten.
    activa = True

    def aplica_a(self, titulo: str) -> bool:
        """¿Es esta la ventana de esta habilidad?"""
        if not titulo:
            return False
        return any(re.search(p, titulo, re.IGNORECASE) for p in self.patrones)

    def intenta(self, texto: str, normalizado: str, contexto: dict) -> bool:
        """Se le ofrece cada frase reconocida ANTES que al nucleo.

        Devuelve True si la ha atendido -- y entonces el nucleo ya no la
        mira -- o False para dejarla pasar, que es lo normal.

        `contexto` trae lo que hace falta para actuar sin importar nada:
        'gui', 'router', 'titulo'. Se pasa asi, y no importando modulos,
        para que una habilidad no pueda enredarse con el nucleo por su
        cuenta.
        """
        return False

    def al_activarse(self, contexto: dict) -> None:
        """Cuando el usuario cambia A la ventana de esta habilidad."""

    def al_desactivarse(self, contexto: dict) -> None:
        """Cuando el usuario se va a otra ventana."""


class HabilidadPorAtajos(Habilidad):
    """Habilidad que traduce frases a ATAJOS DE TECLADO.

    Es la forma mas comun, y sirve para casi cualquier programa de
    escritorio: los menus ya estan cableados a atajos, asi que dar ordenes
    por voz es rellenar una tabla de dos columnas -- lo que se dice y la
    tecla que le corresponde.

    Una habilidad nueva para otro programa es heredar de aqui, poner los
    `patrones` de su ventana y su tabla `atajos`. Nada mas.

    El teclado se inyecta a nivel de dispositivo virtual, asi que la tecla la
    recibe la ventana que tenga el foco -- que es justamente aquella para la
    que se activo esta habilidad.
    """

    # {frase ya normalizada: "ctrl+s"}. Sin acentos y en minusculas: es como
    # llegan las frases (ver command_router._normalize).
    atajos: dict = {}

    def intenta(self, texto: str, normalizado: str, contexto: dict) -> bool:
        atajo = self.atajos.get(normalizado)
        if not atajo:
            return False        # no es cosa nuestra: que siga su camino
        try:
            import backends
            backends.send_key(atajo)
        except Exception as exc:
            print(f"[habilidades] {self.nombre!r} no pudo mandar {atajo!r}: {exc!r}")
            return False
        print(f"[habilidades] {self.nombre}: {normalizado!r} -> {atajo}")
        gui = contexto.get("gui")
        if gui is not None:
            try:
                gui.update_suggestion(f"{normalizado} ({atajo})")
            except Exception:
                pass
        return True


def registrar(habilidad: Habilidad) -> None:
    _registro.append(habilidad)


def cargar() -> int:
    """Importa los modulos de esta carpeta. Cada uno se registra solo.

    Una habilidad que falle al importarse se salta con un aviso: no puede
    impedir que arranque el programa.
    """
    _registro.clear()
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{info.name}")
        except Exception as exc:
            print(f"[habilidades] no se pudo cargar {info.name!r}: {exc!r}")
    activas = [h for h in _registro if h.activa]
    if activas:
        print("[habilidades] cargadas: " + ", ".join(h.nombre for h in activas))
    return len(activas)


def titulo_ventana() -> str:
    """Titulo de la ventana de delante, preguntado como mucho cada _CADA_S."""
    global _ultimo_titulo, _ultimo_momento
    ahora = time.monotonic()
    if ahora - _ultimo_momento < _CADA_S:
        return _ultimo_titulo
    _ultimo_momento = ahora
    try:
        import backends
        geo = backends.focused_window_geometry()
        _ultimo_titulo = geo[4] if geo else ""
    except Exception:
        _ultimo_titulo = ""
    return _ultimo_titulo


def para(titulo: str) -> Optional[Habilidad]:
    """La habilidad que corresponde a esa ventana, o None."""
    for h in _registro:
        if not h.activa:
            continue
        try:
            if h.aplica_a(titulo):
                return h
        except Exception as exc:
            print(f"[habilidades] {h.nombre!r} fallo comprobando la ventana: {exc!r}")
    return None


def ofrecer(texto: str, normalizado: str, contexto: dict) -> bool:
    """Ofrece la frase a la habilidad de la ventana actual, si hay alguna.

    Devuelve True si la ha atendido. Con la lista vacia -- que es como esta
    hoy -- devuelve False sin hacer nada y sin preguntar por la ventana: el
    programa se comporta exactamente igual que si esto no existiera.
    """
    # Se mira si hay alguna ACTIVA antes de preguntar por la ventana:
    # preguntarlo lanza un proceso externo, y hacerlo para nada en cada frase
    # seria pagar un precio real por una lista vacia. Con el ejemplo
    # desactivado, esto sale por aqui sin tocar nada.
    if not any(h.activa for h in _registro):
        return False
    titulo = titulo_ventana()
    h = para(titulo)
    if h is None:
        return False
    contexto = dict(contexto, titulo=titulo)
    try:
        return bool(h.intenta(texto, normalizado, contexto))
    except Exception as exc:
        # Una habilidad rota no puede llevarse el programa por delante.
        print(f"[habilidades] {h.nombre!r} fallo atendiendo {texto!r}: {exc!r}")
        return False
