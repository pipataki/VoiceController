# VoiceController

Control del ordenador por voz, pensado para accesibilidad. Habla, y el
ordenador hace: mover el puntero, pulsar, escribir al dictado, manejar
ventanas, abrir carpetas. Todo el reconocimiento va **en tu ordenador**, sin
enviar tu voz a ningún sitio.

Software libre, licencia **LGPLv3**. La versión está en `version.py`
(`python3 version.py` la dice), y el instalador la enseña al actualizar.

---

## Qué necesitas

- **Linux con KDE Plasma** (Wayland o X11) o **Windows 10/11**.
- Un micrófono. Vale el del portátil, aunque uno decente se nota.
- **Memoria**: el modelo de voz grande de tu lengua ocupa unos 3,4 GB con
  el español y 6,7 GB con el inglés. Cuenta con un equipo de **8 GB** con
  el español, y de 16 GB con el inglés.
- Unos **4 GB de disco** con el español de lengua materna, o unos 6 GB con
  el inglés.
- En Linux, tres programas del sistema que el instalador comprueba y te dice
  cómo poner si faltan: `ydotool` (mover el ratón y teclear), `kdotool`
  (manejar ventanas) y `spectacle` (capturar la pantalla).

---

## Cómo se instala

Descomprime el zip y, dentro de la carpeta:

```bash
./install.sh
```

En Windows, doble clic en `install.bat`.

**El instalador es también el actualizador.** Sobre una instalación que ya
existe detecta de qué versión vienes y **no te pisa nada tuyo**: ni tus
ajustes (`config_local.py`), ni tus comandos (`commands.json`, que se
*fusiona* para que lleguen los nuevos sin perder los tuyos), ni tu perfil de
voz, ni los certificados de la webapp. Los modelos grandes solo se descargan
si faltan.

En Windows, si tienes los modelos descargados de antes, deja sus `.zip` en
`modelos_offline/` dentro de la carpeta descomprimida y los usará sin bajar
nada.

Te pregunta lo poco que necesita saber: en Linux, tu lengua materna; qué micrófono, si
prefieres voz femenina o masculina, y si quieres activar el santo y seña
(que hace que solo obedezca a tu voz).

### Para desinstalar, o para probar una instalación limpia

```bash
./desinstalar.sh --simular      dice lo que borraría, sin tocar nada
./desinstalar.sh                borra, preguntando antes
```

En Windows, `desinstalar.bat` (sin argumentos solo enseña la lista; con
`/borrar` borra de verdad).

**Deja los modelos de voz donde están**, así que la siguiente instalación es
limpia pero tarda un minuto en vez de una hora: el instalador los encuentra
y no los descarga. Con `--con-modelos` (o `/todo` en Windows) se borran
también.

**Y no toca nada del sistema**: VoiceController vive entero en esta carpeta
-- no escribe en el registro de Windows, ni crea servicios, ni arranque
automático, ni ficheros en `/etc` --, así que **borrar la carpeta es
desinstalarlo del todo**.

Lo único que sobrevive son las **dependencias**, porque son del sistema y
las instalaste tú: en Linux, `ydotool`, `kdotool` y `spectacle` (más los
permisos que les diste); en Windows, tu instalación de Python. Quítalas o
déjalas según te convenga: el instalador nunca las puso por su cuenta, te
las dio escritas.

### Para arrancar

```bash
./run.sh                    la ventana de siempre
./silentRun.sh              lo mismo, sin ocupar la terminal
```

---

## Los dos modos

    python main.py                 la ventana normal
    python main.py --as-service    la MISMA ventana, arrancada oculta

En modo servicio no ves nada hasta que dices **"monitor"** o lo pides desde
el icono de la bandeja. Es la misma aplicación: no cambia nada de cómo
funciona, solo si se ve o no al arrancar.

---

## Cómo se usa, en cuatro ideas

**El tablero.** La pantalla se divide en 100 casillas. Dices un número y te
metes en esa casilla, ampliada. Dentro, los elementos que se pueden pulsar
salen numerados en naranja: dices el número y los pulsa.

**El puntero verde.** Dentro de una casilla puedes afinar con la voz o
moviendo el ratón sobre la miniatura. El punto verde marca dónde caerá el
clic.

**La vista de foco.** `foco kate` te enseña **esa ventana** ampliada, en vez
de un trozo de escritorio. Es lo cómodo cuando trabajas en un programa
concreto. Ojo: `foco` y `trae` son cosas distintas — `trae kate` sube esa
ventana al frente y no toca nada más.

