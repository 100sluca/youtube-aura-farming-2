@echo off
setlocal
title YouTube 2.0 - lanceur local

rem ---------------------------------------------------------------------------
rem Demarre YouTube 2.0 (youtube-shorts-daily) en local :
rem   - le worker Python (generation + upload) dans une fenetre, sans port ;
rem   - le dashboard Next.js dans une autre, sur http://localhost:3000 ;
rem   - ComfyUI en plus si le dossier COMFY existe (generation video locale).
rem La base de donnees est hebergee (Supabase) : rien a lancer pour elle.
rem Ollama (LLM de secours) est un service Windows deja actif sur le port 11434.
rem
rem Copie adaptee a ce PC du fichier launcher\ du depot (ROOT corrige).
rem Fichier volontairement sans accents : cmd.exe ne lit pas l'UTF-8 par defaut.
rem ---------------------------------------------------------------------------

set "ROOT=C:\Users\Luca\Documents\GitHub\___CODE\2026_09_19-Youtube2.0"
set "COMFY=C:\ComfyUI_windows_portable"

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
    echo          Copier %ROOT%\.env.example en apps\dashboard\.env.local
    echo          et renseigner la partie Dashboard ^(NEXT_PUBLIC_MOCK=1 suffit pour la demo^).
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
    echo          Copier %ROOT%\.env.example en services\worker\.env
    echo          et renseigner la partie Worker ^(DATABASE_URL, cles LLM, fournisseurs^).
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
    echo Environnement Python absent, installation : uv sync --extra tts
    cd /d "%WORKER%"
    call uv sync --extra tts
    if errorlevel 1 (
        echo [ERREUR] uv sync a echoue.
        pause
        exit /b 1
    )
)

rem ---- Port du dashboard : refuser de demarrer si deja pris ----------------------
rem Sans cette verification, Next.js basculerait en silence sur 3001.
set "BUSY_PID="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":%PORT% .*LISTENING"') do set "BUSY_PID=%%p"
if defined BUSY_PID (
    echo [ERREUR] Le port %PORT% est deja utilise par le processus %BUSY_PID%.
    echo          Un autre serveur de dev tourne sans doute : fermer son autre
    echo          fenetre, ou l'arreter avec :  taskkill /PID %BUSY_PID% /T /F
    echo          puis relancer ce lanceur.
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
    echo        Voir docs\06-local-stack.md pour l'installer ^(portable^), puis adapter COMFY ci-dessus.
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
