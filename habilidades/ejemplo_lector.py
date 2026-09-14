"""EJEMPLO de habilidad. Esta DESACTIVADA a proposito: no hace nada.

Esta aqui para que quien quiera escribir una tenga delante la forma exacta,
sin tener que deducirla del framework. Copiar este fichero, cambiarle el
nombre, poner `activa = True` y rellenar.

El ejemplo elegido -- narrar un PDF -- es el que se dio como caso de uso, y
se queda a medias a proposito: lo interesante de verdad seria que leyera
tambien los esquemas y las tablas, para que un libro se pudiera escuchar
como lo leeria una persona. Eso es trabajo de verdad, no un hueco que
rellenar, y por eso no se finge aqui que este resuelto.
"""
from . import Habilidad, registrar


class LectorDePdf(Habilidad):
    nombre = "lector de PDF (ejemplo, sin implementar)"

    # Contra el titulo de la ventana. Okular y Firefox con un PDF abierto
    # lo llevan en el titulo; otros lectores necesitarian sus patrones.
    patrones = (r"\.pdf\b", r"\bokular\b")

    # AQUI ESTA LA CLAVE: mientras esto sea False el modulo se importa pero
    # no se usa para nada.
    activa = False

    def al_activarse(self, contexto):
        print("[habilidad] hay un PDF delante")

    def intenta(self, texto, normalizado, contexto):
        """Se le ofrece cada frase ANTES que al nucleo.

        Devolver True significa "ya me encargo yo": el nucleo no la vera.
        Devolver False la deja pasar, que es lo que debe hacerse con todo lo
        que no sea claramente de esta habilidad -- si no, se estarian
        secuestrando comandos generales como "arriba" o "cerrar".
        """
        if normalizado in ("lee esta pagina", "leeme la pagina"):
            gui = contexto.get("gui")
            if gui is not None:
                gui.update_suggestion("(ejemplo) aqui se leeria la pagina")
            return True
        return False


registrar(LectorDePdf())
