#!/usr/bin/env bash
# ===========================================================================
#  Arranca VoiceController en segundo plano, de verdad
# ===========================================================================
#  La versión anterior era:   nohup './run.sh' > /dev/null 2>&1 &
#  y fallaba por tres cosas:
#
#   1. Sin `setsid`, el proceso se queda en el grupo de la terminal y se cae
#      al cerrar Konsole. `nohup` solo protege de SIGHUP, no de eso.
#   2. Con la salida a /dev/null, si algo falla no hay forma de saber qué.
#      Y Python la GUARDA EN UN BÚFER al redirigirla a fichero, así que
#      tampoco basta con redirigir: hace falta `-u`.
#   3. Sin guardar el PID no hay manera limpia de pararla. Y `pkill -f`
#      es peligroso: el patrón casa también con la línea de comando del
#      propio script que lo ejecuta, y se mata a sí mismo.
#
#  Uso:
#     ./silentRun.sh              arranca con ventana, y espera a que esté lista
#     ./silentRun.sh --servicio   arranca con la ventana OCULTA (--as-service)
#     ./silentRun.sh --parar      la cierra
#     ./silentRun.sh --estado     dice si corre, y por dónde sirve el móvil
#     ./silentRun.sh --registro   sigue el registro en vivo (Ctrl+C para salir)
# ===========================================================================
set -uo pipefail
cd "$(dirname "$(readlink -f "$0")")"

PIDF="/tmp/voicecontroller.pid"
LOG="/tmp/voicecontroller.log"
PIDF_CAP="/tmp/voicecontroller-capturas.pid"
CAPTURAS_DIR="$(pwd)/capturas_manual"
ESPERA_MAX=600          # cargar los dos modelos puede tardar varios minutos

ok(){  printf "  \033[32m✓\033[0m %s\n" "$*"; }
avi(){ printf "  \033[33m!\033[0m %s\n" "$*"; }
err(){ printf "  \033[31m✗\033[0m %s\n" "$*"; }

corriendo(){
  [ -f "$PIDF" ] || return 1
  local p; p="$(cat "$PIDF" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && grep -q "main.py" "/proc/$p/cmdline" 2>/dev/null
}

# --- Guardado automatico de capturas del GUI (para el manual) --------------
#
# El programa ya escribe webapp/static/board/vc.png con la ventana tal como
# se ve, pero la SOBRESCRIBE cada pocos segundos. tools/guardar_capturas.py
# se queda mirandola y guarda una copia con la hora en el nombre cada vez que
# el contenido cambia -- si no, la del estado anterior se pierde al cambiar
# de pantalla, y con un solo nombre de destino quedaria solo la ultima.
capturas_corriendo(){
  [ -f "$PIDF_CAP" ] || return 1
  local p; p="$(cat "$PIDF_CAP" 2>/dev/null)"
  [ -n "$p" ] && kill -0 "$p" 2>/dev/null && grep -q "guardar_capturas" "/proc/$p/cmdline" 2>/dev/null
}

arrancar_capturas(){
  local vista="${1:-}"
  if capturas_corriendo; then
    avi "el guardado de capturas ya estaba en marcha"
    return
  fi
  # Es de desarrollo (capturas para el manual) y no viaja en el paquete: en
  # una instalacion normal no esta, y sin esto se arrancaria un proceso que
  # muere al instante sin decir nada.
  if [ ! -f tools/guardar_capturas.py ]; then
    avi "el guardado de capturas es de desarrollo: esta instalacion no lo trae"
    return
  fi
  mkdir -p "$CAPTURAS_DIR"
  setsid nohup ./venv/bin/python3 -u tools/guardar_capturas.py "$CAPTURAS_DIR" "$vista" \
    > /tmp/voicecontroller-capturas.log 2>&1 < /dev/null &
  echo $! > "$PIDF_CAP"
  if [ -n "$vista" ]; then
    ok "guardando la vista '$vista' en $CAPTURAS_DIR"
  else
    ok "guardando todas las vistas en $CAPTURAS_DIR"
  fi
}

parar_capturas(){
  if capturas_corriendo; then
    kill "$(cat "$PIDF_CAP")" 2>/dev/null
    rm -f "$PIDF_CAP"
    ok "guardado de capturas detenido"
  fi
  rm -f "$PIDF_CAP"
}

