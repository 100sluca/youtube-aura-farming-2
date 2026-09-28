<#
Démarre YouTube Aura Farming, lancé par LANCER.bat (double-clic) : Docker et la base locale, ComfyUI, le worker et le
tableau de bord, puis ouvre http://localhost:3000 dans le navigateur et rappelle comment s'en servir.
Ce qui tourne déjà est réutilisé : relancer LANCER.bat ne démarre rien en double.
Les trois programmes tournent dans leurs fenêtres (réduites dans la barre des tâches) : C:\YouTube2\comfyui.bat,
worker.bat et dashboard.bat, les mêmes que relance le bouton « Redémarrer » de l'appli (launcher\restart.ps1).
#>

$outils = Join-Path $PSScriptRoot "outils.ps1"
. $outils

# Une clé Gemini collée dans l'appli (Réglages > Intelligence artificielle) est rangée, chiffrée, dans la table app_secrets
function Test-CleGeminiDansAppli {
    $service = Get-EnvValeur $EnvWorker "SUPABASE_SERVICE_ROLE_KEY"
    if (-not $service) { return $false }
    try {
        $r = Invoke-RestMethod -UseBasicParsing -TimeoutSec 15 -Headers @{ apikey = $service; Authorization = "Bearer $service" } `
            -Uri "http://127.0.0.1:54321/rest/v1/app_secrets?select=name&name=like.gemini_api_key*"
        return (@($r | Where-Object { $_ }).Count -gt 0)
    } catch { return $false }
}

Write-Titre "YouTube Aura Farming : démarrage"
Update-Chemins
Restore-Config

$manque = @()
if (-not (Test-Path -LiteralPath (Join-Path $Venv "Scripts\python.exe"))) { $manque += "le moteur Python" }
if (-not (Test-Path -LiteralPath (Join-Path $Front "node_modules\next\package.json"))) { $manque += "les modules du tableau de bord" }
if (-not (Test-Path -LiteralPath $EnvWorker) -or -not (Test-Path -LiteralPath $EnvFront)) { $manque += "les fichiers de réglages" }
if (-not (Test-Path -LiteralPath $LanceurWorker) -or -not (Test-Path -LiteralPath $LanceurDashboard)) { $manque += "les lanceurs de $YT2" }
if ($manque.Count) {
    Write-Erreur "L'installation n'est pas finie : il manque $($manque -join ', ')."
    Write-Info "Double-clique d'abord sur INSTALLER.bat (dans le dossier du projet), puis relance LANCER.bat."
    exit 1
}

# ---- 1. Base de données ---------------------------------------------------------------------------------------------

Write-Etape "1/4  Base de données (Docker)"
if (Test-Port 54322) { Write-Ok "Base déjà démarrée" }
else {
    if (-not (Start-DockerEtAttendre 4)) {
        Write-Erreur "Docker ne démarre pas."
        Write-Info "Ouvre Docker Desktop (menu Démarrer), attends « Engine running » en bas à gauche, puis relance LANCER.bat."
        Write-Info "Si ça ne vient pas, redémarre l'ordinateur."
        exit 1
    }
    if (-not (Sync-DossierSupabase)) { Write-Erreur "Copie du dossier supabase vers $SbWork impossible."; exit 1 }
    Write-Info "Démarrage de la base (30 secondes à 1 minute)…"
    if ((Invoke-Supabase @("start")) -ne 0) {
        Write-Erreur "La base n'a pas démarré (message ci-dessus). Redémarre l'ordinateur puis relance LANCER.bat."
        exit 1
    }
}
if (Sync-DossierSupabase) { $null = Invoke-Supabase @("migration", "up") -Silencieux }   # tables d'une nouvelle version
Write-Ok "Base prête"

# Clé Gemini (installation faite par INSTALLER.bat) : demandée avant de démarrer le worker, qui lit son .env au démarrage
$cleAjoutee = $false
if ((Test-Path -LiteralPath $Marqueur) -and -not (Get-EnvValeur $EnvWorker "GEMINI_API_KEY") -and -not (Test-CleGeminiDansAppli)) {
    Write-Etape "Clé API Gemini manquante"
    Write-Info "Sans elle, l'appli ne trouve pas d'idées et n'écrit pas de scripts (Entrée pour passer)."
    $cle = Read-CleGemini
    if ($cle) { Save-CleGemini $cle; $cleAjoutee = $true }
    else { Write-Info "Tu pourras la coller plus tard dans l'appli : Réglages > Intelligence artificielle." }
}

# ---- 2. ComfyUI -----------------------------------------------------------------------------------------------------

Write-Etape "2/4  ComfyUI (fabrique les images et les vidéos)"
if (Test-Port 8188) { Write-Ok "ComfyUI déjà lancé" }
elseif (@(Get-Processus "python.exe" 'ComfyUI[\\/]main\.py').Count) { Write-Ok "ComfyUI est en train de démarrer" }
elseif (Test-Path -LiteralPath $LanceurComfy) {
    Start-Process -FilePath $LanceurComfy -WorkingDirectory $YT2 -WindowStyle Minimized
    Write-Ok "ComfyUI démarre (fenêtre « ComfyUI » dans la barre des tâches)"
}
else { Write-Attention "ComfyUI n'est pas installé sur ce PC : pas de fabrication d'images ni de vidéos." }

# ---- 3. Worker ------------------------------------------------------------------------------------------------------

Write-Etape "3/4  Moteur (le « worker » : écrit, dessine, anime et monte les vidéos)"
$workers = @(Get-Processus "python.exe" 'worker\.main|worker-venv\\Scripts\\worker') + @(Get-Processus "cmd.exe" 'worker\.bat|uv run --frozen worker')
if ($workers.Count) {
    Write-Ok "Worker déjà lancé"
    if ($cleAjoutee) { Write-Attention "Pour qu'il prenne la nouvelle clé : dans l'appli, bouton « Machine » (à gauche) > Worker > Redémarrer." }
} else {
    Start-Process -FilePath $LanceurWorker -WorkingDirectory $YT2 -WindowStyle Minimized
    Write-Ok "Worker démarré (fenêtre « Worker » dans la barre des tâches)"
}

# ---- 4. Tableau de bord ---------------------------------------------------------------------------------------------

Write-Etape "4/4  Tableau de bord"
if (Test-Port $PortAppli) {
    # Le serveur du tableau de bord est un node.exe ; sa page peut mettre plus d'une minute à répondre s'il est occupé
    $occupant = Get-ProprietairePort $PortAppli
    if ($occupant -and $occupant.Name -ne "node.exe") {
        Write-Erreur "Le port $PortAppli est déjà pris par un autre programme ($($occupant.Name)) : ferme-le, puis relance LANCER.bat."
        exit 1
    }
    Write-Ok "Tableau de bord déjà lancé"
} else {
    Start-Process -FilePath $LanceurDashboard -WorkingDirectory $YT2 -WindowStyle Minimized
    Write-Info "Démarrage du tableau de bord (jusqu'à une minute)…"
    $fin = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $fin -and -not (Test-Port $PortAppli)) { Start-Sleep -Seconds 2; Write-Host "." -NoNewline }
    Write-Host ""
    if (-not (Test-Port $PortAppli)) {
        Write-Erreur "Le tableau de bord ne répond pas : ouvre sa fenêtre « Dashboard » (barre des tâches) pour lire le message."
        exit 1
    }
    Write-Ok "Tableau de bord prêt"
}
Start-Process $UrlAppli

# ---- Mode d'emploi --------------------------------------------------------------------------------------------------

Write-Titre "C'est parti : l'appli s'ouvre dans ton navigateur ($UrlAppli)"
Write-Host ""
Write-Info "Comment ça marche :"
Write-Info "  1. Création : choisis un thème, l'IA propose des idées de vidéos. Coche celles à fabriquer."
Write-Info "  2. L'IA écrit le script et dessine une image par scène (le « storyboard ») : quelques minutes."
Write-Info "  3. Regarde le storyboard puis clique sur « Valider et fabriquer » : clips, voix, musique et"
Write-Info "     montage se font tout seuls (30 minutes à 1 heure par vidéo, plus pour la toute première)."
Write-Info "  4. Bibliothèque : les vidéos terminées, à regarder et à télécharger. Le bouton « Tâches »,"
Write-Info "     en haut, montre ce qui est en cours."
Write-Host ""
Write-Info "Les fenêtres ComfyUI, Worker et Dashboard (barre des tâches) sont les moteurs : laisse-les ouvertes."
Write-Info "Pour tout arrêter : ferme-les. Pour relancer : LANCER.bat (ou le raccourci du Bureau)."
Write-Info "Vidéos et fichiers : $Donnees"
Write-Host ""
Write-Info "Tu peux fermer cette fenêtre : l'appli continue de tourner."
exit 0
