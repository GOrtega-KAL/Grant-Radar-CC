@echo off
setlocal EnableExtensions
rem ============================================================================
rem  Grant-Radar diario.bat
rem
rem  Solucion intermedia hasta alojar la herramienta en un servidor: abre VS Code
rem  con el proyecto y lanza la recopilacion --no-claude en esta misma ventana.
rem
rem  NO llama a Claude, NO toca la cache de analisis y NO publica
rem  convocatorias.json. Solo recopila y publica estado_recopilacion.json, que es
rem  lo que hace que el panel avise de cuantas convocatorias esperan analisis.
rem  El analisis de pago sigue siendo manual y discrecional, como debe ser.
rem
rem  Ademas SONDEA los lotes en Anthropic (--batch-poll) antes de recopilar.
rem  Tampoco cuesta nada: es un listado de solo lectura, no recoge ni envia.
rem  Esta aqui como red diaria. El 04/09/2026 un lote paso 16,5 horas marcado
rem  como "procesando" cuando habia terminado a los 2 min 29 s, porque el
rem  archivo de estado es local y solo se escribe al enviarlo; si ademas ese
rem  archivo se pierde -esta en .gitignore-, el trabajo pagado se vuelve
rem  invisible. El sondeo pregunta a la API, que es lo unico que no depende de
rem  nuestro propio estado (AGENTS.md 64.2).
rem
rem  USO
rem    Doble clic                      -> abre VS Code y recopila
rem    "Grant-Radar diario.bat" /q     -> recopila sin abrir VS Code, util si
rem                                       algun dia se programa la tarea
rem    "Grant-Radar diario.bat" /log   -> ademas guarda la salida en
rem                                       grant_radar_data\logs\
rem    "Grant-Radar diario.bat" /solo-lotes -> solo sondea el estado de los
rem                                       lotes y sale, sin recopilar. Segundos
rem
rem  POR QUE NO LLAMA A "poetry"
rem    1. En una tarea programada el PATH no es el de tu sesion interactiva y
rem       "poetry" puede no encontrarse.
rem    2. Este equipo tiene una variable VIRTUAL_ENV heredada que apunta al
rem       .venv de la carpeta ORIGINAL, no al de esta copia; con ella presente,
rem       poetry puede ejecutar en silencio contra el entorno equivocado
rem       (ver CLAUDE.md).
rem    Llamar directo al interprete del entorno esquiva las dos cosas y hace
rem    esto inmune a que se reinstale o mueva poetry.
rem
rem  POR QUE LA SALIDA NO SE REDIRIGE A UN ARCHIVO POR DEFECTO
rem    La recopilacion tarda 11-15 minutos. El 01/09/2026 se lanzo una ejecucion
rem    redirigiendo toda la salida a un log y el usuario se quedo diecisiete
rem    minutos sin ver nada, creyendo que no habia proceso (AGENTS.md 54.8).
rem    Aqui la salida va a la ventana; /log la guarda ademas, no en lugar de.
rem ============================================================================

rem Acentos y guiones de la salida del pipeline. Sin esto, cmd los destroza.
chcp 65001 >nul 2>&1

rem Raiz del proyecto = la carpeta que contiene a "scripts".
pushd "%~dp0.."
if errorlevel 1 (
    echo No se pudo entrar en la carpeta del proyecto.
    pause
    exit /b 1
)
set "PROYECTO=%CD%"
set "PYTHON=%PROYECTO%\.venv\Scripts\python.exe"
set "SCRIPT=%PROYECTO%\Grant-Radar-prueba.py"

set "ABRIR_VSCODE=1"
set "GUARDAR_LOG=0"
set "SOLO_LOTES=0"
:leer_args
if "%~1"=="" goto fin_args
if /i "%~1"=="/q"          set "ABRIR_VSCODE=0"
if /i "%~1"=="/log"        set "GUARDAR_LOG=1"
if /i "%~1"=="/solo-lotes" set "SOLO_LOTES=1" & set "ABRIR_VSCODE=0"
shift
goto leer_args
:fin_args

