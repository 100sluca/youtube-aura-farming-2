@echo off
setlocal EnableExtensions
title YouTube 2.0 - lanceur local

rem ---------------------------------------------------------------------------
rem Demarre YouTube 2.0 (youtube-shorts-daily) en local, tout sur ce PC :
rem   1. Docker Desktop puis la base Supabase locale (npx supabase start) ;
rem   2. l'environnement Python du worker (uv) ;
rem   3. ComfyUI s'il est installe (et pas deja lance), puis le worker et le dashboard (port 3000).
rem
rem Windows (acces controle aux dossiers) interdit aux programmes non autorises d'ecrire
rem dans Documents : l'environnement Python, les donnees et la copie de travail de Supabase
rem vivent donc dans C:\YouTube2, sur le disque interne (D: est un disque externe branche
rem a l'occasion : rien ne doit en dependre). Le code reste dans le depot.
rem
rem Diagnostic sans rien lancer :  "youtube-shorts-daily - demarrer.bat" /check
rem Fichier volontairement sans accents, en fins de ligne CRLF (cmd.exe l'exige pour les
rem etiquettes) : le modifier avec un editeur qui conserve CRLF (Bloc-notes le fait).
rem ---------------------------------------------------------------------------

set "ROOT=C:\Users\Luca\Documents\GitHub\___CODE\2026_09_19-Youtube2.0"
set "YT2=C:\YouTube2"
set "FRONT=%ROOT%\apps\dashboard"
set "WORKER=%ROOT%\services\worker"
set "SBWORK=%YT2%\supabase-workdir"
set "PORT=3000"
set "DB_PORT=54322"
set "COMFY_PORT=8188"
set "UV_PROJECT_ENVIRONMENT=%YT2%\worker-venv"
set "PYTHONDONTWRITEBYTECODE=1"
set "DOCKER_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set "CHECK="
set "FRONT_RUNNING="
set "COMFY_RUNNING="
if /i "%~1"=="/check" set "CHECK=1"

rem ComfyUI : C:\ComfyUI_windows_portable de preference, sinon dans C:\YouTube2, sinon la ou l'archive a ete decompressee
set "COMFY="
if exist "C:\ComfyUI_windows_portable\run_nvidia_gpu.bat" set "COMFY=C:\ComfyUI_windows_portable"
if not defined COMFY if exist "%YT2%\ComfyUI_windows_portable\run_nvidia_gpu.bat" set "COMFY=%YT2%\ComfyUI_windows_portable"
if not defined COMFY if exist "%USERPROFILE%\Downloads\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\run_nvidia_gpu.bat" set "COMFY=%USERPROFILE%\Downloads\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable"

rem ---- Verifications ------------------------------------------------------------
if not exist "%FRONT%\package.json" (
    echo [ERREUR] Dashboard introuvable : %FRONT%
    echo          Corriger la variable ROOT en tete de ce fichier.
    goto :fail
)
if not exist "%WORKER%\pyproject.toml" (
    echo [ERREUR] Worker introuvable : %WORKER%
    goto :fail
)
if not exist "%FRONT%\.env.local" (
    echo [ERREUR] Pas de fichier .env.local dans %FRONT%
    echo          Copier %ROOT%\.env.example en apps\dashboard\.env.local ^(partie Dashboard^).
    goto :fail
)
if not exist "%WORKER%\.env" (
    echo [ERREUR] Pas de fichier .env dans %WORKER%
    echo          Copier %ROOT%\.env.example en services\worker\.env ^(partie Worker^).
    goto :fail
)
where uv >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] uv introuvable. Installer : winget install astral-sh.uv  ^(puis rouvrir ce lanceur^)
    goto :fail
)
where npx >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] Node.js introuvable. Installer : winget install OpenJS.NodeJS.LTS
    goto :fail
)
if not exist "%DOCKER_EXE%" (
    echo [ERREUR] Docker Desktop introuvable : il faut l'installer pour la base locale.
    goto :fail
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ATTENTION] ffmpeg introuvable dans le PATH : le montage des videos echouera.
    echo             Installer : winget install Gyan.FFmpeg
)

rem Port du dashboard : deja pris par CE dashboard (lance a la main) = on le reutilise ;
rem pris par autre chose = arret, sinon Next.js basculerait en silence sur 3001.
call :port_busy %PORT%
if not defined BUSY_PID goto :port_checked
curl -s -m 20 http://localhost:%PORT%/ 2>nul | findstr /c:"YouTube 2.0" >nul
if errorlevel 1 (
    echo [ERREUR] Le port %PORT% est deja utilise par le processus %BUSY_PID%, qui n'est pas ce dashboard.
    echo          Fermer ce programme, ou l'arreter avec :  taskkill /PID %BUSY_PID% /T /F
    goto :fail
)
set "FRONT_RUNNING=%BUSY_PID%"
:port_checked

rem ComfyUI deja lance a la main (port 8188 occupe) : on le reutilise
call :port_busy %COMFY_PORT%
if defined BUSY_PID set "COMFY_RUNNING=%BUSY_PID%"

if defined CHECK goto :check_report
if not exist "%YT2%\" mkdir "%YT2%"
if not exist "%YT2%\data\" mkdir "%YT2%\data"
if not exist "%YT2%\models\" mkdir "%YT2%\models"