case "${1:-}" in
  --capturas|--captura-foco|--captura-mover|--captura-casilla|--captura-tablero)
      # Sin modificador el arranque es el de siempre. Con uno de estos, ademas
      # se guarda una copia del GUI cada vez que cambie -- para ir haciendo el
      # manual sin perder ningun estado por el camino.
      #
      # Los nombres son los que se dicen HABLANDO, no los de dentro: la vista
      # que el codigo llama "zoom_out" es la del comando "mover".
      case "$1" in
        --captura-foco)     VISTA_CAPTURA="foco" ;;
        --captura-mover)    VISTA_CAPTURA="zoom_out" ;;
        --captura-casilla)  VISTA_CAPTURA="cell" ;;
        --captura-tablero)  VISTA_CAPTURA="overview" ;;
        *)                  VISTA_CAPTURA="" ;;
      esac
      if corriendo; then
        arrancar_capturas "$VISTA_CAPTURA"
        exit 0
      fi
      CON_CAPTURAS=1
      set --
      ;;
  --servicio|--as-service)
      # Modo servicio: la MISMA ventana de siempre, pero arrancada oculta.
      # Se muestra diciendo "monitor" o desde la bandeja del sistema.
      #
      # Lo demas del script vale igual para los dos modos y no hace falta
      # tocarlo: --parar, --estado y --registro van por el PID y por
      # "main.py" en la linea de comando, y los dos modos NUNCA corren a la
      # vez (el propio script lo impide mas abajo).
      ARGS_MAIN="--as-service"
      set --
      ;;
  --sin-capturas)
      parar_capturas
      exit 0
      ;;
  --parar)
      if corriendo; then
        p="$(cat "$PIDF")"
        kill "$p" 2>/dev/null
        for _ in $(seq 1 20); do kill -0 "$p" 2>/dev/null || break; sleep 1; done
        kill -0 "$p" 2>/dev/null && { kill -9 "$p" 2>/dev/null; avi "hubo que forzarla"; }
        rm -f "$PIDF"; ok "cerrada"
      else
        avi "no estaba corriendo"
      fi
      exit 0 ;;
  --estado)
      if corriendo; then
        p="$(cat "$PIDF")"
        # El modo se lee de la propia linea de comando del proceso, no de un
        # fichero aparte: asi no puede quedarse desfasado si algo va mal.
        if tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null | grep -q -- "--as-service"; then
          MODO="servicio (ventana oculta; di 'monitor' o usa la bandeja)"
        else
          MODO="con ventana"
        fi
        ok "corriendo en modo $MODO"
        ok "PID $p, $(( $(awk '{print $2}' "/proc/$p/statm" 2>/dev/null || echo 0) * 4096 / 1048576 )) MB"
        grep -m1 "webapp\] sirviendo" "$LOG" 2>/dev/null | sed 's/^/    /'
        grep -m1 "opening input" "$LOG" 2>/dev/null | sed 's/^/    /'
      else
        avi "no está corriendo"
      fi
      exit 0 ;;
  --registro) exec tail -f "$LOG" ;;
  "") ;;
  *) sed -n '2,25p' "$0"; exit 0 ;;
esac

# --- comprobaciones antes de arrancar --------------------------------------
if corriendo; then
  avi "ya está corriendo (PID $(cat "$PIDF")). Párala antes:  $0 --parar"
  exit 1
fi
[ -x venv/bin/python3 ] || { err "no encuentro venv/bin/python3 -- ¿instalada?"; exit 1; }

# La GUI necesita la sesión gráfica. Si se lanza desde un sitio que no la
# tiene (cron, SSH sin escritorio), Qt falla con un error poco claro; mejor
# decirlo aquí.
if [ -z "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
  err "no hay sesión gráfica (ni WAYLAND_DISPLAY ni DISPLAY)."
  echo "     Esto abre una ventana: hay que lanzarlo desde tu escritorio."
  exit 1
fi

# --- arranque ---------------------------------------------------------------
[ -f "$LOG" ] && mv -f "$LOG" "$LOG.anterior"
# setsid la separa de esta terminal; -u vuelca la salida al momento.
setsid nohup ./venv/bin/python3 -u main.py ${ARGS_MAIN:-} > "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"
sleep 3
corriendo || { err "no llegó a arrancar. Mira: $LOG"; tail -5 "$LOG"; rm -f "$PIDF"; exit 1; }
if [ -n "${ARGS_MAIN:-}" ]; then
  ok "arrancando en modo servicio, con la ventana oculta (PID $(cat "$PIDF"))"
else
  ok "arrancando (PID $(cat "$PIDF"))"
fi

echo "  cargando los modelos de voz, puede tardar varios minutos..."
for _ in $(seq 1 $((ESPERA_MAX / 5))); do
  sleep 5
  grep -q "opening input" "$LOG" 2>/dev/null && break
  corriendo || { err "se cerró durante el arranque. Últimas líneas:"; tail -8 "$LOG"; exit 1; }
done

if grep -q "opening input" "$LOG" 2>/dev/null; then
  ok "lista"
  [ -n "${ARGS_MAIN:-}" ] && \
    echo "    la ventana esta oculta: di 'monitor' o usa la bandeja para verla"
  grep -m1 "webapp\] sirviendo" "$LOG" | sed 's/^/    /'
  grep -m1 "opening input" "$LOG" | sed 's/^/    /'
else
  avi "sigue cargando tras $ESPERA_MAX s; no ha fallado, pero tarda más de lo previsto"
fi
if [ "${CON_CAPTURAS:-0}" = "1" ]; then
  arrancar_capturas "${VISTA_CAPTURA:-}"
fi

echo
echo "     arranque:  $0             (con ventana)"
echo "                $0 --servicio  (ventana oculta)"
echo "     estado:    $0 --estado"
echo "     registro:  $0 --registro"
echo "     parar:     $0 --parar"
echo "     capturas:  $0 --captura-foco | --captura-mover"
echo "                $0 --captura-casilla | --captura-tablero"
echo "                $0 --capturas        (todas las vistas)"
echo "                $0 --sin-capturas    (dejar de guardar)"
