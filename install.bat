@echo off
REM ===========================================================================
REM  VoiceController -- instalador para Windows
REM ===========================================================================
REM  Fichero aparte del install.sh a proposito: no se pisan entre ellos y cada
REM  uno puede hablar de lo suyo.
REM
REM  AVISO IMPORTANTE, leelo antes de perder el tiempo:
REM  ESTADO (probado el 30-ago-2026 en una VM con Windows 10):
REM  (teclado, raton, capturas, ventanas) esta escrita en backends\windows.py
REM  La capa que toca el sistema (backends\windows.py) SI se ha
REM  ejecutado y verificado en Windows 10: teclado con acentos y enes,
REM  raton, scroll, capturas, ventanas, el tablero de casillas y la
REM  interfaz. El reconocimiento da el mismo resultado que en Linux.
REM
REM  Sin comprobar a fondo: el audio del asistente (TTS), que depende
REM  de como este configurada la salida de sonido de cada maquina.
REM ===========================================================================
setlocal EnableDelayedExpansion
REM --- modo desatendido -------------------------------------------------
REM Con VC_AUTO=1 no se pregunta nada: hace falta para reinstalar sin
REM estar delante (pruebas, reinstalaciones repetidas, instalar en varias
REM maquinas). Las respuestas se dan por variables de entorno:
REM   VC_AUTO=1        no preguntar
REM   VC_MIC=<indice>  microfono (vacio = el del sistema)
REM   VC_VOZ=femenina|masculina
if "%VC_AUTO%"=="1" echo   [modo desatendido: no se preguntara nada]
echo.
echo ================================================================
echo   VoiceController -- instalacion en Windows
echo ================================================================
echo.
  echo   Probado:  dictado, teclado, raton, capturas, ventanas, tablero
  echo   Sin probar a fondo: el audio del asistente (TTS)
echo.
if "%VC_AUTO%"=="1" (set "SEGUIR=s") else (set /p SEGUIR="  Continuar de todas formas? [s/N] ")
if /i not "%SEGUIR%"=="s" exit /b 0

REM --- Python -----------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
  echo   [X] No encuentro Python. Instalalo desde python.org y marca
  echo       "Add python.exe to PATH" durante la instalacion.
  pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   [OK] Python %PYVER%

REM --- Paquete y destino ------------------------------------------------
REM
REM EL PAQUETE es la carpeta donde esta este install.bat. EL DESTINO es donde
REM queda instalado. Pueden ser la misma (descomprimir encima y ejecutar) o
REM distintas (descomprimir en Descargas y actualizar la instalacion que ya
REM hay en otra carpeta).
REM
REM Hasta el 12-sep-2026 este instalador NO COPIABA NADA: hacia cd al
REM destino y comprobaba alli. Con destino distinto del paquete, buscaba los
REM ficheros nuevos en la instalacion VIEJA y decia "el paquete esta
REM incompleto" -- con el paquete completo al lado. Lo vio pipataki actualizando
REM en la VM. install.sh siempre copio; este no, y nadie lo habia notado
REM porque siempre se habia actualizado descomprimiendo encima.
set "PKG=%~dp0"
set "PKG=%PKG:~0,-1%"
if not exist "%PKG%\main.py" (
  echo.
  echo   [X] Este install.bat no esta dentro de su paquete: a su lado no hay
  echo       main.py. Pasa si se copia el install.bat SOLO a otra carpeta.
  echo.
  echo       Descomprime el zip entero y ejecuta el install.bat que hay DENTRO
  echo       de la carpeta que sale ^(VoiceController-x.y.z^).
  echo.
  if not "%VC_AUTO%"=="1" pause
  exit /b 1
)

