<#
Installe les moteurs de voix de docs/18-voix.md, chacun dans son environnement Python sous C:\YouTube2\tts\<moteur>
(jamais dans celui du worker ni dans celui de ComfyUI, qui imposent d'autres versions de PyTorch) :

    powershell -ExecutionPolicy Bypass -File services\worker\scripts\install_tts.ps1 [-Engine qwen3,pocket,supertonic]

Exige uv ; Python 3.12 est installe par uv dans C:\YouTube2\uv\python. Tailles (25/09/2026) :
- qwen3      : Qwen3-TTS 12 Hz, Apache 2.0. Base 0.6B (2,5 Go) + VoiceDesign 1.7B (4,5 Go) + PyTorch CUDA 12.8 (~5 Go).
- pocket     : Kyutai Pocket TTS 3.3.0, CC BY 4.0, modele francais (0,22 Go) + PyTorch CPU (~1 Go).
- supertonic : Supertonic 3, OpenRAIL-M, ONNX (0,41 Go) + onnxruntime.
- eval       : pas un moteur, les outils du banc d'essai des voix (scripts/bench_voice.py eval, docs/29) :
               faster-whisper + Whisper large-v3-turbo (1,6 Go) sur le processeur. A demander : -Engine eval.
Ensuite, carte graphique libre (~5 min) : creer les voix Qwen d'apres leur description (catalog.json), puis essayer :
    C:\YouTube2\tts\qwen3\venv\Scripts\python.exe services\worker\tts_runners\qwen3_design.py `
        services\worker\workflows\catalog.json --free-comfy http://127.0.0.1:8188
    yt2 voice list ; yt2 voice say qwen3:narrateur ; yt2 voice say pocket:estelle ; yt2 voice say supertonic:F2
#>
param(
    [string[]]$Engine = @("qwen3", "pocket", "supertonic"),
    [string]$Root = "C:\YouTube2"
)

$ErrorActionPreference = "Stop"
$env:UV_CACHE_DIR = "$Root\uv\cache"
$env:UV_PYTHON_INSTALL_DIR = "$Root\uv\python"
$env:HF_HOME = "$Root\tts\hf-cache"

function Invoke-Step([string]$Label, [scriptblock]$Block) {
    Write-Host "-> $Label"
    & $Block
    if ($LASTEXITCODE -ne 0) { throw "Echec : $Label (code $LASTEXITCODE)" }
}

function New-EngineVenv([string]$Name) {
    $dir = "$Root\tts\$Name"
    New-Item -ItemType Directory -Force "$dir\models" | Out-Null
    $py = "$dir\venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { Invoke-Step "$Name : environnement Python 3.12" { uv venv "$dir\venv" --python 3.12 --seed -q } }
    return $py
}

foreach ($name in $Engine) {
    switch ($name) {
        "qwen3" {
            $py = New-EngineVenv "qwen3"
            New-Item -ItemType Directory -Force "$Root\tts\qwen3\voices" | Out-Null
            Invoke-Step "qwen3 : PyTorch CUDA 12.8" { uv pip install --python $py -q torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128 }
            Invoke-Step "qwen3 : qwen-tts" { uv pip install --python $py -q qwen-tts==0.1.1 "huggingface_hub[cli]" }
            foreach ($repo in @("Qwen3-TTS-12Hz-0.6B-Base", "Qwen3-TTS-12Hz-1.7B-VoiceDesign")) {
                Invoke-Step "qwen3 : modele $repo" { & $py -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/$repo', local_dir=r'$Root\tts\qwen3\models\$repo')" }
            }
        }
        "pocket" {
            $py = New-EngineVenv "pocket"
            Invoke-Step "pocket : PyTorch CPU" { uv pip install --python $py -q torch --index-url https://download.pytorch.org/whl/cpu }
            Invoke-Step "pocket : pocket-tts" { uv pip install --python $py -q pocket-tts==3.3.0 soundfile }
            # Telecharge le modele francais et la voix estelle (depot sans clonage, sans compte Hugging Face)
            Invoke-Step "pocket : modele francais" { & $py -c "from pocket_tts import TTSModel; m = TTSModel.load_model(language='french'); m.get_state_for_audio_prompt('estelle')" }
        }
        "supertonic" {
            $py = New-EngineVenv "supertonic"
            Invoke-Step "supertonic : paquet" { uv pip install --python $py -q supertonic==1.3.1 }
            Invoke-Step "supertonic : modele" { & $py -c "from supertonic import TTS; TTS(model='supertonic-3', model_dir=r'$Root\tts\supertonic\models\supertonic-3', auto_download=True)" }
        }
        "eval" {
            $py = New-EngineVenv "eval"
            Invoke-Step "eval : faster-whisper, num2words" { uv pip install --python $py -q faster-whisper num2words }
            Invoke-Step "eval : modele Whisper large-v3-turbo (1,6 Go)" { & $py -c "from faster_whisper.utils import download_model; print(download_model('large-v3-turbo'))" }
        }
        default { throw "Moteur inconnu : $name (qwen3, pocket, supertonic, eval)" }
    }
}
Write-Host "`nTermine. Voix Qwen a creer (voir l'en-tete du script), puis : yt2 voice list"
