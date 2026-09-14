#!/usr/bin/env bash
# =============================================================================
# VoiceController -- instalador Y actualizador (el mismo script sirve para los dos)
# =============================================================================
# Distingue solo por una cosa: si el destino ya tiene datos personales, es una
# ACTUALIZACIÓN y esos ficheros no se tocan; si no, es una instalación nueva.
#
#   ./install.sh                 -> instala/actualiza en el directorio actual
#   ./install.sh /ruta/destino   -> en otro sitio
#   ./install.sh --sin-modelos   -> no descarga modelos (para pruebas)
#
# Lo que NUNCA se pisa al actualizar está en la lista PERSONALES de abajo. Si
# algún día se añade un fichero que guarde algo del usuario, VA AHÍ MISMO --
# olvidarlo significa que alguien actualiza y pierde datos sin saber por qué.
set -uo pipefail

PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# El instalador tiene que estar DENTRO de su paquete: es de ahi de donde
# copia. Si alguien lo saca solo a otra carpeta, a su lado no hay codigo, y
# sin este freno copiaria un arbol vacio y el fallo saldria mucho despues.
# Mismo criterio que install.bat.
if [ ! -f "$PKG_DIR/main.py" ]; then
  echo "  ✗ Este install.sh no esta dentro de su paquete: a su lado no hay main.py."
  echo "    Descomprime el zip entero y ejecuta el install.sh que hay DENTRO de"
  echo "    la carpeta que sale (VoiceController-x.y.z)."
  exit 1
fi

DESTINO=""
SIN_MODELOS=0
for arg in "$@"; do
  case "$arg" in
    # Ya no construye nada: la APK viene hecha en el paquete. Se acepta para
    # que no se tome por la carpeta de destino.
    --apk) ;;
    --sin-modelos) SIN_MODELOS=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) DESTINO="$arg" ;;
  esac
done
# El destino se pregunta si no se ha dado por argumento -- salvo que ya
# estemos DENTRO de una instalación, en cuyo caso es evidente.
if [ -z "$DESTINO" ]; then
  if [ -f "$PWD/main.py" ] && [ -f "$PWD/paths.py" ]; then
    DESTINO="$PWD"
  else
    read -rp "¿Dónde quieres instalar VoiceController? [$HOME/VoiceController] " DESTINO
    DESTINO="${DESTINO:-$HOME/VoiceController}"
  fi
fi
DESTINO="${DESTINO/#\~/$HOME}"
mkdir -p "$DESTINO"; DESTINO="$(cd "$DESTINO" && pwd)"

# --- ¿Instalacion nueva o actualizacion? ------------------------------------
#
# La version instalada se guarda en .instalado, que NO viaja en el paquete
# (igual que config_local.py). Asi sobrevive a descomprimir la version nueva
# encima, y se puede decir de donde se viene. Mismo criterio que install.bat.
VER_NUEVA="$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$PKG_DIR/version.py" 2>/dev/null)"
VER_VIEJA="$(cat "$DESTINO/.instalado" 2>/dev/null)"
echo
if [ -n "$VER_VIEJA" ]; then
  if [ "$VER_VIEJA" = "$VER_NUEVA" ]; then
    echo "  Reinstalando la versión $VER_NUEVA"
  else
    echo "  ACTUALIZANDO de la $VER_VIEJA a la $VER_NUEVA"
    echo "    Tus ajustes se conservan: config_local.py no se toca, y"
    echo "    commands.json se fusiona en vez de pisarse."
  fi
else
  echo "  Instalación NUEVA de la versión $VER_NUEVA"
fi


# --- Ficheros y carpetas que son DEL USUARIO: nunca se sobrescriben ---------
PERSONALES=(
  config_local.py              # sus ajustes medidos (micrófono, umbrales, voz)
  webapp_config.json           # usuario y hash de contraseña
  webapp_cert.pem webapp_key.pem
  config/speaker_profile.json          # su voz por el micro del PC
  config/speaker_profile_network.json  # su voz por el móvil
  corrections.json             # correcciones aprendidas dictando
  commands.json                # comandos: se FUSIONA, no se pisa (ver abajo)
  window_names.json
  tools/speaker_calibration_data.json
  .backups                     # copias de perfiles
  vosk_models piper_voices     # modelos: cientos de MB, no se rebajan
  venv
)