REM --- ¿Está el paquete completo? ---------------------------------------
REM
REM POR QUE SE COMPRUEBA, y no es paranoia: el 6-sep-2026 se actualizo una
REM instalacion real y NO ARRANCABA. Faltaba la carpeta habilidades\, que
REM nunca habia llegado, y el fallo salio DESPUES de veinte minutos de
REM instalacion y sin pista de que el paquete venia incompleto.
REM
REM Se mira EL PAQUETE, no el destino -- que es lo que dice el mensaje -- y
REM ANTES de instalar dependencias: si esta cojo, mejor saberlo en un
REM segundo que tras cinco minutos de pip.
REM
REM LA MISMA LISTA que ESENCIALES en tools/hacer_paquete.sh: si se separan,
REM el paquete pasaria una comprobacion y fallaria la otra.
echo.
echo   Comprobando que el paquete esta completo...
set "FALTA="
for %%f in (main.py gui.py command_router.py actions.py board.py config.py
            voice_recognizer.py recognizer_worker.py tts.py textos.py
            numbers_es.py numbers_en.py math_notation.py math_notation_es.py
            nombre_archivo.py carpetas.py
            math_notation_en.py zones.py paths.py runlog.py prosody.py
            corrections.py keyboard_keys.py input_action.py grid_vc.py
            microphone_manager.py speaker_id.py window_names.py version.py
            commands.default.json prosody.default.json
            labels.json) do (
  if not exist "%PKG%\%%f" (
    echo     [X] falta %%f
    set "FALTA=1"
  )
)
for %%d in (backends habilidades tools webapp webapp\static) do (
  REM \* en vez de \ al final: una barra pegada a la comilla lia a cmd.
  if not exist "%PKG%\%%d\*" (
    echo     [X] falta la carpeta %%d
    set "FALTA=1"
  )
)
if defined FALTA (
  echo.
  echo   [X] EL PAQUETE ESTA INCOMPLETO.
  echo       Faltan ficheros que la aplicacion necesita para arrancar. No
  echo       tiene sentido seguir: se instalaria algo que no funciona, y el
  echo       fallo apareceria mucho despues y sin explicacion.
  echo.
  echo       Paquete revisado: %PKG%
  echo       Consigue el paquete completo y vuelve a ejecutar el instalador.
  if not "%VC_AUTO%"=="1" pause
  exit /b 1
)
echo     [OK] estan todos los ficheros necesarios

REM El destino. Por defecto, donde esta el paquete -- lo de siempre. Para
REM actualizar otra instalacion, se escribe su ruta. VC_DESTINO lo da sin
REM preguntar (modo desatendido).
echo.
if defined VC_DESTINO (
  set "DESTINO=%VC_DESTINO%"
) else if "%VC_AUTO%"=="1" (
  set "DESTINO=%PKG%"
) else (
  echo   Donde instalar. Intro = aqui mismo, donde lo has descomprimido.
  echo   Para ACTUALIZAR una instalacion que tengas en otra carpeta, escribe
  echo   su ruta: se copia el codigo nuevo y tus ajustes no se tocan.
  set /p DESTINO="  Ruta de instalacion [%PKG%]: "
)
if "!DESTINO!"=="" set "DESTINO=%PKG%"
for %%i in ("!DESTINO!") do set "DESTINO=%%~fi"
if "!DESTINO:~-1!"=="\" set "DESTINO=!DESTINO:~0,-1!"
if not exist "!DESTINO!\" mkdir "!DESTINO!"
echo   [OK] Paquete: %PKG%
echo   [OK] Destino: !DESTINO!

REM --- Copiar el codigo, respetando lo personal -------------------------
REM
REM Solo si destino y paquete son carpetas distintas. La lista de lo que NO
REM se copia es la de PERSONALES en install.sh: si se toca una, se toca la
REM otra.
REM
REM Antes de copiar se guarda una copia de lo que habia en .update_backups\:
REM la lista de personales es manual y por tanto olvidable, y si algun dia
REM falta un fichero en ella, lo pisado se puede recuperar.
REM
REM Sin robocopy /MIR a proposito: borraria de la instalacion todo lo que no
REM venga en el paquete, incluidos ficheros del usuario que no esten en la
REM lista. Los ficheros viejos que ya no se usan se quedan; no estorban.
if /i not "!DESTINO!"=="%PKG%" (
  if exist "!DESTINO!\main.py" (
    set "SELLO="
    for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss" 2^>nul') do set "SELLO=%%t"
    REM Sin PowerShell (o si falla) el sello NO puede quedar vacio: la copia
    REM caeria en .update_backups\ a secas y la siguiente actualizacion la
    REM mezclaria con la suya. %RANDOM% no ordena por fecha, pero separa.
    if not defined SELLO set "SELLO=copia_!RANDOM!!RANDOM!"
    echo   Guardando copia de lo que habia en .update_backups\!SELLO! ...
    robocopy "!DESTINO!" "!DESTINO!\.update_backups\!SELLO!" /E /XD venv vosk_models piper_voices __pycache__ .update_backups .backups webapp_uploads dist modelos_offline /XF *.pyc /NFL /NDL /NJH /NJS /NP >nul
    if errorlevel 8 (
      echo   [X] No se pudo hacer la copia de seguridad. No se copia nada.
      if not "%VC_AUTO%"=="1" pause
      exit /b 1
    )
  )
  echo   Copiando el codigo nuevo ^(tus ajustes no se tocan^)...
  robocopy "%PKG%" "!DESTINO!" /E /XD venv vosk_models piper_voices __pycache__ .git .backups .update_backups dist logs webapp_uploads /XF config_local.py webapp_config.json webapp_cert.pem webapp_key.pem speaker_profile.json speaker_profile_network.json corrections.json commands.json prosody.json window_names.json speaker_calibration_data.json .instalado *.pyc /NFL /NDL /NJH /NJS /NP >nul
  if errorlevel 8 (
    echo   [X] Fallo copiando el codigo al destino.
    if not "%VC_AUTO%"=="1" pause
    exit /b 1
  )
  echo   [OK] codigo copiado
)
cd /d "!DESTINO!"

