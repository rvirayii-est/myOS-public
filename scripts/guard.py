#!/usr/bin/env python3
"""myOS safety guard - Claude Code PreToolUse hook.

The owner runs agents in bypass/Yolo mode on purpose. This hook does not change that. It still
returns a decision for a short list of high-risk actions:

  deny  - destructive git history/worktree operations, recursive deletes of protected roots,
          destructive SQL / database resets, bypassing the Graphify approval gate.
  ask   - mutating operations against production hosts, reading secret files, uploading
          secret files, touching another engagement's repository or notes.

PreToolUse hook decisions apply in every permission mode. "ask" shows the owner a confirmation
prompt in interactive sessions; headless (-p) runs cannot prompt, so they treat it as blocked.

Fail-open: any internal error allows the tool call, so a guard bug can never break an agent.
Disable for one session by launching the agent with MYOS_GUARD=off.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

SEG = r"[^;&|\n]*"  # stays within one shell command segment


def _git(sub: str, rest: str) -> str:
    return rf"\bgit\b{SEG}\b{sub}\b{SEG}{rest}"


SQL_CLIENT = r"(?is)\b(psql|sqlcmd|mysql|sqlite3|pgcli|duckdb|supabase|osql|invoke-sqlcmd)\b.*"

DENY_RULES = [
    ("guard-selftest", r"\bmyos-guard-selftest\b", "guard self-test canary (harmless; proves the hook is active)"),
    ("git-force-push", _git("push", r"(\s--force(-with-lease)?\b|\s-f\b|\s--mirror\b|\s\+[\w./-]+)"),
     "force-push rewrites remote history"),
    ("git-push-delete", _git("push", r"(\s--delete\b|\s-d\b|\s:[\w./-]+)"), "deleting a remote branch"),
    ("git-reset-hard", _git("reset", r"--hard\b"), "git reset --hard discards work"),
    ("git-clean-force", _git("clean", r"(\s-[a-zA-Z]*f|\s--force\b)"), "git clean -f deletes untracked files"),
    ("git-branch-force-delete", r"\bgit\b" + SEG + r"\bbranch\b" + SEG + r"(\s-D\b|--delete\s+--force|\s-d\s+-f\b)",
     "force-deleting a branch"),
    ("git-worktree-force-remove", _git("worktree", r"\bremove\b" + SEG + r"(\s--force\b|\s-f\b)"), "force-removing a worktree"),
    ("git-stash-clear", _git("stash", r"\bclear\b"), "git stash clear destroys all stashes"),
    ("git-history-rewrite", r"\bgit\b" + SEG + r"\b(filter-branch|filter-repo|replace)\b|\bgit\b" + SEG + r"\breflog\b" + SEG
     + r"\bexpire\b|\bgit\b" + SEG + r"\bupdate-ref\b" + SEG + r"\s-d\b", "rewriting or deleting git history"),
    # SQL rules fire only when a database client is in the same command (not e.g. a commit message).
    ("db-destructive", SQL_CLIENT + r"\b(drop\s+(database|schema|table)|truncate\s+(table\s+)?[\w\"\.]+)\b", "destructive SQL"),
    ("db-delete-all", SQL_CLIENT + r"\bdelete\s+from\s+[\w\"\.]+\s*(;|\"|'|$)", "DELETE without WHERE"),
    ("db-reset", r"(?i)\b(flyway\b" + SEG + r"\bclean|supabase\s+db\s+reset|prisma\s+migrate\s+reset|dotnet\s+ef\s+database\s+drop"
     r"|rails\s+db:(drop|reset)|mix\s+ecto\.drop)\b", "database wipe/reset command"),
    ("graphify-direct", r"(?i)(^|[\s\"'/\\])graphify(\.exe)?[\"']?\s+(extract|update|watch|install|uninstall|hook|claude|codex|add|clone"
     r"|cluster-only|label|merge-graphs|global)\b", "Graphify must run through `myos graph` so the exclusion policy and approval gate apply"),
    ("graphify-approve", r"(?i)myos(\.py|\.cmd)?[\"']?\s+graph\s+approve\b", "only the owner approves Graphify corpora, in their own terminal"),
]

ASK_RULES = [
    ("git-discard-all", r"\bgit\b" + SEG + r"\b(checkout|restore)\b" + SEG + r"\s(--\s+)?\.(\s|$|;|&|\|)", "discarding all uncommitted changes"),
    ("git-branch-delete", r"\bgit\b" + SEG + r"\bbranch\b" + SEG + r"(\s-d\b|\s--delete\b)", "deleting a branch"),
    ("git-worktree-remove", _git("worktree", r"\bremove\b"), "removing a worktree"),
    ("git-stash-drop", _git("stash", r"\bdrop\b"), "dropping a stash"),
    ("deploy-command", r"(?i)\b(vercel\b" + SEG + r"--prod|netlify\s+deploy\b" + SEG + r"--prod|fly\s+deploy|firebase\s+deploy"
     r"|kubectl\b" + SEG + r"\b(apply|delete|rollout|scale)\b|helm\s+(install|upgrade|uninstall)|terraform\s+(apply|destroy)"
     r"|docker(-compose|\s+compose)\b" + SEG + r"prod" + SEG + r"\b(up|down|restart|pull|rm|stop)\b)", "deployment / infrastructure change"),
]

# Rules that no environment override can switch off.
NEVER_EXEMPT = {"graphify-approve", "graphify-direct", "guard-selftest", "recursive-delete-protected"}

RECURSIVE_DELETE = re.compile(r"(?i)(\brm\s+(-[a-z]*r[a-z]*|--recursive)\b|\bremove-item\b[^;&|\n]*-r(ecurse)?\b|\b(rmdir|rd)\s+/s\b"
                              r"|\bdel\s+/s\b|shutil\.rmtree|\brimraf\b)")
MUTATING_NET = re.compile(r"(?i)\b(ssh|scp|rsync|sftp|psql|pg_dump|pg_restore|mysql)\b|curl\b" + SEG
                          + r"(-X\s*(POST|PUT|PATCH|DELETE)|--data|-d\s|-F\s|--upload-file|-T\s)|invoke-(webrequest|restmethod)\b"
                          + SEG + r"-method\s+(post|put|patch|delete)")
READ_VERB = re.compile(r"(?i)\b(cat|type|get-content|gc|more|less|head|tail|bat|select-string|findstr|grep|rg|base64|xxd|strings)\b")
NET_TOOL = re.compile(r"(?i)\b(curl|wget|invoke-webrequest|invoke-restmethod|iwr|irm|scp|rsync|nc|ncat|ftp)\b")


def guard_cfg() -> dict:
    return json.loads((ROOT / "config" / "guard.json").read_text(encoding="utf-8"))


def _norm_token(tok: str, cwd: str) -> str | None:
    t = tok.strip("\"'`").rstrip("\\/*").rstrip("\\/")
    if not t:
        return None
    home = os.path.expanduser("~")
    t = re.sub(r"^(\$HOME|\$env:USERPROFILE|~)(?=$|[\\/])", lambda _: home.replace("\\", "/"), t, flags=re.I)
    m = re.match(r"^/([a-zA-Z])(/|$)(.*)", t)
    if m:
        t = f"{m.group(1)}:/{m.group(3)}"
    if t in (".", "./"):
        t = cwd
    if not re.match(r"^[a-zA-Z]:", t) and cwd:
        t = os.path.join(cwd, t)
    return os.path.normcase(os.path.normpath(t))


def protected_roots(cards) -> set[str]:
    import myos
    home = Path.home()
    v = myos.vault_root()
    roots = [Path("C:/"), Path(myos.cfg()["projects_root"]), home, home / ".claude", home / ".codex", home / ".agents",
             Path(os.environ.get("APPDATA", str(home / "AppData/Roaming"))) / "orca", Path(myos.cfg()["orca_workspaces"]),
             ROOT, v, home / "Documents"]
    if v.exists():
        roots += [p for p in v.iterdir() if p.is_dir()]
    roots += [c.repo() for c in cards if c.repo()]
    return {os.path.normcase(os.path.normpath(str(r))) for r in roots}


def path_tokens(cmd: str) -> list[str]:
    return re.findall(r"\"[^\"]+\"|'[^']+'|[^\s;&|<>()]+", cmd)


def engagement_of_path(p: str, cards) -> str | None:
    import myos
    best, eng = -1, None
    for c in cards:
        if str(c["test"]).lower() == "true":
            continue
        cands = ([c.repo()] if c.repo() else []) + c.vault_paths()
        for r in cands:
            if r and myos.is_under(p, r) and not c.excluded(Path(p)) and len(str(r)) > best:
                best, eng = len(str(r)), c["engagement"]
    return eng


def cwd_engagement(cwd: str, cards) -> str | None:
    import myos
    if not cwd or myos.is_under(cwd, ROOT):
        return None  # myOS itself works across engagements (routing, briefing)
    hits, _ = myos.resolve(None, cwd)
    engs = {c["engagement"] for c in hits if str(c["test"]).lower() != "true"}
    return engs.pop() if len(engs) == 1 else None


# Text handed to a shell is code; any other quoted text / heredoc body is data (commit messages,
# prompts, docs being written) and must not trigger command rules.
EXEC_INTRO = re.compile(r"(?i)(\b(bash|sh|zsh|pwsh|powershell|cmd|eval|iex|invoke-expression|ssh\s+\S+)\s*$"
                        r"|\s-(c|command|encodedcommand)\s*$|\s/c\s*$)")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n(.*?)\n[ \t]*\2[ \t]*(?=\n|$)", re.S)


def mask_inert(cmd: str) -> str:
    """Blank out data (heredoc bodies, quoted text containing spaces) unless it is fed to a shell."""
    def heredoc(m):
        line_start = cmd.rfind("\n", 0, m.start()) + 1
        if re.search(r"(?i)\b(bash|sh|zsh|pwsh|powershell|cmd)\b[^\n|]*$", cmd[line_start:m.start()]):
            return m.group(0)
        return m.group(0).replace(m.group(3), " " * len(m.group(3)))
    out = HEREDOC.sub(heredoc, cmd)

    def quoted(m):
        s = m.group(0)
        if not re.search(r"\s", s[1:-1]) or EXEC_INTRO.search(out[:m.start()]):
            return s  # single-token argument (a path, a flag value) or shell code: keep
        return s[0] + " " * (len(s) - 2) + s[-1]
    return re.sub(r"\"(?:\\.|[^\"\\])*\"|'[^']*'", quoted, out)


MYOS_CALL = re.compile(r"(?i)myos(?:\.py|\.cmd)?[\"']?\s+(?:--cwd\s+(\"[^\"]+\"|'[^']+'|\S+)\s+)?(search|resume|status|brief|route)\b([^;&|\n]*)")


def myos_query_scope(cmd: str, cwd: str) -> str | None:
    """Reason string if a myOS knowledge query would read outside the session's engagement."""
    import myos
    calls = list(MYOS_CALL.finditer(cmd))
    if not calls:
        return None
    cards = myos.load_cards()
    here = cwd_engagement(cwd, cards)
    if not here:
        return None  # owner view (myOS root / unregistered folder)
    by_id = {c.id: c for c in cards}
    for m in calls:
        sub, rest = m.group(2).lower(), m.group(3)
        if sub == "brief":
            return f"executive briefing covers all engagements; this session belongs to '{here}'"
        if re.search(r"--all-engagements\b", rest):
            return f"--all-engagements from a '{here}' session"
        e = re.search(r"--engagement\s+(\S+)", rest)
        if e and e.group(1).strip("\"'") != here:
            return f"--engagement {e.group(1)} from a '{here}' session"
        targets = re.findall(r"--project\s+(\S+)", rest)
        if sub in ("resume", "status", "route"):
            pos = [t for t in re.findall(r"(?<!-)\b([a-z0-9][a-z0-9-]+)\b", re.sub(r"--\S+\s+\S+", " ", rest)) if t in by_id]
            targets += pos
        for t in targets:
            c = by_id.get(t.strip("\"'"))
            if c and c["engagement"] != here and str(c["test"]).lower() != "true":
                return f"query for project '{c.id}' (engagement '{c['engagement']}') from a '{here}' session"
        # effective directory: --cwd, or a `cd` earlier in the same command line
        d = m.group(1) or next(iter(re.findall(r"\bcd\s+(\"[^\"]+\"|'[^']+'|\S+)", cmd[:m.start()])[-1:]), None)
        if d and not targets:
            n = _norm_token(d, cwd)
            there = None if (n and myos.is_under(n, ROOT)) else (cwd_engagement(n, cards) if n else None)
            if n and myos.is_under(n, ROOT):
                return f"query run from the myOS root (all-engagement owner view) inside a '{here}' session"
            if there and there != here:
                return f"query run from a '{there}' folder inside a '{here}' session"
    return None


