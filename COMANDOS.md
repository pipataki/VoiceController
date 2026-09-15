<!-- Generado por tools/lista_comandos.py desde commands.default.json: no editar a mano. -->

# Órdenes de voz de VoiceController

Todo lo que se puede decir, por secciones. Cada orden tiene varias formas y **todas funcionan**: aquí sale primero la más natural. Si has cambiado tus órdenes en `commands.json`, di "ayuda" y el programa te enseña las tuyas, las que valen donde estás.

- Lo básico
- El tablero y el punto verde
- Pulsar
- La ventana en la que trabajas
- Seleccionar
- Copiar, pegar y editar
- Archivos
- Teclas
- Desplazarse
- Dictar
- Fórmulas
- Programas y carpetas
- En Kate (editor de texto)

## Lo básico

Valen en cualquier momento. Si tienes activado el santo y seña, al arrancar di tu frase: se reconoce tu voz, no las palabras.

| Di | También vale | Qué hace |
|---|---|---|
| **`ayuda`** | `help`, `socorro`, `que puedo decir` | esta misma ventana: qué puedes decir aquí |
| **`ayuda audio`** | `ayuda con audio`, `ayuda en voz alta`, `help audio`, `léeme la ayuda` | la ayuda, además leída en voz alta |
| **`subir`** | `raise`, `sube` | trae la ventana de VoiceController al frente |
| **`monitor`** | `estado`, `muestra el estado`, `panel` | abre o cierra el panel de estado (solo en modo servicio) |
| **`standby`** | `duerme`, `en espera`, `pausa` | deja de escuchar hasta que digas tu santo y seña. También se pone en espera sola si pasa un rato sin usarse |
| **`soy yo`** | `desbloquear`, `continuar`, `sigue`, `it's me`, `unlock`, `continue` | si no te reconoce la voz o se ha bloqueado por una voz ajena: vuelve a pedirte el santo y seña |
| **`micrófono local`** | `mic local`, `local mic` | vuelve al micrófono del PC (tras usar el del móvil) |
| **`código de emparejamiento`** | `código del móvil`, `emparejar móvil`, `empareja móvil` | dice el código para emparejar el móvil con este ordenador |
| **`cerrar`** | `exit`, `close`, `cierra` | cierra VoiceController |

## El tablero y el punto verde

El tablero divide la pantalla en 100 casillas numeradas. Dentro de una casilla, del zoom o de la vista foco, el punto verde marca dónde se va a actuar, y se mueve con las direcciones.

| Di | También vale | Qué hace |
|---|---|---|
| **`tablero`** | `casillas`, `números`, `board`, `rejilla`, `grid` | vuelve al tablero con las casillas numeradas |
| **`<un número del 1 al 100>`** |  | entra en esa casilla del tablero |
| **`mover`** | `move`, `mueve` | 'mover &lt;casilla 1-100&gt;': entra en el cuarto de escritorio para afinar |
| **`menos zoom`** | `zoom out` | desde una casilla: pasa a ver el cuarto de pantalla que la rodea |
| **`<dirección> <número>`** |  | dentro de una casilla, del zoom o del foco: mueve el punto verde ese número de píxeles: "izquierda 5", "noreste 3" |
| **`táctil`** | `cara`, `touch`, `face` | táctil: el punto verde sigue al ratón o touchpad; cara: deja de seguirlo |
| **`refrescar`** | `refresca`, `refresco`, `refresh` | vuelve a capturar la pantalla y actualiza la vista que estés mirando |

Dentro de una casilla, del zoom o de la vista foco, mueven el punto verde un paso:

| Dirección | También vale |
|---|---|
| **`izquierda`** | `oeste`, `west`, `left` |
| **`derecha`** | `este`, `east`, `right` |
| **`arriba`** | `norte`, `north`, `up` |
| **`abajo`** | `sur`, `south`, `down` |
| **`noreste`** | `nordeste`, `northeast`, `ne` |
| **`noroeste`** | `northwest`, `nw` |
| **`sureste`** | `sudeste`, `southeast`, `se` |
| **`suroeste`** | `sudoeste`, `southwest`, `sw` |

## Pulsar

Con una casilla, el zoom o el foco abiertos, la acción se hace donde está el punto verde.