REM --- Entorno virtual --------------------------------------------------
if not exist venv (
  echo   Creando entorno virtual...
  python -m venv venv || (echo   [X] Fallo creando el venv & pause & exit /b 1)
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1

REM --- Dependencias -----------------------------------------------------
echo   Instalando dependencias (unos minutos)...
REM  python-ydotool se salta: es especifico de Linux.
findstr /v /i /b /c:"python-ydotool" requirements.txt > requirements.win.txt
REM Si pip falla se REINTENTA sin cache: el fallo tipico es
REM "Permission denied" sobre %LOCALAPPDATA%\pip\cache, y con
REM --no-cache-dir se esquiva sin tocar permisos.
REM Y si aun asi falla, se ABORTA: seguir adelante significaria
REM descargar 1,8 GB de modelo sobre una instalacion inservible.
pip install -q -r requirements.win.txt
if errorlevel 1 (
  echo   [aviso] pip fallo; reintentando sin cache...
  pip install -q --no-cache-dir -r requirements.win.txt
  if errorlevel 1 (
    echo   [X] No se pudieron instalar las dependencias. Se aborta:
    echo       sin ellas no arranca nada, y descargar los modelos
    echo       ahora seria tirar 1,8 GB para nada.
    del requirements.win.txt 2>nul
    if not "%VC_AUTO%"=="1" pause
    exit /b 1
  )
)
del requirements.win.txt
echo   Instalando la capa de Windows...
pip install -q pydirectinput mss pygetwindow piper-tts
if errorlevel 1 (
  echo   [aviso] reintentando sin cache...
  pip install -q --no-cache-dir pydirectinput mss pygetwindow piper-tts
  if errorlevel 1 (
    echo   [X] Falta la capa de Windows. Se aborta.
    if not "%VC_AUTO%"=="1" pause
    exit /b 1
  )
)

REM --- Dependencias del sistema -----------------------------------------
REM Mismo criterio que install.sh: NO se instala nada a escondidas. Alli se
REM muestra el "sudo apt install ..." y se pregunta; aqui, si hay winget se
REM OFRECE ejecutarlo, y si no se da el enlace exacto. En los dos casos se
REM puede seguir sin ello: ninguna de las dos es imprescindible para todo.
set "FALTAN="

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo   [X] ffmpeg  -- sin el, el MICROFONO DEL MOVIL no se puede decodificar
  set "FALTAN=!FALTAN! ffmpeg"
  where winget >nul 2>&1
  if errorlevel 1 (
    echo       Descargalo de https://www.gyan.dev/ffmpeg/builds/ y anade su
    echo       carpeta bin al PATH.
  ) else (
    set "R="
    if not "%VC_AUTO%"=="1" set /p R="      Instalarlo ahora con winget? [s/N] "
    if /i "!R!"=="s" (
      winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
    ) else (
      echo       Cuando quieras:  winget install Gyan.FFmpeg
    )
  )
) else (
  echo   [OK] ffmpeg
)

REM onnxruntime (lo usa Piper para la voz) necesita el runtime de Visual C++,
REM que Windows NO trae de serie. Sin el, piper-tts se instala pero revienta
REM al importarlo con "DLL load failed" y el usuario se queda sin voz sin
REM saber por que.
python -c "import onnxruntime" >nul 2>&1
if errorlevel 1 (
  echo   [X] Runtime de Visual C++  -- sin el NO habra voz del asistente
  set "FALTAN=!FALTAN! vcredist"
  where winget >nul 2>&1
  if errorlevel 1 (
    echo       Descargalo de https://aka.ms/vs/17/release/vc_redist.x64.exe
  ) else (
    set "R="
    if not "%VC_AUTO%"=="1" set /p R="      Instalarlo ahora con winget? [s/N] "
    if /i "!R!"=="s" (
      winget install --id Microsoft.VCRedist.2015+.x64 -e --accept-source-agreements --accept-package-agreements
    ) else (
      echo       Cuando quieras:  winget install Microsoft.VCRedist.2015+.x64
    )
  )
) else (
  echo   [OK] runtime de Visual C++
)

