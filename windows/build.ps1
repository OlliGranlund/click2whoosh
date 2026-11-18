$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    Push-Location frontend
    try {
        npm ci
        if ($LASTEXITCODE) { throw 'Frontend dependency installation failed' }
        npm test
        if ($LASTEXITCODE) { throw 'Frontend feedback tests failed' }
        npm run build
        if ($LASTEXITCODE) { throw 'Frontend build failed' }
    } finally { Pop-Location }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE) { throw 'Creating Python environment failed' }
    }
    & .venv/Scripts/python.exe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE) { throw 'Installing dependencies failed' }
    & .venv/Scripts/python.exe -m unittest discover -s tests -v
    if ($LASTEXITCODE) { throw 'Tests failed' }
    & .venv/Scripts/python.exe make_icon.py
    if ($LASTEXITCODE) { throw 'Icon generation failed' }
    & .venv/Scripts/python.exe collect_licenses.py
    if ($LASTEXITCODE) { throw 'Collecting dependency notices failed' }
    & .venv/Scripts/python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name ClickToWhoosh --icon assets/app.ico --version-file assets/version_info.txt --add-data 'assets;assets' --collect-all bleak --collect-all zeroconf app.py
    if ($LASTEXITCODE) { throw 'Packaging failed' }
    $releaseDir = Join-Path $PSScriptRoot 'dist'
    # Replacing these generated directories avoids shipping deleted documentation/notices.
    foreach ($folderName in @('docs', 'legal')) {
        $folderPath = [IO.Path]::GetFullPath((Join-Path $releaseDir $folderName))
        if ([IO.Path]::GetDirectoryName($folderPath) -ne [IO.Path]::GetFullPath($releaseDir)) { throw 'Invalid release directory' }
        if (Test-Path -LiteralPath $folderPath) { Remove-Item -LiteralPath $folderPath -Recurse -Force }
    }
    Copy-Item -LiteralPath '../README.md' -Destination "$releaseDir/README.md"
    Copy-Item -LiteralPath '../LICENSE', '../THIRD_PARTY_NOTICES.md' -Destination $releaseDir
    Copy-Item -LiteralPath '../docs' -Destination $releaseDir -Recurse -Force
    Copy-Item -LiteralPath 'assets/legal' -Destination $releaseDir -Recurse -Force
    Compress-Archive -LiteralPath "$releaseDir/ClickToWhoosh.exe", "$releaseDir/README.md", "$releaseDir/LICENSE", "$releaseDir/THIRD_PARTY_NOTICES.md", "$releaseDir/docs", "$releaseDir/legal" -DestinationPath "$releaseDir/ClickToWhoosh-Windows-x64.zip" -Force
    $hashLines = foreach ($name in @('ClickToWhoosh.exe', 'ClickToWhoosh-Windows-x64.zip')) {
        $hash = (Get-FileHash -LiteralPath (Join-Path $releaseDir $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $name"
    }
    $hashLines | Set-Content -LiteralPath "$releaseDir/SHA256SUMS.txt" -Encoding ascii
    Write-Host "Executable: $PSScriptRoot/dist/ClickToWhoosh.exe"
} finally {
    Pop-Location
}
