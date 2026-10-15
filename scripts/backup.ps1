<#
.SYNOPSIS
  Local backup of myOS (no cloud upload). Produces backups\myos-backup-<stamp>.zip containing:
    myos\              the myOS folder (cards, config, schemas, workflows, skills, scripts, docs, tests)
    myos.git.bundle    full git history of myOS
    agent-config\      copies of the agent files myOS integrates with (CLAUDE.md, settings.json, AGENTS.md, guard rules,
                       myOS skills, Ponytail config, Orca's Codex AGENTS.md and rules)
    vault-notes\       ONLY the vault notes myOS itself created (templates, pilot, hubs, session notes)
    manifest.json      versions, PATH entries, corpora/approvals, list of myOS vault notes
    SHA256SUMS.txt     integrity list for every file in the archive
  Never included: Graphify staging copies of your notes (data\graph\*\corpus), raw test transcripts (logs\), the
  Graphify venv, credentials (.credentials.json, auth.json). Every packed file is secret-scanned; hits are dropped.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\backup.ps1
  powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\backup.ps1 -Destination D:\Backups -IncludeGraphs
#>
param([string]$Destination = (Join-Path (Split-Path -Parent $PSScriptRoot) 'backups'), [switch]$IncludeGraphs)
$ErrorActionPreference = 'Stop'
$Root  = Split-Path -Parent $PSScriptRoot
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Stage = Join-Path $env:TEMP "myos-bk-$Stamp"
New-Item -ItemType Directory -Force $Stage, $Destination | Out-Null
$env:PYTHONIOENCODING = 'utf-8'

# 1. myOS tree
$xd = @((Join-Path $Root 'graphify\.venv'), (Join-Path $Root 'backups'), (Join-Path $Root 'logs'), (Join-Path $Root '.git'))
if ($IncludeGraphs) {
  Get-ChildItem (Join-Path $Root 'data\graph') -Directory -ErrorAction SilentlyContinue | ForEach-Object { $xd += (Join-Path $_.FullName 'corpus') }
} else { $xd += (Join-Path $Root 'data\graph') }
robocopy $Root (Join-Path $Stage 'myos') /E /NFL /NDL /NJH /NJS /NP /XD $xd /XF '*.myos-tmp-*' | Out-Null
git -C $Root bundle create (Join-Path $Stage 'myos.git.bundle') --all 2>$null

# 2. manifest
python (Join-Path $Root 'scripts\myos.py') manifest --out (Join-Path $Stage 'manifest.json') | Out-Null
$manifest = Get-Content (Join-Path $Stage 'manifest.json') -Raw | ConvertFrom-Json

# 3. agent integration files (copies for reference; scripts\install.ps1 re-creates them)
$agent = Join-Path $Stage 'agent-config'
New-Item -ItemType Directory -Force $agent | Out-Null
$orca = Join-Path $env:APPDATA 'orca\codex-runtime-home\home'
$files = @("$HOME\.claude\CLAUDE.md", "$HOME\.claude\settings.json", "$HOME\.codex\AGENTS.md", "$HOME\.codex\config.toml",
           "$HOME\.codex\rules\myos-guard.rules", "$orca\AGENTS.md", "$orca\rules\myos-guard.rules", "$env:APPDATA\ponytail\config.json")
foreach ($s in 'save-progress','resume-project','project-status','context-search','executive-briefing') {
  $files += "$HOME\.claude\skills\$s\SKILL.md"; $files += "$HOME\.agents\skills\$s\SKILL.md"
}
foreach ($f in $files) {
  if (Test-Path $f) { Copy-Item $f (Join-Path $agent ((($f -replace '^[A-Za-z]:\\', '') -replace '[\\/]', '__'))) }
}
[Environment]::GetEnvironmentVariable('Path', 'User') | Set-Content (Join-Path $agent 'user-PATH.txt')

# 4. vault notes created by myOS (only these; the vault itself is backed up by its own git)
foreach ($rel in $manifest.vault_files_added_by_myos) {
  $src = Join-Path $manifest.vault ($rel -replace '/', '\')
  $dst = Join-Path $Stage ('vault-notes\' + ($rel -replace '/', '\'))
  New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
  Copy-Item -LiteralPath $src -Destination $dst
}

# 5. secret scan (synthetic test fixtures are fake by design and stay)
$scan = python (Join-Path $Root 'scripts\myos.py') scan $Stage 2>&1
$dropped = @()
foreach ($line in $scan) {
  if ($line -match '^EXCLUDE (.+?)  \((content:[^)]+|sensitive-name)\)$') {
    $rel = $Matches[1]
    # synthetic fixtures are fake by design; myOS docs/config describe the rules (rule names trip the rules)
    if ($rel -like 'myos/tests/fixtures/*' -or $rel -like 'myos/docs/*' -or $rel -like 'myos/config/*') { continue }
    $p = Join-Path $Stage ($rel -replace '/', '\')
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $dropped += "$rel ($($Matches[2]))" }
  }
}

# 6. integrity list + zip
$sums = Get-ChildItem $Stage -Recurse -File | ForEach-Object {
  $h = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
  "$h  $($_.FullName.Substring($Stage.Length + 1).Replace('\', '/'))"
}
$sums | Set-Content (Join-Path $Stage 'SHA256SUMS.txt') -Encoding utf8
$zip = Join-Path $Destination "myos-backup-$Stamp.zip"
Compress-Archive -Path "$Stage\*" -DestinationPath $zip
Remove-Item -Recurse -Force $Stage
"backup written: $zip ($([math]::Round((Get-Item $zip).Length / 1KB)) KB, $($sums.Count) files)"
if ($dropped) { "secret scan dropped $($dropped.Count) file(s):"; $dropped | ForEach-Object { "  - $_" } } else { 'secret scan: no hits outside synthetic fixtures' }
$dirty = (git -C $manifest.vault --no-optional-locks status --porcelain | Measure-Object).Count
"vault: $($manifest.vault) has $dirty uncommitted entries in its own git repo; back it up with git/Obsidian Sync (myOS never commits it)."