if not "!FALTAN!"=="" (
  echo.
  echo   Falta:!FALTAN!  -- se puede seguir, pero esas partes no funcionaran.
  if not "%VC_AUTO%"=="1" (
    set /p R="  Continuar de todas formas? [s/N] "
    if /i not "!R!"=="s" exit /b 1
  )
)

REM --- ¿Instalacion nueva o actualizacion? ------------------------------
REM
REM La version instalada se guarda en .instalado, que NO viaja en el zip
REM (igual que config_local.py). Asi sobrevive a descomprimir la version
REM nueva encima, y se puede decir de donde se viene -- que es justo lo que
REM no se sabia hasta ahora: al actualizar, el instalador no distinguia una
REM instalacion nueva de una de hace tres versiones.
for /f "tokens=2 delims==" %%v in ('findstr /b "__version__" version.py 2^>nul') do set "VER_NUEVA=%%~v"
set "VER_NUEVA=%VER_NUEVA: =%"
set "VER_NUEVA=%VER_NUEVA:"=%"
set "VER_VIEJA="
if exist .instalado for /f "usebackq delims=" %%v in (".instalado") do set "VER_VIEJA=%%v"
echo.
if defined VER_VIEJA (
  if "%VER_VIEJA%"=="%VER_NUEVA%" (
    echo   Reinstalando la version %VER_NUEVA%
  ) else (
    echo   ACTUALIZANDO de la %VER_VIEJA% a la %VER_NUEVA%
    echo     Tus ajustes se conservan: config_local.py no se toca, y
    echo     commands.json se fusiona en vez de pisarse.
  )
) else (
  echo   Instalacion NUEVA de la version %VER_NUEVA%
)


REM --- Modelos de voz ---------------------------------------------------
REM
REM MODELOS PREDESCARGADOS. Si existe la carpeta modelos_offline junto al
REM instalador, los .zip que haya dentro se usan en vez de bajarlos. Sirve
REM para instalar sin red, y sobre todo para grabar el videotutorial sin
REM tener veinte minutos de barra de descarga.
REM
REM Los nombres tienen que ser exactamente estos:
REM     modelos_offline\vosk-model-es-0.42.zip
REM     modelos_offline\vosk-model-small-en-us-0.15.zip
REM     modelos_offline\vosk-model-spk-0.4.zip
set "MODELOS_OFFLINE=%~dp0modelos_offline"
if exist "%MODELOS_OFFLINE%" echo   Se usaran los modelos de %MODELOS_OFFLINE%

