<#
.SYNOPSIS
  Installs / refreshes myOS agent integration. Idempotent. Backs up every file before changing it.

.DESCRIPTION
  1. Backs up user-level agent instruction files and any existing myOS skills to backups\<timestamp>\
  2. Installs the five myOS skills for Claude Code (~\.claude\skills) and Codex (~\.agents\skills)
  3. Adds (or refreshes) a small marker-delimited myOS block in:
       ~\.claude\CLAUDE.md                      (Claude Code, every project)
       ~\.codex\AGENTS.md                       (Codex launched from a terminal)
       %APPDATA%\orca\codex-runtime-home\home\AGENTS.md  (Codex launched by Orca; Orca sets CODEX_HOME there)
     Existing content outside the markers is never touched.
  4. Creates (never overwrites) the Obsidian templates and the pilot area in the vault.
  Run scripts\uninstall.ps1 to remove everything this script adds.
#>
[CmdletBinding()]
param([switch]$SkipVault)

$ErrorActionPreference = 'Stop'
$Root   = Split-Path -Parent $PSScriptRoot
$Cfg    = Get-Content "$Root\config\myos.json" -Raw | ConvertFrom-Json
$Vault  = if ($env:MYOS_VAULT) { $env:MYOS_VAULT } else { [Environment]::ExpandEnvironmentVariables($Cfg.vault) -replace '^~', $HOME }
if (-not [IO.Path]::IsPathRooted($Vault)) { $Vault = Join-Path $Root $Vault }
$RootFwd = $Root -replace '\\', '/'
$Stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$Backup = Join-Path $Root "backups\$Stamp"
$Log    = Join-Path $Root "logs\install-$Stamp.log"
New-Item -ItemType Directory -Force $Backup, (Split-Path $Log), "$Root\logs\inbox" | Out-Null
function Log($m) { $m | Tee-Object -FilePath $Log -Append }

$Skills = 'save-progress','resume-project','project-status','context-search','executive-briefing'
$ClaudeSkills = Join-Path $HOME '.claude\skills'
$AgentSkills  = Join-Path $HOME '.agents\skills'
$OrcaCodexHome = Join-Path $env:APPDATA 'orca\codex-runtime-home\home'
$Targets = @(
  @{ Path = Join-Path $HOME '.claude\CLAUDE.md'; Agent = 'claude' },
  @{ Path = Join-Path $HOME '.codex\AGENTS.md';  Agent = 'codex' }
)
if (Test-Path $OrcaCodexHome) { $Targets += @{ Path = Join-Path $OrcaCodexHome 'AGENTS.md'; Agent = 'codex' } }

function Backup-Item($p) {
  if (Test-Path $p) {
    $rel = ($p -replace '^[A-Za-z]:\\', '') -replace '[\\:]', '__'
    Copy-Item -Recurse -Force $p (Join-Path $Backup $rel)
    Log "backup  $p"
  }
}

# ---- 1. backups ----------------------------------------------------------
foreach ($t in $Targets) { Backup-Item $t.Path }
foreach ($s in $Skills) { Backup-Item (Join-Path $ClaudeSkills $s); Backup-Item (Join-Path $AgentSkills $s) }

# ---- 2. skills -------------------------------------------------------------
function Install-Skill($name, $destRoot) {
  $dst = Join-Path $destRoot $name
  $existing = Join-Path $dst 'SKILL.md'
  if ((Test-Path $existing) -and -not (Select-String -Path $existing -Pattern 'description: myOS' -Quiet)) {
    Log "SKIP    $dst (existing skill is not a myOS skill - left untouched)"; return
  }
  New-Item -ItemType Directory -Force $dst | Out-Null
  Copy-Item -Force (Join-Path $Root "skills\$name\SKILL.md") $existing
  Log "skill   $existing"
}
foreach ($s in $Skills) { Install-Skill $s $ClaudeSkills; Install-Skill $s $AgentSkills }

# ---- 3. marker-delimited global blocks --------------------------------------
$Begin = '<!-- myos:global:begin -->'; $End = '<!-- myos:global:end -->'
function Block($agent) {
  $cmd = if ($agent -eq 'codex') { '$save-progress, $resume-project, $project-status, $context-search, $executive-briefing' }
         else { '/save-progress, /resume-project, /project-status, /context-search, /executive-briefing' }
@"
$Begin
## myOS - shared project memory (all projects)

- For project context, history, status, or saving and resuming work, use myOS. ``python "$Root\scripts\myos.py" route``
  identifies the current project from the working directory, including Orca and ``.claude/worktrees`` worktrees.
  The routing table is ``$Root\CONTEXT.md``.
- Workflows: $cmd.
- Retrieve narrowly with ``myos search "<terms>"`` and ``myos resume <id>``. Never read the whole Obsidian vault.
- The repository's own instructions govern code. myOS governs records and external transmission.
- Never record a test as passed without output evidence. Never run ``myos graph approve``.
$End
"@
}
foreach ($t in $Targets) {
  $p = $t.Path
  New-Item -ItemType Directory -Force (Split-Path $p) | Out-Null
  $text = if (Test-Path $p) { [IO.File]::ReadAllText($p) } else { '' }
  $blk = Block $t.Agent
  $pattern = [regex]::Escape($Begin) + '[\s\S]*?' + [regex]::Escape($End)
  if ($text -match $pattern) { $new = [regex]::Replace($text, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $blk }) }
  else { $sep = if ($text.Length -gt 0 -and -not $text.EndsWith("`n")) { "`n`n" } elseif ($text.Length -gt 0) { "`n" } else { '' }; $new = $text + $sep + $blk + "`n" }
  if ($new -ne $text) { [IO.File]::WriteAllText($p, $new, (New-Object System.Text.UTF8Encoding $false)); Log "block   $p" } else { Log "same    $p" }
}