azul(){ printf "\033[1;34m%s\033[0m\n" "$*"; }
ok(){   printf "  \033[32m✓\033[0m %s\n" "$*"; }
avi(){  printf "  \033[33m!\033[0m %s\n" "$*"; }
err(){  printf "  \033[31m✗\033[0m %s\n" "$*"; }

# ---------------------------------------------------------------------------
# 1. ¿Instalación nueva o actualización?
# ---------------------------------------------------------------------------
# Lo que hace que algo sea una ACTUALIZACIÓN no es que haya código -- un
# paquete recién descomprimido también lo tiene -- sino que haya DATOS DEL
# USUARIO. Si no los hay, es una instalación nueva aunque estemos dentro de
# una carpeta llena de .py.
MODO="instalación nueva"
for f in config_local.py webapp_config.json config/speaker_profile.json corrections.json; do
  if [ -f "$DESTINO/$f" ]; then MODO="actualización"; break; fi
done
azul "== VoiceController: $MODO en $DESTINO =="
echo "   paquete: $PKG_DIR"
[ "$PKG_DIR" = "$DESTINO" ] && avi "origen y destino son el mismo sitio: no se copiará código"

# ---------------------------------------------------------------------------
# 1b. Cuestionario -- SOLO en instalación nueva
# ---------------------------------------------------------------------------
# Al actualizar NO se pregunta NADA: la configuración ya está hecha y volver a
# preguntarla solo daría ocasión de romperla sin querer.
QUIERE_REMOTO=0; QUIERE_VOZ=0
FRASE_LOGIN=""; USUARIO=""; GENERO_VOZ="femenina"
preguntar_si(){ # $1=pregunta  $2=por_defecto(s/n)
  local d="$2" p
  [ "$d" = "s" ] && p="[S/n]" || p="[s/N]"
  read -rp "   $1 $p " r; r="${r:-$d}"
  [[ "$r" =~ ^[sS] ]]
}

if [ "$MODO" = "instalación nueva" ]; then
  echo
  azul "== Configuración inicial =="
  echo "   Unas preguntas. Al actualizar no se volverán a hacer."
  echo

  if preguntar_si "¿Quieres usar el móvil como micrófono y mando a distancia?" s; then
    QUIERE_REMOTO=1
    read -rp "   Nombre de usuario para entrar desde el móvil [$USER]: " USUARIO
    USUARIO="${USUARIO:-$USER}"
    echo "   (la contraseña se pedirá luego, y se guarda cifrada)"
  fi
  echo

  if preguntar_si "¿Quieres identificarte por VOZ al arrancar (santo y seña)?" s; then
    QUIERE_VOZ=1
    echo "   Se comprueba SOLO tu voz, no lo que digas: la frase existe para que"
    echo "   haya audio suficiente. Vale cualquiera de unos 3 segundos."
    read -rp "   Frase que usarás [La lluvia en Sevilla es una maravilla]: " FRASE_LOGIN
    FRASE_LOGIN="${FRASE_LOGIN:-La lluvia en Sevilla es una maravilla}"
  fi
  echo

  read -rp "   Voz del asistente, ¿femenina o masculina? [femenina]: " GENERO_VOZ
  GENERO_VOZ="${GENERO_VOZ:-femenina}"
  echo

  azul "-- Resumen --"
  echo "   Destino        : $DESTINO"
  echo "   Móvil / remoto : $([ $QUIERE_REMOTO = 1 ] && echo "sí (usuario: $USUARIO)" || echo no)"
  echo "   Santo y seña   : $([ $QUIERE_VOZ = 1 ] && echo "sí -- \"$FRASE_LOGIN\"" || echo no)"
  echo "   Voz            : $GENERO_VOZ"
  echo
  preguntar_si "¿Empezamos?" s || { echo "   Cancelado."; exit 0; }
fi

# ---------------------------------------------------------------------------
# 2. Dependencias del sistema
# ---------------------------------------------------------------------------
azul "== Dependencias del sistema =="
if   command -v apt-get >/dev/null; then GESTOR=apt
elif command -v pacman  >/dev/null; then GESTOR=pacman
elif command -v dnf     >/dev/null; then GESTOR=dnf
elif command -v zypper  >/dev/null; then GESTOR=zypper
else GESTOR=""; fi
[ -n "$GESTOR" ] && ok "gestor de paquetes: $GESTOR" || avi "gestor no reconocido: instala a mano lo que falte"

