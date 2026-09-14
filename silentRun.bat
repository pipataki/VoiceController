@echo off
REM ===========================================================================
REM   Arranca VoiceController en segundo plano, sin consola por delante
REM ===========================================================================
REM   El equivalente en Windows de silentRun.sh. Arrancar con
REM   "python main.py" deja una ventana de consola abierta que estorba, y si
REM   se cierra se lleva el programa por delante.
REM
REM   Usa pythonw.exe, que es el mismo Python SIN consola. Como entonces no
REM   hay donde mirar si algo falla, la salida va a un registro -- y con -u,
REM   porque si no Python la guarda en memoria y el registro va por detras.
REM
REM   Uso:
REM      silentRun.bat              arranca
REM      silentRun.bat --parar      lo cierra
REM      silentRun.bat --estado     dice si corre
REM      silentRun.bat --registro   ensena el final del registro
REM
REM   OJO con los signos de admiracion en los echo: con EnableDelayedExpansion
REM   cmd los interpreta como variables y se come el texto. Por eso los avisos
REM   van marcados [X] y no [!!].
REM ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PIDF=%TEMP%\voicecontroller.pid"
set "LOG=%TEMP%\voicecontroller.log"
set "PYW=%~dp0venv\Scripts\pythonw.exe"

if not exist "%PYW%" (
  echo   [X] No encuentro %PYW%
  echo       Ejecuta antes install.bat
  exit /b 1
)

REM --- Esta corriendo? --------------------------------------------------
REM   Se comprueba con PowerShell y no con tasklist: hay que asegurarse de
REM   que el PID guardado sigue siendo NUESTRO proceso y no un numero que
REM   Windows ha reutilizado para otra cosa.
set "VIVO="
REM   usebackq y comillas invertidas: en un for /f normal las comillas
REM   SIMPLES delimitan el comando, asi que las del propio codigo de
REM   PowerShell lo cortaban por la mitad y devolvia un PID fantasma.
for /f "usebackq" %%i in (`powershell -NoProfile -Command "$f='%PIDF%'; if (Test-Path $f) { $id=(Get-Content $f | Select-Object -First 1); $p=Get-Process -Id $id -ErrorAction SilentlyContinue; if ($p -and $p.ProcessName -like 'python*') { $id } }"`) do set "VIVO=%%i"

if /i "%~1"=="--parar" (
  if defined VIVO (
    taskkill /pid !VIVO! /t /f >nul 2>&1
    del "%PIDF%" >nul 2>&1
    echo   [OK] cerrada
  ) else (
    echo   [..] no estaba corriendo
    del "%PIDF%" >nul 2>&1
  )
  exit /b 0
)

if /i "%~1"=="--estado" (
  if defined VIVO (
    echo   [OK] corriendo, PID !VIVO!
    echo        registro: %LOG%
  ) else (
    echo   [..] parada
  )
  exit /b 0
)

if /i "%~1"=="--registro" (
  if exist "%LOG%" (
    powershell -NoProfile -Command "Get-Content '%LOG%' -Tail 40"
  ) else (
    echo   [..] todavia no hay registro
  )
  exit /b 0
)

if defined VIVO (
  echo   [X] Ya esta corriendo, PID !VIVO!
  echo       Para cerrarla:  silentRun.bat --parar
  exit /b 1
)

REM --- Hay escritorio? --------------------------------------------------
REM   silentRun.sh hace la misma comprobacion mirando DISPLAY/WAYLAND_DISPLAY.
REM
REM   Una sesion remota de Windows corre en la sesion 0, que NO tiene
REM   escritorio: el programa arranca, Qt no encuentra donde dibujar la
REM   ventana y se cae a los pocos segundos sin decir por que.
REM
REM   SESSIONNAME no sirve para detectarlo (por SSH tampoco esta definida en
REM   sesiones que si tienen escritorio). El numero de sesion si.
for /f "usebackq" %%s in (`powershell -NoProfile -Command "(Get-Process -Id $PID).SessionId"`) do set "SESION=%%s"
if "!SESION!"=="0" (
  echo   [X] No hay escritorio en esta sesion.
  echo.
  echo       VoiceController abre una ventana, y una sesion remota de
  echo       Windows no tiene donde dibujarla: arrancaria y se caeria.
  echo.
  echo       Arrancalo desde la pantalla del propio ordenador.
  echo.
  echo       A diferencia de Linux, Windows no deja engancharse a una
  echo       sesion grafica ya abierta con una variable de entorno: hay que
  echo       lanzarlo desde el escritorio, o programar una tarea con
  echo       schtasks /it, que la ejecuta en la sesion del usuario.
  exit /b 1
)

REM --- Arrancar ---------------------------------------------------------
REM   El PID lo escribe PowerShell, NO se captura con for /f sobre el
REM   proceso lanzado: for /f espera a que se cierre la salida del comando, y
REM   el hijo hereda esa tuberia, asi que la consola se quedaba abierta hasta
REM   que el programa entero moria -- lo contrario de un lanzador discreto.
powershell -NoProfile -Command "$p = Start-Process -FilePath '%PYW%' -ArgumentList '-u','main.py' -WorkingDirectory '%~dp0' -RedirectStandardOutput '%LOG%' -RedirectStandardError '%LOG%.err' -PassThru; Set-Content -Path '%PIDF%' -Value $p.Id"

if not exist "%PIDF%" (
  echo   [X] No se pudo arrancar
  exit /b 1
)
set /p NUEVO=<"%PIDF%"
echo   [OK] arrancando, PID %NUEVO%
echo        cargar los modelos de voz puede tardar un par de minutos
echo.
echo        estado:    silentRun.bat --estado
echo        registro:  silentRun.bat --registro
echo        parar:     silentRun.bat --parar
exit /b 0
