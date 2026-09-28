<#
Télécharge les modèles de la voie « meilleure qualité sur 8 Go » (docs/12 §5) et les voix Kokoro.
À lancer soi-même, une fois de la place faite sur C: et ComfyUI installé dans C:\ComfyUI_windows_portable
(≈ 35 Go à écrire, jamais sur D: qui est un disque externe) :

    powershell -ExecutionPolicy Bypass -File services\worker\scripts\download_models.ps1 `
        -ComfyModels "C:\ComfyUI_windows_portable\ComfyUI\models" -Kokoro "C:\YouTube2\models"

Options : -SkipWan (pas le 14B), -SkipZImage (pas le modèle image), -SkipKokoro.
-Formats : seulement les modèles des formats visuels (docs/15 : chantiers en accéléré, visites de luxe), ≈ 39 Go :
musique ACE-Step 1.5 (10 Go), bruitages Stable Audio 3 small-sfx (3,5 Go), retouche Qwen-Image-Edit-2511 GGUF Q5
(25,5 Go avec son encodeur) ; -SkipMusic, -SkipSfx, -SkipEdit pour en retirer.
-Flux : seulement Flux.1 schnell GGUF Q8_0 et ses encodeurs (images du storyboard, alternative à Z-Image), ≈ 18 Go ;
son VAE est ae.safetensors, celui de Z-Image.
-Ltx : seulement LTX-Video 2B 0.9.8 distillé fp8 (animation rapide, à l'essai face à Wan), 4,5 Go ; il réutilise
l'encodeur T5 de Flux (le prendre aussi avec -Flux si absent).
-H3 : seulement MiniMax H3 élagué (animation, essai du 28/09, docs/20 et 21), ≈ 32,6 Go : GGUF Q4_K_M, encodeur
Qwen3-VL 32B en NVFP4 (décompressé en bf16 sur la RTX 3070), VAE vidéo int8 et audio, LoRA 8 passes.
-Post : seulement l'agrandissement SeedVR2 3B int8 et l'interpolation RIFE / FILM (workflows/post), ≈ 4 Go.
-Qwen2512 : seulement Qwen-Image 2512 GGUF Q4_K_M + LoRA Lightning 8 passes, ≈ 14,1 Go ; il reprend l'encodeur et
le VAE de Qwen-Image-Edit-2511 (-Formats s'ils manquent).
Reprend un téléchargement interrompu (curl -C -). En cas de 404, vérifier l'URL sur huggingface.co :
les dépôts renomment parfois leurs fichiers ; le nom attendu par le workflow est celui de la colonne « fichier ».
Le nœud ComfyUI-GGUF (city96) s'installe depuis ComfyUI Manager (« Install Custom Nodes », chercher GGUF).
#>
param(
    [string]$ComfyModels = "C:\ComfyUI_windows_portable\ComfyUI\models",
    [string]$Kokoro = "C:\YouTube2\models",
    [switch]$SkipWan,
    [switch]$SkipZImage,
    [switch]$SkipKokoro,
    [switch]$Formats,
    [switch]$SkipMusic,
    [switch]$SkipSfx,
    [switch]$SkipEdit,
    [switch]$Flux,
    [switch]$Ltx,
    [switch]$H3,
    [switch]$Post,
    [switch]$Qwen2512
)

$hf = "https://huggingface.co"
$files = @()
if ($Formats -or $Flux -or $Ltx -or $H3 -or $Post -or $Qwen2512) { $SkipWan = $true; $SkipZImage = $true; $SkipKokoro = $true }
if ($H3) {
    # MiniMax H3 (licence H3 Community : essais seulement, docs/20) ; version « élaguée » fl2va (image(s) → vidéo), GGUF
    # pour ComfyUI-GGUF ; l'encodeur voit aussi l'image de départ (partie vision), d'où le 32B officiel.
    # workflows/minimax_h3_i2v.json et minimax_h3_flf2v.json
    $files += @(
        @{ url = "$hf/Abiray/MiniMax-H3-Pruned-GGUF/resolve/main/MiniMax-H3-FL2VA-Pruned-Q4_K_M.gguf"; dir = "unet"; size = "11,6 Go" },
        @{ url = "$hf/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"; dir = "text_encoders"; size = "15,7 Go" },
        @{ url = "$hf/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_int8_convrot.safetensors"; dir = "vae"; size = "2,8 Go" },
        @{ url = "$hf/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors"; dir = "vae"; size = "0,6 Go" },
        @{ url = "$hf/Comfy-Org/MiniMax-H3/resolve/main/loras/minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"; dir = "loras"; size = "2,0 Go" }
    )
}
if ($Post) {
    # SeedVR2 3B int8 (Apache 2.0) : agrandissement ×2 en une passe ; RIFE 4.26 (MIT) et FILM (Apache 2.0) :
    # images intermédiaires ; nœuds natifs de ComfyUI 0.37, workflows/post/seedvr2_rife.json
    $files += @(
        @{ url = "$hf/Comfy-Org/SeedVR2/resolve/main/diffusion_models/seedvr2_3b_int8_convrot.safetensors"; dir = "diffusion_models"; size = "3,5 Go" },
        @{ url = "$hf/Comfy-Org/SeedVR2/resolve/main/vae/seedvr2_ema_vae_fp16.safetensors"; dir = "vae"; size = "0,5 Go" },
        @{ url = "$hf/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/rife_v4.26.safetensors"; dir = "frame_interpolation"; size = "0,02 Go" },
        @{ url = "$hf/Comfy-Org/frame_interpolation/resolve/main/frame_interpolation/film_net_fp16.safetensors"; dir = "frame_interpolation"; size = "0,07 Go" }
    )
}
if ($Qwen2512) {
    # Qwen-Image 2512 (Apache 2.0) : 998 contre 940 pour Z-Image aux votes à l'aveugle (docs/20) ; workflows/qwen_image_2512.json
    $files += @(
        @{ url = "$hf/unsloth/Qwen-Image-2512-GGUF/resolve/main/qwen-image-2512-Q4_K_M.gguf"; dir = "unet"; size = "13,2 Go" },
        @{ url = "$hf/lightx2v/Qwen-Image-2512-Lightning/resolve/main/Qwen-Image-2512-Lightning-8steps-V1.0-bf16.safetensors"; dir = "loras"; size = "0,85 Go" }
    )
}
if ($Ltx) {
    # LTX-Video 2B 0.9.8 distillé fp8 (licence LTX Open Weights : gratuite sous 10 M$ de chiffre d'affaires), VAE inclus ;
    # tient entier dans les 8 Go ; workflows/ltxv_2b_i2v.json (8 passes, nœuds natifs de ComfyUI)
    $files += @{ url = "$hf/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.8-distilled-fp8.safetensors"; dir = "checkpoints"; size = "4,5 Go" }
}
if ($Flux) {
    # Flux.1 schnell (Apache 2.0) en GGUF Q8_0 : qualité quasi identique à l'original, 4 passes ; ne tient pas entier
    # dans les 8 Go, ComfyUI décharge le reste en RAM. Encodeur T5 en fp8 « scaled » (plus fidèle que le fp8 simple).
    # workflows/flux1_schnell_gguf.json
    $files += @(
        @{ url = "$hf/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q8_0.gguf"; dir = "unet"; size = "12,7 Go" },
        @{ url = "$hf/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn_scaled.safetensors"; dir = "text_encoders"; size = "5,2 Go" },
        @{ url = "$hf/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"; dir = "text_encoders"; size = "0,25 Go" }
    )
}
if ($Formats -and -not $SkipMusic) {
    # ACE-Step 1.5 turbo, tout-en-un (DiT 2B + encodeurs Qwen 0,6B et 1,7B + VAE) : MIT, sorties utilisables
    # commercialement ; workflows/audio/ace_step_15_music.json
    $files += @{ url = "$hf/Comfy-Org/ace_step_1.5_ComfyUI_files/resolve/main/checkpoints/ace_step_1.5_turbo_aio.safetensors"; dir = "checkpoints"; size = "10,0 Go" }
}
if ($Formats -and -not $SkipSfx) {
    # Stable Audio 3 small-sfx + encodeur T5Gemma : licence communautaire Stability (gratuite sous 1 M$ de chiffre
    # d'affaires, INSCRIPTION GRATUITE OBLIGATOIRE : https://stability.ai/community-license) ; workflows/audio/stable_audio_3_sfx.json
    $files += @(
        @{ url = "$hf/Comfy-Org/stable-audio-3/resolve/main/checkpoints/stable_audio_3_small_sfx.safetensors"; dir = "checkpoints"; size = "2,3 Go" },
        @{ url = "$hf/Comfy-Org/stable-audio-3/resolve/main/text_encoders/t5gemma_b_b_ul2.safetensors"; dir = "text_encoders"; size = "1,2 Go" }
    )
}
if ($Formats -and -not $SkipEdit) {
    # Qwen-Image-Edit-2511 (Apache 2.0) en GGUF Q5_K_M : l'int8 (20,5 Go) + son encodeur saturerait les 32 Go de RAM ;
    # workflows qwen_image_edit_2511(_4step).json
    $files += @(
        @{ url = "$hf/unsloth/Qwen-Image-Edit-2511-GGUF/resolve/main/qwen-image-edit-2511-Q5_K_M.gguf"; dir = "unet"; size = "15,0 Go" },
        @{ url = "$hf/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors"; dir = "text_encoders"; size = "9,4 Go" },
        @{ url = "$hf/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors"; dir = "vae"; size = "0,25 Go" },
        @{ url = "$hf/lightx2v/Qwen-Image-Edit-2511-Lightning/resolve/main/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"; dir = "loras"; size = "0,85 Go" }
    )
}
if (-not $SkipWan) {
    $files += @(
        # Wan 2.2 I2V 14B, deux experts (bruit fort puis faible), GGUF Q4_K_M ≈ 9 Go chacun
        @{ url = "$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/HighNoise/Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf"; dir = "unet"; size = "9 Go" },
        @{ url = "$hf/QuantStack/Wan2.2-I2V-A14B-GGUF/resolve/main/LowNoise/Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf";   dir = "unet"; size = "9 Go" },
        # LoRA lightx2v 4 passes (sans CFG) : 20 × plus rapide que 20 passes avec CFG
        @{ url = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"; dir = "loras"; size = "0,6 Go" },
        @{ url = "$hf/Comfy-Org/Wan_2.2_ComfyUI_Repackaged/resolve/main/split_files/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors";  dir = "loras"; size = "0,6 Go" },
        # VAE Wan 2.1 : c'est celui du 14B (le 5B utilise wan2.2_vae, déjà présent)
        @{ url = "$hf/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors"; dir = "vae"; size = "0,25 Go" }
    )
}
if (-not $SkipZImage) {
    $files += @(
        # Z-Image Turbo (Alibaba, Apache 2.0) : images photoréalistes en 8 passes, workflow zimage_turbo.json.
        # Versions int8 / fp8 (ComfyUI 0.37+) : tiennent dans les 8 Go de la carte, moitié moins de disque que le bf16.
        @{ url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/diffusion_models/z_image_turbo_int8_convrot.safetensors"; dir = "diffusion_models"; size = "6,2 Go" },
        @{ url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/text_encoders/qwen_3_4b_fp8_mixed.safetensors"; dir = "text_encoders"; size = "5,6 Go" },
        @{ url = "$hf/Comfy-Org/z_image_turbo/resolve/main/split_files/vae/ae.safetensors"; dir = "vae"; size = "0,3 Go" }
    )
}
if (-not $SkipKokoro) {
    $files += @(
        @{ url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"; dir = "__kokoro"; size = "0,33 Go" },
        @{ url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin";  dir = "__kokoro"; size = "0,03 Go" }
    )
}

$failed = @()
foreach ($f in $files) {
    $name = Split-Path $f.url -Leaf
    $dest = if ($f.dir -eq "__kokoro") { Join-Path $Kokoro $name } else { Join-Path (Join-Path $ComfyModels $f.dir) $name }
    New-Item -ItemType Directory -Force (Split-Path $dest) | Out-Null
    Write-Host "→ $name ($($f.size)) → $dest"
    & curl.exe -L --fail --retry 3 -C - -o $dest $f.url
    if ($LASTEXITCODE -ne 0) { $failed += $f.url; Write-Host "   ÉCHEC ($LASTEXITCODE)" -ForegroundColor Red }
}
if ($failed.Count) {
    Write-Host "`nÀ vérifier sur huggingface.co (nom de fichier ou dossier changé) :" -ForegroundColor Yellow
    $failed | ForEach-Object { Write-Host "  $_" }
    exit 1
}
if ($Formats) {
    Write-Host "`nTerminé. Redémarrer ComfyUI, puis : yt2 music generate --mood luxury ; yt2 sfx generate (docs/15)."
    if (-not $SkipSfx) { Write-Host "Stable Audio 3 : inscription gratuite obligatoire avant tout usage commercial : https://stability.ai/community-license" -ForegroundColor Yellow }
    exit 0
}
if ($Flux -or $Ltx -or $H3 -or $Qwen2512) {
    Write-Host "`nTerminé. Dashboard : Réglages → Modèles de génération (images : Flux.1 schnell GGUF, Qwen-Image 2512 ; animation : LTX-Video 2B, MiniMax H3)."
    exit 0
}
if ($Post) {
    Write-Host "`nTerminé. Agrandissement + interpolation : workflows/post/seedvr2_rife.json (docs/20 §1.1-1.2)."
    exit 0
}
Write-Host "`nTerminé. Dans services\worker\.env : VIDEO_PROVIDER=comfy_wan22_i2v_4step et COMFY_IMAGE_WORKFLOW=zimage_turbo, puis redémarrer ComfyUI."