echo(
echo ============================================================
echo  Grant-Radar - recopilacion diaria (sin coste)
echo  %DATE% %TIME:~0,8%
echo ============================================================
echo  Proyecto: %PROYECTO%
echo(

if not exist "%PYTHON%" (
    echo ERROR: no se encuentra el interprete del entorno:
    echo   %PYTHON%
    echo Ejecuta "poetry install" en la carpeta del proyecto.
    popd
    pause
    exit /b 1
)
if not exist "%SCRIPT%" (
    echo ERROR: no se encuentra Grant-Radar-prueba.py en:
    echo   %PROYECTO%
    popd
    pause
    exit /b 1
)

rem --- VS Code -------------------------------------------------------------
rem Ojo: "code" es un shim .cmd. Llamarlo sin "start" se llevaria por delante
rem este .bat, que terminaria sin recopilar nada.
if "%ABRIR_VSCODE%"=="0" goto sin_vscode
if exist "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" (
    echo Abriendo VS Code...
    start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" "%PROYECTO%"
    goto sin_vscode
)
if exist "%ProgramFiles%\Microsoft VS Code\Code.exe" (
    echo Abriendo VS Code...
    start "" "%ProgramFiles%\Microsoft VS Code\Code.exe" "%PROYECTO%"
    goto sin_vscode
)
echo AVISO: no se encontro VS Code; se continua solo con la recopilacion.
:sin_vscode

rem --- Sondeo de lotes -----------------------------------------------------
rem Va ANTES de la recopilacion, y a proposito: la recopilacion tarda 11-15
rem minutos y el usuario suele irse de la ventana. Si el aviso de "hay un lote
rem terminado sin recoger" saliera al final, se lo perderia. El sondeo tarda
rem segundos y no cuesta nada.
rem
rem Su codigo de salida NO se mira: es informativo, y un fallo de red no puede
rem impedir la recopilacion diaria, que es lo que de verdad hace este archivo.
set "VIRTUAL_ENV="

echo(
echo ------------------------------------------------------------
echo  Sondeo de lotes en Anthropic (solo lectura, sin coste)
echo ------------------------------------------------------------
"%PYTHON%" "%SCRIPT%" --batch-poll
echo(

if "%SOLO_LOTES%"=="1" (
    echo Solo se pidio el sondeo: no se recopila.
    popd
    exit /b 0
)

rem --- Recopilacion --------------------------------------------------------

rem La marca de tiempo se calcula AQUI y no dentro de un bloque "if": cmd
rem expande las variables al parsear el bloque entero, asi que dentro saldria
rem vacia. Es el fallo clasico de los .bat.
set "MARCA=%DATE:~-4%-%DATE:~3,2%-%DATE:~0,2%_%TIME:~0,2%%TIME:~3,2%"
set "MARCA=%MARCA: =0%"
set "ARCHIVO_LOG=%PROYECTO%\grant_radar_data\logs\recopilacion_%MARCA%.log"

echo(
echo Recopilando de las siete fuentes. Tarda 11-15 minutos.
echo No cierres esta ventana; la salida va apareciendo aqui.
echo(

if "%GUARDAR_LOG%"=="1" goto recopilar_con_log
"%PYTHON%" "%SCRIPT%" --no-claude
set "CODIGO=%ERRORLEVEL%"
goto informar

:recopilar_con_log
if not exist "%PROYECTO%\grant_radar_data\logs" mkdir "%PROYECTO%\grant_radar_data\logs"
call :con_log
set "CODIGO=%ERRORLEVEL%"

:informar
echo(
echo ============================================================
if not "%CODIGO%"=="0" goto informar_error
echo  Recopilacion COMPLETADA sin errores.
echo(
echo  Para ver el desfase acumulado, sin red y sin coste:
echo    .venv\Scripts\python.exe "Grant-Radar-prueba.py" --staleness-report
echo(
echo  El analisis con Claude sigue siendo manual y requiere autorizacion
echo  expresa: este archivo no lo lanza nunca.
goto fin

:informar_error
echo  La recopilacion termino con codigo %CODIGO%.
echo  Revisa la salida de arriba antes de repetirla.

:fin
if "%GUARDAR_LOG%"=="1" echo  Registro guardado en: %ARCHIVO_LOG%
echo ============================================================
echo(

popd
if "%ABRIR_VSCODE%"=="1" pause
exit /b %CODIGO%

:con_log
rem cmd no tiene "tee", asi que se hace con el propio interprete: la salida se
rem ve en la ventana Y se guarda. Aviso: tras un pipe, ERRORLEVEL es el del
rem ultimo proceso, no el del pipeline, asi que en modo /log el codigo de salida
rem no detecta un fallo de la recopilacion. Para eso, usa el modo normal.
"%PYTHON%" "%SCRIPT%" --no-claude 2>&1 | "%PYTHON%" -c "import sys,io;f=io.open(sys.argv[1],'w',encoding='utf-8');[(sys.stdout.write(l),f.write(l)) for l in sys.stdin];f.close()" "%ARCHIVO_LOG%"
exit /b %ERRORLEVEL%
