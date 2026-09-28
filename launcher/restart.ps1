<#
Redemarre un morceau de YouTube 2.0 sur ce PC. Appele par le bouton "Redemarrer" de la barre laterale du dashboard
(docs/28-sante-machine.md), utilisable aussi a la main :

    powershell -NoProfile -ExecutionPolicy Bypass -File launcher\restart.ps1 -Target comfyui|worker|dashboard

- comfyui   : arrete le Python de ComfyUI (ComfyUI\main.py) et sa fenetre, puis relance C:\YouTube2\comfyui.bat et attend
              qu'il reponde (3 min au plus). Un rendu en cours est perdu : le worker reprend la tache.
- worker    : arret force (le bouton normal demande au worker de se relancer lui-meme apres sa tache en cours) : arrete le
              worker, ses sous-processus et sa fenetre, puis relance C:\YouTube2\worker.bat.
- dashboard : attend 3 s (le temps que la page recoive la reponse du bouton), arrete le serveur du port 3000 et sa fenetre,
              puis relance C:\YouTube2\dashboard.bat et attend qu'il ecoute (2 min au plus).
Les fenetres restees ouvertes apres un plantage (".bat" en pause) sont fermees aussi. Chaque programme est relance par
l'explorateur Windows : il ne depend ni de ce script ni du dashboard qui l'a appele.
Journal : C:\YouTube2\data\logs\restart.log. -DryRun : affiche ce qui serait arrete et relance, sans rien toucher.
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet("comfyui", "worker", "dashboard")][string]$Target,
    [string]$Root = "C:\YouTube2",
    [int]$DashboardPort = 3000,
    [string]$ComfyUrl = "http://127.0.0.1:8188",
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"
$Root = [System.IO.Path]::GetFullPath($Root)  # "C:/YouTube2" (dashboard) -> "C:\YouTube2" : explorer.exe veut des "\"
$logDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$logFile = Join-Path $logDir "restart.log"

function Write-Log([string]$Text) {
    if ($DryRun) { Write-Host "[essai] $Text"; return }  # Write-Host : hors du flux des valeurs de retour
    Add-Content -Path $logFile -Encoding UTF8 -Value ("{0:yyyy-MM-dd HH:mm:ss} [{1}] {2}" -f (Get-Date), $Target, $Text)
}

function Get-Procs { @(Get-CimInstance Win32_Process) }

function Get-Proc($All, [int]$Id) { $All | Where-Object { $_.ProcessId -eq $Id } | Select-Object -First 1 }

# Fenetre d'un programme : on remonte ses parents (python, uv, node, npm) jusqu'au premier cmd.exe qui n'est pas le shell
# de script de npm ("/d /s /c"), et jamais au-dela : la fenetre du lanceur, plus haut, a demarre les trois programmes.
function Get-WindowRoot($All, $Proc) {
    $cur = $Proc
    for ($i = 0; $i -lt 12; $i++) {
        $parent = Get-Proc $All $cur.ParentProcessId
        if (-not $parent -or $parent.Name -notin @("cmd.exe", "node.exe", "python.exe", "uv.exe", "worker.exe")) { return $cur }
        $cur = $parent
        if ($parent.Name -eq "cmd.exe" -and $parent.CommandLine -notmatch '/d /s /c') { return $cur }
    }
    return $cur
}

# Arrete chaque programme avec sa fenetre (taskkill /T : tous ses sous-processus avec lui), une seule fois par fenetre
function Stop-Programs($All, $Found, [string]$What) {
    $roots = @($Found | ForEach-Object { Get-WindowRoot $All $_ } | Sort-Object ProcessId -Unique)
    foreach ($r in $roots) {
        Write-Log ("{0} : arret du processus {1} ({2}) {3}" -f $What, $r.ProcessId, $r.Name, $r.CommandLine)
        if (-not $DryRun) { & taskkill.exe /PID $r.ProcessId /T /F 2>&1 | Out-Null }
    }
    return $(if ($DryRun) { 0 } else { $roots.Count })
}

function Start-Bat([string]$Bat) {
    if (-not (Test-Path $Bat)) { Write-Log "introuvable : $Bat"; return $false }
    Write-Log "relance : $Bat"
    if ($DryRun) { return $false }
    Start-Process -FilePath "explorer.exe" -ArgumentList "`"$Bat`""
    return $true
}

function Wait-Until([scriptblock]$Test, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (& $Test) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

Write-Log "debut"
switch ($Target) {
    "comfyui" {
        $all = Get-Procs
        $found = @($all | Where-Object {
            ($_.Name -eq "python.exe" -and $_.CommandLine -match 'ComfyUI[\\/]main\.py') -or
            ($_.Name -eq "cmd.exe" -and $_.CommandLine -match 'comfyui\.bat') })
        if ((Stop-Programs $all $found "ComfyUI") -gt 0) { Start-Sleep -Seconds 3 }
        if (Start-Bat (Join-Path $Root "comfyui.bat")) {
            $ok = Wait-Until { try { (Invoke-WebRequest -UseBasicParsing -Uri "$ComfyUrl/system_stats" -TimeoutSec 3).StatusCode -eq 200 } catch { $false } } 180
            Write-Log $(if ($ok) { "ComfyUI repond" } else { "ComfyUI ne repond toujours pas apres 3 min" })
        }
    }
    "worker" {
        $all = Get-Procs
        $found = @($all | Where-Object {
            ($_.Name -eq "python.exe" -and $_.CommandLine -match 'worker\.main|worker-venv\\Scripts\\worker') -or
            ($_.Name -eq "cmd.exe" -and $_.CommandLine -match 'worker\.bat|uv run --frozen worker') })
        if ((Stop-Programs $all $found "worker") -gt 0) { Start-Sleep -Seconds 2 }
        Start-Bat (Join-Path $Root "worker.bat") | Out-Null
    }
    "dashboard" {
        if (-not $DryRun) { Start-Sleep -Seconds 3 }
        $all = Get-Procs
        $found = @($all | Where-Object { $_.Name -eq "cmd.exe" -and ($_.CommandLine -match 'dashboard\.bat' -or
            ($_.CommandLine -match 'npm run dev' -and $_.CommandLine -match "--port $DashboardPort")) })
        $listen = Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listen) {
            $server = Get-Proc $all $listen.OwningProcess
            if ($server) { $found += $server }
        }
        if ((Stop-Programs $all $found "dashboard") -gt 0) { Start-Sleep -Seconds 2 }
        if (Start-Bat (Join-Path $Root "dashboard.bat")) {
            $ok = Wait-Until { [bool](Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue) } 120
            Write-Log $(if ($ok) { "dashboard en ecoute sur le port $DashboardPort" } else { "le dashboard n'ecoute toujours pas apres 2 min" })
        }
    }
}
Write-Log "fin"
