@echo off
rem YouTube Aura Farming : double-clic = installation (une seule fois, a relancer sans crainte si elle s'arrete).
rem Le travail est fait par installation\installer.ps1 ; mode d'emploi : README.md.
rem Fichier sans accents, en fins de ligne CRLF (cmd.exe l'exige).
title YouTube Aura Farming - installation
if not exist "%~dp0installation\installer.ps1" (
    echo.
    echo  Le dossier du projet est incomplet.
    echo  As-tu bien extrait le fichier ZIP ? Clic droit sur le ZIP, "Extraire tout...",
    echo  puis double-clic sur INSTALLER.bat dans le dossier extrait.
    echo.
    pause
    exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installation\installer.ps1" %*
echo.
pause
