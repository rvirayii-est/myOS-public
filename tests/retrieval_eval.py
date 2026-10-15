"""Retrieval quality on representative project questions (read-only).

  python tests/retrieval_eval.py            -> file search (always) + graph context (for built corpora)

Each question names the note(s) a correct answer must cite. "hit@5" = an expected note is in the top 5 file
results; "graph" = a graph edge/node returned for the question cites an expected note (only if that corpus is built).
"""
import contextlib
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import myos  # noqa: E402

# Example questions for the bundled demo vault. Replace them with representative questions about your own projects.
QUESTIONS = {
    "lumen-ledger": [
        ("Why are journal entries immutable events?", ["ADR-001 Use event sourcing for journal.md"]),
        ("duplicate posting bug idempotency key", ["2026-02-03-lumen-ledger.md"]),
        ("Rust Axum backend with PostgreSQL", ["00-Overview.md"]),
    ],
    "orbit-queue": [
        ("delivery guarantee and ordering of the relay", ["OrbitQueue.md"]),
    ],
}
CORPUS_OF = {"lumen-ledger": "lumen-ledger", "orbit-queue": "orbit-queue"}
ENGAGEMENT_OF = {"lumen-ledger": "acme", "orbit-queue": "globex"}


def file_hits(project, q):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        myos.main(["--cwd", str(ROOT), "search", q, "--project", project, "--limit", "5"])
    return re.findall(r"^\d+\. (.+?):\d+  \[", buf.getvalue(), re.M)


def main():
    built = {n for n, _ in myos.built_graphs()}
    tot_f = tot_g = hit_f = hit_g = 0
    print(f"{'project':<18} {'question':<55} {'hit@5':<6} graph")
    for project, qs in QUESTIONS.items():
        corpus = CORPUS_OF[project]
        for q, expected in qs:
            fh = "-"
            if True:
                paths = file_hits(project, q)
                ok = any(Path(p).name in expected for p in paths)
                fh = "yes" if ok else "NO"
                tot_f += 1
                hit_f += ok
            gh = "not built"
            if corpus in built:
                ctx = "\n".join(myos.graph_context(q, limit=8, project=project, engagement=ENGAGEMENT_OF[project]))
                ok = any(e in ctx for e in expected)
                gh = "yes" if ok else "NO"
                tot_g += 1
                hit_g += ok
            print(f"{project:<18} {q[:55]:<55} {fh:<6} {gh}")
    print(f"\nfile search hit@5: {hit_f}/{tot_f}" + (f"   graph: {hit_g}/{tot_g}" if tot_g else "   graph: no project corpus built yet"))


if __name__ == "__main__":
    main()
