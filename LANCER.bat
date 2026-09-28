@echo off
rem YouTube Aura Farming : double-clic = demarre tout (base, ComfyUI, worker, tableau de bord) et ouvre
rem http://localhost:3000. Le travail est fait par installation\lancer.ps1 ; mode d'emploi : README.md.
rem Fichier sans accents, en fins de ligne CRLF (cmd.exe l'exige).
title YouTube Aura Farming
if not exist "%~dp0installation\lancer.ps1" (
    echo.
    echo  Le dossier du projet est incomplet.
    echo  As-tu bien extrait le fichier ZIP ? Clic droit sur le ZIP, "Extraire tout...",
    echo  puis INSTALLER.bat, et enfin LANCER.bat, dans le dossier extrait.
    echo.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installation\lancer.ps1" %*
echo.
pause