# --- Arquitectura -----------------------------------------------------------
# En ARM (Raspberry Pi 4/5 y portátiles ARM) NO hay rueda de PySide6 en PyPI,
# aunque sí de todo lo demás (vosk, onnxruntime, piper-tts, numpy...). La
# solución no es compilar Qt: Debian y Raspberry Pi OS traen PySide6 como
# paquete del sistema, así que se instala por ahí y el venv se crea con
# --system-site-packages para poder verlo.
ARCH="$(uname -m)"
ES_ARM=0
case "$ARCH" in
  aarch64|arm64|armv7l|armv8*) ES_ARM=1 ;;
esac
ok "arquitectura: $ARCH$([ $ES_ARM = 1 ] && echo '  (ARM: PySide6 vendrá del sistema)')"
if [ "$ES_ARM" = "1" ] && [ "$GESTOR" = "apt" ]; then
  PYSIDE_APT="python3-pyside6.qtwidgets python3-pyside6.qtgui python3-pyside6.qtcore"
  if ! python3 -c "import PySide6" 2>/dev/null; then
    err "falta PySide6 del sistema"
    echo "   sudo apt install $PYSIDE_APT"
    read -rp "   ¿Continuar igualmente? [s/N] " r; [[ "$r" =~ ^[sS] ]] || exit 1
  else
    ok "PySide6 del sistema"
  fi
fi

# nombre_comando:apt:pacman:dnf  (vacío = mismo nombre)
declare -A PAQ=(
  [ydotool]="ydotool:ydotool:ydotool"
  [ffmpeg]="ffmpeg:ffmpeg:ffmpeg"
  [espeak-ng]="espeak-ng:espeak-ng:espeak-ng"
  [paplay]="pulseaudio-utils:libpulse:pulseaudio-utils"
  [spectacle]="kde-spectacle:spectacle:spectacle"
  [openssl]="openssl:openssl:openssl"
)
FALTAN=()
for cmd in "${!PAQ[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then ok "$cmd"
  else
    IFS=':' read -r p_apt p_pac p_dnf <<< "${PAQ[$cmd]}"
    case "$GESTOR" in apt) n=$p_apt;; pacman) n=$p_pac;; dnf|zypper) n=$p_dnf;; *) n=$cmd;; esac
    err "$cmd  (paquete: $n)"; FALTAN+=("$n")
  fi
done
# ydotoold es imprescindible: sin el demonio, ydotool no escribe NADA.
# Ojo: NO basta con que haya un ydotoold vivo. Si el que corre es el de
# root, su socket es /tmp/.ydotool_socket con modo 600 root:root, y tu
# usuario ni siquiera puede abrirlo -> el programa no escribe una tecla
# y el diagnóstico dice que todo está bien. Por eso se comprueba el
# socket de TU usuario, que es el que ydotool 1.x busca por defecto
# ($XDG_RUNTIME_DIR/.ydotool_socket), y no la simple presencia del proceso.
if command -v ydotool >/dev/null; then
  # 1) permiso sobre /dev/uinput: es lo que necesita el demonio de usuario
  #    para crear el teclado virtual, y lo que falta en un equipo recién
  #    instalado. El grupo suele ser 'input'.
  if [ -e /dev/uinput ]; then
    if [ -w /dev/uinput ]; then
      ok "/dev/uinput accesible sin root"
    else
      GRUPO_UINPUT="$(stat -c '%G' /dev/uinput 2>/dev/null || echo input)"
      avi "no puedes escribir en /dev/uinput -> ydotoold de usuario no arrancará.
       Añádete al grupo y vuelve a entrar en la sesión:
         sudo usermod -aG $GRUPO_UINPUT \"$USER\"
       (hace falta cerrar sesión y volver a abrirla, o reiniciar)"
    fi
  else
    avi "/dev/uinput no existe -> carga el módulo:  sudo modprobe uinput
       (para que persista:  echo uinput | sudo tee /etc/modules-load.d/uinput.conf)"
  fi

  # 2) el socket de TU usuario, que es el que de verdad se va a usar
  SOCK_YDO="${YDOTOOL_SOCKET:-${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/.ydotool_socket}"
  if [ -S "$SOCK_YDO" ] && [ -w "$SOCK_YDO" ]; then
    ok "ydotoold de usuario en marcha ($SOCK_YDO)"
  elif pgrep -x ydotoold >/dev/null; then
    avi "hay un ydotoold corriendo, pero NO es el tuyo: falta $SOCK_YDO
       Si es el de root, sobra y encima cuelga un segundo teclado de uinput:
         sudo systemctl disable --now ydotool.service
       Y arranca el tuyo:
         systemctl --user enable --now ydotool.service"
  else
    avi "ydotoold NO está corriendo -> no se escribirá ni una tecla.
       Arráncalo con:  systemctl --user enable --now ydotool.service
       (o a mano:      ydotoold &)"
  fi
