# Manhwa Studio en une ligne, à coller dans PowerShell :
#
#     irm https://raw.githubusercontent.com/sinaypan/Manhwa-TikTok-Automator/main/install/get.ps1 | iex
#
# Télécharge le projet dans C:\Users\<toi>\Manhwa Studio (hors OneDrive : les modèles pèsent 28 Go),
# l'installe avec le profil qui convient à la carte graphique (install.ps1 -Profil auto), sans
# question, puis ouvre le Studio. Relancée, la même ligne met tout à jour (chapitres, clé et modèles gardés).
#
# Réglages facultatifs, avant la ligne : $env:MANHWA_DIR = "D:\Manhwa" (autre dossier),
# $env:MANHWA_ARGS = "-Profil leger -SansSons" (options d'install.ps1), $env:MANHWA_ZIP = "1"
# (le ZIP même si Git est là), $env:MANHWA_SANS_STUDIO = "1" (ne pas ouvrir le Studio à la fin).
& {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"  # Windows PowerShell télécharge 10 fois plus vite sans la barre
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $repo = "https://github.com/sinaypan/Manhwa-TikTok-Automator"
    $dir = if ($env:MANHWA_DIR) { $env:MANHWA_DIR } else { Join-Path $env:USERPROFILE "Manhwa Studio" }
    Write-Host "Manhwa Studio : téléchargement dans $dir" -ForegroundColor Green

    $git = (Get-Command git -ErrorAction SilentlyContinue) -and -not $env:MANHWA_ZIP
    if ($git -and (Test-Path (Join-Path $dir ".git"))) {
        git -C $dir pull --ff-only
        if ($LASTEXITCODE -ne 0) { throw "Mise à jour impossible (git pull) : des fichiers du projet ont été modifiés à la main ?" }
    } elseif ($git -and -not (Test-Path $dir)) {
        git clone --depth 1 "$repo.git" $dir
        if ($LASTEXITCODE -ne 0) { throw "Téléchargement impossible (git clone)" }
    } else {
        # le ZIP de GitHub, posé par-dessus : inbox/, .env et .cache/ n'y sont pas, ils restent
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ("manhwa-" + [guid]::NewGuid())
        New-Item -ItemType Directory $tmp | Out-Null
        try {
            Invoke-WebRequest "$repo/archive/refs/heads/main.zip" -OutFile "$tmp\main.zip" -UseBasicParsing
            Expand-Archive "$tmp\main.zip" $tmp
            $src = Get-ChildItem $tmp -Directory | Select-Object -First 1
            New-Item -ItemType Directory -Force $dir | Out-Null
            Copy-Item (Join-Path $src.FullName "*") $dir -Recurse -Force
        } finally {
            Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    $options = @("-Profil", "auto")
    if ($env:MANHWA_ARGS) { $options = $env:MANHWA_ARGS -split "\s+" | Where-Object { $_ } }
    if ($options -notcontains "-Profil") { $options = @("-Profil", "auto") + $options }
    powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dir "install\install.ps1") @options
    if ($LASTEXITCODE -ne 0) { throw "L'installation s'est arrêtée : relis le message au-dessus, puis relance la même ligne." }

    if (-not $env:MANHWA_SANS_STUDIO) {
        Write-Host "Ouverture du Studio…" -ForegroundColor Green
        Start-Process -FilePath (Join-Path $dir "Studio.bat") -WorkingDirectory $dir
    }
}