| Di | También vale | Qué hace |
|---|---|---|
| **`click`** | `clica`, `clic`, `click izquierdo`, `left click`, `pulsa`, `pulsar`, `toca`, `pincha` | 'click &lt;casilla&gt;' o 'click' con casilla ya elegida |
| **`click derecho`** | `clic derecho`, `right click`, `pulsa derecho`, `toca derecho`, `pincha derecho` | clic derecho, mismo formato que 'click' |
| **`doble click`** | `doble clic`, `double click`, `doble pulsa`, `pulsa dos veces`, `doble toca` | doble clic, mismo formato que 'click' |
| **`scroll arriba`** | `scroll up` | scroll arriba en la casilla apuntada |
| **`scroll abajo`** | `scroll down` | scroll abajo en la casilla apuntada |
| **`scroll izquierda`** | `scroll left` | scroll a la izquierda en la casilla apuntada |
| **`scroll derecha`** | `scroll right` | scroll a la derecha en la casilla apuntada |
| **`<un número del 1 al 9>`** |  | dentro de una casilla: actúa en esa zona detectada |
| **`<acción> <casilla>`** |  | de un tirón, en el centro de esa casilla: "click 45", "doble click 12", "scroll abajo 30" |
| **`<acción> verde`** |  | actúa donde está el punto verde que mueves con el ratón o el touchpad: "click verde" |
| **`<acción> rojo`** |  | actúa donde tiene el móvil su punto rojo: "click rojo". Con el móvil conectado basta la acción a secas |

## La ventana en la que trabajas

La vista foco enseña la ventana en la que estabas trabajando, para actuar sobre ella. Las demás órdenes actúan sobre la ventana que tengas delante.

| Di | También vale | Qué hace |
|---|---|---|
| **`foco`** | `focus`, `enfoca`, `enfocar`, `ventana activa` | enseña la ventana en la que estabas trabajando |
| **`foco <nombre>`** |  | la vista foco, sobre la ventana de ese programa: "foco kate", "foco firefox" |
| **`trae <nombre>`** |  | trae al frente la ventana de esa aplicación: "trae kate", "trae explorador". OJO: no es lo mismo que "foco", que es la vista |
| **`minimiza`** | `minimizar`, `minimize`, `esconde ventana` | minimiza la ventana de delante |
| **`maximiza`** | `maximizar`, `maximize`, `agranda ventana` | maximiza la ventana de delante |
| **`restaura`** | `restaurar` | quita el maximizado de la ventana de delante |
| **`pantalla completa`** | `fullscreen` | pantalla completa (conmuta) |
| **`cierra la ventana`** | `cierra ventana`, `cerrar la ventana`, `close the window`, `cierra esta ventana`, `cerrar esta ventana` | cierra la ventana de delante |
| **`siempre encima`** | `encima de todo` | mantiene la ventana de delante por encima (conmuta) |
| **`cambia ventana`** | `cambiar ventana`, `alt tab` | Alt+Tab |
| **`siguiente pestaña`** | `pestaña siguiente`, `next tab` | Ctrl+Tab |
| **`pestaña anterior`** | `previous tab` | Ctrl+Mayús+Tab |
| **`cierra la pestaña`** | `cerrar ventana`, `close window`, `cerrar pestaña`, `cierra pestaña` | Ctrl+W: cierra la pestaña o el documento |
| **`salir`** | `quit` | Alt+F4: cierra el programa que tienes delante |

## Seleccionar

Se marca dónde empieza, se lleva el punto verde hasta dónde acaba y se dice cómo terminar: como texto o como área.

| Di | También vale | Qué hace |
|---|---|---|
| **`seleccionar`** | `selecciona`, `empieza selección`, `origen de selección`, `origen selección`, `select`, `selección`, `seleccionar aquí`, `marca aquí` | fija DÓNDE empieza la selección (el punto se pone amarillo); para áreas gráficas, en hueco |
| **`fin de la selección`** | `fin de selección`, `fin selección`, `termina selección`, `end of selection`, `hasta aquí` | selecciona desde el origen hasta aquí (texto y listas) |
| **`arrastra aquí`** | `arrastra hasta aquí`, `suelta aquí`, `drag here`, `seleccionar área`, `selecciona área`, `seleccionar el área`, `fin de área`, `select área` | selecciona el área desde el origen hasta aquí (iconos, dibujos) — el ORIGEN debe caer en hueco |
| **`cancela selección`** | `cancelar selección`, `olvida selección`, `cancel selection` | olvida el origen fijado |
| **`seleccionar todo`** | `select all`, `todo`, `selecciona todo` | Ctrl+A |

