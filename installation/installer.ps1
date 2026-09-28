<#
Installe YouTube Aura Farming sur un PC Windows. Lancé par INSTALLER.bat (double-clic) ; mode d'emploi : README.md.

À relancer sans crainte : ce qui est déjà fait est sauté et un téléchargement coupé reprend où il s'était arrêté.
  1. vérification du PC (carte NVIDIA, mémoire, disque)
  2. clé API Gemini (idées et scripts)
  3. logiciels manquants, par winget : Node.js, uv (qui installe Python), FFmpeg, Docker Desktop, 7-Zip
  4. moteur Python du worker (uv, Python 3.13)          5. modules du tableau de bord (npm)
  6. voix Kokoro                                         7. ComfyUI, son nœud GGUF et les modèles (≈ 43 Go)
  8. base de données locale (Docker + Supabase)          9. lanceurs dans C:\YouTube2 et raccourci sur le Bureau
Option -SansComfyUI : ni ComfyUI ni modèles (l'appli s'ouvre, mais ne fabrique ni images ni vidéos).
#>
param([switch]$SansComfyUI)

$outils = Join-Path $PSScriptRoot "outils.ps1"
. $outils

# Modèles des réglages par défaut de l'appli : images Z-Image Turbo, clips Wan 2.2 14B en 4 passes (GGUF), voix Kokoro.
# Tailles exactes en octets : un fichier complet est sauté, un fichier coupé reprend.
$hf = "https://huggingface.co"
$ModelesComfy = @(
    @{ Dossier = "unet"; Taille = 9651728896; Url = "$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf" },
    @{ Dossier = "unet"; Taille = 9651728896; Url = "$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf" },
    @{ Dossier = "loras"; Taille = 1226977424; Url = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors" },
    @{ Dossier = "loras"; Taille = 1226977424; Url = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors" },
    @{ Dossier = "vae"; Taille = 253815318; Url = "$hf/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors" },
    @{ Dossier = "text_encoders"; Taille = 6735906897; Url = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors" },
    @{ Dossier = "diffusion_models"; Taille = 6201001296; Url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors" },
    @{ Dossier = "text_encoders"; Taille = 5631994051; Url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors" },
    @{ Dossier = "vae"; Taille = 335304388; Url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors" }
)
$kokoro = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
$ModelesVoix = @(
    @{ Taille = 325532387; Url = "$kokoro/kokoro-v1.0.onnx" },
    @{ Taille = 28214398; Url = "$kokoro/voices-v1.0.bin" }
)
$Liens = @{
    "Node.js"        = "https://nodejs.org/fr/download (version LTS)"
    "uv"             = "https://docs.astral.sh/uv/getting-started/installation/"
    "FFmpeg"         = "https://www.gyan.dev/ffmpeg/builds/"
    "Docker Desktop" = "https://www.docker.com/products/docker-desktop/"
    "7-Zip"          = "https://www.7-zip.org/"
}

# ---- Outils de l'installeur -----------------------------------------------------------------------------------------

function Stop-Installation([string]$Message) {
    Write-Erreur $Message
    Write-Info "Relance INSTALLER.bat une fois le problème réglé : il reprendra là où il s'est arrêté."
    exit 1
}

# curl.exe est fourni avec Windows : reprise d'un fichier coupé (-C -), plusieurs essais
function Get-Fichier([string]$Url, [string]$Destination, [long]$Taille = 0) {
    $nom = Split-Path -Leaf $Destination
    if ($Taille -gt 0 -and (Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -eq $Taille) {
        Write-Ok "$nom (déjà téléchargé)"
        return $true
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    $poids = ""
    if ($Taille -gt 0) { $poids = " ({0:N1} Go)" -f ($Taille / 1GB) }
    Write-Info "Téléchargement de $nom$poids…"
    for ($essai = 1; $essai -le 5; $essai++) {
        $options = @("-L", "--fail", "--retry", "5", "--retry-delay", "10", "--connect-timeout", "30", "-o", $Destination)
        if ($Taille -gt 0) { $options += @("-C", "-") }
        elseif (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Force }
        & curl.exe @options $Url
        $code = $LASTEXITCODE
        $longueur = 0
        if (Test-Path -LiteralPath $Destination) { $longueur = (Get-Item -LiteralPath $Destination).Length }
        if ($code -eq 0 -or ($Taille -gt 0 -and $longueur -eq $Taille)) {
            if ($Taille -gt 0 -and $longueur -ne $Taille) { Write-Attention "$nom : taille inattendue ($longueur octets au lieu de $Taille), fichier gardé." }
            else { Write-Ok $nom }
            return $true
        }
        if ($Taille -gt 0 -and $longueur -gt $Taille) { Remove-Item -LiteralPath $Destination -Force }  # abîmé : on repart de zéro
        Write-Attention "Téléchargement interrompu (code $code). Nouvel essai dans 15 secondes ($essai sur 5)…"
        Start-Sleep -Seconds 15
    }
    Write-Erreur "Impossible de télécharger $nom. Vérifie ta connexion internet."
    return $false
}

function Test-Node {
    $node = Find-Outil "node"
    if (-not $node) { return $false }
    $version = "$(& $node --version 2>$null)".Trim().TrimStart("v")
    $majeure = 0
    [void][int]::TryParse(($version -split "\.")[0], [ref]$majeure)
    return ($majeure -ge 20)   # Next.js 16 demande Node.js 20 ou plus
}

function Install-Winget([string]$Nom, [string]$Id) {
    Write-Info "Installation de $Nom… (si Windows demande l'autorisation, clique sur « Oui »)"
    & winget install -e --id $Id --source winget --accept-source-agreements --accept-package-agreements | Out-Host
    Update-Chemins
}

function New-Secret([int]$Octets = 32) {
    $b = New-Object byte[] $Octets
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    return [Convert]::ToBase64String($b)
}

# Crée les deux fichiers de réglages s'ils n'existent pas (les clés de la base s'ajoutent à l'étape 8). Fichiers en ASCII :
# le worker les lit dans l'encodage de Windows.
function Initialize-Reglages {
    Restore-Config
    $cred = Get-EnvValeur $EnvWorker "CREDENTIALS_KEY"
    if (-not $cred) { $cred = Get-EnvValeur $EnvFront "CREDENTIALS_KEY" }
    if (-not $cred) { $cred = New-Secret 32 }   # chiffre les clés et les jetons YouTube enregistrés dans la base
    if (-not (Test-Path -LiteralPath $EnvWorker)) {
        Write-Texte $EnvWorker (@(
            "# Reglages du worker ecrits par INSTALLER.bat (copie dans C:\YouTube2\config). Ceux faits dans l'appli",
            "# (menu Reglages) priment sur ce fichier. Tous les reglages possibles : .env.example a la racine du projet.",
            "DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres",
            "SUPABASE_URL=http://127.0.0.1:54321",
            "SUPABASE_SERVICE_ROLE_KEY=",
            "WORKER_ID=pc-$("$env:COMPUTERNAME".ToLower())",
            "DATA_DIR=C:/YouTube2/data",
            "LLM_PROVIDER=gemini",
            "LLM_FALLBACKS=gemini",
            "GEMINI_API_KEY=",
            "VIDEO_PROVIDER=comfy_wan22_i2v_4step",
            "COMFY_BASE_URL=http://127.0.0.1:8188",
            "COMFY_IMAGE_WORKFLOW=zimage_turbo",
            "TTS_PROVIDER=kokoro",
            "KOKORO_MODEL_PATH=C:/YouTube2/models/kokoro-v1.0.onnx",
            "KOKORO_VOICES_PATH=C:/YouTube2/models/voices-v1.0.bin",
            "CREDENTIALS_KEY=$cred",
            "AUTO_PRODUCE=0",
            "ALERT_EMAIL_TO=",
            "WIKIPEDIA_USER_AGENT=`"youtube-aura-farming/1.0 (https://github.com/100sluca/youtube-aura-farming)`""
        ) -join "`r`n")
    }
    if (-not (Test-Path -LiteralPath $EnvFront)) {
        Write-Texte $EnvFront (@(
            "# Reglages du tableau de bord ecrits par INSTALLER.bat (copie dans C:\YouTube2\config).",
            "NEXT_PUBLIC_MOCK=0",
            "DASHBOARD_AUTH=none",
            "NEXT_PUBLIC_APP_URL=$UrlAppli",
            "NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY=",
            "SUPABASE_SERVICE_ROLE_KEY=",
            "CREDENTIALS_KEY=$cred",
            "OAUTH_STATE_SECRET=$(New-Secret 24)",
            "GOOGLE_CLIENT_ID=",
            "GOOGLE_CLIENT_SECRET="
        ) -join "`r`n")
    }
    Save-Config
}

function Install-ComfyUI {
    $python = Join-Path $Comfy "python_embeded\python.exe"
    if (Test-Path -LiteralPath $python) { Write-Ok "ComfyUI déjà installé ($Comfy)"; return $true }
    # Archive « nvidia » de la dernière version publiée ; son nom et sa taille sont lus sur GitHub quand c'est possible
    $url = "https://github.com/Comfy-Org/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
    $taille = 0
    try {
        $version = Invoke-RestMethod -UseBasicParsing -TimeoutSec 30 -Uri "https://api.github.com/repos/Comfy-Org/ComfyUI/releases/latest"
        $fichier = @($version.assets | Where-Object { $_.name -eq "ComfyUI_windows_portable_nvidia.7z" })[0]
        if ($fichier) { $url = $fichier.browser_download_url; $taille = [long]$fichier.size }
    } catch { }
    $archive = Join-Path $Telech "ComfyUI_windows_portable_nvidia.7z"
    if (-not (Get-Fichier $url $archive $taille)) { return $false }
    Write-Info "Décompression de ComfyUI (2 à 5 minutes)…"
    $septZip = Join-Path $env:ProgramFiles "7-Zip\7z.exe"
    if (Test-Path -LiteralPath $septZip) { & $septZip x $archive "-o$YT2" -y | Out-Null }
    else { & tar.exe -xf $archive -C $YT2 | Out-Null }
    if (-not (Test-Path -LiteralPath $python)) {
        Write-Erreur "La décompression de ComfyUI a échoué. Installe 7-Zip ($($Liens["7-Zip"]))."
        return $false
    }
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue   # 1,8 Go rendus
    # Dernière version stable (les réglages de l'appli ont été faits sur ComfyUI 0.37.2)
    Write-Info "Mise à jour de ComfyUI vers sa dernière version stable…"
    Push-Location (Join-Path $Comfy "update")
    & cmd.exe /c "update_comfyui_stable.bat sans-pause" | Out-Host
    Pop-Location
    Write-Ok "ComfyUI installé ($Comfy)"
    return $true
}

# Nœud personnalisé ComfyUI-GGUF (city96) : il lit les modèles vidéo compressés (.gguf) de Wan 2.2
function Install-NoeudGGUF {
    $dossier = Join-Path $Comfy "ComfyUI\custom_nodes\ComfyUI-GGUF"
    $python = Join-Path $Comfy "python_embeded\python.exe"
    if (-not (Test-Path -LiteralPath (Join-Path $dossier "nodes.py"))) {
        $zip = Join-Path $Telech "ComfyUI-GGUF.zip"
        if (-not (Get-Fichier "https://github.com/city96/ComfyUI-GGUF/archive/refs/heads/main.zip" $zip 0)) { return $false }
        $tmp = Join-Path $Telech "ComfyUI-GGUF-extrait"
        Remove-Item -LiteralPath $tmp, $dossier -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $source = @(Get-ChildItem -LiteralPath $tmp -Directory)[0]
        if (-not $source) { Write-Erreur "Archive du nœud GGUF illisible."; return $false }
        Move-Item -LiteralPath $source.FullName -Destination $dossier
        Remove-Item -LiteralPath $tmp, $zip -Recurse -Force -ErrorAction SilentlyContinue
    }
    & $python -s -m pip install --disable-pip-version-check -r (Join-Path $dossier "requirements.txt") | Out-Host
    if ($LASTEXITCODE -ne 0) { Write-Erreur "Installation des dépendances du nœud GGUF impossible."; return $false }
    Write-Ok "Nœud ComfyUI-GGUF prêt"
    return $true
}

# Lanceurs .bat : fins de ligne CRLF et page de codes de la console (un dossier « Jérôme » reste lisible pour cmd.exe)
function Write-Bat([string]$Chemin, [string[]]$Lignes) {
    $oem = [Text.Encoding]::GetEncoding([Globalization.CultureInfo]::CurrentCulture.TextInfo.OEMCodePage)
    [IO.File]::WriteAllText($Chemin, ($Lignes -join "`r`n") + "`r`n", $oem)
}

# ---- 0. Garde-fous --------------------------------------------------------------------------------------------------

Write-Titre "YouTube Aura Farming : installation"
Write-Info "Projet : $Racine"
Write-Info "Tout ce qui se télécharge va dans $YT2 (environ 55 Go au total)."
Write-Info "Tu peux fermer cette fenêtre et relancer INSTALLER.bat quand tu veux : il reprend où il s'était arrêté."

# Une installation faite à la main (celle de Luca) n'est jamais touchée
if ((Test-Path -LiteralPath $LanceurWorker) -and -not (Test-Path -LiteralPath $Marqueur)) {
    Write-Erreur "Ce PC a déjà une installation de YouTube 2.0 faite à la main dans $YT2."
    Write-Info "L'installeur s'arrête pour ne rien écraser. Pour démarrer l'appli : LANCER.bat."
    exit 1
}
if (-not (Test-Path -LiteralPath (Join-Path $Worker "pyproject.toml")) -or -not (Test-Path -LiteralPath (Join-Path $Front "package.json"))) {
    Stop-Installation "Dossier du projet incomplet ($Racine). Retélécharge le ZIP et extrais-le en entier (clic droit > Extraire tout)."
}
New-Item -ItemType Directory -Force -Path $YT2, $Config, $Telech, $Modeles, $Donnees | Out-Null
Write-Texte $Marqueur "Installation par INSTALLER.bat (YouTube Aura Farming) depuis $Racine, dernier passage le $(Get-Date -Format 'yyyy-MM-dd HH:mm')."

# Fichiers venus d'internet (ZIP) : Windows ne redemandera plus l'autorisation pour les lanceurs
foreach ($dossier in @($Racine, $PSScriptRoot, (Join-Path $Racine "launcher"))) {
    Get-ChildItem -LiteralPath $dossier -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue
}

# ---- 1. Le PC -------------------------------------------------------------------------------------------------------

Write-Etape "1/9  Vérification du PC"
if (-not [Environment]::Is64BitOperatingSystem) { Stop-Installation "Il faut Windows 10 ou 11 en 64 bits." }
$ramGo = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
$libreGo = [math]::Floor((Get-PSDrive C).Free / 1GB)
Write-Info "$((Get-CimInstance Win32_OperatingSystem).Caption), mémoire vive $ramGo Go, disque C: $libreGo Go libres"
$gpu = $null
$nvsmi = Find-Outil "nvidia-smi"
if ($nvsmi) {
    $ligne = @(& $nvsmi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits 2>$null)[0]
    if ($ligne) {
        $p = @("$ligne" -split ",\s*") + @("", "", "")
        $vram = 0.0
        [void][double]::TryParse($p[1].Trim(), [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$vram)
        $pilote = 0
        [void][int]::TryParse(($p[2].Trim() -split "\.")[0], [ref]$pilote)
        $gpu = @{ Nom = $p[0].Trim(); VramGo = [math]::Round($vram / 1024); Pilote = $p[2].Trim(); PiloteMajeur = $pilote }
    }
}
if ($gpu) {
    Write-Ok "Carte graphique : $($gpu.Nom), $($gpu.VramGo) Go, pilote $($gpu.Pilote)"
    if ($gpu.VramGo -lt 8) { Write-Attention "Moins de 8 Go de mémoire vidéo : les vidéos risquent d'échouer (8 Go ou plus conseillés)." }
    if ($gpu.PiloteMajeur -gt 0 -and $gpu.PiloteMajeur -lt 580) {
        Write-Attention "Pilote NVIDIA trop ancien pour ComfyUI (il faut la version 580 ou plus)."
        Write-Info "Mets-le à jour avant de lancer l'appli : https://www.nvidia.com/fr-fr/drivers/ (ou l'appli NVIDIA)."
    }
} elseif (-not $SansComfyUI) {
    Write-Attention "Aucune carte graphique NVIDIA trouvée : ComfyUI, qui fabrique les images et les vidéos, en a besoin."
    Write-Info "(Si tu as une carte NVIDIA, installe d'abord son pilote : https://www.nvidia.com/fr-fr/drivers/)"
    if (-not (Read-OuiNon "Installer quand même, sans fabrication d'images ni de vidéos ?")) { exit 1 }
    $SansComfyUI = $true
}
if ($ramGo -lt 30 -and -not $SansComfyUI) { Write-Attention "32 Go de mémoire vive sont conseillés : avec moins, les vidéos risquent d'échouer." }

# ---- 2. Clé Gemini --------------------------------------------------------------------------------------------------

Write-Etape "2/9  Clé API Gemini (gratuite : c'est l'IA qui trouve les idées et écrit les scripts)"
Initialize-Reglages
$cleGemini = Get-EnvValeur $EnvWorker "GEMINI_API_KEY"
if ($cleGemini) { Write-Ok "Clé déjà enregistrée (pour la changer : Réglages > Intelligence artificielle, dans l'appli)." }
else {
    $cleGemini = Read-CleGemini
    if ($cleGemini) { Save-CleGemini $cleGemini }
    else { Write-Attention "Pas de clé pour l'instant : LANCER.bat te la redemandera." }
}

# ---- 3. Logiciels ---------------------------------------------------------------------------------------------------

Write-Etape "3/9  Logiciels nécessaires (Python n'est pas à installer : uv s'en occupe)"
Update-Chemins
$winget = Find-Outil "winget"
$logiciels = @(
    @{ Nom = "Node.js"; Id = "OpenJS.NodeJS.LTS"; Test = { Test-Node } },
    @{ Nom = "uv"; Id = "astral-sh.uv"; Test = { [bool](Find-Outil "uv") } },
    @{ Nom = "FFmpeg"; Id = "Gyan.FFmpeg"; Test = { [bool](Find-Outil "ffmpeg") } },
    @{ Nom = "Docker Desktop"; Id = "Docker.DockerDesktop"; Test = { Test-Path -LiteralPath $DockerExe } }
)
if (-not $SansComfyUI -and -not (Test-Path -LiteralPath (Join-Path $Comfy "python_embeded\python.exe"))) {
    $logiciels += @{ Nom = "7-Zip"; Id = "7zip.7zip"; Test = { Test-Path -LiteralPath (Join-Path $env:ProgramFiles "7-Zip\7z.exe") } }
}
$manquants = @()
foreach ($l in $logiciels) {
    if (& $l.Test) { Write-Ok "$($l.Nom) déjà installé"; continue }
    if ($winget) { Install-Winget $l.Nom $l.Id }
    if (& $l.Test) { Write-Ok "$($l.Nom) installé" } else { $manquants += $l }
}
if ($manquants.Count) {
    Write-Erreur "Ces logiciels n'ont pas pu s'installer tout seuls :"
    foreach ($l in $manquants) { Write-Info "- $($l.Nom) : $($Liens[$l.Nom])" }
    if (-not $winget) { Write-Info "(winget, l'installeur de Windows, manque : https://apps.microsoft.com/detail/9NBLGGH4NNS1)" }
    Stop-Installation "Installe-les avec ces liens (en gardant les choix proposés par défaut)."
}

# ---- 4. Moteur Python -----------------------------------------------------------------------------------------------

Write-Etape "4/9  Moteur de l'appli (le « worker », en Python)"
Push-Location $Worker
& (Find-Outil "uv") sync --frozen --extra tts --extra web --python 3.13
$code = $LASTEXITCODE
Pop-Location
if ($code -ne 0) { Stop-Installation "L'installation du moteur Python a échoué (message ci-dessus)." }
Write-Ok "Moteur prêt ($Venv)"

# ---- 5. Tableau de bord ---------------------------------------------------------------------------------------------

Write-Etape "5/9  Tableau de bord (modules Node.js)"
$trace = Join-Path $Front "node_modules\.installe-par-INSTALLER.txt"
$empreinte = (Get-FileHash -LiteralPath (Join-Path $Front "package-lock.json") -Algorithm SHA256).Hash
if ((Test-Path -LiteralPath $trace) -and "$(Get-Content -LiteralPath $trace -Raw)".Trim() -eq $empreinte) {
    Write-Ok "Modules déjà installés"
} else {
    $npm = Find-Outil "npm.cmd"
    Push-Location $Front
    & $npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { Write-Attention "npm ci a échoué, nouvel essai avec npm install…"; & $npm install --no-audit --no-fund }
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { Stop-Installation "L'installation des modules du tableau de bord a échoué (message ci-dessus)." }
    Write-Texte $trace $empreinte
    Write-Ok "Modules installés"
}

# ---- 6. Voix --------------------------------------------------------------------------------------------------------

Write-Etape "6/9  Voix de narration (Kokoro, 0,35 Go)"
foreach ($m in $ModelesVoix) {
    if (-not (Get-Fichier $m.Url (Join-Path $Modeles (Split-Path -Leaf $m.Url)) $m.Taille)) { Stop-Installation "Voix Kokoro non téléchargées." }
}

# ---- 7. ComfyUI et modèles ------------------------------------------------------------------------------------------

Write-Etape "7/9  ComfyUI et les modèles d'images et de vidéos (environ 43 Go : c'est la partie longue)"
if ($SansComfyUI) {
    Write-Attention "Sauté : l'appli trouvera des idées et écrira des scripts, mais ne fabriquera ni images ni vidéos."
} else {
    $reste = [long]0
    foreach ($m in $ModelesComfy) {
        $f = Join-Path (Join-Path $Comfy "ComfyUI\models\$($m.Dossier)") (Split-Path -Leaf $m.Url)
        $deja = [long]0
        if (Test-Path -LiteralPath $f) { $deja = (Get-Item -LiteralPath $f).Length }
        $reste += [math]::Max([long]0, $m.Taille - $deja)
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Comfy "python_embeded\python.exe"))) { $reste += 9GB }   # archive + ComfyUI décompressé
    $besoin = $reste + 5GB   # + la base de données et un peu de marge
    $libre = (Get-PSDrive C).Free
    if ($libre -lt $besoin) {
        Stop-Installation ("Pas assez de place sur le disque C: : il faut {0:N0} Go libres, il y en a {1:N0}. Libère de la place (Paramètres > Système > Stockage)." -f ($besoin / 1GB), ($libre / 1GB))
    }
    if (-not (Install-ComfyUI)) { Stop-Installation "ComfyUI n'a pas pu être installé." }
    if (-not (Install-NoeudGGUF)) { Stop-Installation "Le nœud GGUF de ComfyUI n'a pas pu être installé." }
    $i = 0
    foreach ($m in $ModelesComfy) {
        $i++
        Write-Info "Modèle $i sur $($ModelesComfy.Count)"
        $dest = Join-Path (Join-Path $Comfy "ComfyUI\models\$($m.Dossier)") (Split-Path -Leaf $m.Url)
        if (-not (Get-Fichier $m.Url $dest $m.Taille)) { Stop-Installation "Modèle non téléchargé." }
    }
}

# ---- 8. Base de données ---------------------------------------------------------------------------------------------

Write-Etape "8/9  Base de données locale (Docker)"
if (-not (Start-DockerEtAttendre 6)) {
    Write-Erreur "Docker ne répond pas."
    Write-Info "1. Redémarre l'ordinateur (Docker en a souvent besoin juste après son installation)."
    Write-Info "2. Ouvre Docker Desktop (menu Démarrer), accepte les conditions, et attends que la baleine soit prête"
    Write-Info "   (« Engine running » en bas à gauche). S'il demande de mettre à jour WSL, accepte."
    Write-Info "3. Relance INSTALLER.bat : il reprendra ici, sans rien retélécharger."
    exit 1
}
Write-Ok "Docker est prêt"
if (-not (Sync-DossierSupabase)) { Stop-Installation "Copie du dossier supabase vers $SbWork impossible." }
if (Test-Port 54322) { Write-Ok "Base déjà démarrée" }
else {
    Write-Info "Démarrage de la base. La première fois : environ 3 Go à télécharger, plusieurs minutes…"
    if ((Invoke-Supabase @("start")) -ne 0) {
        Stop-Installation "La base n'a pas démarré (message ci-dessus). Si ça recommence, redémarre l'ordinateur."
    }
}
$null = Invoke-Supabase @("migration", "up") -Silencieux   # tables ajoutées par une nouvelle version du projet
$base = Get-SupabaseEnv
$anon = $base["ANON_KEY"]; if (-not $anon) { $anon = $base["PUBLISHABLE_KEY"] }
$service = $base["SERVICE_ROLE_KEY"]; if (-not $service) { $service = $base["SECRET_KEY"] }
if (-not $anon -or -not $service) { Stop-Installation "Impossible de lire les clés de la base locale (npx supabase status)." }
Set-EnvValeur $EnvFront "NEXT_PUBLIC_SUPABASE_ANON_KEY" $anon
Set-EnvValeur $EnvFront "SUPABASE_SERVICE_ROLE_KEY" $service
Set-EnvValeur $EnvWorker "SUPABASE_SERVICE_ROLE_KEY" $service
Save-Config
Write-Ok "Base prête et réglages écrits"

# ---- 9. Lanceurs ----------------------------------------------------------------------------------------------------

Write-Etape "9/9  Lanceurs"
# Les programmes lancés depuis l'explorateur ne voient pas toujours le PATH mis à jour par winget : on l'écrit en dur
$dossiers = @(@(foreach ($o in @("uv", "node", "ffmpeg", "docker")) { $p = Find-Outil $o; if ($p) { Split-Path -Parent $p } }) | Select-Object -Unique)
$path = "set `"PATH=$(($dossiers + @('%PATH%')) -join ';')`""
if (Test-Path -LiteralPath (Join-Path $Comfy "python_embeded\python.exe")) {
    # --cache-none et --fast-disk : moins de mémoire vive (réglages de Luca, docs/20) ; seulement si ComfyUI les connaît
    $cli = "$(Get-Content -LiteralPath (Join-Path $Comfy "ComfyUI\comfy\cli_args.py") -Raw -ErrorAction SilentlyContinue)"
    $options = "--windows-standalone-build"
    foreach ($o in @("--cache-none", "--fast-disk")) { if ($cli.Contains("`"$o`"")) { $options += " $o" } }
    Write-Bat $LanceurComfy @(
        "@echo off",
        "title ComfyUI - YouTube Aura Farming",
        "rem Cree par INSTALLER.bat : fabrique les images et les videos (relance par le worker s'il ne repond plus).",
        "cd /d `"$Comfy`"",
        ".\python_embeded\python.exe -s ComfyUI\main.py $options",
        "pause"
    )
}
Write-Bat $LanceurWorker @(
    "@echo off",
    "title Worker - YouTube Aura Farming",
    "rem Cree par INSTALLER.bat : le moteur qui ecrit, dessine, anime et monte les videos.",
    $path,
    "set `"UV_PROJECT_ENVIRONMENT=$Venv`"",
    "set `"UV_PYTHON_INSTALL_DIR=$env:UV_PYTHON_INSTALL_DIR`"",
    "set `"UV_CACHE_DIR=$env:UV_CACHE_DIR`"",
    "set `"PYTHONDONTWRITEBYTECODE=1`"",
    "cd /d `"$Worker`"",
    "uv run --frozen worker",
    "pause"
)
Write-Bat $LanceurDashboard @(
    "@echo off",
    "title Dashboard - YouTube Aura Farming",
    "rem Cree par INSTALLER.bat : le tableau de bord, $UrlAppli",
    $path,
    "cd /d `"$Front`"",
    "call npm run dev -- --port $PortAppli",
    "pause"
)
Write-Ok "Lanceurs écrits dans $YT2"
try {
    $raccourci = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "YouTube Aura Farming.lnk"))
    $raccourci.TargetPath = Join-Path $Racine "LANCER.bat"
    $raccourci.WorkingDirectory = $Racine
    $icone = Join-Path $Front "src\app\favicon.ico"
    if (Test-Path -LiteralPath $icone) { $raccourci.IconLocation = "$icone,0" }
    $raccourci.Save()
    Write-Ok "Raccourci « YouTube Aura Farming » créé sur le Bureau"
} catch { Write-Attention "Raccourci non créé sur le Bureau (pas grave : LANCER.bat fait pareil)." }

# ---- Fin ------------------------------------------------------------------------------------------------------------

Write-Titre "Installation terminée !"
Write-Info "Pour démarrer l'appli : double-clique sur « YouTube Aura Farming » (Bureau) ou sur LANCER.bat."
if (-not $cleGemini) { Write-Attention "Il manque la clé Gemini : LANCER.bat te la demandera." }
if ($SansComfyUI) { Write-Attention "Installée sans ComfyUI : pas de fabrication d'images ni de vidéos sur ce PC." }
Write-Host ""
if (Read-OuiNon "Démarrer l'appli maintenant ?") { & (Join-Path $PSScriptRoot "lancer.ps1") }
exit 0
