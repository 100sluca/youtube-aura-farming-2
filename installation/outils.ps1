<#
Chemins et fonctions communs à installer.ps1 (INSTALLER.bat) et lancer.ps1 (LANCER.bat).

Tout ce qui s'écrit vit dans C:\YouTube2 : environnement Python du worker, ComfyUI et ses modèles, voix, vidéos, copie de
travail de la base. Le dossier du projet ne reçoit que les deux fichiers de réglages (.env) et les modules du dashboard
(node_modules). C:\YouTube2 est le chemin attendu par le worker, le dashboard et launcher\restart.ps1.
Fichier en UTF-8 avec BOM : sans BOM, Windows PowerShell 5.1 lit les accents de travers.
#>

$ErrorActionPreference = "Continue"        # un programme externe qui échoue se lit dans $LASTEXITCODE
$ProgressPreference = "SilentlyContinue"   # la barre de progression de PowerShell 5.1 ralentit fortement les téléchargements
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

$Racine    = Split-Path -Parent $PSScriptRoot           # dossier du projet (celui de INSTALLER.bat)
$YT2       = "C:\YouTube2"
$Config    = Join-Path $YT2 "config"                   # copie des réglages : survit à un nouveau téléchargement du projet
$Marqueur  = Join-Path $Config "installe-par-INSTALLER.txt"
$Donnees   = Join-Path $YT2 "data"
$Venv      = Join-Path $YT2 "worker-venv"
$SbWork    = Join-Path $YT2 "supabase-workdir"
$Comfy     = Join-Path $YT2 "ComfyUI_windows_portable"
$Modeles   = Join-Path $YT2 "models"                   # voix Kokoro
$Telech    = Join-Path $YT2 "telechargements"
$Front     = Join-Path $Racine "apps\dashboard"
$Worker    = Join-Path $Racine "services\worker"
$EnvWorker = Join-Path $Worker ".env"
$EnvFront  = Join-Path $Front ".env.local"
$DockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
$PortAppli = 3000
$UrlAppli  = "http://localhost:$PortAppli"
$UrlCle    = "https://aistudio.google.com/apikey"
$LanceurComfy     = Join-Path $YT2 "comfyui.bat"
$LanceurWorker    = Join-Path $YT2 "worker.bat"
$LanceurDashboard = Join-Path $YT2 "dashboard.bat"

# uv installe lui-même Python 3.13 : tout reste dans C:\YouTube2
$env:UV_PROJECT_ENVIRONMENT = $Venv
$env:UV_PYTHON_INSTALL_DIR = Join-Path $YT2 "uv\python"
$env:UV_CACHE_DIR = Join-Path $YT2 "uv\cache"
$env:PYTHONDONTWRITEBYTECODE = "1"

# ---- Affichage ------------------------------------------------------------------------------------------------------

function Write-Titre([string]$Texte) {
    $ligne = "=" * 76
    Write-Host ""
    Write-Host $ligne -ForegroundColor DarkCyan
    Write-Host "  $Texte" -ForegroundColor Cyan
    Write-Host $ligne -ForegroundColor DarkCyan
}

function Write-Etape([string]$Texte) { Write-Host ""; Write-Host ">> $Texte" -ForegroundColor Cyan }
function Write-Ok([string]$Texte) { Write-Host "   OK   $Texte" -ForegroundColor Green }
function Write-Info([string]$Texte) { Write-Host "        $Texte" }
function Write-Attention([string]$Texte) { Write-Host "   /!\  $Texte" -ForegroundColor Yellow }
function Write-Erreur([string]$Texte) { Write-Host "   ERREUR  $Texte" -ForegroundColor Red }

function Read-OuiNon([string]$Question) {
    while ($true) {
        $r = "$(Read-Host "        $Question (O/N)")".Trim().ToLower()
        if (@("o", "oui", "y", "yes") -contains $r) { return $true }
        if (@("n", "non", "no") -contains $r) { return $false }
    }
}

# ---- Programmes -----------------------------------------------------------------------------------------------------

