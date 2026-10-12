# 66 — FreeVideo (MiniMax H3 accéléré) : est-ce plus rapide chez nous ?

Question de Luca (05/10/2026) : FreeVideo (https://github.com/FlashML-org/FreeVideo) ferait des vidéos MiniMax H3
plus vite que notre ComfyUI. Étude faite sur le dépôt (code lu, pas encore installé) et sur nos temps réels.

## 1. Ce que c'est

- Moteur local pour **MiniMax H3 complet** (pas élagué), construit sur **VDN-H3** d'OpenVDN : H3 distillé en
  **8 passes** + attention « hybride » (fenêtre softmax + branche linéaire Video DeltaNet), annoncé aussi bon que
  H3 en 50 passes et meilleur que FastH3 en 4 passes.
- Se branche comme **nœud ComfyUI** (`FreeVideoGenerate` : texte, largeur, hauteur, durée, graine, première et
  dernière image, LoRA, « two-pass ») : notre worker pourrait l'appeler comme nos gabarits actuels.
- Le calcul tourne dans **son propre environnement Python** (`envs/unified`, torch 2.13 cu130 comme le nôtre) :
  il ne touche pas aux paquets de notre ComfyUI.
- Mémoire : les 50 blocs du modèle (FP8, 432 Mo chacun) sont répartis entre carte, RAM et disque et chargés à la
  volée ; minimum annoncé 8 Go de VRAM et 16 Go de RAM.
- Code Apache 2.0 ; poids sous la licence communautaire MiniMax H3, la même que notre H3 actuel.

## 2. Temps comparés

| Montage | Carte | Format | Durée | Temps | Calcul par seconde de vidéo |
|---|---|---|---|---|---|
| **Nous** (ComfyUI, H3 élagué GGUF Q4, 8 passes) | RTX 3070 8 Go + 32 Go | 480 × 832 | 5,2 s | **4 min 50 à 5 min 10** (40 clips du 04/10 au soir) | ≈ 57 s |
| FreeVideo (chiffre publié, deux passes) | RTX 4060 Ti 8 Go + 64 Go | 1344 × 768 | 10 s | 10 min 03 | ≈ 60 s |
| FreeVideo | RTX 4060 Ti 16 Go + 32 Go | 1344 × 768 | 10 s | 9 min 18 | ≈ 56 s |
| FreeVideo | RTX 5060 Ti 16 Go + 32 Go | 1344 × 768 | 10 s | 8 min 06 | ≈ 49 s |
| FreeVideo | RTX 5090 32 Go + 64 Go | 1344 × 768 | 10 s | 2 min 02 | ≈ 12 s |

Aucun chiffre publié pour une RTX 30.

## 3. Lecture

- **À taille égale, pas plus rapide.** Le même temps par seconde de vidéo que nous, mais avec 2,6 fois plus de
  pixels et le modèle complet. Le gain vient surtout du **FP8 natif** (RTX 40 et 50) et de l'attention allégée, qui
  pèse surtout en haute définition.
- **Sur notre RTX 3070 (Ampere)**, pas de calcul FP8 : FreeVideo garde les poids en FP8 et calcule en BF16 (prévu
  dans `hardware.py`). Le modèle complet est ≈ 1,8 fois plus gros que notre H3 élagué. Estimation : **≈ 5 min en
  480 × 832** (comme aujourd'hui) et **≈ 7 à 8 min pour 5 s en 768 × 1344** (deux passes : scène en basse
  définition, agrandissement du latent, 2 passes d'affinage). À vérifier par un essai.
- **Le vrai intérêt est la qualité** : H3 complet au lieu de l'élagué Q4, et la 768 × 1344 qu'on ne peut pas
  faire aujourd'hui (SeedVR2 coûtait 14 min 40 par clip de 4 s, docs/20).
- Inconnue : notre RAM (32 Go). Le test publié en 8 Go de VRAM avait 64 Go de RAM ; l'encodeur Qwen3-VL 32B
  (14,6 Go) doit aussi passer.

## 4. Ce qu'il faut pour l'essayer

| Élément | Taille | Déjà là ? |
|---|---|---|
| Paquet du modèle pour RTX 30/40 (`OpenVDN/vdn-minimax-h3-edge`) | 21,4 Go | non |
| VAE vidéo de H3 (h3-base) | ≈ 9,7 Go | non (notre VAE int8 est un autre fichier) |
| VAE audio + agrandisseur de latent | ≈ 1,2 Go | en partie |
| Encodeur `qwen3vl_32b_minimax_h3_nvfp4_awq` | 14,6 Go | **oui**, même fichier |
| Environnement Python de FreeVideo | ≈ 6 à 12 Go | non |

Total ≈ **38 à 44 Go**, alors que C: a **21,4 Go libres** au 05/10 (Corbeille vide, Temp 1,7 Go). Les plus gros
fichiers non utilisés depuis plusieurs jours : Wan 2.2 A14B High + Low (18 Go, 29/09), umt5 (6,3 Go, 29/09),
Flux.1 schnell Q8 (11,8 Go, 28/09). Le tri reste à Luca.

## 5. Essai prévu (si Luca valide)

1. Place libérée sur C:.
2. `git clone` dans `ComfyUI/custom_nodes`, réglages FreeVideo pour réutiliser nos modèles, téléchargement du reste.
3. File ComfyUI et tâches du worker vides ; même image et même prompt qu'un clip H3 déjà fait.
4. Trois clips : 480 × 832 une passe, 480 × 832 deux passes, 768 × 1344 deux passes. Temps, VRAM, RAM relevés.
5. Résultats dans `C:\YouTube2\bench\2026-10-05-freevideo` (+ `demo.json`), donc visibles dans
   Bibliothèque → Démos et essais, à côté du clip actuel.
6. Si c'est mieux : gabarits `freevideo_h3_i2v` / `flf2v` dans le worker et choix dans Réglages.