def decide(tool: str, ti: dict, cwd: str) -> tuple[str, str, str] | None:
    """Return (decision, rule, reason) or None to stay silent."""
    gc = guard_cfg()
    secret_rx = [re.compile(p, re.I) for p in gc["secret_file_patterns"]]
    # also test the part after `=` / `@` (curl -F file=@.env, --env-file=.env)
    def is_secret(s: str) -> bool:
        s = s.strip("\"'`")
        if re.search(r"[|()^$?*\[\]{}]", s):
            return False  # a regex / glob pattern (e.g. Select-String -Pattern), not a file path
        return any(r.search(part) for part in re.split(r"[=@]", s) for r in secret_rx)
    raw = ti.get("command") if tool in ("Bash", "PowerShell") else None
    cmd = mask_inert(raw) if raw else None

    if cmd:
        for rid, rx, why in DENY_RULES:
            if re.search(rx, cmd):
                return "deny", rid, why
        delete_segments = [seg for seg in re.split(r"&&|\|\||[;|\n]", cmd) if RECURSIVE_DELETE.search(seg)]
        if delete_segments:
            import myos
            prot = protected_roots(myos.load_cards())
            # only paths in the same command segment as the delete verb are delete targets
            for tok in [t for seg in delete_segments for t in path_tokens(seg)]:
                n = _norm_token(tok, cwd)
                # protected roots, any .git dir, and any repo/worktree root (a folder holding .git)
                if n and (n in prot or re.search(r"[\\/]\.git$", n) or os.path.exists(os.path.join(n, ".git"))):
                    return "deny", "recursive-delete-protected", f"recursive delete of a protected location ({tok.strip(chr(34))})"
        hosts = [h for h in gc["production_hosts"] if h.lower() in cmd.lower()]
        if hosts and MUTATING_NET.search(cmd):
            return "deny", "production-host", (f"mutating command against production-class host {hosts[0]} "
                                               f"({gc['production_hosts'][hosts[0]]}). For a deliberate deploy session, the owner "
                                               "launches the agent with MYOS_GUARD_ALLOW=production-host")
        toks = path_tokens(cmd)
        if any(is_secret(t) for t in toks):
            if NET_TOOL.search(cmd):
                return "deny", "secret-upload", "a secret file is referenced in a network command"
            if READ_VERB.search(cmd):
                return "ask", "secret-read", "reading a secret file (.env / key / credentials) would expose its contents"
            if re.search(r"\bgit\b" + SEG + r"\badd\b", cmd):
                return "ask", "secret-git-add", "staging a secret file into git"
        for rid, rx, why in ASK_RULES:
            if re.search(rx, cmd):
                return "ask", rid, why
    elif tool == "Read" and is_secret(str(ti.get("file_path", ""))):
        return "ask", "secret-read", "reading a secret file (.env / key / credentials) would expose its contents"

    # self-protection: changing the guard itself needs the owner
    rn = "(?:myOS|" + re.escape(ROOT.name) + ")"  # the default folder name and wherever this copy is installed
    GUARD_FILES = (r"(?i)(" + rn + r"[\\/]config[\\/]guard\.json|" + rn + r"[\\/]scripts[\\/]guard\.py"
                   r"|myos-guard\.rules|codex-guard\.rules)")
    if tool in ("Edit", "Write", "MultiEdit") and re.search(GUARD_FILES, str(ti.get("file_path", ""))):
        return "ask", "guard-self-edit", "changing the myOS guard"
    if cmd and re.search(GUARD_FILES, raw) and re.search(r"(?i)(sed\s+-i|>|set-content|out-file|add-content|copy-item|\bcp\b|\bmv\b"
                                                         r"|\brm\b|remove-item|move-item)", cmd):
        return "ask", "guard-self-edit", "changing the myOS guard"

    # myOS knowledge queries that reach another engagement (explicit flags, positional id, --cwd, or `cd` elsewhere)
    if cmd and gc.get("cross_engagement") == "ask":
        r = myos_query_scope(raw, cwd)
        if r:
            return "ask", "cross-engagement-query", r

    # cross-engagement access (ask)
    if gc.get("cross_engagement") == "ask":
        targets = []
        if tool in ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit"):
            targets = [ti.get("file_path") or ti.get("notebook_path") or ""]
        elif tool in ("Grep", "Glob"):
            targets = [ti.get("path") or ""]
        elif cmd:
            targets = [t.strip("\"'") for t in path_tokens(cmd) if re.match(r"^[\"']?([a-zA-Z]:[\\/]|/[a-zA-Z]/)", t)]
        targets = [t for t in targets if t]
        if targets:
            import myos
            cards = myos.load_cards()
            here = cwd_engagement(cwd, cards)
            if here:
                for t in targets:
                    n = _norm_token(t, cwd)
                    there = engagement_of_path(n, cards) if n else None
                    if there and there != here:
                        return gc["cross_engagement"], "cross-engagement", (
                            f"this session belongs to engagement '{here}' but the target belongs to '{there}' ({t})")
                    # a folder that CONTAINS another engagement's project (vault root, 03-PROJECTS, C:\projects)
                    if n and not there:
                        spans = [c for c in cards if c["engagement"] != here and str(c["test"]).lower() != "true"
                                 and any(myos.is_under(r, n) for r in ([c.repo()] if c.repo() else []) + c.vault_paths())]
                        if spans:
                            return gc["cross_engagement"], "cross-engagement", (
                                f"'{t}' spans other engagements' material (e.g. {spans[0].id}); search from myOS or scope to this project")
    return None


