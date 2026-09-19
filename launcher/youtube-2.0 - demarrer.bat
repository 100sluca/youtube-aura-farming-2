@echo off
setlocal
title YouTube 2.0 - lanceur local

rem Demarre YouTube 2.0 en local : le worker Python (generation + upload) dans une
rem fenetre, le dashboard Next.js dans une autre, puis ouvre http://localhost:3000.
rem La base de donnees est hebergee (Supabase) : rien a lancer pour elle.
rem ComfyUI est lance en plus si le dossier COMFY existe (generation video locale).
rem Fichier volontairement sans accents : cmd.exe ne lit pas l'UTF-8 par defaut.

rem ---- A ADAPTER : chemin du depot et de ComfyUI ---------------------------------
set "ROOT=C:\Users\Luca\Documents\GitHub\YouTube-2.0"
set "COMFY=C:\ComfyUI_windows_portable"
rem -------------------------------------------------------------------------------

set "FRONT=%ROOT%\apps\dashboard"
set "WORKER=%ROOT%\services\worker"
set "PORT=3000"

if not exist "%FRONT%\package.json" (
    echo [ERREUR] Dashboard introuvable : %FRONT%
    echo          Corriger la variable ROOT en tete de ce fichier.
    pause
    exit /b 1
)
if not exist "%WORKER%\pyproject.toml" (
    echo [ERREUR] Worker introuvable : %WORKER%
    pause
    exit /b 1
)

rem ---- Verifications du dashboard -----------------------------------------------
if not exist "%FRONT%\.env.local" (
    echo [ERREUR] Pas de fichier .env.local dans %FRONT%
    echo          Copier %ROOT%\.env.example en .env.local et renseigner la partie Dashboard.
    pause
    exit /b 1
)
if not exist "%FRONT%\node_modules\" (
    echo Dependances du dashboard absentes, installation : npm install
    cd /d "%FRONT%"
    call npm install
    if errorlevel 1 (
        echo [ERREUR] npm install a echoue.
        pause
        exit /b 1
    )
)

rem ---- Verifications du worker --------------------------------------------------
if not exist "%WORKER%\.env" (
    echo [ERREUR] Pas de fichier .env dans %WORKER%
    echo          Copier %ROOT%\.env.example en .env et renseigner la partie Worker.
    pause
    exit /b 1
)
where uv >nul 2>nul
if errorlevel 1 (
    echo [ERREUR] uv introuvable. Installer : winget install astral-sh.uv  ^(puis rouvrir ce lanceur^)
    pause
    exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [ATTENTION] ffmpeg introuvable dans le PATH : l'assemblage des videos echouera.
    echo             Installer : winget install Gyan.FFmpeg
)
if not exist "%WORKER%\.venv\" (
    echo Environnement Python absent, installation : uv sync
    cd /d "%WORKER%"
    call uv sync --extra tts
    if errorlevel 1 (
        echo [ERREUR] uv sync a echoue.
        pause
        exit /b 1
    )
)

rem ---- Port du dashboard : refuser de demarrer si deja pris ----------------------
netstat -ano | findstr ":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
    echo [ERREUR] Le port %PORT% est deja utilise. Processus concerne :
    netstat -ano | findstr ":%PORT% .*LISTENING"
    echo          Fermer l'autre serveur ou : taskkill /PID ^<pid^> /T /F
    pause
    exit /b 1
)

rem ---- Lancement ------------------------------------------------------------------
if exist "%COMFY%\run_nvidia_gpu.bat" (
    echo Lancement de ComfyUI ^(%COMFY%^)
    start "ComfyUI" /D "%COMFY%" cmd /k run_nvidia_gpu.bat
    timeout /t 5 >nul
) else (
    echo [INFO] ComfyUI non trouve dans %COMFY% : la generation video locale ne sera pas disponible.
)

echo Lancement du worker
start "Worker - YouTube 2.0" /D "%WORKER%" cmd /k uv run worker
timeout /t 3 >nul

echo Lancement du dashboard sur http://localhost:%PORT%
start "Dashboard - YouTube 2.0" /D "%FRONT%" cmd /k npm run dev -- --port %PORT%
timeout /t 8 >nul
start "" http://localhost:%PORT%

echo.
echo  YouTube 2.0 est lance : dashboard http://localhost:%PORT%, worker et ComfyUI dans leurs fenetres.
echo  Fermer les fenetres ^(ou Ctrl+C dedans^) pour arreter.
echo.
pause
endlocal