# Un logiciel installé pendant que la fenêtre est ouverte n'est pas encore dans son PATH : on le relit dans le registre,
# plus les dossiers où winget, Node.js, Docker et 7-Zip s'installent.
function Update-Chemins {
    $morceaux = @(
        [Environment]::GetEnvironmentVariable("Path", "Machine"),
        [Environment]::GetEnvironmentVariable("Path", "User"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"),
        (Join-Path $env:USERPROFILE ".local\bin"),
        (Join-Path $env:ProgramFiles "nodejs"),
        (Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"),
        (Join-Path $env:ProgramFiles "7-Zip")
    ) | Where-Object { $_ }
    $env:Path = $morceaux -join ";"
}

function Find-Outil([string]$Nom) {
    $c = Get-Command $Nom -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.Source }
    return $null
}

function Test-Port([int]$Numero) {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Numero -State Listen -ErrorAction Stop | Select-Object -First 1)
    } catch {
        return [bool](netstat -ano -p tcp | Select-String -Pattern ":$Numero\s+\S+\s+LISTENING")
    }
}

# À appeler dans @(…) : un seul processus trouvé revient seul, et PowerShell 5.1 ne sait pas compter un objet CIM seul
function Get-Processus([string]$Nom, [string]$Motif) {
    @(Get-CimInstance Win32_Process -Filter "Name='$Nom'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $Motif })
}

# Programme qui écoute sur ce port (processus Win32_Process), ou $null
function Get-ProprietairePort([int]$Numero) {
    try {
        $c = Get-NetTCPConnection -LocalPort $Numero -State Listen -ErrorAction Stop | Select-Object -First 1
        return Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue
    } catch { return $null }
}

# ---- Fichiers de réglages (.env) ------------------------------------------------------------------------------------

function Write-Texte([string]$Chemin, [string]$Texte) {
    $dossier = Split-Path -Parent $Chemin
    if ($dossier -and -not (Test-Path -LiteralPath $dossier)) { New-Item -ItemType Directory -Force -Path $dossier | Out-Null }
    [IO.File]::WriteAllText($Chemin, $Texte.TrimEnd() + "`r`n", (New-Object Text.UTF8Encoding($false)))
}

function Get-EnvValeur([string]$Fichier, [string]$Nom) {
    if (-not (Test-Path -LiteralPath $Fichier)) { return "" }
    foreach ($l in Get-Content -LiteralPath $Fichier -Encoding UTF8) {
        if ($l -match "^\s*$([regex]::Escape($Nom))\s*=(.*)$") {
            return ($Matches[1] -replace "\s+#.*$", "").Trim().Trim('"')
        }
    }
    return ""
}

function Set-EnvValeur([string]$Fichier, [string]$Nom, [string]$Valeur) {
    $lignes = New-Object System.Collections.Generic.List[string]
    if (Test-Path -LiteralPath $Fichier) { foreach ($l in Get-Content -LiteralPath $Fichier -Encoding UTF8) { $lignes.Add($l) } }
    $motif = "^\s*$([regex]::Escape($Nom))\s*="
    $trouve = $false
    for ($i = 0; $i -lt $lignes.Count; $i++) {
        if ($lignes[$i] -match $motif) { $lignes[$i] = "$Nom=$Valeur"; $trouve = $true }
    }
    if (-not $trouve) { $lignes.Add("$Nom=$Valeur") }
    Write-Texte $Fichier ($lignes -join "`r`n")
}

# Les réglages vivent dans le projet (là où le worker et le dashboard les lisent) et sont recopiés dans C:\YouTube2\config :
# un nouveau téléchargement du projet les retrouve (la clé de chiffrement CREDENTIALS_KEY ne doit jamais changer).
function Save-Config {
    New-Item -ItemType Directory -Force -Path $Config | Out-Null
    if (Test-Path -LiteralPath $EnvWorker) { Copy-Item -LiteralPath $EnvWorker -Destination (Join-Path $Config "worker.env") -Force }
    if (Test-Path -LiteralPath $EnvFront) { Copy-Item -LiteralPath $EnvFront -Destination (Join-Path $Config "dashboard.env.local") -Force }
}

function Restore-Config {
    $w = Join-Path $Config "worker.env"
    $d = Join-Path $Config "dashboard.env.local"
    if (-not (Test-Path -LiteralPath $EnvWorker) -and (Test-Path -LiteralPath $w)) { Copy-Item -LiteralPath $w -Destination $EnvWorker }
    if (-not (Test-Path -LiteralPath $EnvFront) -and (Test-Path -LiteralPath $d)) { Copy-Item -LiteralPath $d -Destination $EnvFront }
}

# ---- Clé Gemini -----------------------------------------------------------------------------------------------------

# "ok", "invalide" (Google la refuse) ou "inconnu" (pas de réponse : pas d'internet, Google indisponible…)
function Test-CleGemini([string]$Cle) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 -Headers @{ "x-goog-api-key" = $Cle } `
            -Uri "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1"
        if ($r.StatusCode -eq 200) { return "ok" }
        return "inconnu"
    } catch {
        $reponse = $_.Exception.Response
        if ($reponse -and @(400, 401, 403) -contains [int]$reponse.StatusCode) { return "invalide" }
        return "inconnu"
    }
}

function Read-CleGemini {
    Write-Info "La page pour créer ta clé s'ouvre dans le navigateur : $UrlCle"
    Write-Info "  1. Connecte-toi avec ton compte Google."
    Write-Info "  2. Clique sur « Create API key » (Créer une clé API), puis copie la clé (elle commence par AIza)."
    Write-Info "  3. Reviens dans cette fenêtre, fais un clic droit pour coller la clé, puis appuie sur Entrée."
    Start-Process $UrlCle | Out-Null
    for ($essai = 1; $essai -le 3; $essai++) {
        $cle = "$(Read-Host "        Ta clé Gemini (Entrée sans rien écrire = plus tard)")".Trim()
        if (-not $cle) { return "" }
        $verdict = Test-CleGemini $cle
        if ($verdict -eq "ok") { Write-Ok "Clé Gemini vérifiée auprès de Google."; return $cle }
        if ($verdict -eq "inconnu") {
            Write-Attention "Impossible de vérifier la clé pour l'instant (connexion internet ?) : elle est gardée telle quelle."
            return $cle
        }
        Write-Attention "Google refuse cette clé. Vérifie qu'elle est copiée en entier, puis colle-la de nouveau."
    }
    return ""
}

function Save-CleGemini([string]$Cle) {
    Set-EnvValeur $EnvWorker "GEMINI_API_KEY" $Cle
    Save-Config
}

# ---- Docker et base de données (Supabase en local) ------------------------------------------------------------------

function Test-DockerPret {
    $docker = Find-Outil "docker"
    if (-not $docker) { return $false }
    & $docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Start-DockerEtAttendre([int]$Minutes = 5) {
    if (Test-DockerPret) { return $true }
    if (-not (Test-Path -LiteralPath $DockerExe)) { return $false }
    Write-Info "Démarrage de Docker Desktop (1 à 2 minutes)…"
    Write-Info "S'il affiche des conditions d'utilisation : clique sur « Accept »."
    Write-Info "S'il propose de créer un compte ou de se connecter : clique sur « Skip » (ou « Continue without signing in »)."
    Start-Process -FilePath $DockerExe | Out-Null
    $fin = (Get-Date).AddMinutes($Minutes)
    while ((Get-Date) -lt $fin) {
        Start-Sleep -Seconds 5
        Update-Chemins
        if (Test-DockerPret) { Write-Host ""; return $true }
        Write-Host "." -NoNewline
    }
    Write-Host ""
    return $false
}

# La CLI Supabase travaille sur une copie du dossier supabase\ du projet (comme le lanceur de Luca)
function Sync-DossierSupabase {
    New-Item -ItemType Directory -Force -Path $SbWork | Out-Null
    & robocopy.exe (Join-Path $Racine "supabase") (Join-Path $SbWork "supabase") /MIR /XD .temp .branches /NFL /NDL /NJH /NJS /NP | Out-Null
    return ($LASTEXITCODE -lt 8)
}

# Affiche ce que dit la CLI (sauf -Silencieux) et renvoie seulement son code de sortie
function Invoke-Supabase([string[]]$Arguments, [switch]$Silencieux) {
    $npx = Find-Outil "npx.cmd"
    if (-not $npx) { Write-Erreur "Node.js (npx) introuvable."; return 1 }
    Push-Location $SbWork
    try {
        if ($Silencieux) { & $npx --yes supabase --workdir $SbWork @Arguments *> $null }
        else { & $npx --yes supabase --workdir $SbWork @Arguments | Out-Host }
    } finally { Pop-Location }
    return $LASTEXITCODE
}

# Adresses et clés de la base locale (supabase status -o env) : ANON_KEY, SERVICE_ROLE_KEY, API_URL…
function Get-SupabaseEnv {
    $valeurs = @{}
    $npx = Find-Outil "npx.cmd"
    if (-not $npx) { return $valeurs }
    Push-Location $SbWork
    try { $sortie = & $npx --yes supabase --workdir $SbWork status -o env 2>$null } finally { Pop-Location }
    foreach ($l in @($sortie)) {
        if ("$l" -match '^\s*([A-Z0-9_]+)\s*=\s*"?([^"]*)"?\s*$') { $valeurs[$Matches[1]] = $Matches[2] }
    }
    return $valeurs
}
