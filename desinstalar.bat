@echo off
setlocal EnableDelayedExpansion
REM ==========================================================================
REM  Deja VoiceController como recien descomprimido. Sin borrar los modelos.
REM ==========================================================================
REM  PARA QUE SIRVE
REM
REM  Para probar una instalacion desde cero sin volver a descargar los
REM  modelos de voz. Borra lo que creo install.bat -- el entorno de Python,
REM  tus ajustes, el perfil de voz, los certificados -- y DEJA la carpeta
REM  vosk_models, porque el instalador se salta la descarga cuando el modelo
REM  ya esta.
REM
REM  NO borra el codigo: esta carpeta sigue siendo el programa. Si quieres que
REM  no quede nada, borra la carpeta entera: VoiceController no toca el
REM  sistema, vive todo aqui dentro.
REM
REM  Uso:
REM     desinstalar.bat                solo dice lo que haria
REM     desinstalar.bat /borrar        borra de verdad (pregunta antes)
REM     desinstalar.bat /borrar /todo  borra TAMBIEN los modelos
REM ==========================================================================
cd /d "%~dp0"

set "BORRAR=0"
set "TODO=0"
for %%a in (%*) do (
  if /i "%%a"=="/borrar" set "BORRAR=1"
  if /i "%%a"=="/todo"   set "TODO=1"
)

echo.
echo   == Lo que se borraria ==
echo.
set "HAY=0"
for %%f in (venv dist webapp_uploads .instalado voicecontroller.log voicecontroller.log.1) do (
  if exist "%%f" ( echo      %%f & set "HAY=1" )
)
for %%f in (tablero.png casilla.png zoom_out.png foco.png vc.png) do (
  if exist "webapp\static\board\%%f" ( echo      webapp\static\board\%%f & set "HAY=1" )
)
echo.
echo   Y esto son AJUSTES TUYOS -- se pierden:
for %%f in (config_local.py commands.json prosody.json corrections.json window_names.json webapp_config.json webapp_cert.pem webapp_key.pem) do (
  if exist "%%f" ( echo      %%f & set "HAY=1" )
)
if exist "config\speaker_profile.json" ( echo      config\speaker_profile.json & set "HAY=1" )

echo.
if "%TODO%"=="1" (
  echo   [!] Y TAMBIEN LOS MODELOS. Volver a descargarlos lleva mucho rato:
  if exist vosk_models  echo      vosk_models
  if exist piper_voices echo      piper_voices
) else (
  echo   [OK] Los modelos SE QUEDAN: la siguiente instalacion no los descargara.
)

if "%HAY%"=="0" (
  echo.
  echo   No hay nada que borrar: esta carpeta ya esta sin instalar.
  echo.
  pause
  exit /b 0
)

if not "%BORRAR%"=="1" (
  echo.
  echo   Esto ha sido solo una lista. Para borrar de verdad:
  echo       desinstalar.bat /borrar
  echo.
  pause
  exit /b 0
)

echo.
set /p RESP="  Escribe BORRAR para continuar: "
if /i not "!RESP!"=="BORRAR" (
  echo   Cancelado. No se ha tocado nada.
  pause
  exit /b 0
)

echo.
echo   == Borrando ==
for %%f in (venv dist webapp_uploads) do (
  if exist "%%f" ( rmdir /s /q "%%f" & echo      %%f )
)
for %%f in (.instalado voicecontroller.log voicecontroller.log.1 config_local.py commands.json prosody.json corrections.json window_names.json webapp_config.json webapp_cert.pem webapp_key.pem) do (
  if exist "%%f" ( del /q "%%f" & echo      %%f )
)
for %%f in (tablero.png casilla.png zoom_out.png foco.png vc.png) do (
  if exist "webapp\static\board\%%f" ( del /q "webapp\static\board\%%f" & echo      webapp\static\board\%%f )
)
if exist "config\speaker_profile.json" ( del /q "config\speaker_profile.json" & echo      config\speaker_profile.json )
for /d /r %%d in (__pycache__) do ( if exist "%%d" rmdir /s /q "%%d" )
if "%TODO%"=="1" (
  if exist vosk_models  ( rmdir /s /q vosk_models  & echo      vosk_models )
  if exist piper_voices ( rmdir /s /q piper_voices & echo      piper_voices )
)

echo.
echo   == Lo que NO se va ==
echo   Borrar esta carpeta quita el programa entero: no escribe en el registro
echo   ni en el arranque. Lo unico que sobrevive es tu instalacion de Python.
echo.
echo   == Listo ==
echo   Para volver a instalar:   install.bat
if not "%TODO%"=="1" echo   Los modelos estan puestos, asi que no habra descargas.
echo.
pause