if not exist vosk_models mkdir vosk_models
if not exist vosk_models\vosk-model-es-0.42 (
  if exist "%MODELOS_OFFLINE%\vosk-model-es-0.42.zip" (
    echo   Instalando el modelo de espanol desde la copia local...
    copy /y "%MODELOS_OFFLINE%\vosk-model-es-0.42.zip" "%TEMP%\vosk-es.zip" >nul
  ) else (
  echo   Descargando el modelo de espanol (unos 1,8 GB^)...
REM -C - reanuda: una descarga de 1,8 GB que se corta (se cae la red,
REM se desconecta el disco...) no puede empezar de cero cada vez.
  curl -# -L -C - --retry 5 --retry-delay 3 -o "%TEMP%\vosk-es.zip" https://alphacephei.com/vosk/models/vosk-model-es-0.42.zip
  )
  REM Verificar ANTES de extraer: una descarga reanudada puede quedar
  REM corrupta con el tamano correcto. Paso de verdad, y el sintoma
  REM aparecio mucho despues como "Failed to read token" al cargar el
  REM modelo. Si esta corrupto se BORRA, para no reanudar sobre el.
  tar -tf "%TEMP%\vosk-es.zip" >nul 2>&1
  if errorlevel 1 (
    echo   [X] La descarga quedo corrupta. Se borra; vuelve a ejecutar
    echo       el instalador para bajarla de nuevo.
    del "%TEMP%\vosk-es.zip" 2^>nul
    if not "%VC_AUTO%"=="1" pause
    exit /b 1
  )
  tar -xf "%TEMP%\vosk-es.zip" -C vosk_models
  REM Un modelo a medias NO falla aqui: revienta al arrancar, y con un
  REM mensaje que parece del microfono. Ya paso: una extraccion dejo
  REM fuera conf\ e ivector\ (10 MB de 2,3 GB) y costo encontrarlo.
  for %%d in (am conf graph ivector) do (
    if not exist "vosk_models\vosk-model-es-0.42\%%d" (
      echo   [X] El modelo quedo incompleto: falta %%d
      echo       Borra vosk_models\vosk-model-es-0.42 y repite.
      rmdir /s /q "vosk_models\vosk-model-es-0.42" 2^>nul
      if not "%VC_AUTO%"=="1" pause
      exit /b 1
    )
  )
  del "%TEMP%\vosk-es.zip"
)
REM El modelo PEQUENO de ingles: es el del idioma secundario.
REM
REM Son unos 40 MB, y sin el la aplicacion carga el grande (3,8 GB) o se
REM queda sin segundo idioma. Medido el 6-sep-2026 en Linux: con el
REM secundario en pequeno la aplicacion pide 3.400 MB en vez de 10.300.
REM Aqui tiene que ser igual, o Windows gastaria tres veces mas para lo
REM mismo.
if not exist vosk_models\vosk-model-small-en-us-0.15 (
  if exist "%MODELOS_OFFLINE%\vosk-model-small-en-us-0.15.zip" (
    echo   Instalando el modelo de ingles desde la copia local...
    copy /y "%MODELOS_OFFLINE%\vosk-model-small-en-us-0.15.zip" "%TEMP%\vosk-en.zip" >nul
  ) else (
    echo   Descargando el modelo pequeno de ingles (unos 40 MB^)...
    curl -# -L -C - --retry 5 --retry-delay 3 -o "%TEMP%\vosk-en.zip" https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
  )
  tar -tf "%TEMP%\vosk-en.zip" >nul 2>&1
  if errorlevel 1 (
    echo   [!] El modelo de ingles quedo corrupto: se sigue sin el.
    echo       Los comandos en ingles no funcionaran hasta reinstalarlo.
    del "%TEMP%\vosk-en.zip" 2^>nul
  ) else (
    tar -xf "%TEMP%\vosk-en.zip" -C vosk_models
    del "%TEMP%\vosk-en.zip"
  )
)
if not exist vosk_models\vosk-model-spk-0.4 (
  if exist "%MODELOS_OFFLINE%\vosk-model-spk-0.4.zip" (
    echo   Instalando el modelo de locutor desde la copia local...
    copy /y "%MODELOS_OFFLINE%\vosk-model-spk-0.4.zip" "%TEMP%\vosk-spk.zip" >nul
  ) else (
  echo   Descargando el modelo de locutor...
  curl -# -L -C - --retry 5 --retry-delay 3 -o "%TEMP%\vosk-spk.zip" https://alphacephei.com/vosk/models/vosk-model-spk-0.4.zip
  )
  tar -xf "%TEMP%\vosk-spk.zip" -C vosk_models
  del "%TEMP%\vosk-spk.zip"
)
if not exist piper_voices mkdir piper_voices
dir /b piper_voices\*.onnx >nul 2>&1 || (
  REM Piper usa onnxruntime, que necesita el runtime de Visual C++.
  REM Windows NO lo trae de serie: sin el, piper-tts se instala pero
  REM revienta al importarlo con "DLL load failed", y el usuario se
  REM queda sin voz sin saber por que. Se comprueba ANTES de bajar la
  REM voz, que son 60 MB para nada si falta.
  python -c "import onnxruntime" 2>nul
  if errorlevel 1 (
    echo   [X] Sin el runtime de Visual C++ no se descarga la voz
    echo       - serian 60 MB para nada, porque Piper no podria cargarla.
  ) else (
    echo   Descargando la voz...
    REM El descargador de Piper usa urllib, y Python en Windows NO usa el
    REM almacen de certificados de Windows: busca el suyo de OpenSSL en
    REM "C:\Program Files\Common Files\SSL\cert.pem", que no existe en una
    REM instalacion normal. Resultado: urllib se queda SIN NINGUN almacen
    REM de confianza y la descarga muere con CERTIFICATE_VERIFY_FAILED.
    REM (curl si funciona porque usa Schannel, el almacen de Windows.)
    REM Se le pasa el almacen de certifi, que viene en el entorno virtual.
    for /f "delims=" %%c in ('python -c "import certifi;print(certifi.where())"') do set "SSL_CERT_FILE=%%c"
    python -m piper.download_voices es_ES-sharvard-medium --download-dir piper_voices
    set "SSL_CERT_FILE="
  )
)

