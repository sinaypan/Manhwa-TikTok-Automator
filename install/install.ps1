<#
Installe Manhwa Studio (lancé par Installer.bat, à la racine du projet).

    Installer.bat                  demande « complet » ou « léger »
    Installer.bat -Profil complet  tout : le Studio et les modèles IA locaux (carte NVIDIA de 6 Go ou plus)
    Installer.bat -Profil leger    le Studio seul : lecture du texte, voix de base, vidéo (n'importe quel PC)
    Installer.bat -SansModeles     les modèles se téléchargeront au premier usage au lieu de maintenant

Relancer l'installateur met tout à jour sans rien perdre : les chapitres (inbox/), la clé (.env)
et les modèles déjà téléchargés (.cache/) restent.
#>
param(
    [ValidateSet("", "complet", "leger")] [string]$Profil = "",
    [switch]$SansModeles,    # les modèles se téléchargeront au premier usage
    [switch]$SansSons,       # pas de bibliothèque Sonniss (≈ 2 Go)
    [switch]$SansRaccourci,
    [switch]$SansCarte       # installer comme sur un PC sans carte NVIDIA (pour essayer)
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$Watch = [Diagnostics.Stopwatch]::StartNew()
$PaddleIndex = "https://www.paddlepaddle.org.cn/packages/stable/cu126/"
$TorchIndex = "https://download.pytorch.org/whl/cu124"

function Step($text) { Write-Host ""; Write-Host "== $text  ($([int]$Watch.Elapsed.TotalMinutes) min)" -ForegroundColor Cyan }
function Note($text) { Write-Host "   $text" -ForegroundColor DarkGray }
function Run {
    # une commande ; si elle échoue, on s'arrête en le disant
    & $args[0] @($args | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) { throw "La commande a échoué : $($args -join ' ')" }
}
function Python($venv) { Join-Path $Root "$venv\Scripts\python.exe" }
function NewVenv($venv) {
    if (Test-Path (Python $venv)) { Note "$venv existe déjà : mis à jour" }
    else { Run uv venv --python 3.12 $venv }
}

Write-Host "Manhwa Studio : installation" -ForegroundColor Green

# ---------- 1. uv : installe Python 3.12 et les bibliothèques, bien plus vite que pip ----------
Step "1/7  uv (gestionnaire de Python)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Note "uv absent : installation depuis astral.sh (le site officiel de uv)"
    powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv ne s'est pas installé : voir https://docs.astral.sh/uv/" }
}
Note (uv --version)

# ---------- 2. la carte graphique et le profil ----------
Step "2/7  Carte graphique"
$Gpu = $null; $Vram = 0
if (-not $SansCarte -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) {
    $line = (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits | Select-Object -First 1)
    if ($line) { $Gpu, $mib = $line.Split(","); $Gpu = $Gpu.Trim(); $Vram = [math]::Round([int]$mib.Trim() / 1024, 1) }
}
if ($Gpu) { Note "$Gpu, $Vram Go" } else { Note "pas de carte NVIDIA : tout tournera sur le processeur" }
$Full = $Gpu -and $Vram -ge 5.5
if (-not $Profil) {
    Write-Host ""
    Write-Host "   1. Complet : voix IA qui jouent l'émotion, visages qui parlent, sons choisis en regardant les cases"
    Write-Host "      (≈ 50 Go sur le disque, ≈ 30 à 60 min selon la connexion ; carte NVIDIA de 6 Go conseillée)"
    Write-Host "   2. Léger : lecture du texte, voix de base, vidéo qui défile (≈ 5 Go, ≈ 10 min ; n'importe quel PC)"
    $default = if ($Full) { "1" } else { "2" }
    $answer = Read-Host "   Ton choix [$default]"
    if (-not $answer) { $answer = $default }
    $Profil = if ($answer -eq "1") { "complet" } else { "leger" }
}
if ($Profil -eq "complet" -and -not $Full) {
    Write-Host "   [!] Le profil complet demande une carte NVIDIA d'au moins 6 Go : installation légère." -ForegroundColor Yellow
    $Profil = "leger"
}
Note "profil : $Profil"

# ---------- 3. l'environnement du Studio ----------
Step "3/7  Le Studio (.venv)"
NewVenv ".venv"
$py = Python ".venv"
if ($Gpu) {
    # versions exactes de la machine de test : Paddle et onnxruntime pour la carte graphique (CUDA 12)
    Run uv pip sync --python $py install\lock-main-gpu.txt --extra-index-url $PaddleIndex --index-strategy unsafe-best-match
} else {
    Run uv pip install --python $py -r requirements.txt -r requirements-dev.txt
    Run uv pip install --python $py --no-deps kokoro-onnx==0.6.1
}
Note "le navigateur qui télécharge les chapitres (Chromium de Playwright)"
Run $py -m playwright install chromium

# ---------- 4. les modèles IA locaux, chacun dans son environnement ----------
Step "4/7  Modèles IA locaux"
if ($Profil -eq "complet") {
    $envs = [ordered]@{
        "tts"  = "voix de secours, ce qui se passe dans les cases, écoute des sons (≈ 5 Go)"
        "qwen" = "voix décrites qui jouent l'émotion (≈ 5 Go)"
        "edit" = "visages qui parlent (≈ 4,5 Go)"
    }
    foreach ($name in $envs.Keys) {
        Note ".venv-$name : $($envs[$name])"
        NewVenv ".venv-$name"
        Run uv pip sync --python (Python ".venv-$name") "install\lock-$name.txt" --extra-index-url $TorchIndex --index-strategy unsafe-best-match
    }
    if (-not $SansModeles) {
        Note "les modèles (≈ 28 Go au total, une seule fois)"
        foreach ($name in $envs.Keys) { Run (Python ".venv-$name") install\download_models.py $name }
    }
} else {
    Note "sauté (profil léger) : voix de base Kokoro / edge-tts, pas de visages qui parlent"
}

# ---------- 5. la bibliothèque de bruitages pro ----------
Step "5/7  Bruitages et ambiances (Sonniss)"
if ($Profil -eq "complet" -and -not $SansSons) {
    try { Run $py -m manhwa.soundbank --download }
    catch { Write-Host "   [!] Bibliothèque de sons non prête ($_). Relance plus tard : .venv\Scripts\python -m manhwa.soundbank --download" -ForegroundColor Yellow }
} else {
    Note "sauté : les sons de base (Kenney, fabriqués) servent"
}

# ---------- 6. la clé et le raccourci ----------
Step "6/7  Clé GPT et raccourci"
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Note ".env créé : colle la clé dans les Réglages du Studio (roue dentée)" }
else { Note ".env déjà là : gardé" }
if (-not $SansRaccourci) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop "Manhwa Studio.lnk"))
    $link.TargetPath = Join-Path $Root "Studio.bat"
    $link.WorkingDirectory = $Root
    $link.Save()
    Note "raccourci « Manhwa Studio » sur le Bureau"
}

# ---------- 7. vérification, et combien de temps prendra un épisode ici ----------
Step "7/7  Vérification"
Run $py -m manhwa doctor

Write-Host ""
Write-Host "Installé en $([int]$Watch.Elapsed.TotalMinutes) min. Double-clique sur « Manhwa Studio » (Bureau) pour commencer." -ForegroundColor Green