## Copiar, pegar y editar

Van a la ventana que tengas delante.

| Di | También vale | Qué hace |
|---|---|---|
| **`copiar`** | `copy`, `copia` | Ctrl+C |
| **`pegar`** | `paste`, `pega` | Ctrl+V |
| **`cortar`** | `cut`, `corta` | Ctrl+X |
| **`deshacer`** | `undo`, `deshaz` | Ctrl+Z |
| **`rehacer`** | `redo` | Ctrl+Mayús+Z: rehace lo que se deshizo |
| **`buscar`** | `find`, `búsqueda`, `busca` | Ctrl+F |
| **`reemplazar`** | `replace`, `reemplaza` | Ctrl+H: buscar y reemplazar (en Kate, Ctrl+R) |
| **`eliminar`** | `delete`, `elimina` | tecla Supr |
| **`retroceso`** | `backspace`, `atrás` | tecla Retroceso |
| **`insertar`** | `insert`, `inserta` | tecla Insert |

## Archivos

| Di | También vale | Qué hace |
|---|---|---|
| **`guardar`** | `save`, `guarda` | Ctrl+S |
| **`guardar como`** | `save as`, `guarda como` | Ctrl+Mayús+S |
| **`guardar como <nombre>`** |  | abre Guardar como y escribe el nombre; luego di intro |
| **`nuevo`** | `nuevo archivo`, `new file` | Ctrl+N |
| **`abrir`** | `open`, `abre` | Ctrl+O: abrir un archivo |
| **`imprimir`** | `print`, `imprime` | Ctrl+P |
| **`renombrar`** | `rename`, `renombra` | F2 |
| **`recarga`** | `reload` | F5: recarga la página |

## Teclas

Sin casilla, zoom ni foco abiertos, arriba, abajo, izquierda y derecha son las flechas del teclado; dentro, mueven el punto verde.

| Di | También vale | Qué hace |
|---|---|---|
| **`intro`** | `enter`, `entrar`, `retorno` | tecla Intro |
| **`escape`** | `esc`, `escapar`, `escapa` | tecla Escape |
| **`tabulador`** | `tab` | tecla Tabulador |
| **`tabulador atrás`** | `tab atrás`, `shift tab`, `back tab` | Mayús+Tabulador (campo anterior) |
| **`espacio`** | `space`, `barra espaciadora`, `barra` | barra espaciadora |
| **`inicio`** | `home` | tecla Inicio |
| **`fin`** | `final`, `end`, `fin de línea` | tecla Fin |
| **`página arriba`** | `page up` | tecla RePág |
| **`página abajo`** | `page down` | tecla AvPág |
| **`arriba`** | `up` | flecha arriba |
| **`abajo`** | `down` | flecha abajo |
| **`izquierda`** | `left` | flecha izquierda |
| **`derecha`** | `right` | flecha derecha |

## Desplazarse

"desplaza" mueve cinco líneas; con "una" al final, solo una, que es lo cómodo para ir por un menú. "otra" repite el último desplazamiento, sea cual sea.

