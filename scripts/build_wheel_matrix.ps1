[CmdletBinding()]
param(
    [string[]] $PythonVersions = @("3.11", "3.12", "3.13"),
    [switch] $SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepositoryRoot = Split-Path -Parent $PSScriptRoot
$Wheelhouse = Join-Path $RepositoryRoot "build\wheelhouse"
$SmokeRoot = Join-Path $RepositoryRoot "build\wheel-smoke"

function Assert-LastCommand {
    param([Parameter(Mandatory)][string] $Description)

    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory)][string] $Path)

    $Stream = [System.IO.File]::OpenRead($Path)
    $Algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        $Bytes = $Algorithm.ComputeHash($Stream)
        return ([System.BitConverter]::ToString($Bytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $Algorithm.Dispose()
        $Stream.Dispose()
    }
}

if (-not (Get-Command py.exe -ErrorAction SilentlyContinue)) {
    throw "The Windows Python launcher (py.exe) is required."
}

if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    throw "cl.exe was not found. Run this script from an x64 Visual Studio developer shell."
}

New-Item -ItemType Directory -Force -Path $Wheelhouse, $SmokeRoot | Out-Null
$ManifestLines = New-Object 'System.Collections.Generic.List[string]'
Push-Location $RepositoryRoot

try {
    foreach ($Version in $PythonVersions) {
        if ($Version -notmatch '^3\.(11|12|13)$') {
            throw "Unsupported matrix entry '$Version'; expected 3.11, 3.12, or 3.13."
        }

        $Tag = "cp" + $Version.Replace(".", "")
        Write-Host "==> Building RIX for CPython $Version ($Tag)"

        & py "-$Version" -c "import platform, struct, sys; assert sys.implementation.name == 'cpython'; assert struct.calcsize('P') == 8; assert platform.system() == 'Windows'; print(sys.version)"
        Assert-LastCommand "CPython $Version prerequisite check"

        & py "-$Version" -m pip wheel . --no-deps --wheel-dir $Wheelhouse
        Assert-LastCommand "CPython $Version wheel build"

        $Wheels = @(Get-ChildItem -LiteralPath $Wheelhouse -Filter "rix-*-$Tag-$Tag-win_amd64.whl")
        if ($Wheels.Count -ne 1) {
            throw "Expected one $Tag win_amd64 wheel in '$Wheelhouse', found $($Wheels.Count)."
        }

        $Wheel = $Wheels[0]
        $Environment = Join-Path $SmokeRoot $Tag
        & py "-$Version" -m venv --clear $Environment
        Assert-LastCommand "CPython $Version clean virtual environment creation"

        $Python = Join-Path $Environment "Scripts\python.exe"
        & $Python -m pip install --disable-pip-version-check --no-index $Wheel.FullName
        Assert-LastCommand "CPython $Version wheel install"

        & $Python -m pip check
        Assert-LastCommand "CPython $Version dependency check"

        & $Python -c "import rix; assert rix.engine_version() == rix.__version__; assert rix.native_add(2, 3) == 5; print(rix.__file__, rix.engine_version())"
        Assert-LastCommand "CPython $Version native import smoke test"

        if (-not $SkipTests) {
            & $Python -m pip install --disable-pip-version-check "pytest==9.2.0" "mypy==1.18.2" "pygame-ce==2.5.8"
            Assert-LastCommand "CPython $Version test dependency install"

            & $Python -m pytest -q
            Assert-LastCommand "CPython $Version test suite"
        }

        $Hash = Get-Sha256 -Path $Wheel.FullName
        $ManifestLines.Add("$Hash  $($Wheel.Name)")
        Write-Host "$($Wheel.Name) SHA256=$Hash"
    }

    $Manifest = Join-Path $Wheelhouse "SHA256SUMS.txt"
    [System.IO.File]::WriteAllLines($Manifest, $ManifestLines, [System.Text.Encoding]::ASCII)
    Write-Host "Wrote $Manifest"
}
finally {
    Pop-Location
}
