param(
    [string]$DataRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$StageRoot
)

$localDataRoot = (Resolve-Path -LiteralPath $DataRoot -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath (Join-Path $localDataRoot '0510_f3/L1-TIME_ANGE_DIST_DATA') -PathType Container)) {
    throw "No L1 directory under $localDataRoot. Supply -DataRoot with the copied dataset location."
}
if ([string]::IsNullOrWhiteSpace($StageRoot)) {
    $StageRoot = Join-Path (Split-Path -Parent $localDataRoot) ((Split-Path -Leaf $localDataRoot) + '_2.0')
}
$localStageRoot = (Resolve-Path -LiteralPath $StageRoot -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $localStageRoot -PathType Container)) {
    throw "StageRoot must be an existing result directory: $localStageRoot"
}

$env:AIRBORNE_LIDAR_PROJECT_DATA_ROOT = $localDataRoot
$env:AIRBORNE_LIDAR_STAGE_ROOT = $localStageRoot
Write-Output "Data root: $localDataRoot"
Write-Output "Stage root: $localStageRoot"