# ---- 3b. safety guards (work under bypass/Yolo; permission settings are NOT changed) ----
# Claude Code: PreToolUse hook -> scripts\guard.py
$settings = Join-Path $HOME '.claude\settings.json'
Backup-Item $settings
$guardCmd = "python `"$RootFwd/scripts/guard.py`""
$py = @"
import json,sys
p=sys.argv[1]; cmd=sys.argv[2]
s=json.load(open(p,encoding='utf-8'))
pre=s.setdefault('hooks',{}).setdefault('PreToolUse',[])
if any(h.get('command')==cmd for e in pre for h in e.get('hooks',[])): print('same'); sys.exit()
pre.append({'matcher':'Bash|PowerShell|Read|Edit|Write|MultiEdit|NotebookEdit|Grep|Glob','hooks':[{'type':'command','command':cmd,'timeout':10}]})
json.dump(s,open(p,'w',encoding='utf-8'),indent=2); print('added')
"@
$r = $py | python - $settings $guardCmd
Log "guard   $settings ($r)"
# Codex: exec-policy rules file in both Codex homes (terminal + Orca)
foreach ($home2 in (Join-Path $HOME '.codex'), $OrcaCodexHome) {
  if (-not (Test-Path $home2)) { continue }
  $rules = Join-Path $home2 'rules'
  New-Item -ItemType Directory -Force $rules | Out-Null
  $dst = Join-Path $rules 'myos-guard.rules'
  Backup-Item $dst
  Copy-Item -Force "$Root\config\codex-guard.rules" $dst
  Log "guard   $dst"
}

# ---- 4. vault: create-only ---------------------------------------------------
if (-not $SkipVault) {
  if (-not (Test-Path $Vault)) { throw "Vault not found: $Vault" }
  $tplDst = Join-Path $Vault ($Cfg.vault_layout.templates -replace '/', '\')
  New-Item -ItemType Directory -Force $tplDst | Out-Null
  Get-ChildItem "$Root\templates\obsidian\*.md" | ForEach-Object {
    $d = Join-Path $tplDst $_.Name
    if (Test-Path $d) { Log "exists  $d (kept)" } else { Copy-Item $_.FullName $d; Log "create  $d" }
  }
  $pilot = Join-Path $Vault '03-PROJECTS\_myOS-Pilot'
  New-Item -ItemType Directory -Force "$pilot\sessions" | Out-Null
  $hub = Join-Path $pilot '00-Overview.md'
  if (-not (Test-Path $hub)) {
    $d = Get-Date -Format 'yyyy-MM-dd'
@"
---
type: project-hub
project: myos-sandbox
engagement: personal
created: $d
updated: $d
status: active
tags: [project, myos, pilot]
summary: Pilot knowledge area for myOS - safe, non-client notes used to prove save, resume and graph workflows.
---
# myOS Pilot

This folder is the pilot knowledge area created by myOS. It contains only notes written by myOS
or by its owner for testing. It holds no client data, so it is the first candidate corpus for Graphify
(``myos graph plan vault-pilot``).

- Project card: ``$Root\projects\myos-sandbox.md``
- Templates: [[07-TEMPLATES/myOS/myOS - Project hub]] and the other ``myOS - *`` templates
- Sessions: ``sessions/`` (written by /save-progress)

## Decisions
- [[ADR-0001 myOS keeps graph output outside the vault]]
"@ | Set-Content -Encoding utf8 $hub
    Log "create  $hub"
  }
  $adr = Join-Path $pilot 'ADR-0001 myOS keeps graph output outside the vault.md'
  if (-not (Test-Path $adr)) {
    $d = Get-Date -Format 'yyyy-MM-dd'
@"
---
type: decision
project: myos-sandbox
engagement: personal
created: $d
updated: $d
status: accepted
tags: [decision, adr, myos, graphify]
summary: Graphify output lives in the myOS data\graph folder, never inside the Obsidian vault.
---
# ADR-0001 myOS keeps graph output outside the vault

## Context
Graphify writes graph.json, GRAPH_REPORT.md, graph.html and a cache. Writing these into the vault would
pollute Obsidian search and the graph view, and could sync derived data to the vault's GitHub remote.

## Decision
Stage approved notes into ``$Root\data\graph\<corpus>\corpus`` and write the outputs to
``data\graph\<corpus>\graphify-out``. The vault stays the source and is never a build target.

## Consequences
- Rebuilding a graph never touches the vault.
- Graph outputs are git-ignored in myOS and are rebuildable at any time.
"@ | Set-Content -Encoding utf8 $adr
    Log "create  $adr"
  }
}
Log "done. backups: $Backup"
