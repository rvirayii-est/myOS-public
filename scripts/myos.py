#!/usr/bin/env python3
"""myOS - personal AI operating system CLI (stdlib only).

Routing (ICM), project cards, Obsidian session records, deterministic context
search, Graphify policy layer, executive briefing.

Every command that touches a product repository is read-only: it runs
`git --no-optional-locks` plumbing/porcelain queries and never fetches,
checks out, resets, commits or pushes.

Run `python scripts/myos.py --help` (or `myos --help` via scripts/myos.cmd).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "myos.json"
POLICY_PATH = ROOT / "config" / "exclusion-policy.json"
APPROVALS_PATH = Path(os.environ.get("MYOS_APPROVALS", ROOT / "config" / "graph-approvals.json"))
# MYOS_PROJECTS_DIR / MYOS_JOURNAL_DIR exist so tests can run against a scratch copy.
PROJECTS_DIR = Path(os.environ.get("MYOS_PROJECTS_DIR", ROOT / "projects"))
ENGAGEMENTS_DIR = ROOT / "engagements"
JOURNAL_DIR = Path(os.environ.get("MYOS_JOURNAL_DIR", ROOT / "logs" / "journal"))
GRAPH_DIR = Path(os.environ.get("MYOS_GRAPH_DIR", ROOT / "data" / "graph"))
GRAPHIFY_EXE = ROOT / "graphify" / ".venv" / "Scripts" / "graphify.exe"
SHIM_DIR = ROOT / "graphify" / "shim"

UNVERIFIED = "UNVERIFIED"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# basics
# --------------------------------------------------------------------------- #
def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def expand_path(s: str) -> str:
    """Config/card path: ~ and %VAR%/$VAR expand; @projects/<x> is under projects_root; @myos is the myOS root;
    a relative path is relative to the myOS root."""
    s = os.path.expanduser(os.path.expandvars(str(s)))
    if s == "@myos" or s.startswith(("@myos/", "@myos\\")):
        s = str(ROOT) + s[5:]
    elif s.startswith("@projects"):
        s = cfg()["projects_root"] + s[len("@projects"):]
    return str(Path(s) if Path(s).is_absolute() else (ROOT / s))


# Environment overrides (used by tests, or to point at another vault) so tests never touch the real one.
PATH_ENV = {"vault": "MYOS_VAULT", "projects_root": "MYOS_PROJECTS_ROOT", "orca_workspaces": "MYOS_ORCA_WORKSPACES"}


def cfg() -> dict:
    data = load_json(CONFIG_PATH)
    for key, env in PATH_ENV.items():
        data[key] = os.environ.get(env) or data.get(key) or ""
        if data[key]:
            data[key] = expand_path(data[key])
    return data


def vault_root() -> Path:
    return Path(cfg()["vault"])


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def today() -> str:
    return now().date().isoformat()


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def npath(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def is_under(child, parent) -> bool:
    c, p = npath(child), npath(parent)
    return c == p or c.startswith(p.rstrip("\\/") + os.sep)


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def die(msg: str, code: int = 2):
    print(f"myos: {msg}", file=sys.stderr)
    sys.exit(code)


# --------------------------------------------------------------------------- #
# frontmatter (small YAML subset: scalars, inline [lists], quoted strings)
# --------------------------------------------------------------------------- #
FM_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def _parse_scalar(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(x) for x in re.findall(r'"[^"]*"|\'[^\']*\'|[^,]+', inner)]
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if v in ("null", "~", ""):
        return None
    return v


def parse_frontmatter(text: str):
    m = FM_RE.match(text)
    if not m:
        return {}, text
    data = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^([A-Za-z0-9_\-]+):\s*(.*)$", line)
        if mm:
            data[mm.group(1)] = _parse_scalar(mm.group(2))
    return data, text[m.end():]


def _dump_scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, list):
        return "[" + ", ".join(_dump_scalar(x) for x in v) + "]"
    s = str(v)
    if s == "" or re.search(r"[:#\[\]{},&*!|>'\"%@`]", s) or s.strip() != s:
        return '"' + s.replace('"', "'") + '"'
    return s


def dump_frontmatter(data: dict) -> str:
    return "---\n" + "".join(f"{k}: {_dump_scalar(v)}\n" for k, v in data.items()) + "---\n"


def set_frontmatter(text: str, updates: dict) -> str:
    data, body = parse_frontmatter(text)
    data.update(updates)
    return dump_frontmatter(data) + body


# --------------------------------------------------------------------------- #
# managed blocks: <!-- myos:NAME:begin --> ... <!-- myos:NAME:end -->
# --------------------------------------------------------------------------- #
def replace_block(text: str, name: str, content: str, anchor_before: str | None = None) -> str:
    begin, end = f"<!-- myos:{name}:begin -->", f"<!-- myos:{name}:end -->"
    block = f"{begin}\n{content.rstrip()}\n{end}"
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if pat.search(text):
        return pat.sub(lambda _: block, text, count=1)
    if anchor_before and anchor_before in text:
        return text.replace(anchor_before, block + "\n\n" + anchor_before, 1)
    return text.rstrip() + "\n\n" + block + "\n"


def get_block(text: str, name: str) -> str | None:
    m = re.search(rf"<!-- myos:{name}:begin -->\n?(.*?)\n?<!-- myos:{name}:end -->", text, re.S)
    return m.group(1) if m else None


# --------------------------------------------------------------------------- #
# crash-safe multi-file writes (journal -> temp files -> os.replace)
# --------------------------------------------------------------------------- #
def atomic_write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".myos-tmp-{os.getpid()}")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def journaled_write(writes: list[tuple[Path, str]], label: str) -> list[str]:
    """Write several files as one recoverable transaction.

    The journal holds the full target content, so `myos recover` can replay an
    interrupted transaction; replay is idempotent."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    changed = [(p, c) for p, c in writes if not (p.exists() and p.read_text(encoding="utf-8") == c)]
    if not changed:
        return []
    txn = JOURNAL_DIR / f"{now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}.pending.json"
    atomic_write(txn, json.dumps({"label": label, "created": now_iso(),
                                  "writes": [{"path": str(p), "content": c} for p, c in changed]}, indent=1))
    for p, c in changed:
        atomic_write(p, c)
    txn.replace(txn.with_name(txn.name.replace(".pending.json", ".done.json")))
    return [str(p) for p, _ in changed]


