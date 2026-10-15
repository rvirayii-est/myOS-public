<#
.SYNOPSIS
  Restore myOS from a backup zip made by scripts\backup.ps1. Safe by default.

.EXAMPLE  (test a backup without touching anything live)
  powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\restore.ps1 -Zip C:\projects\myOS\backups\myos-backup-X.zip -Target C:\Temp\myos-restore-test -Verify

.EXAMPLE  (real recovery after C:\projects\myOS was lost or broken: rename the broken folder first)
  powershell -ExecutionPolicy Bypass -File D:\Backups\restore.ps1 -Zip D:\Backups\myos-backup-X.zip -Target C:\projects\myOS -Verify -ReinstallAgents -RestoreVaultNotes

  -Verify             check every file against SHA256SUMS.txt, then run the myOS tests and a routing check in the restored copy
  -ReinstallAgents    re-run scripts\install.ps1 from the restored copy (skills, CLAUDE.md/AGENTS.md blocks, guard); idempotent
  -RestoreVaultNotes  copy back myOS-created vault notes that are MISSING from the vault (never overwrites an existing note)
  The Target folder must not exist or must be empty. The Graphify venv is rebuilt with the command printed at the end.
#>
param([Parameter(Mandatory)][string]$Zip, [Parameter(Mandatory)][string]$Target,
      [switch]$Verify, [switch]$ReinstallAgents, [switch]$RestoreVaultNotes)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
if ((Test-Path $Target) -and (Get-ChildItem $Target -Force | Select-Object -First 1)) {
  throw "Target '$Target' exists and is not empty. Choose an empty folder (rename a broken myOS folder first)."
}
$tmp = Join-Path $env:TEMP ("myos-restore-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
Expand-Archive -Path $Zip -DestinationPath $tmp

# integrity
$bad = 0
foreach ($line in Get-Content (Join-Path $tmp 'SHA256SUMS.txt')) {
  if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { continue }
  $p = Join-Path $tmp ($Matches[2] -replace '/', '\')
  if (-not (Test-Path -LiteralPath $p) -or (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower() -ne $Matches[1]) {
    $bad++; "INTEGRITY FAIL: $($Matches[2])"
  }
}
if ($bad) { throw "$bad file(s) failed the integrity check; nothing was restored." }
"integrity: all files match SHA256SUMS.txt"

New-Item -ItemType Directory -Force $Target | Out-Null
robocopy (Join-Path $tmp 'myos') $Target /E /NFL /NDL /NJH /NJS /NP | Out-Null
git clone -q (Join-Path $tmp 'myos.git.bundle') (Join-Path $tmp 'gitrepo') 2>$null
if (Test-Path (Join-Path $tmp 'gitrepo\.git')) { Copy-Item -Recurse (Join-Path $tmp 'gitrepo\.git') (Join-Path $Target '.git') }
"restored myOS files to $Target"

$manifest = Get-Content (Join-Path $tmp 'manifest.json') -Raw | ConvertFrom-Json
if ($RestoreVaultNotes) {
  $n = 0
  foreach ($rel in $manifest.vault_files_added_by_myos) {
    $dst = Join-Path $manifest.vault ($rel -replace '/', '\')
    $src = Join-Path $tmp ('vault-notes\' + ($rel -replace '/', '\'))
    if (-not (Test-Path -LiteralPath $dst) -and (Test-Path -LiteralPath $src)) {
      New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null; Copy-Item -LiteralPath $src $dst; $n++
    }
  }
  "vault: restored $n missing myOS note(s); existing notes were not touched"
}
if ($ReinstallAgents) { & (Join-Path $Target 'scripts\install.ps1') -SkipVault }

if ($Verify) {
  Push-Location $Target
  $ErrorActionPreference = 'Continue'  # Windows PowerShell 5.1 turns native stderr into terminating errors under 'Stop'
  try {
    $t = python -m unittest discover -s tests 2>&1 | Select-Object -Last 3
    "tests in restored copy: " + ($t -join ' ')
    $r = python scripts\myos.py route lumen-ledger 2>&1 | Select-String 'Project card'
    "routing check: " + $r
  } finally { Pop-Location }
}
Remove-Item -Recurse -Force $tmp
"Graphify venv (only needed for graph builds): python -m venv `"$Target\graphify\.venv`"; & `"$Target\graphify\.venv\Scripts\pip.exe`" install graphifyy==0.9.90"