REM --- Ajustes personales ------------------------------------------------
if exist config_local.py (
  echo   [OK] config_local.py ya existe: NO se toca
) else (
  echo.
  echo   Microfonos disponibles:
  python -c "import sounddevice as s;[print('    %%3d  %%s'%%(i,d['name'][:50])) for i,d in enumerate(s.query_devices()) if d['max_input_channels']>0]"
  if "%VC_AUTO%"=="1" (set "MIC=%VC_MIC%") else (set /p MIC="  Indice del microfono (vacio = el del sistema): ")
    REM Se guarda el NOMBRE, no el numero: el indice cambia solo en
    REM cuanto se conecta o se quita otro dispositivo, y entonces la
    REM aplicacion deja de oir sin dar ninguna pista. El nombre se
    REM resuelve en cada arranque.
    set "NOMBREMIC="
    if not "!MIC!"=="" (
      for /f "delims=" %%n in ('python -c "import sounddevice as s;print(s.query_devices(!MIC!)['name'])"') do set "NOMBREMIC=%%n"
    )
  if "%VC_AUTO%"=="1" (set "GENERO=%VC_VOZ%") else (set /p GENERO="  Voz del asistente, femenina o masculina? [femenina]: ")
  if "!GENERO!"=="" set "GENERO=femenina"
    REM Identificacion por voz: igual que en install.sh. Si se activa
    REM hay que enrolar la voz, y eso se ofrece al final.
    if "%VC_AUTO%"=="1" (set "QUIEREVOZ=%VC_VOZLOGIN%") else (
      echo.
      echo   El santo y sena hace que solo obedezca a TU voz. Requiere
      echo   grabar tu voz, unos 4 minutos, y se puede hacer al terminar.
      set /p QUIEREVOZ="  Activar identificacion por voz? [s/N] "
    )
    set "FRASE="
    if /i "!QUIEREVOZ!"=="s" (
      if "%VC_AUTO%"=="1" (set "FRASE=%VC_FRASE%") else (
        set /p FRASE="  Frase de acceso [La lluvia en Sevilla es una maravilla]: "
      )
      if "!FRASE!"=="" set "FRASE=La lluvia en Sevilla es una maravilla"
    )
  (
    echo """Tus ajustes. Este fichero NO se pisa al actualizar."""
    echo.
    if not "!NOMBREMIC!"=="" (
      echo INPUT_DEVICE = "!NOMBREMIC!"
    ) else (
      if "!MIC!"=="" (echo INPUT_DEVICE = None) else (echo INPUT_DEVICE = !MIC!)
    )
    echo.
    echo TTS_VOICE_GENDER = "!GENERO!"
    echo BACKEND = "windows"
      echo.
      if /i "!QUIEREVOZ!"=="s" (
        echo VOICE_LOGIN_ENABLED = True
        echo VOICE_LOGIN_HINT = "!FRASE!"
        echo # El umbral se rellena al calibrar con speaker_calibration.py
      ) else (
        echo # Identificacion por voz desactivada en la instalacion.
        echo # Para activarla: pon True, enrola tu voz y calibra el umbral.
        echo VOICE_LOGIN_ENABLED = False
      )
    echo.
    echo # ---------------------------------------------------------------
    echo # TUS EXTENSIONES DE ARCHIVO
    echo # ---------------------------------------------------------------
    echo # Al decir "crear archivo ^<nombre^>", si la ULTIMA palabra es el
    echo # nombre de una extension, se usa como tal y el punto lo pone el
    echo # programa:
    echo #
    echo #     crear archivo apuntes texto      -^> apuntes.txt
    echo #     crear archivo arranque guion     -^> arranque.sh
    echo #     crear archivo programa python    -^> programa.py
    echo #     crear archivo apuntes            -^> apuntes  ^(sin extension^)
    echo #
    echo # Vienen de fabrica las corrientes. Las TUYAS se anaden aqui:
    echo #
    echo #     EXTENSIONES_HABLADAS = {"maqueta": "kra"}
    echo #
    echo # AVISO: tambien se puede deletrear ^("apuntes te equis te"^), pero el
    echo # reconocedor casi nunca acierta una ristra de letras -- las junta y
    echo # las convierte en palabras. Usa el NOMBRE siempre que puedas.
  ) > config_local.py
  echo   [OK] config_local.py creado
)


