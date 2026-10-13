# One click: check the inputs, set up (first time only), check the GPU, reconstruct every
# pair, then analyse them. Stops at the first failure with exit code 1. Log: logs\run_all.log.
#   powershell -ExecutionPolicy Bypass -File scripts\run_all_windows.ps1
# run_corridor.bat and run_room.bat call this with the corridor and room comparisons.
param(
    # comparisons to run: name=before_folder,after_folder;name2=...
    [string]$Pairs = "corridor_right=data\corridor\before_Right,data\corridor\after_Right;corridor_same=data\corridor\before_Left,data\corridor\after_Left;corridor_cross=data\corridor\before_Left,data\corridor\after_Right;corridor_null=data\corridor\before_Left,data\corridor\before_Right",
    [double]$Height = 1.20,
    [int]$Frames = 0          # 0 = let the planner choose for this GPU
)
$ErrorActionPreference = "Continue"
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force -Path logs | Out-Null
$log = (Resolve-Path logs).Path + "\run_all.log"
[System.IO.File]::WriteAllText($log, "=== run_all started $(Get-Date) ===`r`n")
$env:PYTHONUNBUFFERED = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

function Say($m) { Write-Host "`n>>> $m" -ForegroundColor Cyan; [System.IO.File]::AppendAllText($log, ">>> $m`r`n") }
function Run($cmdline) {
    Say $cmdline
    cmd /c "$cmdline 2>&1" | ForEach-Object { Write-Host $_; [System.IO.File]::AppendAllText($log, "$_`r`n") }
    if ($LASTEXITCODE -ne 0) { Say "FAILED (exit $LASTEXITCODE): $cmdline"; throw "step failed" }
}

function HasInput($p) {
    foreach ($x in @("", ".MOV", ".mov", ".mp4", ".MP4")) { if (Test-Path "$p$x") { return $true } }
    return $false
}

try {
    # check every input before spending time on setup or the GPU
    $jobs = @()
    foreach ($p in $Pairs.Split(";")) {
        $name, $rest = $p.Split("=")
        $b, $a = $rest.Split(",")
        $jobs += ,@($name.Trim(), $b.Trim(), $a.Trim())
    }
    $missing = @()
    foreach ($j in $jobs) { foreach ($v in $j[1], $j[2]) { if (-not (HasInput $v)) { $missing += $v } } }
    if ($missing.Count -gt 0) {
        Say "Input video(s) not found: $($missing -join ', '). See the Data section of README.md."
        throw "missing input"
    }

    $vpy = ".\.venv\Scripts\python.exe"
    if (-not (Test-Path $vpy)) {
        Say "Finding Python 3.10-3.12"
        $py = $null
        foreach ($v in "3.12", "3.11", "3.10") {
            $exe = cmd /c "py -$v -c ""import sys;print(sys.executable)"" 2>nul"
            if ($LASTEXITCODE -eq 0 -and $exe) { $py = "$exe".Trim(); break }
        }
        if (-not $py) {
            $exe = cmd /c "python -c ""import sys;assert (3,10)<=sys.version_info[:2]<=(3,12);print(sys.executable)"" 2>nul"
            if ($LASTEXITCODE -eq 0 -and $exe) { $py = "$exe".Trim() }
        }
        if (-not $py) { Say "No Python 3.10-3.12 found. Install it from python.org, tick 'Add to PATH', then run again."; throw "no python" }
        Say "Using $py"
        Run """$py"" -m venv .venv"
    }
    Run "$vpy -m pip install --upgrade pip"
    $hasCuda = cmd /c "$vpy -c ""import torch;print(torch.cuda.is_available())"" 2>nul"
    if ("$hasCuda".Trim() -ne "True") {
        Run "$vpy -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128"
    }
    if (-not (Test-Path third_party\vggt)) {
        New-Item -ItemType Directory -Force -Path third_party | Out-Null
        $git = Get-Command git -ErrorAction SilentlyContinue
        if ($git) { Run "git clone https://github.com/facebookresearch/vggt.git third_party\vggt"; Run "git -C third_party\vggt checkout --quiet a288dd0f14786c93483e45524328726ab7b1b4ce" }
        else {
            Say "git not found, downloading VGGT as a zip"
            Invoke-WebRequest https://github.com/facebookresearch/vggt/archive/a288dd0f14786c93483e45524328726ab7b1b4ce.zip -OutFile third_party\vggt.zip
            Expand-Archive third_party\vggt.zip third_party -Force
            Rename-Item third_party\vggt-a288dd0f14786c93483e45524328726ab7b1b4ce vggt
        }
    }
    # one resolution so VGGT's numpy<2 pin and OpenCV agree
    Run "$vpy -m pip install -r requirements.txt -e third_party\vggt numpy==1.26.4"
    Run "$vpy -m roomdiff doctor"

    $fr = ""
    if ($Frames -gt 0) { $fr = "--frames $Frames" }
    # GPU step for every comparison first (always recomputed), then detection and outputs
    foreach ($j in $jobs) { Run "$vpy -m roomdiff reconstruct --before $($j[1]) --after $($j[2]) --out results\$($j[0]) $fr" }
    foreach ($j in $jobs) { Run "$vpy -m roomdiff reanalyse --out results\$($j[0]) --camera-height $Height" }
    Say "ALL DONE. Results are in results\ ($(($jobs | ForEach-Object { $_[0] }) -join ', '))."
}
catch {
    Say "FAILED, stopped: $_  (full log: $log)"
    exit 1
}
exit 0
