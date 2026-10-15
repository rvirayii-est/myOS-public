"""Verify every statement in the compact executive briefing against its source (read-only).

[V] repo cells are re-checked against live git; [H] session dates against the card's session list; [H] claims against
card status_claim; [H] next actions against the card text. Every cell must carry a [V]/[H]/[I]/[M] tag.
Run: python tests/verify_briefing.py   (exit 1 on any mismatch)
"""
import contextlib
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import myos  # noqa: E402

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    myos.main(["brief"])
cards = {c.name: c for c in myos.load_cards()}
rows = [l for l in buf.getvalue().splitlines() if l.startswith("| ") and not l.startswith(("| Project", "| ---"))]
checked = bad = untagged = 0
for r in rows:
    name, repo, rec, nxt, dec = [x.strip() for x in r.strip("|").split("|")]
    c = cards[name]
    for cell in (repo, rec, nxt):
        if not re.match(r"^\[(V|H|I|M)\]", cell) and cell not in ("-", "(not checked)"):
            untagged += 1
            print("UNTAGGED", name, cell)
    f = myos.git_facts(c.repo()) if c.repo() else {}
    m = re.match(r"\[V\] (.+)@(\w+), (\d+) dirty", repo)
    if m:
        checked += 1
        if not (f.get("head") == m.group(2) and str(f.get("dirty_total")) == m.group(3)
                and str(f.get("branch")).startswith(m.group(1).rstrip("…"))):
            bad += 1
            print("V-MISMATCH (repo changed since the briefing, or a defect)", name, repo)
    s = re.search(r"\[H\] session (\d{4}-\d\d-\d\d)", rec)
    if s:
        checked += 1
        if s.group(1) not in (myos.get_block(c.text, "sessions") or ""):
            bad += 1
            print("H-MISMATCH session", name)
    cl = re.search(r"\[H\] claim: (.+?)(…|;|$)", rec)
    if cl:
        checked += 1
        if not str(c["status_claim"]).startswith(cl.group(1).strip()):
            bad += 1
            print("H-MISMATCH claim", name)
    if nxt.startswith("[H]"):
        checked += 1
        if nxt[4:40].rstrip("…") not in c.text:
            bad += 1
            print("H-MISMATCH next action", name)
print(f"rows {len(rows)}, statements checked {checked}, mismatches {bad}, untagged cells {untagged}")
sys.exit(1 if bad or untagged else 0)
