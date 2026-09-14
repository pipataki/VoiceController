"""Habilidad para Kate: lo que el nucleo NO sabe hacer, o hace distinto.

Es la primera habilidad de verdad, y sirve tambien de plantilla: casi
cualquier programa de escritorio se maneja igual, porque sus menus ya estan
cableados a atajos de teclado. Dar ordenes por voz se reduce a una tabla de
dos columnas -- lo que se dice, y la tecla que le toca.

Para otro editor (gedit, VS Code) basta con copiar este fichero, cambiar
`patrones` y corregir los atajos. Para un programa de dibujo, lo mismo con
sus herramientas.

QUE ENTRA EN LA TABLA, Y QUE NO
-------------------------------
Al escribirla salieron 31 ordenes, y 15 ya existian en el nucleo haciendo
EXACTAMENTE lo mismo ("guardar" ya manda ctrl+s). Duplicarlas no aporta
nada y si añade riesgo: dos sitios que mantener y uno que puede quedarse
atras.

Asi que aqui solo esta lo que aporta algo:

  1. Lo que el nucleo no tiene, porque es propio de un editor: comentar,
     sangrar, ir a una linea, numeros de linea.
  2. Lo que el nucleo hace MAL en este programa. Y salio uno de verdad:
     "reemplazar" manda ctrl+h, que es lo habitual, pero **Kate usa
     ctrl+r**. Ese comando llevaba haciendo otra cosa en Kate. Corregirlo
     desde aqui es justamente para lo que sirven las habilidades.

Y se quedo FUERA "terminal": en el nucleo abre una terminal de verdad, y
aqui abriria el panel de Kate. Eso seria secuestrar un comando que el
usuario espera que haga otra cosa. Se dice "panel de terminal".

AVISO SOBRE LOS ATAJOS
----------------------
Son los de Kate de fabrica. Kate deja cambiarlos y algunos han variado entre
versiones: si alguno no hace lo que debe, se corrige EN ESTA TABLA y nada
mas. Esa es la ventaja de tenerlo junto y no repartido por el codigo.
"""
from . import HabilidadPorAtajos, registrar


class Kate(HabilidadPorAtajos):
    nombre = "editor Kate"
    patrones = (r"\bkate\b",)
    activa = True

    atajos = {
        # --- Lo que el nucleo hace MAL en Kate ---
        # ctrl+h es lo normal en otros programas, pero Kate usa ctrl+r.
        "reemplazar":           "ctrl+r",
        "reemplaza":            "ctrl+r",

        # --- Propio de un editor: no esta en el nucleo ---
        "ir a linea":           "ctrl+g",
        "ir a la linea":        "ctrl+g",
        "buscar siguiente":     "F3",
        "buscar anterior":      "shift+F3",

        "comentar":             "ctrl+d",
        "descomentar":          "ctrl+shift+d",
        "sangrar":              "ctrl+i",
        "quitar sangria":       "ctrl+shift+i",

        "guardar todo":         "ctrl+l",
        "documento nuevo":      "ctrl+n",
        "nuevo documento":      "ctrl+n",
        "cerrar documento":     "ctrl+w",

        "numeros de linea":     "F11",
        "ajuste de linea":      "F10",
        # "terminal" a secas NO: en el nucleo abre una terminal de verdad.
        "panel de terminal":    "F4",

        # Fuera por no darlos por seguros -- varian entre versiones. Mejor
        # que falten a que hagan otra cosa: plegar bloques, marcadores,
        # dividir la vista, documento anterior/siguiente.
    }


registrar(Kate())
