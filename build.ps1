[CmdletBinding()]
param([ValidateNotNullOrEmpty()][string]$OutputDirectory = 'dist')

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$buildRoot = $PSScriptRoot
$buildLog = Join-Path $buildRoot 'build.log'
$buildPython = Join-Path $buildRoot '.build-venv\Scripts\python.exe'
$buildDist = if ([System.IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $buildRoot $OutputDirectory }

function Invoke-LoggedPython {
    param([Parameter(Mandatory = $true)][string[]]$ArgumentList)
    $previousPreference = $ErrorActionPreference
    try {
        # Native build tools log progress to stderr even when successful.
        $ErrorActionPreference = 'Continue'
        & $buildPython @ArgumentList 2>&1 | Tee-Object -FilePath $buildLog -Append
        $nativeExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($nativeExitCode -ne 0) {
        throw "Build command failed (exit $nativeExitCode). See build.log."
    }
}

Push-Location -LiteralPath $buildRoot
try {
    Set-Content -LiteralPath $buildLog -Value ('Build started: ' + [DateTime]::UtcNow.ToString('o')) -Encoding UTF8
    if (-not (Test-Path -LiteralPath (Join-Path $buildRoot 'THIRD_PARTY_NOTICES.txt') -PathType Leaf)) {
        throw 'THIRD_PARTY_NOTICES.txt is required before building.'
    }
    if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
        $pythonLauncher = Get-Command 'py' -ErrorAction SilentlyContinue
        if ($null -eq $pythonLauncher) {
            throw 'Install Python 3.12 (64-bit) and its py launcher, then run this script again.'
        }
        & $pythonLauncher.Source -3.12 -m venv (Join-Path $buildRoot '.build-venv') 2>&1 | Tee-Object -FilePath $buildLog -Append
        if ($LASTEXITCODE -ne 0) {
            throw 'Could not create the project Python 3.12 environment. See build.log.'
        }
    }
    Invoke-LoggedPython -ArgumentList @('-c', 'import struct, sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 is required"; assert struct.calcsize("P") == 8, "64-bit Python is required"')
    Invoke-LoggedPython -ArgumentList @('-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '-r', 'requirements-build.txt')
    Invoke-LoggedPython -ArgumentList @('outline_mod.py', '--self-test')
    Invoke-LoggedPython -ArgumentList @('-m', 'unittest', 'discover', '-v')
    Invoke-LoggedPython -ArgumentList @('-c', 'from app_version import VERSION; print("Building COTWAnimalOutline " + VERSION)')
    # Some Python distributions require this public CA companion when creating
    # SSLContext. Keep their trust policy intact in the frozen application.
    Invoke-LoggedPython -ArgumentList @('-c', 'import ssl; ssl.create_default_context(); print("SSL context preflight: PASS")')
    Invoke-LoggedPython -ArgumentList @('-c', 'import hashlib; from pathlib import Path; from corpse_outline import CODE_SIZE, STUB_SHA256; code = Path("corpse_stub.bin").read_bytes(); assert len(code) == CODE_SIZE and hashlib.sha256(code).hexdigest() == STUB_SHA256; print("Corpse renderer binary: PASS")')
    Invoke-LoggedPython -ArgumentList @('-c', 'import hashlib; from pathlib import Path; from ninja_mode import CODE_SIZE, BUNDLE_SIZE, STUB_SHA256, VISION_STUB_SHA256; code = Path("ninja_stub.bin").read_bytes(); assert len(code) == BUNDLE_SIZE and hashlib.sha256(code[:CODE_SIZE]).hexdigest() == STUB_SHA256 and hashlib.sha256(code[CODE_SIZE:]).hexdigest() == VISION_STUB_SHA256; print("Ninja hearing and vision binaries: PASS")')
    Invoke-LoggedPython -ArgumentList @('-c', 'import hashlib; from pathlib import Path; from pet_outline import CODE_SIZE, STUB_SHA256; code = Path("pet_stub.bin").read_bytes(); assert len(code) == CODE_SIZE and hashlib.sha256(code).hexdigest() == STUB_SHA256; print("Pet outline binary: PASS")')
    $sslCompanion = & $buildPython -c 'from pathlib import Path; import ssl; p = Path(ssl.__file__).with_name("codex-rejected-cas.pem"); print(str(p) if p.is_file() else "")'
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not inspect Python SSL companion data.'
    }
    $freezeArguments = @('-m', 'PyInstaller', '--noconfirm', '--workpath', 'build/package', '--distpath', $buildDist, '--onefile', '--windowed', '--noupx', '--name', 'COTWAnimalOutline', '--add-data', 'THIRD_PARTY_NOTICES.txt;.', '--add-data', 'corpse_stub.bin;.', '--add-data', 'ninja_stub.bin;.', '--add-data', 'pet_stub.bin;.')
    if (-not [string]::IsNullOrWhiteSpace($sslCompanion)) {
        $freezeArguments += @('--add-data', "$sslCompanion;.")
    }
    $freezeArguments += 'outline_mod.py'
    Invoke-LoggedPython -ArgumentList $freezeArguments
    $buildArtifact = Get-Item -LiteralPath (Join-Path $buildDist 'COTWAnimalOutline.exe')
    $buildHash = Get-FileHash -LiteralPath $buildArtifact.FullName -Algorithm SHA256
    $buildResult = "PASS: $($buildArtifact.Name), $($buildArtifact.Length) bytes, SHA256 $($buildHash.Hash)"
    $buildResult | Tee-Object -FilePath $buildLog -Append
}
catch {
    $_.Exception.Message | Add-Content -LiteralPath $buildLog -Encoding UTF8
    throw
}
finally {
    Pop-Location
}