def log(decision, rule, tool, cwd, ti):
    try:
        import myos
        snippet = myos.redact(str(ti.get("command") or ti.get("file_path") or ti.get("path") or ""))[:160].replace("\n", " ")
        p = Path(os.environ.get("MYOS_GUARD_LOG") or (ROOT / guard_cfg().get("log", "logs/guard.log")))
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{myos.now_iso()}\t{decision}\t{rule}\t{tool}\t{cwd}\t{snippet}\n")
    except Exception:
        pass


def main():
    if os.environ.get("MYOS_GUARD", "").lower() == "off":
        return
    try:
        data = json.loads(sys.stdin.read() or "{}")
        tool, ti, cwd = data.get("tool_name", ""), data.get("tool_input") or {}, data.get("cwd") or os.getcwd()
        res = decide(tool, ti, cwd)
    except Exception:
        return  # fail open
    if not res:
        return
    decision, rule, why = res
    # owner-granted, per-session exemptions (set in the agent's launch environment; agents cannot set it)
    if rule in {r.strip() for r in os.environ.get("MYOS_GUARD_ALLOW", "").split(",")} and rule not in NEVER_EXEMPT:
        log("allow-by-owner", rule, tool, cwd, ti)
        return
    if decision == "ask" and guard_cfg().get("ask_as") == "deny":
        decision = "deny"
    log(decision, rule, tool, cwd, ti)
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": f"myOS guard [{rule}]: {why}. "
        + ("Blocked. If this is truly intended, the owner runs it manually." if decision == "deny"
           else "Owner confirmation required.")}}))


if __name__ == "__main__":
    main()
