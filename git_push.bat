@echo off
SETLOCAL ENABLEDELAYEDEXPANSION
REM Permitir desactivar la pausa final con --no-pause o -q
for %%A in (%*) do (
  if /I "%%~A"=="--no-pause" set NO_PAUSE=1
  if /I "%%~A"=="-q" set NO_PAUSE=1
  if /I "%%~A"=="--debug" set DEBUG=1
)
REM =============================================================
REM  Script: git_push.bat
REM  Uso:    git_push.bat [mensaje commit opcional]
REM  Objetivo: Agregar cambios, crear commit solo si hay modificaciones y hacer push a origin main.
REM  Requisitos previos:
REM   - Repositorio ya inicializado (git init)
REM   - Remoto configurado (git remote add origin <URL>)
REM   - Credenciales guardadas (git te pedirá usuario/token la 1a vez)
REM =============================================================

REM Comprobar que estamos en un repo git
git rev-parse --is-inside-work-tree >NUL 2>&1
IF ERRORLEVEL 1 (
  echo [ERROR] Este directorio no es un repositorio git.
  echo Ejecuta: git init
  exit /b 1
)

REM Verificar remoto origin
git remote get-url origin >NUL 2>&1
IF ERRORLEVEL 1 (
  echo [ERROR] No existe remoto 'origin'.
  echo Agrega uno: git remote add origin https://github.com/USUARIO/REPO.git
  exit /b 1
)

REM Obtener rama actual
FOR /F "delims=" %%i IN ('git rev-parse --abbrev-ref HEAD') DO set CURR_BRANCH=%%i
IF /I NOT "%CURR_BRANCH%"=="main" (
  echo [INFO] Cambiando a rama main (actual: %CURR_BRANCH%)
  git checkout -B main
)

REM Preparar mensaje de commit
set MSG=%*
IF "%MSG%"=="" (
  for /f "tokens=1-4 delims=/ " %%a in ("%date%") do (
    set FECHA=%%a-%%b-%%c
  )
  set HORA=%time:~0,8%
  set MSG=chore: auto commit %FECHA% %HORA%
)

echo ===============================================
echo  Git Push Automatizado
echo  Rama: main
echo  Mensaje: %MSG%
echo ===============================================

REM Agregar archivos (incluye borrados, renombrados)
git add -A
IF ERRORLEVEL 1 (
  echo [ERROR] Fallo al ejecutar git add.
  exit /b 1
)

REM Verificar si hay cambios staged respecto a HEAD
git diff --cached --quiet
IF %ERRORLEVEL%==0 (
  echo [INFO] No hay cambios para commitear.
) ELSE (
  git commit -m "%MSG%"
  IF ERRORLEVEL 1 (
    echo [ERROR] Fallo al crear el commit.
    exit /b 1
  )
)

echo [INFO] Haciendo push a origin main...
if defined DEBUG (
  git push -v -u origin main
) else (
  git push -u origin main
)
IF ERRORLEVEL 1 (
  echo.
  echo [ERROR] Push fallido. Posibles causas:
  echo   - Token/credenciales no configuradas (primera vez)
  echo   - Permisos insuficientes en el repo remoto
  echo   - Conexion a internet o firewall bloqueando
  echo.
  echo Sugerencias:
  echo   1) Genera un PAT: https://github.com/settings/tokens (scope: repo)
  echo   2) Configura helper: git config --global credential.helper manager
  echo   3) Repite: git push (usuario + token como password)
  set EXITCODE=1
) else (
  set EXITCODE=0
)

IF !EXITCODE! EQU 0 (
  echo [OK] Push completado correctamente.
  echo.
  echo Si Render esta vinculado a GitHub, la deployment se iniciara automaticamente.
  echo (Ver logs en el panel de Render.)
) else (
  echo.
  echo --- FIN con errores (EXITCODE=!EXITCODE!) ---
)
echo.
if not defined NO_PAUSE (
  echo Presiona una tecla para cerrar...
  pause >NUL
)
exit /b !EXITCODE!
