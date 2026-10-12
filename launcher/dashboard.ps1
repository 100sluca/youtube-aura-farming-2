<#
Sert le dashboard en version de production sur http://localhost:3000 et le tient à jour tout seul
(docs/56-dashboard-rapide.md). Lancé par C:\YouTube2\dashboard.bat, que relance aussi le bouton « Redémarrer le
dashboard » (launcher\restart.ps1).

- Au démarrage : sert tout de suite la dernière version construite (apps\dashboard\.next-live\a ou \b) ; s'il n'y en a
  pas encore, la construit d'abord (une vingtaine de secondes).
- Toutes les 10 s : si le code du dashboard a changé (src, public, package.json, next.config.ts, .env.local…) et n'a
  plus bougé depuis 30 s, construit la nouvelle version dans l'autre dossier pendant que l'ancienne sert, puis bascule
  (environ une seconde de coupure). Une construction ratée laisse l'ancienne version en place, s'affiche dans le bloc
  « Machine » de la barre latérale et la suivante part au prochain changement du code.
- Pas de construction tant que la mémoire libre est sous 3 Go (gros rendu ComfyUI) : elle attend.
- Repli : si aucune version n'a jamais pu être construite, lance « next dev » (lent, mais l'appli s'ouvre).
- Le serveur arrêté de l'extérieur (plantage) est relancé.
État lu par le dashboard : apps\dashboard\.next-live\status.json ; journal : C:\YouTube2\data\logs\dashboard.log.
Fichier en UTF-8 avec BOM : sans BOM, Windows PowerShell 5.1 lit les accents de travers.
#>
param(
    [int]$Port = 3000,
    [string]$Root = "C:\YouTube2",
    [int]$QuietSeconds = 30,
    [double]$MinFreeGb = 3
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

$App = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\apps\dashboard"))
$Live = Join-Path $App ".next-live"
$NextBin = Join-Path $App "node_modules\next\dist\bin\next"
$StateFile = Join-Path $Live "state.json"    # version servie : dossier, empreinte du code construit, date
$StatusFile = Join-Path $Live "status.json"  # lu par le bloc « Machine »
$LogDir = Join-Path ([IO.Path]::GetFullPath($Root)) "data\logs"
$LogFile = Join-Path $LogDir "dashboard.log"
$Utf8 = New-Object Text.UTF8Encoding $false
New-Item -ItemType Directory -Force $Live, $LogDir | Out-Null
$env:NEXT_TELEMETRY_DISABLED = "1"
$Host.UI.RawUI.WindowTitle = "Dashboard - YouTube 2.0"

# Clé fixe des actions serveur, propre à ce PC (jamais dans le dépôt) : sans elle, chaque construction renomme toutes les
# actions et les boutons d'une page restée ouverte échouent après une mise à jour ; avec elle, leurs noms ne changent pas.
$KeyFile = Join-Path $Live "actions.key"
if (-not (Test-Path -LiteralPath $KeyFile)) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [IO.File]::WriteAllText($KeyFile, [Convert]::ToBase64String($bytes), $Utf8)
}
$env:NEXT_SERVER_ACTIONS_ENCRYPTION_KEY = (Get-Content -LiteralPath $KeyFile -Raw).Trim()

function Write-Log([string]$Text, [string]$Color = "Gray") {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text
    Write-Host $line -ForegroundColor $Color
    try { Add-Content -Path $LogFile -Value $line -Encoding UTF8 } catch { }
}