fi
if command -v kdotool >/dev/null; then ok "kdotool"
else
  avi "kdotool no está: los comandos de ventana (minimiza/maximiza) no funcionarán."
  echo "       Se instala con cargo:  cargo install kdotool"
  [ "${ES_ARM:-0}" = "1" ] && echo "       En ARM tarda bastante en compilar, pero funciona."
fi
if [ ${#FALTAN[@]} -gt 0 ]; then
  echo
  case "$GESTOR" in
    apt)    echo "   sudo apt install ${FALTAN[*]}" ;;
    pacman) echo "   sudo pacman -S ${FALTAN[*]}" ;;
    dnf)    echo "   sudo dnf install ${FALTAN[*]}" ;;
    zypper) echo "   sudo zypper install ${FALTAN[*]}" ;;
    *)      echo "   instala: ${FALTAN[*]}" ;;
  esac
  read -rp "   ¿Continuar de todas formas? [s/N] " r; [[ "$r" =~ ^[sS] ]] || exit 1
fi

# ---------------------------------------------------------------------------
# 3. Copiar el código (respetando lo personal)
# ---------------------------------------------------------------------------
if [ "$PKG_DIR" != "$DESTINO" ]; then
  azul "== Copiando código =="
  # --- Red de seguridad ANTES de copiar -------------------------------
  # La lista PERSONALES es manual, y por tanto olvidable: si algún día se
  # añade un fichero que guarde datos del usuario y nadie lo apunta ahí,
  # se pisaría sin avisar. Eso es un fallo SILENCIOSO -- alguien actualiza
  # y pierde algo sin saber por qué.
  #
  # Así que antes de copiar nada se guarda copia de TODO lo que el paquete
  # va a sobrescribir y que además sea DISTINTO de lo que ya había. Aunque
  # la lista falle, lo perdido se puede recuperar.
  COPIA="$DESTINO/.update_backups/$(date +%Y%m%d_%H%M%S)"
  N_COPIADOS=0
  while IFS= read -r rel; do
    [ -f "$DESTINO/$rel" ] || continue
    cmp -s "$PKG_DIR/$rel" "$DESTINO/$rel" && continue   # idéntico: nada que salvar
    mkdir -p "$COPIA/$(dirname "$rel")"
    cp -p "$DESTINO/$rel" "$COPIA/$rel"
    N_COPIADOS=$((N_COPIADOS+1))
  done < <(cd "$PKG_DIR" && find . -type f \
             -not -path "./venv/*" -not -path "./.git/*" \
             -not -path "*/__pycache__/*" -not -name "*.pyc" \
             -not -path "./vosk_models/*" -not -path "./piper_voices/*" \
             -not -path "./dist/*" -printf "%P\n")
  if [ "$N_COPIADOS" -gt 0 ]; then
    ok "copia de seguridad de $N_COPIADOS ficheros que van a cambiar"
    echo "     $COPIA"
  fi

  EXCL=(); for p in "${PERSONALES[@]}"; do EXCL+=(--exclude="$p"); done
  if command -v rsync >/dev/null; then
    rsync -a "${EXCL[@]}" --exclude='__pycache__' --exclude='*.pyc' \
          --exclude='logs' --exclude='webapp_uploads' --exclude='.git' \
          "$PKG_DIR"/ "$DESTINO"/
    ok "código actualizado (sin tocar lo personal)"
  else
    err "rsync no está instalado: hace falta para copiar sin pisar lo personal"; exit 1
  fi
fi

# ---------------------------------------------------------------------------
# 4. Entorno Python
# ---------------------------------------------------------------------------
azul "== Entorno Python =="
cd "$DESTINO"
if [ ! -d venv ]; then
  if [ "$ES_ARM" = "1" ]; then
    # --system-site-packages: para que el venv vea el PySide6 del sistema,
    # que en ARM es la única forma razonable de tenerlo.
    python3 -m venv --system-site-packages venv && ok "venv creado (viendo los paquetes del sistema)"
  else
    python3 -m venv venv && ok "venv creado"
  fi