REM --- Acceso remoto (movil) ---------------------------------------------
REM El instalador de Linux preguntaba por esto y el de Windows no, asi que
REM webapp_config.json no se creaba nunca. Y como main.py importa la webapp
REM al arrancar, eso IMPEDIA abrir el programa (ya corregido en app.py, pero
REM aun asi hay que poder configurar el movil desde aqui).
REM
REM El certificado NO se genera aqui: lo crea la propia webapp la primera
REM vez que arranca (webapp/app.py, con la biblioteca cryptography). Asi no
REM hace falta openssl, que Windows no trae.
if exist webapp_config.json (
  echo   [OK] webapp_config.json ya existe: NO se toca
) else (
  set "QUIERE_REMOTO="
  if "%VC_AUTO%"=="1" (
    set "QUIERE_REMOTO=%VC_REMOTO%"
  ) else (
    echo.
    set /p QUIERE_REMOTO="  Vas a usar el movil como microfono/mando? [s/N] "
  )
  if /i "!QUIERE_REMOTO!"=="s" (
    REM Sin comillas dentro del python -c: en un for /f de cmd se escapan
    REM mal y acaban duplicadas, que es un error de sintaxis.
    REM Y OJO: nada de parentesis en los REM de dentro de un bloque; cmd
    REM los cuenta aunque sean comentarios y cierra el bloque antes.
    for /f "delims=" %%i in ('python -c "import socket;print(socket.gethostbyname(socket.gethostname()))"') do set "MIIP=%%i"
    if "%VC_AUTO%"=="1" (set "IP=!MIIP!") else (
      set /p IP="  IP de este PC en tu red [!MIIP!]: "
      if "!IP!"=="" set "IP=!MIIP!"
    )
    if "%VC_AUTO%"=="1" (set "USUARIO=%VC_USUARIO%") else (
      set /p USUARIO="  Usuario para entrar desde el movil [pipa]: "
    )
    if "!USUARIO!"=="" set "USUARIO=pipa"
    REM gen_config.py PIDE la contrasena por teclado si no se le pasa, y eso
    REM deja el instalador colgado esperando cuando va desatendido. Con
    REM VC_PASSWORD se le da; sin modo desatendido se deja que pregunte,
    REM que es lo correcto: asi no queda escrita en ningun sitio.
    if "%VC_AUTO%"=="1" (
      if "%VC_PASSWORD%"=="" (
        echo   [aviso] Modo desatendido sin VC_PASSWORD: no se puede crear la
        echo       configuracion del movil sin contrasena. Se omite.
      ) else (
        python webapp\gen_config.py --host "!IP!" --user "!USUARIO!" --password "%VC_PASSWORD%"
      )
    ) else (
      python webapp\gen_config.py --host "!IP!" --user "!USUARIO!"
    )
    if exist webapp_config.json (
      echo   [OK] webapp_config.json creado para !IP!
      echo       El certificado HTTPS se generara solo al arrancar.
      echo.
      echo   FILTRADO POR IP ^(opcional, y con trampa^):
      echo   Solo tiene sentido si vas a usar la app de Android desde fuera.
      echo   Deja entrar SOLO a los aparatos que digas; los demas ni llegan
      echo   a la pantalla de contrasena. Es una capa MAS, no un sustituto
      echo   de ella: una IP se puede falsificar dentro de una red local.
      echo.
      echo   La trampa: si pones una IP fija y luego cambias de movil, o tu
      echo   router reparte por DHCP y le toca otra, la aplicacion dejara de
      echo   responderte SIN NINGUN MENSAJE. Ponla fija solo si te la asigna
      echo   siempre la misma tu VPN; si no, usa un rango.
      if not "%VC_AUTO%"=="1" (
        set /p FILTRAR="  Activar filtrado por IP? [s/N] "
        if /i "!FILTRAR!"=="s" (
          echo   Formatos: 10.8.0.2  ^|  10.8.0.10-50  ^|  10.8.0.0/24
          set /p IPS="  IPs o rangos permitidos, separados por espacios: "
          REM Va a config_local.py, NO a webapp_config.json: es un ajuste de
          REM ESTA maquina y de ESTA red, y config_local.py no se pisa al
          REM actualizar. La herramienta valida las IPs antes de escribir,
          REM porque una mal puesta no da error: deja fuera al movil en
          REM silencio y se busca el fallo en la VPN o en el router.
          python tools\poner_ips_permitidas.py !IPS!
        ) else (
          echo   Sin filtrar: cualquier aparato de la red podra intentar
          echo   entrar, y necesitara la contrasena. Se activa mas tarde
          echo   poniendo WEBAPP_ALLOWED_IPS en config_local.py.
        )
      )
    ) else (
      echo   [aviso] No se pudo crear webapp_config.json: el movil quedara
      echo       desactivado. Se puede hacer luego con webapp\gen_config.py
    )
  ) else (
    echo   [OK] sin movil: la webapp queda desactivada
  )
)

