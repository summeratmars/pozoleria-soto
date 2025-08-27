@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
REM =============================================================
REM  Script: deploy_render.bat
REM  Uso:    deploy_render.bat [mensaje commit opcional] [opciones]
REM
REM  Función:
REM    1) Crea commit (solo si hay cambios) y push a origin main (usa git_push.bat)
REM    2) Lanza un deploy manual en Render mediante API
REM    3) (Opcional) Espera hasta que termine (--watch)
REM
REM  Requisitos previos:
REM    - git_push.bat en el mismo directorio
REM    - Variables de entorno definidas:
REM        RENDER_API_KEY       -> API Key de Render (scopes por defecto)
REM        RENDER_SERVICE_ID    -> ID del servicio (ver URL del panel Render)
REM    - curl disponible (Windows 10+ lo incluye). Si no, instala curl.
REM
REM  Opciones:
REM    --watch       : Hace polling hasta que el deploy finalice
REM    --interval=N  : Segundos entre polls (default 10)
REM    --no-pause    : No pausar al final
REM    --debug       : Verbose en git push
REM =============================================================

REM Parse flags propios (antes de pasar mensaje completo a git_push)
set WATCH=0
set INTERVAL=10
set NO_PAUSE=
set DEBUG=
set MSG_ARGS=
for %%A in (%*) do (
  if /I "%%~A"=="--watch" set WATCH=1
  if /I "%%~A"=="--no-pause" set NO_PAUSE=1
  if /I "%%~A"=="-q" set NO_PAUSE=1
  if /I "%%~A"=="--debug" set DEBUG=1
)

REM Extraer --interval=N (no se puede con for %%A easily parse '='), hacer loop distinto
:parse_interval
for %%A in (%*) do (
  echo %%~A | findstr /I /B /C:"--interval=" >NUL
  if !errorlevel! == 0 (
    for /F "tokens=2 delims==" %%I in ("%%~A") do set INTERVAL=%%I
  )
)

REM Construir lista de args para git_push (excluyendo --watch / --interval)
for %%A in (%*) do (
  if /I NOT "%%~A"=="--watch" if /I NOT "%%~A"=="--debug" if /I NOT "%%~A"=="--no-pause" if /I NOT "%%~A"=="-q" (
    echo %%~A | findstr /I /B /C:"--interval=" >NUL
    if !errorlevel! NEQ 0 (
      set MSG_ARGS=!MSG_ARGS! %%~A
    )
  ) else (
    if /I "%%~A"=="--debug" set MSG_ARGS=!MSG_ARGS! --debug
    if /I "%%~A"=="--no-pause" set MSG_ARGS=!MSG_ARGS! --no-pause
    if /I "%%~A"=="-q" set MSG_ARGS=!MSG_ARGS! -q
  )
)

REM 1) Ejecutar git_push.bat
if exist git_push.bat (
  call git_push.bat !MSG_ARGS!
  if errorlevel 1 (
    echo [ERROR] git_push.bat fallo. Abortando deploy.
    goto :end
  )
) else (
  echo [WARN] git_push.bat no encontrado. Se realizará push básico.
  git add -A && git commit -m "auto: commit" 2>NUL
  git push -u origin main
  if errorlevel 1 (
    echo [ERROR] Push fallido.
    goto :end
  )
)

REM 2) Validar variables de entorno para Render
if "%RENDER_API_KEY%"=="" (
  echo [ERROR] Falta variable RENDER_API_KEY
  goto :end
)
if "%RENDER_SERVICE_ID%"=="" (
  echo [ERROR] Falta variable RENDER_SERVICE_ID
  goto :end
)

REM 3) Lanzar deploy manual
set DEPLOY_RESPONSE=
for /F "delims=" %%R in ('curl -s -X POST "https://api.render.com/v1/services/%RENDER_SERVICE_ID%/deploys" -H "Authorization: Bearer %RENDER_API_KEY%" -H "Content-Type: application/json" -d "{}"') do set DEPLOY_RESPONSE=%%R

REM Intentar extraer deploy ID rudimentariamente (busca "id":"xxxxx")
set DEPLOY_ID=
for /F "tokens=2 delims=:" %%I in ("!DEPLOY_RESPONSE:",=:") do (
  rem nada (placeholder)
)
REM Metodo sencillo con findstr + parsing
echo !DEPLOY_RESPONSE! | findstr /I /C:"\"id\":" >NUL
if !errorlevel! == 0 (
  for /F "tokens=2 delims=," %%I in ("!DEPLOY_RESPONSE!") do (
    rem no confiable para todos los casos; preferimos segundo metodo
  )
)
REM Segundo metodo: usar for con "id":" y cortar comillas
for /F "tokens=1-8 delims=," %%a in ("!DEPLOY_RESPONSE!") do (
  echo %%a | findstr /C:"\"id\":" >NUL
  if !errorlevel! == 0 (
    for /F "tokens=2 delims=:" %%x in ("%%a") do (
      set raw=%%x
      set raw=!raw:~1!
      for /F "tokens=1 delims=\"" %%y in ("!raw!") do set DEPLOY_ID=%%y
    )
  )
)

if "!DEPLOY_ID!"=="" (
  echo [WARN] No se pudo extraer DEPLOY_ID. Respuesta cruda:
  echo !DEPLOY_RESPONSE!
  if !WATCH! EQU 1 echo [WARN] No se puede hacer watch sin ID.
  goto :after_watch
) else (
  echo [INFO] Deploy iniciado. ID=!DEPLOY_ID!
)

if !WATCH! EQU 1 (
  echo [INFO] Iniciando watch cada !INTERVAL!s (Ctrl+C para abortar)...
  :poll_loop
    timeout /t !INTERVAL! >NUL
    set STATUS_JSON=
    for /F "delims=" %%R in ('curl -s -H "Authorization: Bearer %RENDER_API_KEY%" "https://api.render.com/v1/deploys/!DEPLOY_ID!"') do set STATUS_JSON=%%R
    set STATE=
    echo !STATUS_JSON! | findstr /I /C:"\"status\":" >NUL
    if !errorlevel! == 0 (
      for /F "tokens=1-8 delims=," %%a in ("!STATUS_JSON!") do (
        echo %%a | findstr /C:"\"status\":" >NUL
        if !errorlevel! == 0 (
          for /F "tokens=2 delims=:" %%x in ("%%a") do (
            set raw=%%x
            set raw=!raw:~1!
            for /F "tokens=1 delims=\"" %%y in ("!raw!") do set STATE=%%y
          )
        )
      )
    )
    if "!STATE!"=="" (
      echo [WARN] No se pudo leer estado. JSON parcial:
      echo !STATUS_JSON!
      goto poll_loop
    )
    echo [INFO] Estado actual: !STATE!
    if /I "!STATE!"=="live" goto deploy_ok
    if /I "!STATE!"=="failed" goto deploy_fail
    if /I "!STATE!"=="canceled" goto deploy_fail
    goto poll_loop
  :deploy_ok
    echo [OK] Deploy finalizo con estado LIVE.
    goto :after_watch
  :deploy_fail
    echo [ERROR] Deploy termino en estado: !STATE!
)

:after_watch

echo.
echo --- Fin script deploy_render.bat ---

:end
if not defined NO_PAUSE (
  echo Presiona una tecla para cerrar...
  pause >NUL
)
exit /b 0