rem ---- 1. Base de donnees locale (Supabase) --------------------------------------
call :port_busy %DB_PORT%
if defined BUSY_PID (
    echo Base locale deja demarree.
    goto :db_ok
)
call :ensure_docker
if errorlevel 1 goto :fail
echo Copie de travail de Supabase : %SBWORK%
robocopy "%ROOT%\supabase" "%SBWORK%\supabase" /MIR /XD .temp .branches /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo [ERREUR] Copie de %ROOT%\supabase vers %SBWORK% impossible.
    goto :fail
)
echo Demarrage de Supabase local. La premiere fois : telechargement d'environ 3 Go, plusieurs minutes.
pushd "%SBWORK%"
call npx --yes supabase --workdir "%SBWORK%" start
if errorlevel 1 (
    popd
    echo [ERREUR] Supabase n'a pas demarre. Lire le message ci-dessus ; docs\11 section 8.
    goto :fail
)
popd
:db_ok

rem Nouvelles migrations (base deja demarree) : appliquees sans rien casser
robocopy "%ROOT%\supabase" "%SBWORK%\supabase" /MIR /XD .temp .branches /NFL /NDL /NJH /NJS /NP >nul
call npx --yes supabase --workdir "%SBWORK%" migration up >nul 2>nul

rem ---- 2. Environnement Python du worker ----------------------------------------
if exist "%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" goto :venv_ok
echo Environnement Python du worker : %UV_PROJECT_ENVIRONMENT%  ^(premiere fois : quelques minutes^)
pushd "%WORKER%"
call uv sync --frozen --extra tts --extra web
if errorlevel 1 (
    popd
    echo [ERREUR] uv sync a echoue.
    goto :fail
)
popd
:venv_ok

rem ---- 3. Dependances du dashboard ------------------------------------------------
if exist "%FRONT%\node_modules\" goto :deps_ok
echo Dependances du dashboard absentes, installation : npm install
pushd "%FRONT%"
call npm install
if errorlevel 1 (
    popd
    echo [ERREUR] npm install a echoue.
    goto :fail
)
popd
:deps_ok

rem ---- 4. Lancement ----------------------------------------------------------------
if defined COMFY_RUNNING (
    echo ComfyUI deja lance ^(processus %COMFY_RUNNING%^) : il est reutilise.
) else if defined COMFY (
    echo Lancement de ComfyUI ^(%COMFY%^)
    rem --cache-none : l'encodeur de 15 Go de MiniMax H3 est jete des qu'il a servi ; --fast-disk : les poids GGUF sont
    rem relus sur le SSD au lieu d'etre recopies en RAM verrouillee (sinon la RAM deborde, docs/20)
    start "ComfyUI" /D "%COMFY%" cmd /k .\python_embeded\python.exe -s ComfyUI\main.py --windows-standalone-build --cache-none --fast-disk
    timeout /t 5 /nobreak >nul
) else (
    echo [INFO] ComfyUI non installe : pas de generation d'images ni de videos pour l'instant.
    echo        L'installer dans C:\ComfyUI_windows_portable ^(voir services\worker\workflows\README.md^).
)

echo Lancement du worker
start "Worker - YouTube 2.0" /D "%WORKER%" cmd /k uv run --frozen worker
timeout /t 3 /nobreak >nul

if defined FRONT_RUNNING (
    echo Dashboard deja lance ^(processus %FRONT_RUNNING%^) : il est reutilise.
) else (
    echo Lancement du dashboard sur http://localhost:%PORT%
    start "Dashboard - YouTube 2.0" /D "%FRONT%" cmd /k npm run dev -- --port %PORT%
    timeout /t 8 /nobreak >nul
)
start "" http://localhost:%PORT%

echo.
echo  YouTube 2.0 est lance :
echo    dashboard  http://localhost:%PORT%
echo    base       http://127.0.0.1:54323  ^(Supabase Studio^)
echo    donnees    %YT2%\data
echo  Fermer les fenetres ^(ou Ctrl+C dedans^) pour arreter. La base reste active :
echo  pour l'arreter, fermer Docker Desktop.
echo.
pause
endlocal
exit /b 0

rem ---- Sous-programmes ---------------------------------------------------------------
:port_busy
set "BUSY_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%1 .*LISTENING"') do set "BUSY_PID=%%p"
exit /b 0

:ensure_docker
docker info >nul 2>nul
if not errorlevel 1 exit /b 0
echo Demarrage de Docker Desktop...
start "" "%DOCKER_EXE%"
set /a TRIES=0
:docker_wait
timeout /t 5 /nobreak >nul
docker info >nul 2>nul
if not errorlevel 1 (
    echo Docker est pret.
    exit /b 0
)
set /a TRIES+=1
if %TRIES% lss 36 goto :docker_wait
echo [ERREUR] Docker ne repond pas apres 3 minutes. Ouvrir Docker Desktop, attendre qu'il soit pret,
echo          puis relancer ce lanceur.
exit /b 1

:check_report
echo.
echo  Diagnostic ^(rien n'est lance^) :
echo    fichiers .env ............ ok
echo    dossier de travail ...... %YT2%
call :port_busy %DB_PORT%
if defined BUSY_PID (echo    base locale ............. demarree) else (echo    base locale ............. arretee, sera demarree)
docker info >nul 2>nul
if errorlevel 1 (echo    Docker .................. arrete, sera demarre) else (echo    Docker .................. demarre)
if exist "%UV_PROJECT_ENVIRONMENT%\Scripts\python.exe" (echo    environnement Python .... pret) else (echo    environnement Python .... a creer dans %UV_PROJECT_ENVIRONMENT%)
if defined COMFY_RUNNING (echo    ComfyUI ................. deja lance ^(processus %COMFY_RUNNING%^)) else if defined COMFY (echo    ComfyUI ................. %COMFY%) else (echo    ComfyUI ................. absent)
if defined FRONT_RUNNING (echo    dashboard ............... deja lance, reutilise ^(processus %FRONT_RUNNING%^)) else (echo    dashboard ............... sera lance sur le port %PORT%)
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