**Dictado.** `dictado` empieza a escribir lo que digas y **`entra`** lo
termina: envía lo dictado a la ventana en la que estabas trabajando. Si
prefieres volver a espera sin enviar nada, `escucha`. Los números y las
fórmulas se escriben como números y símbolos, no como palabras.

Ojo con **`cerrar`**: no cierra el dictado, **cierra la aplicación**. Lo
mismo `fin`, `exit` y `close`.

Di **"ayuda"** en cualquier momento y salen los comandos que valen ahí
mismo, en una ventana que se cierra sola. Es la lista buena: sale de tus
propios `commands.json`, así que incluye lo que hayas añadido.

---

## El móvil

La aplicación levanta una web local a la que puedes entrar desde el teléfono
por HTTPS, con usuario y contraseña. Desde ahí ves lo que ve el ordenador y
tienes un touchpad para mover el puntero con el dedo.

Hay además una **APK de Android**, la misma para todo el mundo: no
lleva nada de tu ordenador dentro, así que se instala una vez y se
configura desde ella. El móvil funciona igual abriendo la dirección del PC
en el navegador; la APK solo evita tener que aceptar el certificado cada
vez.

---

## Tus ajustes van en `config_local.py`

**Nunca en `config.py`.** `config_local.py` se importa el último y gana, y
es el único que el actualizador respeta. Cambiar un valor en `config.py` que
también esté en `config_local.py` no hace nada.

El instalador te lo crea con lo básico y con comentarios explicando lo que
más se toca. Un ejemplo de los que se usan de verdad:

```python
INPUT_DEVICE = "nombre de tu micrófono"
TTS_VOICE_GENDER = "femenina"

# Extensiones propias al crear archivos por voz:
EXTENSIONES_HABLADAS = {"maqueta": "kra", "partitura": "mscz"}
```

### Dos idiomas

`LENGUA_MATERNA` ("es" o "en") decide cuál es tu lengua principal. Esa lleva
el modelo grande, dicta y entiende los números; la otra solo caza comandos,
con un modelo pequeño. No es un idioma "peor": es que reconocer dictado
libre cuesta 3,4 GB de memoria y cazar órdenes sueltas cuesta 155 MB.

En Linux el instalador te la pregunta y baja los modelos que tocan. Para
cambiarla, cámbiala en `config_local.py` y vuelve a pasar el instalador: bajará
el grande de la nueva. En Windows el instalador pone el español.

---

## Herramientas

```bash
./venv/bin/python tools/calibrar_zonas.py        ajusta la detección de elementos
./venv/bin/python tools/probar_voces.py          escucha las voces y elige una
./venv/bin/python tools/poner_ips_permitidas.py  filtro de IP para el móvil
./venv/bin/python tools/codigo_emparejamiento.py el código para emparejar el móvil
./venv/bin/python tools/probar_backend.py        comprueba lo que necesita del sistema
```

---

## Si algo va mal

Todo queda en **`voicecontroller.log`**, en la carpeta del programa (el del
arranque anterior, en `voicecontroller.log.1`). Ahí sale lo que oyó de
verdad el reconocedor y qué hizo con ello, que es casi siempre lo que hace
falta para entender por qué algo no responde.

Dos avisos que ahorran tiempo:

- **Si el filtrado por IP está puesto y tu móvil cambia de dirección**, la
  aplicación deja de responderte **sin ningún mensaje**. Se conecta y no
  pasa nada. Si usas DHCP, pon un rango en vez de una IP suelta.
- **`config_local.py` y `commands.json` son ficheros de texto con formato**.
  Si te dejas una coma de más, el programa te lo dirá al arrancar con la
  línea exacta.

---

## Dónde está escrito lo demás

- **`COMANDOS.md`** — todas las órdenes de voz, por secciones. En inglés,
  `COMMANDS.md`.
- El **manual en PDF** viene en el paquete, en español y en inglés
  (`VoiceController_Manual_<versión>_ES.pdf` y `…_EN.pdf`). Es corto, lleva
  la lista de órdenes como anexo y se puede leer con lector de pantalla.
- **`LICENSE`** — la LGPLv3, que es la licencia del proyecto.
- **`LICENSE.GPL-3.0`** — la GPLv3, que la LGPLv3 incorpora por
  referencia: hacen falta las dos.