| Di | También vale | Qué hace |
|---|---|---|
| **`desplaza arriba`** | `scroll arriba`, `scroll up`, `desplazar arriba`, `sube página` | desplaza la vista hacia arriba |
| **`desplaza abajo`** | `scroll abajo`, `scroll down`, `desplazar abajo`, `baja página` | desplaza la vista hacia abajo |
| **`desplaza a la izquierda`** | `scroll izquierda`, `scroll left`, `desplazar izquierda`, `desplaza izquierda`, `desplaza la izquierda` | desplaza la vista a la izquierda |
| **`desplaza a la derecha`** | `scroll derecha`, `scroll right`, `desplazar derecha`, `desplaza derecha`, `desplaza la derecha` | desplaza la vista a la derecha |
| **`desplaza arriba una`** | `desplazar arriba una`, `desplaza arriba uno`, `desplazar arriba uno`, `scroll up one` | una sola línea hacia arriba: de uno en uno por un menú. También con una casilla seleccionada |
| **`desplaza abajo una`** | `desplazar abajo una`, `desplaza abajo uno`, `desplazar abajo uno`, `scroll down one` | una sola línea hacia abajo: de uno en uno por un menú. También con una casilla seleccionada |
| **`desplaza izquierda una`** | `desplazar izquierda una`, `desplaza a la izquierda una`, `desplaza la izquierda una`, `desplaza izquierda uno`, `desplaza a la izquierda uno`, `scroll left one` | un solo paso a la izquierda: de uno en uno por un menú. También con una casilla seleccionada |
| **`desplaza derecha una`** | `desplazar derecha una`, `desplaza a la derecha una`, `desplaza la derecha una`, `desplaza derecha uno`, `desplaza a la derecha uno`, `scroll right one` | un solo paso a la derecha: de uno en uno por un menú. También con una casilla seleccionada |
| **`otra`** | `otro`, `otra vez`, `again` | repite el último desplazamiento, sea cual sea y en el mismo sitio |

## Dictar

Con "dictar" empiezas: desde ahí, lo que dices va entero al Pre-Texto, como frase. Habla con normalidad: los signos de interrogación y de exclamación los pone el programa, y los números salen en cifras. Si se equivoca, "interrogación", "exclamación", "afirmación" o "matemática" rehacen la última frase. Mientras dictas valen solo las órdenes de abajo, dichas tras una pausa.

| Di | También vale | Qué hace |
|---|---|---|
| **`dictar`** | `type`, `dicta` | pasa a modo dictado (escribir texto por voz) |
| **`entra`** | `enter`, `okey`, `ok`, `yes` | confirma lo dictado y lo escribe en la app de destino |
| **`borra`** | `reset`, `erase`, `borrar` | borra el Pre-Texto y empieza de cero |
| **`corrige`** | `corregir`, `correct`, `fix` | corrige una palabra: 'corrige &lt;nº&gt; &lt;mayúscula/siglas/cifras...&gt;' |
| **`corrige <número> <cómo>`** |  | cambia esa palabra del Pre-Texto: mayúscula, minúscula, siglas, cifras o letras. "corrige 3 mayúscula" |
| **`interrogación`** | `question` | la última frase, como pregunta: ¿...? |
| **`exclamación`** | `exclamation` | la última frase, como exclamación: ¡...! |
| **`afirmación`** | `statement` | la última frase, sin interrogación ni exclamación: con punto |
| **`matemática`** | `math` | la última frase, como fórmula (como el modo "deletrear") |
| **`vale`** |  | acepta la sugerencia que aparece abajo |
| **`escucha`** | `idle`, `listen`, `oye` | vuelve a modo escucha sin confirmar |

## Fórmulas

El modo fórmula escribe símbolos en vez de palabras. Se termina igual que el dictado, con "entra" o "escucha".

| Di | También vale | Qué hace |
|---|---|---|
| **`deletrear`** | `formule`, `fórmula`, `math`, `matemática`, `deletrea` | modo fórmula/matemáticas, letra a letra |

| Di | Escribe |
|---|---|
| `mayor o igual que` | `>=` |
| `menor o igual que` | `<=` |
| `distinto de` | `!=` |
| `distinto a` | `!=` |
| `no es` | `!=` |
| `es igual a` | `==` |
| `igual a` | `=` |
| `mayor que` | `>` |
| `menor que` | `<` |
| `elevado a` | `^` |
| `al cuadrado` | `^2` |
| `al cubo` | `^3` |
| `raíz cuadrada de` | `sqrt(` |
| `abre paréntesis` | `(` |
| `cierra paréntesis` | `)` |
| `abre corchetes` | `[` |
| `cierra corchetes` | `]` |
| `abre llaves` | `{` |
| `cierra llaves` | `}` |
| `por ciento` | `%` |
| `y griega` | `y` |
| `i griega` | `y` |
| `si y solo si` | `<-->` |
| `si solo si` | `<-->` |
| `imprime salto de línea` | `P/n>>` |
| `más` | `+` |
| `menos` | `-` |
| `por` | `*` |
| `entre` | `/` |
| `dividido` | `/` |
| `igual` | `=` |
| `módulo` | `%` |
| `coma` | `,` |
| `vale` | `=` |
| `mayor` | `>` |
| `menor` | `<` |
| `cuadrado` | `^2` |
| `cubo` | `^3` |
| `elevado` | `^` |
| `corchetes` | `[` |
| `llaves` | `{` |
| `paréntesis` | `(` |
| `cierto` | `True` |
| `no` | `!` |
| `verdadero` | `True` |
| `falso` | `False` |