$Node = (Get-Command node.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if (-not $Node) { Write-Log "node.exe introuvable : Node.js n'est pas installé ou pas dans le PATH." Red; exit 1 }
if (-not (Test-Path -LiteralPath $NextBin)) { Write-Log "Modules du dashboard absents ($NextBin) : lancer « npm install » dans $App." Red; exit 1 }

# ---- État partagé avec le dashboard ---------------------------------------------------------------------------------

$Status = [ordered]@{
    mode = "starting"      # production | dev | starting
    slot = $null           # a | b : dossier servi
    builtAt = $null        # date de construction de la version servie
    building = $false
    waiting = $null        # code (le code bouge encore) | memoire (moins de 3 Go libres)
    error = $null          # fin du journal de la dernière construction ratée
    errorAt = $null
    supervisorPid = $PID
    updatedAt = $null
}

function Save-Status {
    $Status.updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    try { [IO.File]::WriteAllText($StatusFile, ($Status | ConvertTo-Json -Depth 3), $Utf8) } catch { }
}

function Read-State {
    try { if (Test-Path -LiteralPath $StateFile) { return (Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json) } } catch { }
    return $null
}

function Save-State([string]$Slot, [string]$Fingerprint, [string]$BuiltAt) {
    $state = [ordered]@{ slot = $Slot; fingerprint = $Fingerprint; builtAt = $BuiltAt }
    [IO.File]::WriteAllText($StateFile, ($state | ConvertTo-Json), $Utf8)
}

function Test-Slot([string]$Slot) { return [bool]$Slot -and (Test-Path -LiteralPath (Join-Path $Live "$Slot\BUILD_ID")) }

# ---- Empreinte du code : chemins, dates et tailles des fichiers qui changent la version construite -------------------

$WatchedDirs = @("src", "public")
$WatchedFiles = @("package.json", "package-lock.json", "next.config.ts", "postcss.config.mjs", "tsconfig.json", ".env", ".env.local")

function Get-CodeFingerprint {
    $items = New-Object System.Collections.Generic.List[string]
    foreach ($d in $WatchedDirs) {
        $p = Join-Path $App $d
        if (Test-Path -LiteralPath $p) {
            Get-ChildItem -LiteralPath $p -Recurse -File -ErrorAction SilentlyContinue |
                ForEach-Object { $items.Add(("{0}|{1}|{2}" -f $_.FullName, $_.LastWriteTimeUtc.Ticks, $_.Length)) }
        }
    }
    foreach ($f in $WatchedFiles) {
        $p = Join-Path $App $f
        if (Test-Path -LiteralPath $p) { $i = Get-Item -LiteralPath $p; $items.Add(("{0}|{1}|{2}" -f $i.FullName, $i.LastWriteTimeUtc.Ticks, $i.Length)) }
    }
    $items.Sort()
    $md5 = [Security.Cryptography.MD5]::Create()
    return [BitConverter]::ToString($md5.ComputeHash($Utf8.GetBytes(($items -join "`n")))).Replace("-", "")
}

function Get-FreeGb { return [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 1) }

# ---- Port et serveur ------------------------------------------------------------------------------------------------

function Test-Port {
    $client = New-Object Net.Sockets.TcpClient
    try { return $client.ConnectAsync("127.0.0.1", $Port).Wait(500) -and $client.Connected } catch { return $false } finally { $client.Dispose() }
}

function Wait-Port([bool]$Open, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ((Test-Port) -eq $Open) { return $true }
        Start-Sleep -Milliseconds 300
    }
    return $false
}

# Un ancien serveur du dashboard (next dev lancé à la main, fenêtre restée ouverte) libère le port ; jamais un autre programme
function Clear-Port {
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listen) { return $true }
    $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listen.OwningProcess)" -ErrorAction SilentlyContinue
    if ($owner -and $owner.Name -eq "node.exe" -and $owner.CommandLine -match 'next') {
        Write-Log "Port $Port tenu par un ancien serveur du dashboard (processus $($owner.ProcessId)) : arrêt." Yellow
        & taskkill.exe /PID $owner.ProcessId /T /F 2>&1 | Out-Null
        return (Wait-Port $false 15)
    }
    $name = if ($owner) { $owner.Name } else { "processus $($listen.OwningProcess)" }
    Write-Log "Le port $Port est pris par un autre programme ($name) : fermer ce programme puis relancer dashboard.bat." Red
    return $false
}

$Server = $null