fi
# Instala un requirements.txt y ABORTA si no puede.
#
# Antes esto era `pip install ... | tail -3` seguido de un ok incondicional:
# la tubería se come el código de salida, así que decía "requirements.txt OK"
# aunque no se hubiera instalado nada, y luego seguía a descargar cientos de
# MB de modelos sobre una instalación inservible. Un fallo aquí es fatal.
#
# El reintento sin caché cubre el error típico de permisos en ~/.cache/pip.
instalar_requisitos() {
  local fichero="$1" etiqueta="$2" salida
  if salida="$(./venv/bin/pip install -q -r "$fichero" 2>&1)"; then
    ok "$etiqueta"; return 0
  fi
  avi "pip falló; reintentando sin caché"
  if salida="$(./venv/bin/pip install -q --no-cache-dir -r "$fichero" 2>&1)"; then
    ok "$etiqueta (sin caché)"; return 0
  fi
  echo "$salida" | tail -5
  err "No se pudieron instalar las dependencias. Se aborta: sin ellas no"
  err "arranca nada, y descargar los modelos ahora sería tirar el ancho de"
  err "banda para nada."
  exit 1
}

./venv/bin/pip install -q --upgrade pip >/dev/null 2>&1
if [ "$ES_ARM" = "1" ]; then
  # En ARM se instala todo MENOS PySide6 y pyaudio, que vienen del sistema:
  # pip intentaría compilarlos y en una Raspberry eso son horas, si termina.
  grep -viE "^(PySide6|pyaudio)" requirements.txt > /tmp/req_arm.txt
  instalar_requisitos /tmp/req_arm.txt "requirements (sin PySide6 ni pyaudio: los pone el sistema)"
  rm -f /tmp/req_arm.txt
else
  instalar_requisitos requirements.txt "requirements.txt"
fi
python3 - <<'PYCHK' || avi "PySide6 no es visible desde el venv: la ventana no arrancará"
import subprocess, sys
r = subprocess.run(["./venv/bin/python", "-c", "import PySide6; print(PySide6.__version__)"],
                   capture_output=True, text=True)
sys.exit(0 if r.returncode == 0 else 1)
PYCHK
./venv/bin/pip install -q piper-tts >/dev/null 2>&1 && ok "piper-tts" || avi "piper-tts falló: la voz caerá a espeak-ng"

