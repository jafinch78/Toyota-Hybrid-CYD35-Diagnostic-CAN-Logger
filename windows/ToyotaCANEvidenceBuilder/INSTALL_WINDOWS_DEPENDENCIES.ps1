$ErrorActionPreference = 'Stop'

function Add-UserPath([string]$Directory) {
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return }
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $items = @()
    if ($current) { $items = $current -split ';' | Where-Object { $_ -and $_.Trim() } }
    $already = $items | Where-Object { $_.TrimEnd('\') -ieq $Directory.TrimEnd('\') }
    if (-not $already) {
        $items += $Directory
        [Environment]::SetEnvironmentVariable('Path', ($items -join ';'), 'User')
        Write-Host "Added user PATH entry: $Directory"
    }
    if (($env:Path -split ';' | Where-Object { $_.TrimEnd('\') -ieq $Directory.TrimEnd('\') }).Count -eq 0) {
        $env:Path = "$Directory;$env:Path"
    }
}

function Find-Executable([string]$Name, [string[]]$Candidates) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in $Candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Install-Ffmpeg {
    $preferredBin = 'C:\Tools\ffmpeg\bin'
    $ffmpeg = Join-Path $preferredBin 'ffmpeg.exe'
    $ffprobe = Join-Path $preferredBin 'ffprobe.exe'
    if ((Test-Path -LiteralPath $ffmpeg -PathType Leaf) -and
        (Test-Path -LiteralPath $ffprobe -PathType Leaf)) {
        Add-UserPath $preferredBin
        return $preferredBin
    }
    $existingFfmpeg = Find-Executable 'ffmpeg' @()
    $existingFfprobe = Find-Executable 'ffprobe' @()
    if ($existingFfmpeg -and $existingFfprobe) {
        Add-UserPath (Split-Path -Parent $existingFfmpeg)
        Add-UserPath (Split-Path -Parent $existingFfprobe)
        return (Split-Path -Parent $existingFfmpeg)
    }

    $zipPath = Join-Path $env:TEMP 'toyota-can-ffmpeg-essentials.zip'
    $extractRoot = Join-Path $env:TEMP ('toyota-can-ffmpeg-' + [guid]::NewGuid().ToString('N'))
    Write-Host 'FFmpeg was not found. Downloading the Gyan essentials build...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile $zipPath
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
    $sourceExe = Get-ChildItem -LiteralPath $extractRoot -Filter 'ffmpeg.exe' -File -Recurse | Select-Object -First 1
    if (-not $sourceExe) { throw 'The downloaded FFmpeg archive did not contain ffmpeg.exe.' }
    $sourceBin = $sourceExe.Directory.FullName
    $targetBin = $preferredBin
    try {
        New-Item -ItemType Directory -Path $targetBin -Force | Out-Null
        Copy-Item -Path (Join-Path $sourceBin '*') -Destination $targetBin -Recurse -Force
    } catch {
        $targetBin = Join-Path $env:LOCALAPPDATA 'ToyotaCAN\ffmpeg\bin'
        Write-Host "C:\Tools is not writable; using per-user FFmpeg path: $targetBin"
        New-Item -ItemType Directory -Path $targetBin -Force | Out-Null
        Copy-Item -Path (Join-Path $sourceBin '*') -Destination $targetBin -Recurse -Force
    }
    Add-UserPath $targetBin
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path -LiteralPath (Join-Path $targetBin 'ffprobe.exe') -PathType Leaf)) {
        throw "FFmpeg was copied but ffprobe.exe is missing from $targetBin."
    }
    return $targetBin
}

function Install-Tesseract {
    $candidates = @(
        'C:\Program Files\Tesseract-OCR\tesseract.exe',
        'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
    )
    $tesseract = Find-Executable 'tesseract' $candidates
    if (-not $tesseract) {
        $installer = Join-Path $env:TEMP 'tesseract-ocr-w64-setup.exe'
        Write-Host 'Tesseract OCR was not found. Downloading the 64-bit UB Mannheim build...'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/tesseract-ocr/tesseract/releases/download/5.5.3/tesseract-ocr-w64-setup-5.5.3.20260724.exe' -OutFile $installer
        $process = Start-Process -FilePath $installer -ArgumentList @('/SILENT', '/NORESTART') -Wait -PassThru -Verb RunAs
        if ($process.ExitCode -ne 0) { throw "Tesseract installer failed with exit code $($process.ExitCode)." }
        $tesseract = Find-Executable 'tesseract' $candidates
        if (-not $tesseract) { throw 'Tesseract installer completed but tesseract.exe was not found.' }
        Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
    }
    $tesseractRoot = Split-Path -Parent $tesseract
    Add-UserPath $tesseractRoot
    $tessdata = Join-Path $tesseractRoot 'tessdata'
    New-Item -ItemType Directory -Path $tessdata -Force | Out-Null
    $languages = (& $tesseract '--list-langs' 2>$null | Out-String)
    foreach ($language in @('eng', 'osd')) {
        if ($languages -notmatch "(?m)^$language\s*$") {
            $traineddata = Join-Path $tessdata ($language + '.traineddata')
            Write-Host "Installing missing Tesseract language data: $language"
            Invoke-WebRequest -UseBasicParsing -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/$language.traineddata" -OutFile $traineddata
        }
    }
    return $tesseract
}

Write-Host 'Checking external Evidence Builder tools...'
$ffmpegBin = Install-Ffmpeg
$tesseract = Install-Tesseract
$ffmpeg = Find-Executable 'ffmpeg' @(Join-Path $ffmpegBin 'ffmpeg.exe')
$ffprobe = Find-Executable 'ffprobe' @(Join-Path $ffmpegBin 'ffprobe.exe')
if (-not (Test-Path -LiteralPath $ffmpeg -PathType Leaf)) { throw "ffmpeg.exe was not found at $ffmpeg" }
if (-not (Test-Path -LiteralPath $ffprobe -PathType Leaf)) { throw "ffprobe.exe was not found at $ffprobe" }
if (-not (Test-Path -LiteralPath $tesseract -PathType Leaf)) { throw "tesseract.exe was not found at $tesseract" }
Write-Host "FFmpeg: $ffmpeg"
Write-Host "FFprobe: $ffprobe"
Write-Host "Tesseract: $tesseract"
Write-Host 'External tool installation and PATH checks passed.'
