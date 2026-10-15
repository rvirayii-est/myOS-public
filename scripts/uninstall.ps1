<#
.SYNOPSIS
  Removes what scripts\install.ps1 added: the myOS marker blocks and the five myOS skills.
  The vault is left untouched (templates and pilot notes are ordinary notes; delete them by hand if wanted).
  Backups in backups\<timestamp>\ are kept.
#>
$ErrorActionPreference = 'Stop'
$Begin = '<!-- myos:global:begin -->'; $End = '<!-- myos:global:end -->'
$files = @((Join-Path $HOME '.claude\CLAUDE.md'), (Join-Path $HOME '.codex\AGENTS.md'),
           (Join-Path $env:APPDATA 'orca\codex-runtime-home\home\AGENTS.md'))
foreach ($p in $files) {
  if (-not (Test-Path $p)) { continue }
  $t = [IO.File]::ReadAllText($p)
  $n = [regex]::Replace($t, '\r?\n?' + [regex]::Escape($Begin) + '[\s\S]*?' + [regex]::Escape($End) + '\r?\n?', "`n")
  if ($n -ne $t) { [IO.File]::WriteAllText($p, $n.TrimEnd() + "`n", (New-Object System.Text.UTF8Encoding $false)); "removed block from $p" }
}
# safety guards
foreach ($f in (Join-Path $HOME '.codex\rules\myos-guard.rules'), (Join-Path $env:APPDATA 'orca\codex-runtime-home\home\rules\myos-guard.rules')) {
  if (Test-Path $f) { Remove-Item -Force $f; "removed $f" }
}
$py = @"
import json,sys,os
p=os.path.expanduser('~/.claude/settings.json'); s=json.load(open(p,encoding='utf-8'))
pre=s.get('hooks',{}).get('PreToolUse',[])
keep=[e for e in pre if not any('myOS/scripts/guard.py' in h.get('command','') for h in e.get('hooks',[]))]
if len(keep)!=len(pre): s['hooks']['PreToolUse']=keep; json.dump(s,open(p,'w',encoding='utf-8'),indent=2); print('removed guard hook from',p)
"@
$py | python -
foreach ($root in (Join-Path $HOME '.claude\skills'), (Join-Path $HOME '.agents\skills')) {
  foreach ($s in 'save-progress','resume-project','project-status','context-search','executive-briefing') {
    $f = Join-Path $root "$s\SKILL.md"
    if ((Test-Path $f) -and (Select-String -Path $f -Pattern 'description: myOS' -Quiet)) {
      Remove-Item -Recurse -Force (Join-Path $root $s); "removed skill $root\$s"
    }
  }
}