# ---------------------------------------------------------------------------
# 5. Modelos (grandes: solo si faltan)
# ---------------------------------------------------------------------------
if [ "$SIN_MODELOS" = "0" ]; then
  azul "== Modelos de voz =="
  mkdir -p vosk_models piper_voices
  # Un modelo a medias NO da error al instalar: falla mucho despues, al
  # arrancar, y con un mensaje que parece del microfono. Ya pasó: una
  # extraccion dejo fuera conf/ e ivector/ (10 MB de 2,3 GB) y el
  # sintoma fue "error de reconocimiento".
  # Verificar el ZIP ANTES de extraer. Una descarga reanudada puede quedar
  # corrupta con el tamaño correcto (si el servidor ignora el Range, curl
  # añade al final y el fichero acaba desalineado). Ya pasó: el zip medía
  # lo que debía, unzip extrajo la mayor parte, y el fallo salió mucho
  # después como "Failed to read token" al cargar el modelo.
  # Si está corrupto se BORRA, para que el siguiente intento no lo reanude.
  comprobar_zip(){
    if unzip -tq "$1" >/dev/null 2>&1; then return 0; fi
    err "el archivo descargado está corrupto: se borra y habrá que repetir"
    rm -f "$1"
    return 1
  }


  comprobar_modelo(){ # $1 = carpeta del modelo
    local falta=""
    case "$(basename "$1")" in
      *spk*)
        # El modelo de locutor NO tiene la estructura de los de idioma:
        # son ficheros sueltos. Comprobarlo con la otra lista lo daría por
        # incompleto y lo borraría estando bien.
        for f in final.ext.raw mean.vec mfcc.conf transform.mat; do
          [ -f "$1/$f" ] || falta="$falta $f"
        done
        ;;
      *)
        for d in am conf graph ivector; do
          [ -d "$1/$d" ] || falta="$falta $d"
        done
        ;;
    esac
    if [ -n "$falta" ]; then
      err "el modelo $(basename "$1") esta incompleto: falta$falta"
      err "borra esa carpeta y vuelve a pasar el instalador"
      rm -rf "$1"
      return 1
    fi
  }

  bajar_vosk(){ # $1 = nombre del modelo
    [ -d "vosk_models/$1" ] && { ok "$1 (ya estaba)"; return; }
    echo "   descargando $1 ..."
    # -C - reanuda y --retry reintenta: son varios GB, y una descarga
    # que se corta a media hora no puede empezar de cero. El trozo
    # bajado se conserva en /tmp para poder continuar.
    curl -# -L -C - --retry 5 --retry-delay 3 \
         -o "/tmp/$1.zip" "https://alphacephei.com/vosk/models/$1.zip" \
      && comprobar_zip "/tmp/$1.zip" \
      && unzip -q -o "/tmp/$1.zip" -d vosk_models && rm -f "/tmp/$1.zip" \
      && comprobar_modelo "vosk_models/$1" && ok "$1" \
      || err "no se pudo descargar $1 (lo bajado se conserva en /tmp/$1.zip)"
  }
  bajar_vosk vosk-model-es-0.42
  bajar_vosk vosk-model-en-us-0.42
  bajar_vosk vosk-model-spk-0.4
  if ls piper_voices/*.onnx >/dev/null 2>&1; then ok "voz de Piper (ya estaba)"
  else
    ./venv/bin/python -m piper.download_voices es_ES-sharvard-medium \
        --download-dir piper_voices >/dev/null 2>&1 && ok "voz es_ES-sharvard-medium" \
      || avi "no se pudo bajar la voz de Piper"
  fi
fi

# ---------------------------------------------------------------------------
# 6. commands.json: FUSIÓN, nunca sobrescritura
# ---------------------------------------------------------------------------
azul "== Comandos =="
if [ -f commands.json ] && [ -f "$PKG_DIR/commands.default.json" ]; then
  ./venv/bin/python tools/merge_commands.py "$PKG_DIR/commands.default.json" --aplicar
elif [ ! -f commands.json ]; then
  cp "$PKG_DIR/commands.default.json" commands.json 2>/dev/null && ok "commands.json inicial"
fi

# Lo mismo con las listas de prosodia: lo que hayas ampliado se conserva y
# lo nuevo de la version llega. Sin esto, quien personalice su prosody.json
# no recibiria nunca una palabra nueva.
if [ -f prosody.json ] && [ -f "$PKG_DIR/prosody.default.json" ]; then
  ./venv/bin/python tools/merge_prosody.py "$PKG_DIR/prosody.default.json" --aplicar \
    && ok "prosodia al dia" || avi "no se pudo fusionar prosody.json"
elif [ -f "$PKG_DIR/prosody.default.json" ]; then
  cp "$PKG_DIR/prosody.default.json" prosody.json 2>/dev/null && ok "prosody.json inicial"
fi

# ---------------------------------------------------------------------------
# 7. config_local.py: los ajustes personales
# ---------------------------------------------------------------------------
azul "== Ajustes personales =="
if [ -f config_local.py ]; then
  ok "config_local.py ya existe: NO se toca"
else
  echo "   Micrófonos disponibles:"
  ./venv/bin/python - <<'PY'
import sounddevice as sd
for i, d in enumerate(sd.query_devices()):
    if d["max_input_channels"] > 0:
        print(f"     {i:3}  {d['name'][:52]}")
PY
  read -rp "   Índice del micrófono a usar (vacío = el del sistema): " MIC
  # Se guarda el NOMBRE, no el número. El índice cambia solo: basta con que
  # se conecte o desaparezca otro dispositivo para que el micrófono pase
  # del 5 al 3, y entonces la aplicación "no oye nada" sin dar ninguna
  # pista. El nombre se resuelve en cada arranque
  # (microphone_manager.find_device_by_name).
  NOMBRE_MIC=""
  if [ -n "$MIC" ]; then
    NOMBRE_MIC="$(./venv/bin/python -c "import sys,sounddevice as s;print(s.query_devices(int(sys.argv[1]))['name'])" "$MIC" 2>/dev/null)"
  fi
  { echo '"""Tus ajustes. Este fichero NO se pisa al actualizar."""'
    echo
    if [ -n "$NOMBRE_MIC" ]; then echo "INPUT_DEVICE = \"$NOMBRE_MIC\""; elif [ -n "$MIC" ]; then echo "INPUT_DEVICE = $MIC"; else echo "INPUT_DEVICE = None"; fi
    echo
    echo "TTS_VOICE_GENDER = \"${GENERO_VOZ:-femenina}\""
    echo
    if [ "$QUIERE_VOZ" = "1" ]; then
      echo "VOICE_LOGIN_ENABLED = True"
      echo "VOICE_LOGIN_HINT = \"${FRASE_LOGIN}\""
      echo "# El umbral se rellena al calibrar:"
      echo "#   ./venv/bin/python tools/speaker_calibration.py login"
    else
      echo "# Identificación por voz desactivada en la instalación."
      echo "# Para activarla: pon True, enrola tu voz y calibra el umbral."
      echo "VOICE_LOGIN_ENABLED = False"
    fi
    echo
    echo "# ---------------------------------------------------------------"
    echo "# TUS EXTENSIONES DE ARCHIVO"
    echo "# ---------------------------------------------------------------"
    echo "# Al decir \"crear archivo <nombre>\", si la ULTIMA palabra es el"
    echo "# nombre de una extension, se usa como tal y el punto lo pone el"
    echo "# programa:"
    echo "#"
    echo "#     crear archivo apuntes texto      ->  apuntes.txt"
    echo "#     crear archivo arranque guion     ->  arranque.sh"
    echo "#     crear archivo programa python    ->  programa.py"
    echo "#     crear archivo apuntes            ->  apuntes  (sin extension)"
    echo "#"
    echo "# Vienen de fabrica las corrientes (texto, documento, hoja de"
    echo "# calculo, imagen, foto, audio, video, comprimido, guion, python,"
    echo "# pagina web, datos, marcas, libro, subtitulos, base de datos,"
    echo "# configuracion, registro). Las TUYAS se anaden aqui:"
    echo "#"
    echo "#     EXTENSIONES_HABLADAS = {\"maqueta\": \"kra\", \"partitura\": \"mscz\"}"
    echo "#"
    echo "# AVISO: tambien se puede deletrear (\"apuntes te equis te\"), pero el"
    echo "# reconocedor casi nunca acierta una ristra de letras -- las junta y"
    echo "# las convierte en palabras. Usa el NOMBRE siempre que puedas, y si"
    echo "# la extension que necesitas no tiene, dale uno aqui."
  } > config_local.py
  ok "config_local.py creado"
fi

# ---------------------------------------------------------------------------
# 8. Modo remoto: certificados, contraseña y filtrado por IP
# ---------------------------------------------------------------------------
azul "== Acceso remoto (móvil) =="
if [ -f webapp_config.json ] && [ -f webapp_cert.pem ]; then
  ok "ya configurado: NO se toca"
else
  # Ya se preguntó en el cuestionario inicial; al actualizar sin config se
  # pregunta aquí, que es la única vía que queda.
  if [ "$MODO" != "instalación nueva" ]; then
    preguntar_si "¿Vas a usar el móvil como micrófono/mando?" s && QUIERE_REMOTO=1
  fi
  if [ "$QUIERE_REMOTO" = "1" ]; then
    IP=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' | head -1)
    read -rp "   IP de este PC en tu red [$IP]: " IP2; IP="${IP2:-$IP}"
    if [ ! -f webapp_cert.pem ]; then
      openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout webapp_key.pem -out webapp_cert.pem \
        -subj "/CN=VoiceController" \
        -addext "subjectAltName=DNS:localhost,IP:$IP" >/dev/null 2>&1 \
        && ok "certificado HTTPS generado para $IP" || err "fallo generando el certificado"
    fi
    ARGS_USR=(); [ -n "${USUARIO:-}" ] && ARGS_USR=(--user "$USUARIO")
    ./venv/bin/python webapp/gen_config.py --host "$IP" "${ARGS_USR[@]}" \
      || avi "configura la contraseña a mano con webapp/gen_config.py"
    echo
    echo
    echo "   FILTRADO POR IP (opcional, y con trampa):"
    echo "   Solo tiene sentido si vas a usar la app de Android desde fuera."
    echo "   Deja entrar SOLO a los aparatos que digas; los demas ni llegan a"
    echo "   la pantalla de contrasena. Es una capa MAS, no un sustituto de"
    echo "   ella: una IP se puede falsificar dentro de una red local."
    echo
    echo "   La trampa: si pones una IP fija y luego cambias de movil, o tu"
    echo "   router reparte por DHCP y le toca otra, la aplicacion dejara de"
    echo "   responderte SIN NINGUN MENSAJE. Se conecta, no pasa nada, y no"
    echo "   hay forma de adivinar por que. Ponla fija solo si te la asigna"
    echo "   siempre la misma tu VPN; si no, usa un rango."
    if preguntar_si "¿Activar filtrado por IP?" n; then
      echo "   Formatos que valen:"
      echo "     10.8.0.2                 una sola, fija"
      echo "     10.8.0.10-10.8.0.50    un rango, con guion"
      echo "     10.8.0.10-50             el mismo rango, abreviado"
      echo "     10.8.0.0/24              el mismo rango, en CIDR"
      read -rp "   IPs o rangos permitidos (separados por espacios): " IPS
      ./venv/bin/python tools/poner_ips_permitidas.py $IPS
    else
      echo "   Sin filtrar: cualquier aparato de la red podra intentar entrar,"
      echo "   y necesitara la contrasena. Se activa mas tarde poniendo"
      echo "   WEBAPP_ALLOWED_IPS en config_local.py."
    fi
  fi
fi

# ---------------------------------------------------------------------------
# 9. App de Android
# ---------------------------------------------------------------------------
# La APK viene DENTRO del paquete, ya construida y firmada. Es la genérica:
# no lleva dirección ni certificado dentro, así que vale para cualquier
# instalación, Linux o Windows. Hasta el 12-sep-2026 se construía aquí, y eso
# pedía el SDK de Android y un JDK 21 que casi nadie tiene.
#
# Se sigue diciendo dónde está y qué hacer con ella: quien no conozca el
# proyecto tiene el fichero y ninguna pista de que hay que pasarlo al teléfono.
APK="$DESTINO/VoiceController.apk"
if [ "$QUIERE_REMOTO" = "1" ] && [ -f "$APK" ]; then
  azul "== App de Android =="
  echo "   La app del móvil está en:"
  echo "     $APK"
  echo
  echo "   Para instalarla, cualquiera de las dos:"
  echo "     - Cópiala al teléfono (cable, correo, o la nube que uses) y"
  echo "       ábrela desde allí. Android pedirá permiso para instalar"
  echo "       aplicaciones de fuera de la tienda: hay que dárselo."
  echo "     - O con el cable y la depuración USB activada:"
  echo "         adb install \"$APK\""
  echo
  echo "   Al abrirla pide la dirección de este ordenador (la que ha dicho"
  echo "   este instalador) y, la primera vez, enseña un código de doce"
  echo "   cifras. Aquí, di \"código de emparejamiento\": si los dos números"
  echo "   coinciden, es tu ordenador."
elif [ "$QUIERE_REMOTO" = "1" ]; then
  avi "este paquete no trae la app de Android (VoiceController.apk)"
  echo "   El móvil funciona igual abriendo la dirección del PC en Firefox."
elif [ "$MODO" != "instalación nueva" ] && [ -f "$APK" ]; then
  echo "   La app del móvil de esta versión: $APK"
  echo "   Si la tienes en el teléfono, se instala encima y no pierde nada."
fi

# ---------------------------------------------------------------------------
# 10. Resumen y siguientes pasos
# ---------------------------------------------------------------------------
azul "== Listo =="
echo "   Arrancar:  ./run.sh"
if [ "$QUIERE_VOZ" = "1" ] && [ ! -f config/speaker_profile.json ]; then
  echo
  avi "Falta enrolar tu voz: sin ella el santo y seña no puede funcionar."
  echo "   Son unos 4 minutos, manos libres."
  if preguntar_si "¿Lo hacemos ahora?" s; then
    ./venv/bin/python tools/speaker_calibration.py enroll \
      && ./venv/bin/python tools/speaker_calibration.py login \
      && ./venv/bin/python tools/speaker_calibration.py export --force \
      && ok "voz enrolada y umbral calibrado"
    echo
    avi "Copia el UMBRAL que te ha propuesto a config_local.py:"
    echo "     VOICE_LOGIN_THRESHOLD = <el número>"
  else
    echo "   Cuando quieras:"
    echo "     ./venv/bin/python tools/speaker_calibration.py enroll"
    echo "     ./venv/bin/python tools/speaker_calibration.py login"
    echo "     ./venv/bin/python tools/speaker_calibration.py export"
  fi
fi
echo "   El perfil de voz del MÓVIL se graba solo la primera vez que lo conectes."

# Se apunta la version instalada, para saber la proxima vez de donde se
# viene. Al final a proposito: si algo falla antes, no se apunta una version
# que no llego a instalarse.
[ -n "$VER_NUEVA" ] && echo "$VER_NUEVA" > "$DESTINO/.instalado"