REM --- Comandos y prosodia: fusionar, no solo copiar ---------------------
REM
REM Antes esto solo copiaba SI NO EXISTIA. O sea que al actualizar, quien ya
REM tuviera su commands.json no recibia jamas los comandos nuevos de la
REM version -- se quedaba con los de su primera instalacion sin enterarse.
REM Linux ya lo hacia bien con merge_commands.py; Windows no.
REM
REM La fusion anade lo nuevo y NO toca lo que hayas personalizado.
if exist commands.json (
  if exist commands.default.json (
    venv\Scripts\python.exe tools\merge_commands.py commands.default.json --aplicar
  )
) else (
  if exist commands.default.json copy /y commands.default.json commands.json >nul
)

if exist prosody.json (
  if exist prosody.default.json (
    venv\Scripts\python.exe tools\merge_prosody.py prosody.default.json --aplicar
  )
) else (
  if exist prosody.default.json copy /y prosody.default.json prosody.json >nul
)
REM --- Enrolado de la voz ----------------------------------------------
REM Sin perfil no hay santo y sena NI filtro por locutor, y ademas el
REM enrolado del MOVIL se queda en punto muerto la primera vez que se
REM conecta. install.sh ya lo ofrecia; aqui faltaba.
findstr /c:"VOICE_LOGIN_ENABLED = True" config_local.py >nul 2>&1
if not errorlevel 1 (
  if exist config\speaker_profile.json (
    echo   [OK] ya hay perfil de voz
  ) else (
    echo.
    echo   [aviso] Falta grabar tu voz: sin ella el santo y sena no funciona.
    echo       Son unos 4 minutos, manos libres.
    set "ENROLAR="
    if "%VC_AUTO%"=="1" (set "ENROLAR=n") else (set /p ENROLAR="  Lo hacemos ahora? [s/N] ")
    if /i "!ENROLAR!"=="s" (
      venv\Scripts\python.exe tools\speaker_calibration.py enroll
      venv\Scripts\python.exe tools\speaker_calibration.py login
      venv\Scripts\python.exe tools\speaker_calibration.py export --force
      echo.
      echo   [aviso] Copia el UMBRAL propuesto a config_local.py:
      echo         VOICE_LOGIN_THRESHOLD = el numero
    ) else (
      echo   Cuando quieras:
      echo     venv\Scripts\python.exe tools\speaker_calibration.py enroll
      echo     venv\Scripts\python.exe tools\speaker_calibration.py login
      echo     venv\Scripts\python.exe tools\speaker_calibration.py export
    )
  )
)
echo   El perfil del MOVIL se graba solo la primera vez que lo conectes.

REM Antes el instalador no decia NADA de como poner la app en el telefono.
REM Quien acaba de instalar tiene el PC listo y ninguna pista de que le falta
REM algo en el movil, ni de que puede usarlo sin instalar nada.
if /i "!QUIERE_REMOTO!"=="s" (
  echo.
  echo   Para usar el movil hay dos caminos:
  echo.
  echo     1. Sin instalar nada. Abre Firefox en el telefono y entra en la
  echo        direccion que ha dicho este instalador. Habra que aceptar el
  echo        aviso de certificado la primera vez.
  echo.
  echo     2. Con la app, que viene en este paquete ya construida:
  echo          !DESTINO!\VoiceController.apk
  echo        Copiala al telefono y abrela alli. Pedira la direccion de este
  echo        ordenador y, la primera vez, un codigo de doce cifras: di aqui
  echo        "codigo de emparejamiento" y comprueba que coinciden.
  echo.
  echo   Con la app no hay que aceptar nada cada vez, y el microfono va mejor.
)

REM Se apunta la version instalada, para que la proxima vez se sepa de
REM donde se viene. Va al final: si el instalador falla antes, no se
REM apunta una version que no llego a instalarse del todo.
> .instalado echo %VER_NUEVA%

echo.
echo ================================================================
echo   Listo. Arrancar con:   venv\Scripts\python.exe main.py
echo.
  echo   Si algo falla, apuntalo: es informacion util para el port.
echo ================================================================
if not "%VC_AUTO%"=="1" pause