class card_lock:
    """Cross-process lock for a card's read-modify-write (two agents saving the same project at once)."""

    def __init__(self, card_id: str, timeout=30.0, stale=120.0):
        self.path = JOURNAL_DIR.parent / "locks" / f"{card_id}.lock"
        self.timeout, self.stale = timeout, stale

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {now_iso()}".encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()  # holder crashed; lock is stale
                        continue
                except FileNotFoundError:
                    continue
                if time.time() > deadline:
                    die(f"another myOS write holds {self.path.name}; try again shortly", 6)
                time.sleep(0.2)

    def __exit__(self, *exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def recover_pending(verbose=True) -> int:
    n = 0
    for txn in sorted(JOURNAL_DIR.glob("*.pending.json")):
        data = json.loads(txn.read_text(encoding="utf-8"))
        for w in data["writes"]:
            atomic_write(Path(w["path"]), w["content"])
        txn.replace(txn.with_name(txn.name.replace(".pending.json", ".recovered.json")))
        n += 1
        if verbose:
            print(f"recovered interrupted write: {data['label']} ({len(data['writes'])} files)")
    return n


# --------------------------------------------------------------------------- #
# git (read-only)
# --------------------------------------------------------------------------- #
def git(repo, *args, timeout=20) -> str | None:
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def git_main_repo(path) -> Path | None:
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    p = Path(common)
    return p.parent if p.name == ".git" else p


def git_facts(repo) -> dict:
    """Live, read-only facts about a working tree. Never fetches."""
    repo = Path(repo)
    f = {"path": str(repo), "exists": repo.exists(), "checked_at": now_iso()}
    if not f["exists"]:
        return f
    top = git(repo, "rev-parse", "--show-toplevel")
    f["is_git"] = bool(top)
    if not top:
        return f
    f["toplevel"] = str(Path(top))
    f["branch"] = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    log = git(repo, "log", "-1", "--format=%h%x09%cI%x09%s")
    if log:
        sha, date, subj = (log.split("\t", 2) + ["", ""])[:3]
        f.update(head=sha, head_date=date, head_subject=subj[:120])
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=normal") or ""
    lines = [l for l in status.splitlines() if l.strip()]
    f["dirty_total"] = len(lines)
    f["untracked"] = sum(1 for l in lines if l.startswith("??"))
    f["modified"] = f["dirty_total"] - f["untracked"]
    f["dirty_sample"] = [l[3:] for l in lines[:12]]
    up = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    f["upstream"] = up
    if up:
        ab = git(repo, "rev-list", "--left-right", "--count", f"{up}...HEAD")
        if ab and len(ab.split()) == 2:
            f["behind"], f["ahead"] = (int(x) for x in ab.split())
    f["remote"] = git(repo, "remote", "get-url", "origin")
    wt = git(repo, "worktree", "list", "--porcelain") or ""
    f["worktrees"] = sum(1 for l in wt.splitlines() if l.startswith("worktree "))
    # human-facing worktrees (Orca and plain), skipping Claude's throwaway agent worktrees
    f["worktree_list"] = [
        (blk.split("\n")[0][9:], (re.search(r"^branch refs/heads/(.+)$", blk, re.M) or [None, "(detached)"])[1])
        for blk in wt.split("\n\n") if blk.startswith("worktree ") and "/.claude/worktrees/" not in blk.replace("\\", "/")]
    return f


def diff_stat(repo) -> str:
    return git(repo, "diff", "--stat", "HEAD") or ""


# --------------------------------------------------------------------------- #
# cards and engagements
# --------------------------------------------------------------------------- #
class Card:
    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.fm, self.body = parse_frontmatter(self.text)

    def __getitem__(self, k):
        return self.fm.get(k)

    @property
    def id(self):
        return self.fm.get("id") or self.path.stem

    @property
    def name(self):
        return self.fm.get("name") or self.id

    def repo(self) -> Path | None:
        r = self.fm.get("repo")
        return Path(expand_path(r)) if r and r != UNVERIFIED else None

    def vault_folder(self) -> Path | None:
        vf = self.fm.get("vault_folder")
        return vault_root() / vf if vf and vf != UNVERIFIED else None

    def vault_paths(self) -> list[Path]:
        """Vault folder + explicitly related notes/folders (card fields vault_folder, vault_related)."""
        out = [self.vault_folder()] if self.vault_folder() else []
        return out + [vault_root() / r for r in (self.fm.get("vault_related") or [])]

    def excluded(self, p: Path) -> bool:
        """True for notes listed in vault_exclude (they belong to another project)."""
        return any(is_under(p, vault_root() / r) for r in (self.fm.get("vault_exclude") or []))

    def sessions_folder(self) -> Path:
        vf = self.fm.get("vault_folder")
        if not vf or vf == UNVERIFIED:
            vf = f"{cfg()['vault_layout']['projects']}/{re.sub(r'[^A-Za-z0-9-]', '', self.name.title().replace(' ', '-'))}"
        return vault_root() / vf / cfg()["vault_layout"]["sessions_subdir"]

    def save(self, text: str):
        self.text = text
        self.fm, self.body = parse_frontmatter(text)


def load_cards(include_test=True) -> list[Card]:
    cards = [Card(p) for p in sorted(PROJECTS_DIR.glob("*.md")) if not p.name.startswith("_")]
    return [c for c in cards if include_test or str(c["test"]).lower() != "true"]


def load_engagements() -> list[dict]:
    out = []
    for p in sorted(ENGAGEMENTS_DIR.glob("*/ENGAGEMENT.md")):
        fm, _ = parse_frontmatter(p.read_text(encoding="utf-8"))
        fm["_path"] = str(p)
        fm.setdefault("id", p.parent.name)
        out.append(fm)
    out.sort(key=lambda e: int(e.get("order") or 99))
    return out


def card_keys(c: Card) -> set[str]:
    keys = {norm(c.id), norm(c.name)}
    keys |= {norm(a) for a in (c["aliases"] or [])}
    return {k for k in keys if k}


def resolve(query: str | None = None, cwd: str | None = None) -> tuple[list[Card], str]:
    """Return (candidates, how). One candidate means a confident match."""
    cards = load_cards()
    if query:
        q = norm(query)
        exact = [c for c in cards if q in card_keys(c)]
        if exact:
            return exact, "name/alias"
        part = [c for c in cards if any(q in k or (len(k) > 3 and k in q) for k in card_keys(c))]
        if part:
            return part, "partial name"
        return [], "no match"

    cwd = Path(cwd or os.getcwd())
    # 1. git: map any worktree (Orca, .claude/worktrees, plain) to its main repository
    main = git_main_repo(cwd)
    if main:
        hits = [c for c in cards if c.repo() and npath(c.repo()) == npath(main)]
        if hits:
            return _narrow_by_subpath(hits, cwd, main), "git repository"
    # 2. Orca workspace folder named after the repo
    ows = Path(cfg()["orca_workspaces"])
    if is_under(cwd, ows):
        rel = Path(os.path.relpath(cwd, ows)).parts
        if rel and rel[0] != ".":
            hits = [c for c in cards if c.repo() and c.repo().name.lower() == rel[0].lower()]
            if hits:
                return hits, "Orca workspace"
    # 3. inside a repo path that is not a git repo / inside a vault project folder
    hits = [c for c in cards if c.repo() and is_under(cwd, c.repo())]
    if hits:
        return _narrow_by_subpath(hits, cwd, hits[0].repo()), "repository folder"
    hits = [c for c in cards if c.vault_folder() and is_under(cwd, c.vault_folder())]
    if hits:
        return hits, "vault folder"
    return [], "cwd not inside a registered project"


def _narrow_by_subpath(hits: list[Card], cwd: Path, repo_root: Path) -> list[Card]:
    if len(hits) < 2:
        return hits
    try:
        rel = Path(os.path.relpath(cwd, git(cwd, "rev-parse", "--show-toplevel") or repo_root))
    except ValueError:
        return hits
    best = [c for c in hits for sp in (c["repo_subpaths"] or []) if rel.parts and rel.parts[0].lower() == sp.lower()]
    return best or hits


def require_one(query, cwd=None) -> Card:
    hits, how = resolve(query, cwd)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        die(f"could not identify the project ({how}). Pass a name, e.g. `myos route lumen-ledger`, or run `myos list`.", 3)
    die("ambiguous project; candidates: " + ", ".join(f"{c.id} ({c.name})" for c in hits)
        + ". Re-run with one of these ids.", 3)


def obsidian_uri(rel: str) -> str:
    from urllib.parse import quote
    return f"obsidian://open?vault={quote(cfg()['vault_name'])}&file={quote(rel.replace(os.sep, '/'))}"


def vault_rel(p: Path) -> str:
    try:
        return Path(os.path.relpath(p, vault_root())).as_posix()
    except ValueError:
        return str(p)


# --------------------------------------------------------------------------- #
# redaction (for anything we print from notes)
# --------------------------------------------------------------------------- #
def policy() -> dict:
    return load_json(POLICY_PATH)


def _content_rules():
    return {k: re.compile(v) for k, v in policy()["content_rules"].items()}


def redact(line: str) -> str:
    for rx in _content_rules().values():
        line = rx.sub("[REDACTED]", line)
    return line


# --------------------------------------------------------------------------- #
# sessions
# --------------------------------------------------------------------------- #
SESSION_RE = re.compile(r"<!-- myos:session:begin id=(?P<id>[^ ]+) -->(?P<body>.*?)<!-- myos:session:end id=(?P=id) -->", re.S)


def session_files(c: Card) -> list[Path]:
    folder = c.sessions_folder()
    if not folder.exists():
        return []
    files = [p for p in folder.glob("*.md") if c.id in p.stem or parse_frontmatter(p.read_text(encoding="utf-8"))[0].get("project") == c.id]
    return sorted(files, key=lambda p: p.name, reverse=True)


def latest_sessions(c: Card, n=3) -> list[dict]:
    out = []
    for f in session_files(c):
        text = f.read_text(encoding="utf-8")
        for m in reversed(list(SESSION_RE.finditer(text))):
            out.append({"file": f, "id": m.group("id"), "body": m.group("body").strip()})
            if len(out) >= n:
                return out
    return out


def section(body: str, heading: str) -> str:
    m = re.search(rf"^###\s+{re.escape(heading)}[^\n]*\n(.*?)(?=^###\s|\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else ""


# --------------------------------------------------------------------------- #
# commands: list / route
# --------------------------------------------------------------------------- #
def cmd_list(a):
    engs = {e["id"]: e for e in load_engagements()}
    by = {}
    for c in load_cards():
        by.setdefault(c["engagement"] or "?", []).append(c)
    for eid in list(engs) + [k for k in by if k not in engs]:
        e = engs.get(eid, {})
        print(f"\n## {e.get('name', eid)}  [{eid}]")
        for c in by.get(eid, []):
            print(f"  {c.id:<22} {c.name:<22} repo={c['repo'] or UNVERIFIED}")
        if not by.get(eid):
            print("  (no projects registered)")


def cmd_route(a):
    hits, how = resolve(a.query, a.cwd)
    if a.json:
        print(json.dumps({"how": how, "candidates": [
            {"id": c.id, "name": c.name, "engagement": c["engagement"], "card": str(c.path),
             "repo": c["repo"], "vault_hub": c["vault_hub"], "vault_folder": c["vault_folder"]} for c in hits]}, indent=2))
        return
    if not hits:
        print(f"No project identified ({how}). Run `myos list` to see registered projects.")
        return
    if len(hits) > 1:
        print(f"Ambiguous ({how}). Candidates:")
    for c in hits:
        eng = c["engagement"]
        print(f"""Project      : {c.name}  [{c.id}]   (matched by {how})
Engagement   : {eng}  -> {ENGAGEMENTS_DIR / str(eng) / 'ENGAGEMENT.md'}
Project card : {c.path}
Repository   : {c['repo']}
Vault hub    : {c['vault_hub']}  ({obsidian_uri(c['vault_hub']) if c['vault_hub'] and c['vault_hub'] != UNVERIFIED else 'none'})
Vault folder : {c['vault_folder']}
Sessions     : {c.sessions_folder()}
Rules        : read the card, then follow {ROOT / 'workflows'} for the requested workflow.
""")


# --------------------------------------------------------------------------- #
# commands: verify (refresh the card's live evidence block)
# --------------------------------------------------------------------------- #
def live_block(f: dict, source: str = "`myos verify`") -> str:
    ts = f["checked_at"]
    if not f.get("exists"):
        return f"## Live repository evidence\n_Checked {ts}: path `{f['path']}` does **not exist**._"
    if not f.get("is_git"):
        return f"## Live repository evidence\n_Checked {ts}: `{f['path']}` exists but is not a git repository._"
    up = "no upstream configured"
    if f.get("upstream"):
        up = f"{f['upstream']} - ahead {f.get('ahead', '?')} / behind {f.get('behind', '?')} (as of last fetch; myOS never fetches)"
    return "\n".join([
        "## Live repository evidence",
        f"_Verified {ts} by {source} (read-only git, no fetch). This block is regenerated; do not edit by hand._",
        "",
        "| Field | Value |", "| --- | --- |",
        f"| Path | `{f['path']}` |",
        f"| Branch | `{f.get('branch')}` |",
        f"| HEAD | `{f.get('head')}` {str(f.get('head_date', ''))[:10]} - {f.get('head_subject', '').replace('|', '/')} |",
        f"| Uncommitted | {f.get('dirty_total')} entries ({f.get('modified')} tracked changes, {f.get('untracked')} untracked) |",
        f"| Upstream | {up} |",
        f"| Worktrees | {f.get('worktrees')} total; active: "
        + (", ".join(f"`{Path(p).name}` ({b})" for p, b in (f.get("worktree_list") or [])[:8]) or "-") + " |",
        f"| Remote | {f.get('remote') or 'none'} |",
    ])


def verify_card(c: Card) -> dict:
    repo = c.repo()
    f = git_facts(repo) if repo else {"path": UNVERIFIED, "exists": False, "checked_at": now_iso()}
    with card_lock(c.id):
        c = Card(c.path)
        text = replace_block(c.text, "live", live_block(f), anchor_before="<!-- myos:handoff:begin -->")
        text = set_frontmatter(text, {"last_verified": f["checked_at"]})
        journaled_write([(c.path, text)], f"verify {c.id}")
    c.save(text)
    return f


def cmd_verify(a):
    cards = load_cards() if a.all else [require_one(a.project, a.cwd)]
    for c in cards:
        f = verify_card(c)
        state = ("missing" if not f.get("exists") else "not-git" if not f.get("is_git")
                 else f"{f.get('branch')} @ {f.get('head')} dirty={f.get('dirty_total')}")
        print(f"{c.id:<22} {state}")


# --------------------------------------------------------------------------- #
# commands: status / resume
# --------------------------------------------------------------------------- #
def _print_live(f: dict):
    print(live_block(f, source="this command, just now (not written anywhere)").replace("## Live repository evidence", "LIVE (checked now)"))
    if f.get("dirty_sample"):
        print("Pending changes (sample): " + ", ".join(f["dirty_sample"][:8]))


def _cwd_facts(c: Card, cwd):
    """Prefer the worktree the agent is in, when it belongs to this project."""
    here = Path(cwd or os.getcwd())
    main = git_main_repo(here)
    if main and c.repo() and npath(main) == npath(c.repo()):
        return git_facts(here)
    return git_facts(c.repo()) if c.repo() else {"path": UNVERIFIED, "exists": False, "checked_at": now_iso()}


def cmd_status(a):
    c = require_one(a.project, a.cwd)
    print(f"# Project status - {c.name} [{c.id}]   engagement={c['engagement']}")
    print(f"Card: {c.path}   (card last verified: {c['last_verified'] or 'never'})\n")
    _print_live(_cwd_facts(c, a.cwd))
    print("\nHISTORICAL (from records - may be stale; dates shown)")
    claim = c["status_claim"] or UNVERIFIED
    print(f"- Status claim: {claim}  (source: {c['status_source'] or 'none'})")
    sess = latest_sessions(c, 1)
    if sess:
        s = sess[0]
        print(f"- Latest session: {vault_rel(s['file'])} id={s['id']}")
        for h in ("Summary", "Tests", "Bugs and blockers", "Next actions"):
            body = section(s["body"], h)
            if body:
                print(f"  {h}:\n" + "\n".join("    " + redact(l) for l in body.splitlines()[:12]))
    else:
        print("- Latest session: none recorded by myOS yet. Last known test evidence: UNVERIFIED.")
    hand = get_block(c.text, "handoff")
    if not sess and hand:
        print(hand)
    known = re.search(r"## Known next actions.*?(?=\n## |\Z)", c.body, re.S)
    if known:
        print("\n" + known.group(0).strip())
    print(f"\nEvidence references: card {c.path}; hub {c['vault_hub']}; sessions {c.sessions_folder()}")


def recent_vault_notes(c: Card, n=6) -> list[Path]:
    notes = []
    for root in c.vault_paths():
        if root.is_file():
            notes.append(root)
        elif root.exists():
            notes += [p for p in root.rglob("*.md") if not any(x in p.parts for x in (".obsidian", "attachments"))]
    notes = [p for p in notes if not c.excluded(p)]
    if not notes:
        return []

    def key(p):
        m = re.search(r"(20\d\d)-(\d\d)-(\d\d)", p.name)
        return (m.group(0) if m else "", p.stat().st_mtime)
    return sorted(notes, key=key, reverse=True)[:n]


def cmd_resume(a):
    c = require_one(a.project, a.cwd)
    print(f"# Resume - {c.name} [{c.id}]  (read-only; nothing is modified)\n")
    print(f"1. Project card: {c.path}")
    print(f"   Status claim: {c['status_claim'] or UNVERIFIED} (source: {c['status_source'] or 'none'})")
    print(f"   Vault hub: {c['vault_hub']}")
    print("\n2. Recent myOS sessions:")
    sess = latest_sessions(c, 3)
    if not sess:
        print("   none recorded yet")
    for s in sess:
        print(f"   - {vault_rel(s['file'])} [{s['id']}]")
        for h in ("Summary", "Next actions", "Bugs and blockers", "Decisions"):
            body = section(s["body"], h)
            if body:
                print(f"     {h}: " + " | ".join(redact(l.strip("- ").strip()) for l in body.splitlines()[:6] if l.strip()))
    print("\n3. Most recent project notes in the vault (open only what you need):")
    for p in recent_vault_notes(c):
        print(f"   - {vault_rel(p)}")
    print("\n4. Related graph context:")
    hits = graph_context(" ".join([c.name] + list(c["aliases"] or [])), limit=6, project=c.id, engagement=c["engagement"])
    print("\n".join("   " + l for l in hits) if hits else "   no built graph covers this project (fallback: file search below)")
    print("\n5. Current repository state:")
    _print_live(_cwd_facts(c, a.cwd))
    hand = get_block(c.text, "handoff")
    print("\n6. Next actionable step / blockers / open decisions:")
    print(hand.strip() if hand else "   no /save-progress handoff yet - see 'Known next actions' in the card.")
    known = re.search(r"## Known next actions.*?(?=\n## |\Z)", c.body, re.S)
    if known and not hand:
        print(known.group(0).strip())


# --------------------------------------------------------------------------- #
# commands: search (deterministic) + graph context
# --------------------------------------------------------------------------- #
TYPE_HINTS = {
    "decision": r"decision|adr|decided",
    "session": r"session|\d{4}-\d\d-\d\d",
    "bug": r"bug|fix|error|defect|incident|investigat",
    "runbook": r"runbook|install|deploy|setup|guide",
    "spec": r"spec|requirement|design|plan",
}


def session_engagement(cwd: str | None) -> str | None:
    """Engagement of the session's working directory; None inside myOS or an unregistered folder."""
    here = Path(cwd or os.getcwd())
    if is_under(here, ROOT):
        return None
    hits, _ = resolve(None, str(here))
    engs = {c["engagement"] for c in hits if str(c["test"]).lower() != "true"}
    return engs.pop() if len(engs) == 1 else None


def engagement_scope(eng: str) -> tuple[list[Path], list[Card], list[Card]]:
    """(vault roots allowed for `eng`, its cards, cards of other engagements)."""
    v = vault_root()
    cards = [c for c in load_cards() if str(c["test"]).lower() != "true"]
    mine = [c for c in cards if c["engagement"] == eng]
    others = [c for c in cards if c["engagement"] != eng]
    e = next((x for x in load_engagements() if x["id"] == eng), {})
    roots = [p for c in mine for p in c.vault_paths()] + [c.sessions_folder() for c in mine]
    roots += [v / s for s in (e.get("vault_shared") or [])]
    roots += [v / s for s in cfg()["search"].get("shared_all_engagements", [])]
    return roots, mine, others


def iter_search_files(project: Card | None, engagement: str | None = None):
    c = cfg()
    v = vault_root()
    ex = set(c["search"]["exclude_dir_names"])
    others: list[Card] = []
    if project:
        roots, cards = project.vault_paths() + [project.sessions_folder()], [project]
    elif engagement:
        roots, cards, others = engagement_scope(engagement)
    else:
        roots, cards = [v / inc for inc in c["search"]["include"]], load_cards()
    # a note owned by a project of ANOTHER engagement is never returned in an engagement-scoped search
    foreign = [r for o in others for r in o.vault_paths()]
    own = [r for cd in cards for r in cd.vault_paths()] + [cd.sessions_folder() for cd in cards]
    # shared (non-project) notes that NAME another engagement's projects are portfolio-level/mixed: owner view only
    foreign_terms = None
    if others:
        terms = {t.lower() for o in others for t in [o.name, o.id, *(o["aliases"] or [])] if len(str(t)) >= 4}
        terms |= {str(e.get("name", "")).lower() for e in load_engagements() if e["id"] != engagement}
        terms = {re.sub(r"\s*\(.*?\)", "", t).strip() for t in terms if t}
        foreign_terms = re.compile(r"(?i)\b(" + "|".join(re.escape(t) for t in sorted(terms) if len(t) >= 4) + r")\b")
    seen = set()
    for r in roots:
        if r.is_file():
            files = [r]
        elif r.exists():
            files = r.rglob("*.md")
        else:
            continue
        for p in files:
            rel_parts = Path(os.path.relpath(p, v)).parts
            if any(part in ex for part in rel_parts) or npath(p) in seen or (project and project.excluded(p)):
                continue
            if engagement and any(cd.excluded(p) for cd in cards):
                continue  # a card of this engagement excludes the note (misfiled / belongs elsewhere)
            if foreign and any(is_under(p, f) for f in foreign):
                continue
            if foreign_terms and not any(is_under(p, o) for o in own):
                try:
                    if foreign_terms.search(p.read_text(encoding="utf-8", errors="ignore")):
                        continue
                except OSError:
                    continue
            seen.add(npath(p))
            yield p
    for card in cards:
        yield card.path


def cmd_search(a):
    q = a.query
    tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9._-]+", q.lower()) if len(t) > 1]
    if not tokens:
        die("empty query")
    project = require_one(a.project) if a.project else None
    if project:
        engagement = project["engagement"]
        scope = f"project {project.id}"
    elif a.all_engagements:
        engagement, scope = None, "ALL engagements (explicit --all-engagements)"
    else:
        engagement = a.engagement or session_engagement(a.cwd)
        scope = f"engagement {engagement}" if engagement else "all engagements (owner view: myOS or unregistered folder)"
    trx = re.compile(TYPE_HINTS.get(a.type, re.escape(a.type)), re.I) if a.type else None
    need = max(1, -(-len(tokens) * 6 // 10))  # at least 60% of terms
    words = re.findall(r"[a-z0-9]+", q.lower())
    joins = [(a1, b1, j) for a1, b1 in zip(words, words[1:]) for j in (a1 + b1, f"{a1}-{b1}")]
    results = []
    for p in iter_search_files(project, engagement):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")[:400_000]
        except OSError:
            continue
        fm, body = parse_frontmatter(text)
        name = p.stem.lower()
        if trx and not (trx.search(name) or trx.search(str(fm.get("type", ""))) or trx.search(" ".join(map(str, fm.get("tags") or [])))):
            continue
        low = text.lower()
        heads = " ".join(re.findall(r"^#+ .*$", body, re.M)).lower()
        fmtxt = json.dumps(fm).lower()
        matched, score = 0, 0.0
        # joined forms of adjacent words ("z reading" -> zreading / z-reading) as bonus terms;
        # a joined hit also counts its words as matched
        joined_hit, name_bonus = set(), 0
        for a1, b1, j in joins:
            in_name = j in p.name.lower()
            where = (6 if j in str(p).lower() else 0) + (3 if j in heads else 0) + min(low.count(j), 5)
            if where:
                score += where + 4 + (6 if in_name else 0)
                joined_hit |= {a1, b1}
                name_bonus = max(name_bonus, 1 if in_name else 0)
        for t in tokens:
            hit = t in joined_hit
            if t in str(p).lower():
                score += 6; hit = True
            if t in heads:
                score += 3; hit = True
            if t in fmtxt:
                score += 2; hit = True
            n = low.count(t)
            if n:
                score += min(n, 5); hit = True
            matched += hit
        matched = min(len(tokens), matched + name_bonus)  # a joined term in the file NAME is strong evidence
        if matched < need:
            continue
        lines = text.splitlines()
        best = max(range(len(lines)), key=lambda i: sum(t in lines[i].lower() for t in tokens), default=0)
        snippet = redact(lines[best].strip())[:180] if lines else ""
        results.append((matched, score, p, best + 1, snippet, fm))
    results.sort(key=lambda r: (r[0], r[1]), reverse=True)
    print(f"# Context search: {q!r}" + (f"  project={project.id}" if project else "") + (f"  type={a.type}" if a.type else ""))
    print(f"Scope: {scope}. Deterministic file search over approved vault folders + project cards. Showing top {a.limit}.\n")
    if not results:
        print("No file matches.")
    for i, (m, s, p, ln, snip, fm) in enumerate(results[: a.limit], 1):
        where = vault_rel(p) if is_under(p, vault_root()) else str(p)
        date = fm.get("updated") or fm.get("created") or fm.get("Date") or ""
        print(f"{i}. {where}:{ln}  [terms {m}/{len(tokens)}, score {s:.0f}{', ' + str(date) if date else ''}]")
        print(f"   {snip}")
    g = graph_context(q, limit=a.limit, project=project.id if project else None, engagement=engagement)
    print("\n## Graph relationships (Graphify)")
    print("\n".join(g) if g else "No built graph matched (or none built). File results above are the fallback.")
    print("\nNote: INFERRED/AMBIGUOUS edges are hypotheses from the model, not established facts. Confirm against the source note.")


def built_graphs(project: str | None = None, engagement: str | None = None) -> list[tuple[str, Path]]:
    """Built graphs for real data (never the synthetic fixture), scoped like the file search:
    project given -> that project's corpus + its engagement's general corpus;
    engagement given -> corpora of that engagement only; neither -> all (owner view)."""
    out = []
    corpora = cfg()["graph"]["corpora"]
    for gj in sorted(GRAPH_DIR.glob("*/graphify-out/graph.json")):
        name = gj.parent.parent.name
        cc = corpora.get(name)
        if not cc or (npath(corpus_source(cc)) != npath(vault_root()) and cc.get("kind") != "repo-docs"):
            continue
        if project and not (cc.get("project") == project or (cc.get("project") is None and cc.get("engagement") == engagement)):
            continue
        if engagement and not project and cc.get("engagement") not in (engagement,):
            continue
        out.append((name, gj))
    return out


def graph_context(query: str, limit=8, project: str | None = None, engagement: str | None = None) -> list[str]:
    tokens = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2]
    if not tokens:
        return []
    lines = []
    for name, gj in built_graphs(project, engagement):
        try:
            g = json.loads(gj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        nodes = {n["id"]: n for n in g.get("nodes", [])}
        scored = []
        for n in nodes.values():
            hay = f"{n.get('label', '')} {n.get('norm_label', '')}".lower()
            s = sum(t in hay for t in tokens)
            if s:
                scored.append((s, n))
        scored.sort(key=lambda x: -x[0])
        top = {n["id"] for _, n in scored[:4]}
        if not top:
            continue
        edges = [e for e in g.get("links", g.get("edges", [])) if e.get("source") in top or e.get("target") in top]
        edges.sort(key=lambda e: (e.get("confidence") != "EXTRACTED", -(e.get("confidence_score") or 0)))
        lines.append(f"[{name}] matched nodes: " + "; ".join(f"{nodes[i].get('label')} ({nodes[i].get('source_file')})" for i in top))
        for e in edges[:limit]:
            s, t = nodes.get(e["source"], {}), nodes.get(e["target"], {})
            conf = e.get("confidence", "?")
            score = e.get("confidence_score")
            # Semantic EXTRACTED edges are still model output; show the score so <1.0 is visible.
            tag = f"{conf} {score}" + ("" if conf == "EXTRACTED" else " - hypothesis")
            lines.append(f"  - {s.get('label')} --{e.get('relation')}--> {t.get('label')}  [{tag}]  src: {e.get('source_file')}")
    return lines


# --------------------------------------------------------------------------- #
# commands: save (save-progress)
# --------------------------------------------------------------------------- #
VALID_RESULTS = {"passed", "failed", "partial", "not-run", "skipped", "unknown"}


def _bullets(items, empty="- none recorded"):
    items = [i for i in (items or []) if str(i).strip()]
    return "\n".join(f"- {redact(str(i))}" for i in items) if items else empty


def normalize_tests(tests) -> list[dict]:
    out = []
    for t in tests or []:
        if isinstance(t, str):
            t = {"command": t, "result": "unknown", "evidence": ""}
        res = str(t.get("result", "unknown")).lower().strip()
        res = res if res in VALID_RESULTS else "unknown"
        ev = str(t.get("evidence") or "").strip()
        if res == "passed" and not ev:
            res = "claimed-passed-NO-EVIDENCE"
        out.append({"command": str(t.get("command", "")).strip(), "result": res, "evidence": ev})
    return out


def render_session(c: Card, sid: str, data: dict, facts: dict, dstat: str) -> str:
    tests = normalize_tests(data.get("tests"))
    trows = "\n".join(f"| `{t['command'] or '?'}` | **{t['result']}** | {redact(t['evidence'])[:300].replace('|', '/').replace(chr(10), ' ')} |" for t in tests)
    tests_md = ("| Command | Result | Evidence |\n| --- | --- | --- |\n" + trows) if tests else "- No tests were executed in this session (none reported)."
    decisions = []
    for d in data.get("decisions") or []:
        if isinstance(d, dict):
            decisions.append(f"{d.get('decision', '')} - rationale: {d.get('rationale', 'not given')}")
        else:
            decisions.append(str(d))
    ev = facts
    evidence = ("- Repository path not available (not a registered repo)." if not ev.get("is_git") else "\n".join([
        f"- Worktree: `{ev.get('toplevel')}`",
        f"- Branch: `{ev.get('branch')}`  HEAD: `{ev.get('head')}` ({str(ev.get('head_date', ''))[:10]}) {ev.get('head_subject', '')}",
        f"- Uncommitted entries: {ev.get('dirty_total')} ({ev.get('modified')} tracked, {ev.get('untracked')} untracked)",
        f"- Upstream: {ev.get('upstream') or 'none'}" + (f" ahead {ev.get('ahead')} / behind {ev.get('behind')}" if ev.get('upstream') else ""),
        "- Diff vs HEAD:\n```\n" + (dstat[-1500:] or "(no tracked changes)") + "\n```",
    ]))
    gaps = list(data.get("gaps") or [])
    if not tests:
        gaps.append("No test evidence supplied for this session.")
    return f"""<!-- myos:session:begin id={sid} -->
## Session {sid} - {now().strftime('%H:%M')} ({data.get('agent', 'unknown-agent')})
_Recorded {now_iso()} by `myos save`. Repository evidence below was captured by myOS, not reported by the agent._

### Summary
{redact(str(data.get('summary', '')).strip()) or '- none'}

### Repository evidence (captured at save time)
{evidence}

### Changes made
{_bullets(data.get('changes'))}

### Tests
{tests_md}

### Decisions (agent-recorded - review before treating as accepted)
{_bullets(decisions)}

### Bugs and blockers
{_bullets(list(data.get('bugs') or []) + list(data.get('blockers') or []))}

### Next actions
{_bullets(data.get('next_actions'))}

### Pending approvals
{_bullets(data.get('pending_approvals'))}

### Gaps in this record
{_bullets(gaps, empty='- none declared')}
<!-- myos:session:end id={sid} -->"""


def ensure_hub(c: Card) -> list[tuple[Path, str]]:
    """Create a minimal hub note for a project that has no vault folder yet."""
    if c.vault_folder() and c.vault_folder().exists():
        return []
    folder = c.sessions_folder().parent
    hub = folder / "00-Overview.md"
    if hub.exists():
        return []
    content = dump_frontmatter({"type": "project-hub", "project": c.id, "engagement": c["engagement"],
                                "created": today(), "updated": today(), "status": c["status_claim"] or UNVERIFIED,
                                "tags": ["project", "myos"], "summary": f"Hub note for {c.name} (created by myOS)."})
    content += f"""# {c.name}

Hub created by myOS on {today()} because this project had no vault folder.
Operational summary and next action live in the myOS project card: `{c.path}`.

## Sessions
Dated session records are in [[{vault_rel(c.sessions_folder())}]].
"""
    return [(hub, content)]


def cmd_save(a):
    recover_pending()
    raw = Path(a.input).read_text(encoding="utf-8-sig") if a.input and a.input != "-" else sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # agents often write Windows paths with single backslashes (C:\projects\x) inside JSON strings
        fixed = re.sub(r'\\(?![\\/"bfnrtu])', r"\\\\", raw)
        try:
            data = json.loads(fixed)
        except json.JSONDecodeError as e:
            die(f"input is not valid JSON ({e}). Tip: write Windows paths with forward slashes.")
    c = require_one(data.get("project") or a.project, a.cwd)
    with card_lock(c.id):
        return _save(a, data, Card(c.path))  # re-read the card under the lock


def _save(a, data, c: Card):
    if not str(data.get("summary", "")).strip():
        die("`summary` is required")
    agent = re.sub(r"[^a-z0-9-]", "-", str(data.get("agent") or "agent").lower())
    sid = re.sub(r"[^A-Za-z0-9_.-]", "-", str(data.get("session_id") or f"{today()}-{agent}"))
    data["agent"] = agent

    here = Path(a.cwd or os.getcwd())
    main = git_main_repo(here)
    wt = here if (main and c.repo() and npath(main) == npath(c.repo())) else c.repo()
    facts = git_facts(wt) if wt else {"exists": False, "checked_at": now_iso()}
    dstat = diff_stat(wt) if facts.get("is_git") else ""

    sess_dir = c.sessions_folder()
    sfile = sess_dir / f"{today()}-{c.id}.md"
    # Fingerprint of everything that matters (input + git evidence, not timestamps): an unchanged
    # re-save is a true no-op instead of a rewrite with new timestamps.
    fp = sha256_text(json.dumps([data, {k: v for k, v in facts.items() if k != "checked_at"}, dstat], sort_keys=True))[:16]
    if sfile.exists() and f"<!-- myos:fp={fp} -->" in sfile.read_text(encoding="utf-8"):
        print(f"Session `{sid}` for {c.name} is already recorded with identical content - nothing to do.")
        print(f"  session note : {sfile}")
        return
    block = render_session(c, sid, data, facts, dstat).replace("\n", f"\n<!-- myos:fp={fp} -->\n", 1)
    if sfile.exists():
        text = sfile.read_text(encoding="utf-8")
        pat = re.compile(rf"<!-- myos:session:begin id={re.escape(sid)} -->.*?<!-- myos:session:end id={re.escape(sid)} -->", re.S)
        text = pat.sub(lambda _: block, text, count=1) if pat.search(text) else text.rstrip() + "\n\n" + block + "\n"
        text = set_frontmatter(text, {"updated": now_iso(), "summary": str(data["summary"])[:200]})
    else:
        hub = c["vault_hub"] if c["vault_hub"] and c["vault_hub"] != UNVERIFIED else vault_rel(sess_dir.parent / "00-Overview.md")
        text = dump_frontmatter({"type": "session", "project": c.id, "engagement": c["engagement"], "created": today(),
                                 "updated": now_iso(), "status": "recorded", "tags": ["session", "myos", c.id],
                                 "summary": str(data["summary"])[:200]})
        text += f"# {c.name} - sessions {today()}\n\nProject hub: [[{hub.removesuffix('.md')}]] · Project card: `{c.path}`\n\n{block}\n"

    # card: sessions list + latest handoff
    link = f"{vault_rel(sfile).removesuffix('.md')}"
    old = get_block(c.text, "sessions") or ""
    entries = [l for l in old.splitlines() if l.startswith("- ") and f"`{sid}`" not in l]
    entry = f"- {today()} `{sid}` - {redact(str(data['summary']))[:140]}  ([[{link}]] / {sfile})"
    entries = [entry] + entries
    sessions_md = "## Session records (newest first, max 10)\n" + "\n".join(entries[:10])
    tests = normalize_tests(data.get("tests"))
    test_md = "\n".join(f"- `{t['command']}` -> **{t['result']}**" for t in tests) or "- none executed in the latest session"
    handoff = f"""## Latest handoff
_From session `{sid}` ({agent}) recorded {now_iso()}. History: {sfile}_

**Summary:** {redact(str(data['summary']))}

**Next actions**
{_bullets(data.get('next_actions'))}

**Blockers**
{_bullets(list(data.get('blockers') or []) + list(data.get('bugs') or []), empty='- none reported')}

**Pending approvals**
{_bullets(data.get('pending_approvals'), empty='- none reported')}

**Last test evidence**
{test_md}"""
    ctext = replace_block(c.text, "handoff", handoff)
    ctext = replace_block(ctext, "sessions", sessions_md)
    ctext = replace_block(ctext, "live", live_block(facts, source="`myos save`") if facts.get("exists") else "## Live repository evidence\n_Not available._",
                          anchor_before="<!-- myos:handoff:begin -->")
    ctext = set_frontmatter(ctext, {"updated": now_iso(), "last_verified": facts.get("checked_at")})

    writes = ensure_hub(c) + [(sfile, text), (c.path, ctext)]
    if a.dry_run:
        print(f"[dry-run] would write {len(writes)} files:")
        for p, t in writes:
            print(f"  {p} ({len(t)} chars)")
        print("\n" + block)
        return
    changed = journaled_write(writes, f"save {c.id} {sid}")
    print(f"Saved session `{sid}` for {c.name}.")
    print(f"  session note : {sfile}")
    print(f"  project card : {c.path}")
    print("  files changed: " + (", ".join(changed) if changed else "none (identical content - nothing to do)"))
    cov = corpora_covering(sfile)
    if cov:
        print(f"  graph        : approved corpus `{cov[0]}` covers this note, but its content changed, so the owner must "
              f"re-approve before `myos graph update {cov[0]}` (every content change needs fresh approval)")
    else:
        print("  graph        : skipped - no approved Graphify corpus covers this project's notes")


# --------------------------------------------------------------------------- #
# commands: brief
# --------------------------------------------------------------------------- #
DUE_RE = re.compile(r"due[:\s]+(\d{4}-\d\d-\d\d)", re.I)


def age_note(text: str) -> str:
    """', 36 days old' for the newest YYYY-MM-DD found in a source string."""
    dates = re.findall(r"(20\d\d-\d\d-\d\d)", text)
    if not dates:
        return ""
    try:
        days = (now().date() - dt.date.fromisoformat(max(dates))).days
    except ValueError:
        return ""
    return f"; {days} days old" if days > 0 else "; today"


def session_delta(c: Card) -> str | None:
    """Commits landed in the recorded worktree since the latest myOS session (read-only git)."""
    sess = latest_sessions(c, 1)
    if not sess:
        return None
    body = sess[0]["body"]
    wt = re.search(r"Worktree: `([^`]+)`", body)
    head = re.search(r"HEAD: `([0-9a-f]{6,40})`", body)
    branch = re.search(r"Branch: `([^`]+)`", body)
    if not (wt and head and Path(wt.group(1)).exists()):
        return None
    n = git(wt.group(1), "rev-list", "--count", f"{head.group(1)}..HEAD")
    now_branch = git(wt.group(1), "rev-parse", "--abbrev-ref", "HEAD")
    if n is None:
        return f"recorded HEAD {head.group(1)} is no longer reachable in `{Path(wt.group(1)).name}` (rewritten or moved)"
    moved = f", now on `{now_branch}`" if branch and now_branch and now_branch != branch.group(1) else ""
    return (f"{n} new commit(s) in worktree `{Path(wt.group(1)).name}` since the record (HEAD {head.group(1)}){moved}"
            + (" - the handoff may be stale" if int(n) else " - record is current"))


def _hand_list(hand: str, title: str) -> list[str]:
    m = re.search(rf"\*\*{title}\*\*\n(.*?)(\n\n|\Z)", hand, re.S)
    items = [l[2:].strip() for l in m.group(1).splitlines() if l.startswith("- ")] if m else []
    return [i for i in items if i and not i.startswith("none")]


def _cut(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip().replace("|", "/")
    return s if len(s) <= n else s[: n - 1] + "…"


def brief_compact(a):
    """One table per engagement; every cell tagged [V]erified, [H]istorical, [I]nferred or [M]issing."""
    cards = load_cards(include_test=a.include_test)
    print(f"# Executive briefing (compact) - {now_iso()[:16]}")
    print("Tags: [V] verified now (read-only git) · [H] historical record (date/age shown) · [I] inferred · [M] missing. "
          "Nothing invented. Full detail: `myos brief --detail`.\n")
    attention = []
    seen_repos = set()
    for e in load_engagements():
        ec = [c for c in cards if c["engagement"] == e["id"]]
        print(f"## {e.get('name', e['id'])}")
        for d in e.get("open_decisions") or []:
            print(f"- [H] Decision pending: {_cut(d, 140)}")
        if not ec:
            print("- [M] No projects, repositories or notes registered.\n")
            continue
        print("| Project | Repo now | Last record | Next action | Decisions / blockers |")
        print("| --- | --- | --- | --- | --- |")
        for c in ec:
            f = git_facts(c.repo()) if (c.repo() and not a.cached) else {}
            if not c.repo():
                repo = "[M] repo"
            elif not f:
                repo = "(not checked)"
            elif not f.get("exists"):
                repo = "[M] path missing"
            else:
                repo = (f"[V] {_cut(f.get('branch'), 26)}@{f.get('head')}, {f.get('dirty_total')} dirty"
                        + ("" if f.get("upstream") else ", no upstream") + (f", {f.get('ahead')} unpushed" if f.get("ahead") else ""))
            sess = get_block(c.text, "sessions") or ""
            last = re.search(r"^- (\d{4}-\d\d-\d\d) `[^`]+` - (.*?)\s+\(\[\[", sess, re.M)
            if last:
                rec = f"[H] session {last.group(1)}{age_note(last.group(1))}"
                delta = session_delta(c) if not a.cached else None
                if delta and "new commit" in delta and not delta.startswith("0 "):
                    rec += f"; [V] {delta.split(' since')[0]} since"
            else:
                rec = f"[H] claim: {_cut(c['status_claim'] or 'UNVERIFIED', 40)}{age_note(str(c['status_source'] or ''))}" \
                    if c["status_claim"] and not str(c["status_claim"]).startswith(UNVERIFIED) else "[M] no record"
            hand = get_block(c.text, "handoff") or ""
            nxt = _hand_list(hand, "Next actions")
            if nxt:
                nxt_s = f"[H] {_cut(nxt[0], 70)}"
            else:
                known = re.search(r"## Known next actions \(historical\)\n_Source: (.*?)_\n- (.*?)\n", c.body, re.S)
                nxt_s = f"[H] {_cut(known.group(2), 60)}{age_note(known.group(1))}" if known else "[M]"
            dec = list(c["open_decisions"] or []) + _hand_list(hand, "Blockers") + _hand_list(hand, "Pending approvals")
            dec_s = (f"[H] {_cut(dec[0], 60)}" + (f" (+{len(dec) - 1})" if len(dec) > 1 else "")) if dec else "-"
            if c["repo_confidence"] in ("inferred", "ambiguous"):
                dec_s += " · [I] repo mapping"
            print(f"| {c.name} | {repo} | {rec} | {nxt_s} | {dec_s} |")
            key = npath(c.repo()) if c.repo() else c.id
            if f and key not in seen_repos:
                seen_repos.add(key)
                if f.get("is_git") and not f.get("upstream") and f.get("dirty_total", 0) >= 15:
                    attention.append(f"{c.repo().name}: {f['dirty_total']} uncommitted on `{f.get('branch')}` with no upstream")
        print()
    pending = [n for n, cc in cfg()["graph"]["corpora"].items() if cc.get("requires_approval") and not approval_for(n)]
    if pending:
        print(f"**Owner approvals pending:** Graphify corpora {', '.join(pending)} (`docs/corpus-review-guide.md`).")
    if attention:
        print("**RECOMMENDATION - loss risk (work exists only on this PC):** " + "; ".join(attention[:6]))


def cmd_brief(a):
    if not a.detail:
        return brief_compact(a)
    print(f"# Executive briefing - generated {now_iso()}")
    print("Labels: **VERIFIED** = read-only git checked now. **HISTORICAL** = from records, with source/date.")
    print("**INFERRED** = a mapping or relationship not confirmed by the owner. **MISSING** = not recorded anywhere (UNVERIFIED).")
    print("Nothing is invented. Due dates appear only when a record states one.\n")
    cards = load_cards(include_test=a.include_test)
    engs = load_engagements()
    pending_graph = [n for n, cc in cfg()["graph"]["corpora"].items() if cc.get("requires_approval") and not approval_for(n)]

    print("| Engagement | Projects | With a recorded session | Open decisions |")
    print("| --- | --- | --- | --- |")
    for e in engs:
        ec = [c for c in cards if c["engagement"] == e["id"]]
        withs = sum(1 for c in ec if re.search(r"^- \d{4}-", get_block(c.text, "sessions") or "", re.M))
        nd = len(e.get("open_decisions") or []) + sum(len(c["open_decisions"] or []) for c in ec)
        print(f"| {e.get('name', e['id'])} | {len(ec)} | {withs} | {nd} |")
    print()

    recs, no_session, seen_repos = [], [], set()
    for e in engs:
        ecards = [c for c in cards if c["engagement"] == e["id"]]
        print(f"## {e.get('name', e['id'])}")
        if e.get("summary"):
            print(f"_{e['summary']}_")
        for d in e.get("open_decisions") or []:
            print(f"- **Open decision (engagement):** {d}")
        if not ecards:
            print("- **MISSING:** no projects, repositories or notes are registered for this engagement.\n")
            recs.append(f"[{e.get('name')}] register at least one project or confirm the engagement is inactive.")
            continue
        for c in ecards:
            f = git_facts(c.repo()) if (c.repo() and not a.cached) else {}
            hand = get_block(c.text, "handoff") or ""
            sess = get_block(c.text, "sessions") or ""
            last = re.search(r"^- (\d{4}-\d\d-\d\d) `([^`]+)` - (.*?)\s+\(\[\[", sess, re.M)
            live = ("repo " + UNVERIFIED) if not c.repo() else (
                "repo path missing" if f and not f.get("exists") else
                f"`{f.get('branch')}` @ {f.get('head')} (last commit {str(f.get('head_date', ''))[:10]}), {f.get('dirty_total')} uncommitted"
                + (f", {f.get('ahead')} unpushed" if f.get("ahead") else "")
                + ("" if f.get("upstream") else ", no upstream") if f else "not checked (--cached)")
            print(f"### {c.name} [`{c.id}`]")
            print(f"- **VERIFIED:** {live}")
            wts = [(Path(p).name, b) for p, b in (f.get("worktree_list") or []) if npath(p) != npath(f.get("toplevel", ""))]
            if wts:
                print(f"- **VERIFIED:** {len(wts)} other active worktree(s): " + ", ".join(f"`{n}` ({b})" for n, b in wts[:6]))
            delta = session_delta(c) if not a.cached else None
            if delta:
                print(f"- **VERIFIED since last session:** {delta}")
            print(f"- **HISTORICAL:** status claim \"{c['status_claim'] or UNVERIFIED}\" (source: {c['status_source'] or 'none'}"
                  f"{age_note(str(c['status_source'] or ''))})")
            if last:
                print(f"- **HISTORICAL:** last myOS session {last.group(1)}{age_note(last.group(1))} `{last.group(2)}` - {last.group(3)[:140]}")
            inferred = []
            if c["repo_confidence"] in ("inferred", "ambiguous"):
                inferred.append(f"repository mapping is {c['repo_confidence']}")
            if c["repo_subpaths"] and c["repo_confidence"] != "verified-path" and c["subpath_confidence"] != "verified":
                inferred.append(f"component folder {', '.join(c['repo_subpaths'])} inferred from repo docs")
            if inferred:
                print("- **INFERRED:** " + "; ".join(inferred))
            rel = [f"depends on `{d}`" for d in (c["depends_on"] or [])]
            rel += [f"`{x.id}` depends on it" for x in cards if c.id in (x["depends_on"] or [])]
            if rel:
                print("- **Relationships (owner-stated):** " + "; ".join(rel))
            missing = [k for k in ("status_claim", "vault_hub", "github") if not c[k] or str(c[k]).startswith(UNVERIFIED)]
            if not last:
                missing.append("no myOS session recorded")
                no_session.append(c.name)
            if missing:
                print("- **MISSING:** " + ", ".join(missing))
            nxt = _hand_list(hand, "Next actions")
            if nxt:
                print("- **Next actions** (from the latest session): " + " | ".join(nxt[:3]))
            else:
                known = re.search(r"## Known next actions \(historical\)\n_Source: (.*?)_\n(.*?)(\n\n|\n##|\Z)", c.body, re.S)
                if known:
                    items = [l[2:] for l in known.group(2).splitlines() if l.startswith("- ")]
                    print(f"- **Next actions (HISTORICAL, {known.group(1)}):** " + " | ".join(items[:3]))
                else:
                    print("- **Next actions:** MISSING")
            blk = _hand_list(hand, "Blockers")
            if blk:
                print("- **Blockers:** " + " | ".join(blk[:3]))
            decisions = list(c["open_decisions"] or []) + _hand_list(hand, "Pending approvals")
            if decisions:
                print("- **Open decisions / approvals:** " + " | ".join(decisions[:4]))
            for d in DUE_RE.findall(c.text):
                print(f"- **Due date in record:** {d}" + ("  **OVERDUE**" if d < today() else ""))
            repo_key = npath(c.repo()) if c.repo() else c.id
            if repo_key in seen_repos:
                continue  # several cards share one repo (components): recommend once
            seen_repos.add(repo_key)
            shared = [x.name for x in cards if x.repo() and npath(x.repo()) == repo_key]
            label = c.name if len(shared) < 2 else f"repo {c.repo().name}: " + ", ".join(shared)
            if f.get("dirty_total", 0) >= 15:
                recs.append(f"[{label}] {f['dirty_total']} uncommitted entries on `{f.get('branch')}` - commit or stash deliberately to reduce loss risk.")
            if f.get("ahead"):
                recs.append(f"[{label}] {f['ahead']} local commits not on upstream - consider pushing (myOS never pushes).")
            if f.get("is_git") and not f.get("upstream"):
                recs.append(f"[{label}] branch `{f.get('branch')}` has no upstream - work exists only on this PC.")
        print()
    print("## Pending approvals (system)")
    print("\n".join(f"- Graphify corpus `{n}` awaits your approval: preview `data/graph/{n}/TRANSMISSION-PREVIEW.md`, "
                    f"then `myos graph approve {n}` in your own terminal." for n in pending_graph) or "- none")
    if no_session:
        recs.append(f"No myOS session recorded yet for: {', '.join(no_session)} - run /save-progress at the end of the next session on each.")
    print("\n## Suggested priorities - RECOMMENDATIONS, not facts")
    for r in recs[:15]:
        print(f"- {r}")
    if not recs:
        print("- none")


# --------------------------------------------------------------------------- #
# graph: staging, approval, build
# --------------------------------------------------------------------------- #
def corpus_cfg(name: str) -> dict:
    cc = cfg()["graph"]["corpora"].get(name)
    if not cc:
        die(f"unknown corpus '{name}'. Defined: {', '.join(cfg()['graph']['corpora'])}")
    return cc


def corpus_source(cc: dict) -> Path:
    s = cc["source"]
    if s == "@vault":
        return vault_root()
    return Path(expand_path(s))


# Patterns that do NOT exclude a file but are listed in the preview so the owner can judge before approving.
REVIEW_FLAGS = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "ip-address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "phone": re.compile(r"(?<!\d)\+?\d{1,3}[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}(?!\d)"),
    "credential-word": re.compile(r"(?i)\b(password|passwd|credential|secret|api[_ -]?key|token|login)\b"),
}
# Production hosts come from config/guard.json (single home).
_hosts = list((load_json(ROOT / "config" / "guard.json", {}) or {}).get("production_hosts", {}))
if _hosts:
    REVIEW_FLAGS["production-host"] = re.compile(r"(?i)\b(" + "|".join(re.escape(h) for h in _hosts) + r")\b")


def include_bases(src: Path, globs: list[str]) -> list[Path]:
    """Only walk the static prefix of each include glob (never the whole repo/vault)."""
    out = []
    for g in globs:
        parts = []
        for part in g.split("/"):
            if any(ch in part for ch in "*?["):
                break
            parts.append(part)
        out.append(src.joinpath(*parts) if parts else src)
    return out


def policy_hash() -> str:
    return sha256_text(POLICY_PATH.read_text(encoding="utf-8"))


def classify(rel: str, path: Path, pol: dict, rules) -> str | None:
    parts = Path(rel).parts
    for d in parts[:-1]:
        if d.lower() in {x.lower() for x in pol["excluded_dir_names"]}:
            return f"excluded-dir:{d}"
    if path.suffix.lower() not in pol["allowed_extensions"]:
        return f"extension:{path.suffix or '(none)'}"
    for pat in pol["excluded_name_patterns"]:
        if re.search(pat, rel, re.I):
            return "sensitive-name"
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "unreadable"
    for name, rx in rules.items():
        if rx.search(text):
            return f"content:{name}"
    return None


def glob_match(rel: str, pattern: str) -> bool:
    """gitignore-style glob: `**/` = zero or more folders, `*` and `?` never cross `/`."""
    rx, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            rx += "(?:.*/)?"; i += 3
        elif pattern.startswith("**", i):
            rx += ".*"; i += 2
        elif pattern[i] == "*":
            rx += "[^/]*"; i += 1
        elif pattern[i] == "?":
            rx += "[^/]"; i += 1
        else:
            rx += re.escape(pattern[i]); i += 1
    return re.fullmatch(rx, rel, re.I) is not None


def stage(name: str, write: bool = True) -> dict:
    """Select, scan and (if write) copy a corpus into its staging folder + write manifest and preview.
    write=False only computes the manifest (used to check approvals without touching anything)."""
    cc = corpus_cfg(name)
    src = corpus_source(cc)
    pol = policy()
    rules = _content_rules()
    cdir = GRAPH_DIR / name / "corpus"
    if write:
        cdir.mkdir(parents=True, exist_ok=True)
    included, excluded, flagged = [], [], []
    candidates = set()
    for base in include_bases(src, cc["include"]):
        if base.is_file():
            candidates.add(base)
        elif base.is_dir():
            candidates.update(p for p in base.rglob("*") if p.is_file())
    for p in sorted(candidates):
        rel = Path(os.path.relpath(p, src)).as_posix()
        if not any(glob_match(rel, g) for g in cc["include"]):
            continue
        if any(glob_match(rel, g) for g in cc.get("exclude", [])):
            excluded.append({"path": rel, "reason": "corpus-exclude (explicit owner/myOS rule)"})
            continue
        reason = classify(rel, p, pol, rules)
        if reason:
            excluded.append({"path": rel, "reason": reason})
            continue
        included.append({"path": rel, "bytes": p.stat().st_size, "sha256": sha256_file(p)})
        text = p.read_text(encoding="utf-8", errors="ignore")
        hits = {k: len(rx.findall(text)) for k, rx in REVIEW_FLAGS.items()}
        hits = {k: v for k, v in hits.items() if v}
        if hits:
            flagged.append({"path": rel, "flags": hits})
        dst = cdir / rel
        if write and (not dst.exists() or sha256_file(dst) != included[-1]["sha256"]):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    keep = {npath(cdir / i["path"]) for i in included}
    for p in (list(cdir.rglob("*")) if write else []):  # staging copy only: drop files no longer approved
        if p.is_file() and npath(p) not in keep:
            p.unlink()
    g = cfg()["graph"]
    manifest = {"corpus": name, "generated": now_iso(), "source": str(src), "include": cc["include"],
                "provider": g["provider_description"], "backend": g["backend"], "model": g["model"],
                "policy_sha256": policy_hash(), "files": included, "excluded": excluded, "review_flags": flagged,
                "corpus_exclude": cc.get("exclude", []), "notes": cc.get("notes", ""),
                "total_bytes": sum(i["bytes"] for i in included)}
    manifest["content_sha256"] = sha256_text(json.dumps([(i["path"], i["sha256"]) for i in included]))
    if not write:
        return manifest
    atomic_write(GRAPH_DIR / name / "manifest.json", json.dumps(manifest, indent=1))
    preview = [f"# Transmission preview - corpus `{name}`", "",
               f"Generated {manifest['generated']}.", "",
               f"**Destination:** {g['provider_description']} (model alias `{g['model']}`).",
               "**What is sent:** the full text of each included file below, in chunks, for entity/relationship extraction,",
               "plus node labels for community naming. Nothing else leaves the machine.", "",
               f"**Included ({len(included)} files, {manifest['total_bytes']:,} bytes):**"]
    preview += [f"- `{i['path']}` ({i['bytes']:,} B)" for i in included] or ["- none"]
    preview += ["", f"**Excluded by policy ({len(excluded)}):**"] + [f"- `{e['path']}` - {e['reason']}" for e in excluded] + [""]
    preview += [f"**Review before approving ({len(flagged)} included files contain these patterns; values are NOT shown):**"]
    preview += [f"- `{f['path']}` - " + ", ".join(f"{k} x{v}" for k, v in f["flags"].items()) for f in flagged] or ["- none"]
    preview += ["", "If any flagged file should not leave this PC, add it to this corpus's `exclude` list in config/myos.json", ""]
    if cc.get("notes"):
        preview[3:3] = [f"**Corpus notes:** {cc['notes']}", ""]
    preview += ["To approve, run in your own PowerShell window (not through an agent):",
                f"    myos graph approve {name}"]
    atomic_write(GRAPH_DIR / name / "TRANSMISSION-PREVIEW.md", "\n".join(preview) + "\n")
    return manifest


def approvals() -> dict:
    return load_json(APPROVALS_PATH, {}) or {}


def approval_for(name: str) -> dict | None:
    ap = approvals().get(name)
    if not ap:
        return None
    cc = cfg()["graph"]["corpora"].get(name, {})
    if ap.get("include") != cc.get("include"):
        return None  # scope changed -> re-approve
    if not set(ap.get("exclude", [])) <= set(cc.get("exclude", [])):
        return None  # an exclusion was removed -> re-approve
    if ap.get("policy_sha256") != policy_hash() and not policy_is_stricter(policy_at_approval(ap), policy()):
        return None  # policy loosened (or unknown) -> re-approve
    return ap


def content_changes(name: str, ap: dict) -> list[str]:
    """Files added/changed/removed since the owner approved (empty list = content is exactly what was approved)."""
    m = stage(name, write=False)
    if m["content_sha256"] == ap.get("content_sha256_at_approval"):
        return []
    then = {f["path"]: f["sha256"] for f in ap.get("files", [])}
    now_ = {f["path"]: f["sha256"] for f in m["files"]}
    if not then:  # approvals recorded before per-file hashes were kept
        return [f"content hash differs from approval ({len(now_)} files now, {ap.get('files_at_approval')} at approval)"]
    out = [f"added: {p}" for p in sorted(set(now_) - set(then))]
    out += [f"changed: {p}" for p in sorted(p for p in set(now_) & set(then) if now_[p] != then[p])]
    out += [f"removed: {p}" for p in sorted(set(then) - set(now_))]
    return out


def approval_state(name: str) -> tuple[str, list[str]]:
    cc = cfg()["graph"]["corpora"].get(name, {})
    if not cc.get("requires_approval"):
        return "n/a", []
    ap = approval_for(name)
    if not ap:
        return "NOT approved", []
    changes = content_changes(name, ap)
    return ("approved", []) if not changes else ("RE-APPROVAL needed (content changed)", changes)


def policy_at_approval(ap: dict) -> dict | None:
    """The exclusion policy in force when the owner approved: stored snapshot, else found in myOS git history by hash."""
    if ap.get("policy_snapshot"):
        return ap["policy_snapshot"]
    want = ap.get("policy_sha256")
    revs = (git(ROOT, "log", "--format=%H", "--", "config/exclusion-policy.json") or "").split()
    for rev in revs:
        blob = git(ROOT, "show", f"{rev}:config/exclusion-policy.json")  # git() strips the final newline
        if blob is not None and want in (sha256_text(blob + "\n"), sha256_text(blob)):
            return json.loads(blob)
    return None


def policy_is_stricter(old: dict | None, new: dict) -> bool:
    """True if `new` keeps every exclusion of `old` (it may add more) and allows no new file types."""
    if not old:
        return False
    return (set(old["content_rules"].items()) <= set(new["content_rules"].items())
            and set(old["excluded_name_patterns"]) <= set(new["excluded_name_patterns"])
            and {d.lower() for d in old["excluded_dir_names"]} <= {d.lower() for d in new["excluded_dir_names"]}
            and set(new["allowed_extensions"]) <= set(old["allowed_extensions"]))


def corpora_covering(path: Path) -> list[str]:
    out = []
    for name, cc in cfg()["graph"]["corpora"].items():
        src = corpus_source(cc)
        if not is_under(path, src):
            continue
        rel = Path(os.path.relpath(path, src)).as_posix()
        if any(glob_match(rel, g) for g in cc["include"]) and (not cc.get("requires_approval") or approval_for(name)):
            out.append(name)
    return out


def run_graphify(args: list[str]) -> int:
    if not GRAPHIFY_EXE.exists():
        die(f"Graphify not installed at {GRAPHIFY_EXE}. Run scripts\\setup.ps1.")
    env = dict(os.environ)
    env["PATH"] = str(SHIM_DIR) + os.pathsep + env.get("PATH", "")  # hardened claude.cmd first
    env["GRAPHIFY_CLAUDE_CLI_MODEL"] = cfg()["graph"]["model"]
    env["PYTHONUTF8"] = "1"
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "MOONSHOT_API_KEY",
              "KIMI_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"):
        env.pop(k, None)  # only the configured backend may be used
    print("$ graphify " + " ".join(args), flush=True)
    return subprocess.call([str(GRAPHIFY_EXE), *args], env=env, cwd=str(ROOT))


def cmd_graph(a):
    name = a.corpus
    if a.action == "list":
        for n, cc in cfg()["graph"]["corpora"].items():
            built = (GRAPH_DIR / n / "graphify-out" / "graph.json").exists()
            st, ch = approval_state(n)
            print(f"{n:<24} approval={st:<13} built={built}  {cc['description']}")
            for c in ch[:5]:
                print(f"{'':<26}- {c}")
        return
    cc = corpus_cfg(name)
    if a.action in ("plan", "stage"):
        m = stage(name)
        print((GRAPH_DIR / name / "TRANSMISSION-PREVIEW.md").read_text(encoding="utf-8"))
        st, ch = approval_state(name)
        print(f"approval status: {st}" + "".join(f"\n  - {c}" for c in ch))
        return
    if a.action == "approve":
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            die("approval must be given interactively by the user in a terminal; agents cannot approve.", 5)
        m = stage(name)
        print((GRAPH_DIR / name / "TRANSMISSION-PREVIEW.md").read_text(encoding="utf-8"))
        ans = input(f"Type the corpus name '{name}' to approve sending these {len(m['files'])} files to the provider above: ")
        if ans.strip() != name:
            die("not approved.", 1)
        aps = approvals()
        aps[name] = {"approved_at": now_iso(), "approved_by": os.environ.get("USERNAME", "user"),
                     "include": cc["include"], "exclude": cc.get("exclude", []), "policy_sha256": m["policy_sha256"],
                     "policy_snapshot": policy(),
                     "content_sha256_at_approval": m["content_sha256"], "files_at_approval": len(m["files"]),
                     "files": [{"path": f["path"], "sha256": f["sha256"]} for f in m["files"]]}
        atomic_write(APPROVALS_PATH, json.dumps(aps, indent=1))
        print(f"approved: {name}")
        return
    if a.action in ("build", "update"):
        if cc.get("requires_approval") and not approval_for(name):
            die(f"corpus '{name}' is not approved for external transmission. Run `myos graph plan {name}` to see what "
                f"would be sent, then the user runs `myos graph approve {name}` in their own terminal.", 5)
        st, ch = approval_state(name)
        if cc.get("requires_approval") and st != "approved":
            die(f"corpus '{name}' changed since it was approved; nothing was sent. Changes:\n  - " + "\n  - ".join(ch[:20])
                + f"\nReview `myos graph plan {name}`, then the user re-approves with `myos graph approve {name}`.", 5)
        m = stage(name)
        print(f"staged {len(m['files'])} files ({len(m['excluded'])} excluded by policy) -> {GRAPH_DIR / name / 'corpus'}")
        if not m["files"]:
            die(f"corpus '{name}' has no files to send - nothing to build.", 4)
        args = ["extract", str(GRAPH_DIR / name / "corpus"), "--backend", cfg()["graph"]["backend"], "--out", str(GRAPH_DIR / name)]
        if a.action == "build" and a.force:
            args.append("--force")
        rc = run_graphify(args)
        if rc != 0:
            die(f"graphify extract failed (exit {rc})", rc)
        rc = run_graphify(["cluster-only", str(GRAPH_DIR / name), "--backend=" + cfg()["graph"]["backend"]])
        out = GRAPH_DIR / name / "graphify-out"
        print(f"\noutputs: {out / 'graph.json'}\n         {out / 'GRAPH_REPORT.md'}\n         {out / 'graph.html'}")
        sys.exit(rc)
    if a.action == "query":
        gj = GRAPH_DIR / name / "graphify-out" / "graph.json"
        if not gj.exists():
            die(f"no graph built for '{name}'")
        sys.exit(run_graphify(["query", a.text or "", "--graph", str(gj), "--budget", "1500"]))
    if a.action == "provenance":
        gj = GRAPH_DIR / name / "graphify-out" / "graph.json"
        g = json.loads(gj.read_text(encoding="utf-8"))
        from collections import Counter
        edges = g.get("links", [])
        cnt = Counter(e.get("confidence") for e in edges)
        print(f"{name}: {len(g.get('nodes', []))} nodes, {len(edges)} edges; by confidence: {dict(cnt)}")
        for kind in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
            sample = [e for e in edges if e.get("confidence") == kind][:3]
            for e in sample:
                print(f"  {kind:<9} score={e.get('confidence_score')} {e['source']} --{e.get('relation')}--> {e['target']}")


# --------------------------------------------------------------------------- #
def cmd_scan(a):
    pol, rules = policy(), _content_rules()
    root = Path(a.path)
    files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
    bad = 0
    for p in files:
        rel = Path(os.path.relpath(p, root if root.is_dir() else root.parent)).as_posix()
        r = classify(rel, p, pol, rules)
        if r and (a.all or not r.startswith("extension")):
            bad += 1
            print(f"EXCLUDE {rel}  ({r})")
    print(f"{len(files)} files scanned, {bad} would be excluded")


def myos_vault_files() -> list[str]:
    """Vault notes created by myOS: myOS templates/pilot, myOS-tagged notes, and session notes written by `myos save`."""
    v = vault_root()
    out = []
    for p in v.rglob("*.md"):
        rel = Path(os.path.relpath(p, v)).as_posix()
        if rel.startswith((".obsidian", ".git")):
            continue
        if rel.startswith(("07-TEMPLATES/myOS/", "03-PROJECTS/_myOS-Pilot/")):
            out.append(rel)
            continue
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            continue
        fm, _ = parse_frontmatter(head)
        if "<!-- myos:session:begin" in head or "myos" in [str(t).lower() for t in (fm.get("tags") or [])] \
                or "(myOS)" in p.name:
            out.append(rel)
    return sorted(out)


def cmd_manifest(a):
    def out_of(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=60, shell=True).stdout or ""
        except Exception:  # noqa: BLE001
            return ""

    def ver(cmd):
        lines = out_of(cmd).strip().splitlines()
        return lines[0] if lines else "unavailable"

    plugins = out_of("claude plugin list")
    pm = re.search(r"ponytail@ponytail.*?Version:\s*(\S+)", plugins, re.S)
    user_path = subprocess.run(["powershell", "-NoProfile", "-Command", "[Environment]::GetEnvironmentVariable('Path','User')"],
                               capture_output=True, text=True).stdout.strip().split(";") if os.name == "nt" else []
    pony = Path(os.environ.get("APPDATA", "")) / "ponytail" / "config.json"
    m = {
        "generated": now_iso(), "myos_root": str(ROOT), "myos_head": git(ROOT, "rev-parse", "--short", "HEAD"),
        "versions": {"python": sys.version.split()[0], "claude": ver("claude --version"),
                     "codex (myOS shim)": ver(f'"{ROOT / "bin" / "codex.cmd"}" --version'), "orca": ver("orca --version"),
                     "graphify": ver(f'"{GRAPHIFY_EXE}" --version') if GRAPHIFY_EXE.exists() else "not installed",
                     "ponytail (claude plugin)": pm.group(1) if pm else "not installed"},
        "ponytail_default_mode": (json.loads(pony.read_text(encoding="utf-8")).get("defaultMode") if pony.exists() else "plugin default (full)"),
        "user_path_entries_added_by_myos": [p for p in user_path if "myOS" in p],
        "agent_integration_files": [str(Path.home() / x) for x in (
            ".claude/CLAUDE.md", ".claude/settings.json", ".codex/AGENTS.md", ".codex/rules/myos-guard.rules",
            ".claude/skills/save-progress/SKILL.md", ".claude/skills/resume-project/SKILL.md", ".claude/skills/project-status/SKILL.md",
            ".claude/skills/context-search/SKILL.md", ".claude/skills/executive-briefing/SKILL.md", ".agents/skills")],
        "orca_codex_home_files": [str(Path(os.environ.get("APPDATA", "")) / "orca/codex-runtime-home/home" / x)
                                  for x in ("AGENTS.md", "rules/myos-guard.rules")],
        "projects": [c.id for c in load_cards()], "engagements": [e["id"] for e in load_engagements()],
        "graph_corpora": {n: approval_state(n)[0] for n in cfg()["graph"]["corpora"]},
        "vault": str(vault_root()), "vault_files_added_by_myos": myos_vault_files(),
    }
    out = json.dumps(m, indent=1)
    if a.out:
        atomic_write(Path(a.out), out)
        print(f"manifest written: {a.out}")
    else:
        print(out)


def cmd_remind(a):
    """Session-end reminder (for an optional Stop/SessionEnd hook). Silent unless useful; never fails."""
    try:
        hits, _ = resolve(None, a.cwd)
        if len(hits) != 1:
            return
        c = hits[0]
        if not any(p.name.startswith(today()) for p in session_files(c)):
            f = git_facts(Path(a.cwd or os.getcwd()))
            if f.get("dirty_total") or f.get("ahead"):
                print(f"myOS: no /save-progress recorded today for {c.name} and the tree has "
                      f"{f.get('dirty_total')} uncommitted entries. Consider running /save-progress.")
    except Exception:  # a reminder must never break the agent
        pass


def cmd_recover(a):
    n = recover_pending()
    print(f"{n} interrupted transaction(s) replayed." if n else "No interrupted writes found.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="myos", description="myOS context routing and memory CLI")
    ap.add_argument("--cwd", help="treat this directory as the current one (project detection)")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("list", help="list engagements and registered projects").set_defaults(fn=cmd_list)
    p = sp.add_parser("route", help="identify the project (by name or current directory) and show where its facts live")
    p.add_argument("query", nargs="?"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_route)
    p = sp.add_parser("status", help="verified project status: live git + historical records")
    p.add_argument("project", nargs="?"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("resume", help="read-only resume briefing for a project")
    p.add_argument("project", nargs="?"); p.set_defaults(fn=cmd_resume)
    p = sp.add_parser("search", help="deterministic search over approved notes + graph relationships")
    p.add_argument("query"); p.add_argument("--project"); p.add_argument("--type", help="decision|session|bug|runbook|spec|<regex>")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--engagement", help="limit to one engagement (default: the session's engagement)")
    p.add_argument("--all-engagements", action="store_true", help="owner view: search every engagement")
    p.set_defaults(fn=cmd_search)
    p = sp.add_parser("save", help="record a session note + update the project card (JSON on stdin or --input)")
    p.add_argument("--input"); p.add_argument("--project"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(fn=cmd_save)
    p = sp.add_parser("brief", help="engagement-by-engagement executive briefing")
    p.add_argument("--cached", action="store_true", help="skip live git checks")
    p.add_argument("--detail", action="store_true", help="full labelled report (default is the compact table)")
    p.add_argument("--include-test", action="store_true"); p.set_defaults(fn=cmd_brief)
    p = sp.add_parser("verify", help="refresh a card's live evidence block (read-only git)")
    p.add_argument("project", nargs="?"); p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_verify)
    p = sp.add_parser("graph", help="Graphify corpus: list|plan|approve|build|update|query|provenance")
    p.add_argument("action", choices=["list", "plan", "stage", "approve", "build", "update", "query", "provenance"])
    p.add_argument("corpus", nargs="?"); p.add_argument("text", nargs="?"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_graph)
    p = sp.add_parser("scan", help="show which files the exclusion policy would block"); p.add_argument("path")
    p.add_argument("--all", action="store_true"); p.set_defaults(fn=cmd_scan)
    sp.add_parser("recover", help="replay interrupted multi-file writes").set_defaults(fn=cmd_recover)
    p = sp.add_parser("manifest", help="installation manifest: versions, files, vault notes added by myOS, approvals")
    p.add_argument("--out"); p.set_defaults(fn=cmd_manifest)
    sp.add_parser("remind", help="print a save-progress reminder if today's session is unrecorded (hook helper)").set_defaults(fn=cmd_remind)

    a = ap.parse_args(argv)
    if a.cmd == "graph" and a.action != "list" and not a.corpus:
        die("graph: corpus name required")
    a.fn(a)


if __name__ == "__main__":
    main()