Las letras se dicen por su nombre: **a**: a, ah; **b**: be; **c**: ce; **d**: de; **e**: e, eh; **f**: efe; **g**: ge; **h**: ache, hache; **i**: i; **j**: jota; **k**: ka, ca; **l**: ele; **m**: eme; **n**: ene; **o**: o, oh; **p**: pe; **q**: cu, ku; **r**: erre, ere; **s**: ese; **t**: te; **u**: u, uh; **v**: uve, ube, ue; **w**: uvedoble, ubedoble, uedoble; **x**: equis, ekis; **y**: igriega, ygriega, ye; **z**: zeta, ceta.

Palabras de pseudocódigo: `si` → `-->`, `entonces` → `THEN`, `sino` → `! -->`, `mientras` → `WHILE`, `para` → `FOR`, `función` → `F#`, `resultado` → `F<<`, `retorna` → `>>>`, `devuelve` → `>>>`, `recibe` → `<<<`, `imprime` → `P>>`, `variable` → `VAR`, `hacer` → `DO`, `repetir` → `2X`, `entero` → `INT`, `flotante` → `FLOAT`, `booleano` → `BOOL`, `binario` → `BOOL`, `and` → `AND`, `or` → `OR`, `corchetes` → `[`, `llaves` → `{`, `paréntesis` → `(`, `cierto` → `True`, `no` → `!`, `verdadero` → `True`, `falso` → `False`.

## Programas y carpetas

Las carpetas son las de tu perfil (Documentos, Descargas...). Nunca se crea una carpeta que no existe al pedirla.

| Di | También vale | Qué hace |
|---|---|---|
| **`terminal`** | `consola`, `konsole` | abre una terminal (en Windows abre `cmd`) |
| **`explorar`** |  | gestor de archivos/carpetas (en Windows abre `explorer`) |
| **`editor`** | `editar`, `texto`, `edita` | abre el editor de texto (en Windows abre `notepad`) |
| **`navegar`** | `web`, `firefox`, `navega` | abre el navegador |
| **`dibujar`** | `dibujo`, `inkscape`, `dibuja` | abre Inkscape, el programa de dibujo |
| **`carpeta <nombre>`** |  | trae esa carpeta del perfil si está abierta, o la abre. NO la crea |
| **`terminal en <nombre>`** |  | abre una consola dentro de esa carpeta |
| **`crear carpeta <nombre>`** |  | crea una carpeta DONDE tengas abierto Dolphin |
| **`crear archivo <nombre>`** |  | crea un archivo donde tengas abierto Dolphin. Di la extensión por su NOMBRE al final: "apuntes texto" -&gt; apuntes.txt, "arranque guion" -&gt; .sh, "programa python" -&gt; .py. El punto lo pone el programa |

## En Kate (editor de texto)

Solo valen con Kate delante. Todo lo demás de esta lista sigue valiendo también en Kate.

| Di | Tecla |
|---|---|
| **`reemplazar`**, `reemplaza` | Ctrl+R |
| **`ir a línea`**, `ir a la línea` | Ctrl+G |
| **`buscar siguiente`** | F3 |
| **`buscar anterior`** | Mayús+F3 |
| **`comentar`** | Ctrl+D |
| **`descomentar`** | Ctrl+Mayús+D |
| **`sangrar`** | Ctrl+I |
| **`quitar sangría`** | Ctrl+Mayús+I |
| **`guardar todo`** | Ctrl+L |
| **`documento nuevo`**, `nuevo documento` | Ctrl+N |
| **`cerrar documento`** | Ctrl+W |
| **`números de línea`** | F11 |
| **`ajuste de línea`** | F10 |
| **`panel de terminal`** | F4 |

*107 órdenes en total, sin contar las de Kate.*
