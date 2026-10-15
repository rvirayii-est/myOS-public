<#
.SYNOPSIS
  Guided, owner-only review of pending Graphify corpora. Run it yourself in PowerShell:
      powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\review-corpora.ps1
  For each corpus that is not yet approved it:
    1. refreshes the transmission preview locally (nothing is sent),
    2. shows what would be sent, what was excluded and why, and what is flagged for your judgement,
    3. lets you [a]pprove (the existing typed-name confirmation), [s]kip, [o]pen the full preview, or [q]uit,
    4. after an approval, offers to build the graph now (this is the moment data is sent).
  Agents cannot run this: the approval step refuses non-interactive callers.
#>
param([string[]]$Only)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$myos = Join-Path $Root 'scripts\myos.py'
if (-not [Environment]::UserInteractive -or [Console]::IsInputRedirected) { throw 'Run this yourself in an interactive PowerShell window.' }

$cfg = Get-Content (Join-Path $Root 'config\myos.json') -Raw | ConvertFrom-Json
$names = $cfg.graph.corpora.PSObject.Properties | Where-Object { $_.Value.requires_approval } | ForEach-Object Name
if ($Only) { $names = $names | Where-Object { $Only -contains $_ } }

foreach ($n in $names) {
  $status = (python $myos graph list | Select-String "^$([regex]::Escape($n))\s").Line
  if ($status -match 'approval=approved') { Write-Host "`n[$n] already approved - skipping review." -ForegroundColor DarkGray; continue }
  python $myos graph plan $n | Out-Null
  $m = Get-Content (Join-Path $Root "data\graph\$n\manifest.json") -Raw | ConvertFrom-Json
  Write-Host "`n================ $n ================" -ForegroundColor Cyan
  Write-Host $cfg.graph.corpora.$n.description
  if ($cfg.graph.corpora.$n.notes) { Write-Host "Note: $($cfg.graph.corpora.$n.notes)" -ForegroundColor Yellow }
  Write-Host ("Would send {0} files ({1:N0} KB) to: {2}" -f $m.files.Count, ($m.total_bytes / 1KB), $m.provider)
  Write-Host "Excluded ($($m.excluded.Count)):"
  $m.excluded | ForEach-Object { Write-Host ("   - {0}  [{1}]" -f $_.path, $_.reason) -ForegroundColor DarkYellow }
  Write-Host "Flagged for your judgement ($($m.review_flags.Count) included files; values never shown):"
  $m.review_flags | ForEach-Object { $f = ($_.flags.PSObject.Properties | ForEach-Object { "$($_.Name) x$($_.Value)" }) -join ', '; Write-Host "   - $($_.path)  [$f]" }
  while ($true) {
    $c = Read-Host "[a]pprove / [s]kip / [o]pen full preview / [q]uit"
    if ($c -eq 'o') { notepad (Join-Path $Root "data\graph\$n\TRANSMISSION-PREVIEW.md"); continue }
    break
  }
  if ($c -eq 'q') { break }
  if ($c -ne 'a') { Write-Host "skipped $n"; continue }
  python $myos graph approve $n
  if ($LASTEXITCODE -ne 0) { Write-Host "not approved: $n" -ForegroundColor Red; continue }
  if ((Read-Host "Build the $n graph now? This sends the files listed above. [y/N]") -eq 'y') {
    python $myos graph build $n
  } else { Write-Host "Approved but not built. Later: myos graph build $n" }
}
Write-Host "`nDone. Status:"; python $myos graph list
