#!/usr/bin/env bash
# ===========================================================================
#  Deja VoiceController como recien descomprimido. Sin borrar los modelos.
# ===========================================================================
#  PARA QUE SIRVE
#
#  Para probar una instalacion desde cero sin volver a descargar 4 GB de
#  modelos de voz. Borra todo lo que creo el instalador -- el entorno de
#  Python, tus ajustes, el perfil de voz, los certificados -- y DEJA la
#  carpeta vosk_models/, porque el instalador se salta la descarga cuando
#  el modelo ya esta ("ya estaba").
#
#  Asi la siguiente instalacion es limpia de verdad: vuelve a preguntarte el
#  microfono, la voz y el santo y seña, pero tarda un minuto en vez de una
#  hora.
#
#  NO borra el codigo: esta carpeta sigue siendo el proyecto. Si lo que
#  quieres es que no quede nada, borra la carpeta entera a mano -- todo
#  VoiceController vive aqui dentro, no toca el sistema.
#
#  Uso:
#     ./desinstalar.sh              pregunta antes de nada
#     ./desinstalar.sh --simular    solo dice lo que haria, no borra
#     ./desinstalar.sh --con-modelos  borra TAMBIEN los modelos (4 GB)
#     ./desinstalar.sh --si         no pregunta (para scripts)
# ===========================================================================
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"

ok(){  printf "  \033[32m✓\033[0m %s\n" "$*"; }
avi(){ printf "  \033[33m!\033[0m %s\n" "$*"; }
err(){ printf "  \033[31m✗\033[0m %s\n" "$*"; }
azul(){ printf "\n\033[36m%s\033[0m\n" "$*"; }

SIMULAR=0; CON_MODELOS=0; SIN_PREGUNTAR=0
for a in "$@"; do
  case "$a" in
    --simular|-n) SIMULAR=1 ;;
    --con-modelos) CON_MODELOS=1 ;;
    --si|-y) SIN_PREGUNTAR=1 ;;
    --help|-h) sed -n '2,26p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) err "opcion desconocida: $a"; exit 1 ;;
  esac
done

# Lo que creo el instalador. El codigo NO esta en esta lista.
#
# Se separa en dos grupos a proposito: lo de arriba se puede rehacer en un
# minuto; lo de abajo son DATOS TUYOS y se avisa aparte antes de borrarlos.
REHACIBLES=(venv __pycache__ dist .instalado webapp_uploads
            voicecontroller.log voicecontroller.log.1
            webapp/static/board/tablero.png webapp/static/board/casilla.png
            webapp/static/board/zoom_out.png webapp/static/board/foco.png
            webapp/static/board/vc.png)
TUYOS=(config_local.py commands.json prosody.json corrections.json
       window_names.json webapp_config.json webapp_cert.pem webapp_key.pem
       config/speaker_profile.json)
MODELOS=(vosk_models piper_voices)

tam(){ du -sh "$1" 2>/dev/null | cut -f1; }

# FRENO: esto NO es para la carpeta de desarrollo.
#
# El script vive dentro del proyecto, asi que esta a un comando de distancia
# de borrarle a uno su propio perfil de voz, sus certificados y sus ajustes
# mientras trabaja. Si hay un .git al lado, esto es el repositorio y casi
# seguro no es lo que se quiere.
if [ -d .git ] && [ "${VC_AUN_ASI:-0}" != "1" ]; then
  err "Esto parece el REPOSITORIO DE DESARROLLO (hay un .git aqui al lado),"
  echo "     no una instalacion. Si lo borras, pierdes tu config_local.py, tu"
  echo "     perfil de voz y tus certificados de trabajo."
  echo
  echo "     Este script es para la maquina donde se PRUEBA la instalacion."
  echo "     Si aun asi sabes lo que haces:"
  echo
  echo "         VC_AUN_ASI=1 ./desinstalar.sh"
  exit 1
fi

azul "== Lo que se va a borrar =="
hay=0
for f in "${REHACIBLES[@]}"; do
  [ -e "$f" ] && { echo "     $f  ($(tam "$f"))"; hay=1; }
done
echo
echo "  Y esto son AJUSTES TUYOS -- se pierden:"
for f in "${TUYOS[@]}"; do
  [ -e "$f" ] && { echo "     $f  ($(tam "$f"))"; hay=1; }
done
if [ "$CON_MODELOS" = "1" ]; then
  echo
  avi "Y TAMBIEN LOS MODELOS. Volver a descargarlos lleva mucho rato:"
  for f in "${MODELOS[@]}"; do
    [ -e "$f" ] && echo "     $f  ($(tam "$f"))"
  done
else
  echo
  ok "Los modelos SE QUEDAN (vosk_models, piper_voices): $(tam vosk_models 2>/dev/null || echo 0)"
  echo "     La siguiente instalacion los encontrara y no los descargara."
fi

if [ "$hay" = "0" ]; then
  azul "No hay nada que borrar: esta carpeta ya esta sin instalar."
  exit 0
fi

if [ "$SIMULAR" = "1" ]; then
  azul "SIMULACION: no se ha borrado nada."
  exit 0
fi

if [ "$SIN_PREGUNTAR" = "0" ]; then
  echo
  read -r -p "  Escribe BORRAR para continuar: " RESP
  [ "$RESP" = "BORRAR" ] || { azul "Cancelado. No se ha tocado nada."; exit 0; }
fi

azul "== Borrando =="
n=0
borra(){ [ -e "$1" ] || return; rm -rf "$1" && { ok "$1"; n=$((n+1)); } || err "no se pudo borrar $1"; }
for f in "${REHACIBLES[@]}" "${TUYOS[@]}"; do borra "$f"; done
[ "$CON_MODELOS" = "1" ] && for f in "${MODELOS[@]}"; do borra "$f"; done
find . -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null

azul "== Lo que NO se va =="
echo "  Borrar esta carpeta quita el programa entero: no escribe fuera de"
echo "  ella -- ni servicios, ni arranque automatico, ni /etc."
echo
echo "  Sobreviven solo las DEPENDENCIAS del sistema, que las instalaste tu:"
echo "  ydotool, kdotool y spectacle, con los permisos que les diste. Quitalas"
echo "  o dejalas segun te convenga."

azul "== Listo: $n cosas borradas =="
echo "  Para volver a instalar:   ./install.sh"
if [ "$CON_MODELOS" = "0" ]; then
  echo "  Los modelos estan puestos, asi que no habra descargas."
fi