function Start-Server([string]$Mode, [string]$Slot) {
    if ($Mode -eq "production") {
        $env:YT2_DIST_DIR = ".next-live/$Slot"   # lu par next.config.ts : dossier de la version servie
        $argList = @("`"$NextBin`"", "start", "--port", "$Port")
    } else {
        Remove-Item Env:YT2_DIST_DIR -ErrorAction SilentlyContinue
        $argList = @("`"$NextBin`"", "dev", "--port", "$Port")
    }
    $p = Start-Process -FilePath $Node -ArgumentList $argList -WorkingDirectory $App -NoNewWindow -PassThru
    $null = $p.Handle  # sans cela, ExitCode reste vide une fois le processus fini (PowerShell 5.1)
    Remove-Item Env:YT2_DIST_DIR -ErrorAction SilentlyContinue
    $script:Server = $p
    $Status.mode = $Mode
    $Status.slot = $(if ($Mode -eq "production") { $Slot } else { $null })
    Save-Status
    if (Wait-Port $true 90) {
        $what = if ($Mode -eq "production") { "version de production ($Slot)" } else { "mode développement (repli, lent)" }
        Write-Log "Dashboard prêt sur http://localhost:$Port : $what" Green
    } else {
        Write-Log "Le serveur ne répond pas sur le port $Port après 90 s." Red
    }
}

function Stop-Server {
    if ($script:Server -and -not $script:Server.HasExited) {
        & taskkill.exe /PID $script:Server.Id /T /F 2>&1 | Out-Null
        try { $script:Server.WaitForExit(10000) | Out-Null } catch { }
    }
    $null = Wait-Port $false 15
}

# ---- Construction ---------------------------------------------------------------------------------------------------

function Invoke-Build([string]$Slot) {
    Copy-Item -LiteralPath (Join-Path $App "tsconfig.json") -Destination (Join-Path $App "tsconfig.live.json") -Force
    $out = Join-Path $Live "build-$Slot.log"
    $err = Join-Path $Live "build-$Slot.err.log"
    $Status.building = $true
    $Status.waiting = $null
    Save-Status
    Write-Log "Construction de la nouvelle version (.next-live\$Slot)…" Cyan
    $started = Get-Date
    $env:YT2_DIST_DIR = ".next-live/$Slot"
    $p = Start-Process -FilePath $Node -ArgumentList @("`"$NextBin`"", "build") -WorkingDirectory $App -NoNewWindow -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError $err
    $null = $p.Handle
    Remove-Item Env:YT2_DIST_DIR -ErrorAction SilentlyContinue
    try { $p.PriorityClass = "BelowNormal" } catch { }  # ses sous-processus en héritent : le worker et ComfyUI passent avant
    $p.WaitForExit()
    $Status.building = $false
    $seconds = [int]((Get-Date) - $started).TotalSeconds
    if ($p.ExitCode -eq 0 -and (Test-Slot $Slot)) {
        Write-Log "Nouvelle version construite en $seconds s." Green
        $Status.error = $null
        $Status.errorAt = $null
        Save-Status
        return $true
    }
    $tail = @(Get-Content -LiteralPath $out, $err -Encoding UTF8 -ErrorAction SilentlyContinue) -replace "\x1b\[[0-9;]*m", "" |
        Where-Object { $_.Trim() } | Select-Object -Last 25
    $Status.error = ($tail -join "`n")
    $Status.errorAt = (Get-Date).ToUniversalTime().ToString("o")
    Save-Status
    Write-Log "Construction ratée (code $($p.ExitCode), $seconds s) : la version en place continue de servir. Fin du journal :" Red
    $tail | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
    return $false
}

# ---- Démarrage ------------------------------------------------------------------------------------------------------

# Un seul superviseur à la fois : un second arrêterait le serveur du premier, qui le relancerait, et ainsi de suite
try {
    $previous = (Get-Content -LiteralPath $StatusFile -Raw -Encoding UTF8 -ErrorAction Stop | ConvertFrom-Json).supervisorPid
    $other = Get-CimInstance Win32_Process -Filter "ProcessId = $([int]$previous)" -ErrorAction SilentlyContinue
    if ($previous -and $previous -ne $PID -and $other -and $other.CommandLine -match 'dashboard\.ps1') {
        Write-Log "Le dashboard est déjà servi par un autre superviseur (processus $previous) : rien à faire ici." Yellow
        exit 0
    }
} catch { }

Write-Log "Superviseur du dashboard démarré (processus $PID), dossier $App"
if (-not (Clear-Port)) { exit 1 }

$state = Read-State
$slot = $null
$builtFp = $null
$failedFp = $null
if ($state -and (Test-Slot $state.slot)) {
    $slot = [string]$state.slot
    $builtFp = [string]$state.fingerprint
    $Status.builtAt = $state.builtAt
    Start-Server "production" $slot
} else {
    Write-Log "Aucune version construite : première construction (une vingtaine de secondes)." Cyan
    $fp = Get-CodeFingerprint
    if (Invoke-Build "a") {
        $slot = "a"
        $builtFp = $fp
        $Status.builtAt = (Get-Date).ToUniversalTime().ToString("o")
        Save-State $slot $builtFp $Status.builtAt
        Start-Server "production" $slot
    } else {
        $failedFp = $fp
        Start-Server "dev" $null
    }
}

# ---- Surveillance ---------------------------------------------------------------------------------------------------

$lastFp = $null
$changedAt = Get-Date
$memoryLogged = $false
while ($true) {
    Start-Sleep -Seconds 10

    if ($Server.HasExited) {
        Write-Log "Le serveur s'est arrêté (code $($Server.ExitCode)) : relance." Yellow
        if (Clear-Port) { Start-Server $Status.mode $slot }
        continue
    }

    $fp = Get-CodeFingerprint
    if ($fp -ne $lastFp) { $lastFp = $fp; $changedAt = Get-Date }
    if ($fp -eq $builtFp -or $fp -eq $failedFp) {
        # code revenu à la version servie (faute retirée) : l'erreur de construction ne la concerne plus
        $stale = $fp -eq $builtFp -and $Status.error
        if ($Status.waiting -or $stale) {
            $Status.waiting = $null
            if ($stale) { $Status.error = $null; $Status.errorAt = $null; $failedFp = $null }
            Save-Status
        }
        continue
    }
    if (((Get-Date) - $changedAt).TotalSeconds -lt $QuietSeconds) {
        if ($Status.waiting -ne "code") { $Status.waiting = "code"; Save-Status }
        continue
    }
    $free = Get-FreeGb
    if ($free -lt $MinFreeGb) {
        if (-not $memoryLogged) { Write-Log "Code changé, mais $free Go de mémoire libre : construction remise à plus tard." Yellow; $memoryLogged = $true }
        if ($Status.waiting -ne "memoire") { $Status.waiting = "memoire"; Save-Status }
        continue
    }
    $memoryLogged = $false

    $next = if ($slot -eq "a") { "b" } else { "a" }
    if (Invoke-Build $next) {
        $builtFp = $fp   # empreinte prise avant la construction : un changement pendant celle-ci en relance une autre
        $failedFp = $null
        Stop-Server
        $slot = $next
        $Status.builtAt = (Get-Date).ToUniversalTime().ToString("o")
        Save-State $slot $builtFp $Status.builtAt
        Start-Server "production" $slot
    } else {
        $failedFp = $fp
    }
}
