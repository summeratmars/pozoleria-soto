@echo off
SETLOCAL
REM =============================================================
REM  Script: create_repo_and_push.bat
REM  Uso:    create_repo_and_push.bat [nombre_repo] [--public]
REM  Requiere: GitHub CLI (gh) autenticado: gh auth login
REM  Funcion: Crear repo en GitHub y hacer push del contenido actual.
REM =============================================================

set REPO=%~1
if "%REPO%"=="" set REPO=pozoleria-2

REM Visibilidad por defecto privada, usar --public para hacerlo público
set VIS=--private
if /I "%~2"=="--public" set VIS=--public

where gh >NUL 2>&1
IF ERRORLEVEL 1 (
  echo [ERROR] No se encontro la CLI de GitHub (gh).
  echo Instala: https://github.com/cli/cli/releases o via winget: winget install GitHub.cli
  exit /b 1
)

echo [INFO] Verificando autenticacion en gh...
gh auth status >NUL 2>&1
IF ERRORLEVEL 1 (
  echo [ERROR] No estas autenticado en gh.
  echo Ejecuta: gh auth login
  exit /b 1
)

REM Verificar si ya existe remoto origin apuntando a otro URL
git remote get-url origin >NUL 2>&1
IF NOT ERRORLEVEL 1 (
  for /f "delims=" %%u in ('git remote get-url origin') do set CURR_URL=%%u
  echo [INFO] Remoto origin actual: %CURR_URL%
  echo [INFO] Eliminando remoto origin para recrearlo...
  git remote remove origin
)

echo [INFO] Creando repo %REPO% en GitHub (%VIS%) ...
REM --source . usa este directorio y crea primer push
REM --remote origin define el remoto
REM --push hace push inicial automatico
gh repo create %REPO% %VIS% --source=. --remote=origin --push
IF ERRORLEVEL 1 (
  echo [ERROR] Fallo al crear o empujar el repositorio.
  exit /b 1
)

echo.
echo [OK] Repositorio creado y push inicial completado.
echo URL del repo:
gh repo view %REPO% --web --json url -q .url

echo.
echo Para siguientes commits usa: git_push.bat

ENDLOCAL
exit /b 0
