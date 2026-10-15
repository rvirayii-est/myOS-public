"""Automated tests for scripts/myos.py.  Run:  python -m unittest discover -s tests -v

Isolation: every test runs in a throwaway demo world (tests/demo_world.py): scratch vault, scratch cards,
scratch repos and journal, all selected through MYOS_* environment variables.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from demo_world import EnvPatch, destroy, make_world  # noqa: E402


def fresh_myos():
    """Re-import myos so module-level paths pick up the current env vars."""
    sys.modules.pop("myos", None)
    import myos  # noqa: E402
    return myos


def run(m, *argv) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.main(list(argv))
    return buf.getvalue()


class Scratch(unittest.TestCase):
    def setUp(self):
        self.world = make_world()
        self.tmp, self.vault, self.cards = self.world["tmp"], self.world["vault"], self.world["cards"]
        self.env = self.world["env"]
        self._patch = EnvPatch(self.env).__enter__()
        self.m = fresh_myos()

    def tearDown(self):
        self._patch.__exit__()
        destroy(self.world)
        sys.modules.pop("myos", None)


class TestFrontmatter(unittest.TestCase):
    def test_roundtrip(self):
        m = fresh_myos()
        fm = {"type": "session", "tags": ["a", "b c"], "summary": "x: y", "n": None}
        data, body = m.parse_frontmatter(m.dump_frontmatter(fm) + "body")
        self.assertEqual(data, fm)
        self.assertEqual(body, "body")

    def test_glob_match(self):
        m = fresh_myos()
        self.assertTrue(m.glob_match("03-PROJECTS/_myOS-Pilot/00-Overview.md", "03-PROJECTS/_myOS-Pilot/**/*.md"))
        self.assertTrue(m.glob_match("03-PROJECTS/_myOS-Pilot/sessions/a.md", "03-PROJECTS/_myOS-Pilot/**/*.md"))
        self.assertFalse(m.glob_match("03-PROJECTS/LumenLedger/a.md", "03-PROJECTS/_myOS-Pilot/**/*.md"))
        self.assertFalse(m.glob_match("07-TEMPLATES/myOS/sub/a.md", "07-TEMPLATES/myOS/*.md"))

    def test_replace_block_idempotent(self):
        m = fresh_myos()
        t = m.replace_block("hello", "x", "one")
        t2 = m.replace_block(t, "x", "two")
        self.assertEqual(t2.count("myos:x:begin"), 1)
        self.assertIn("two", t2)
        self.assertNotIn("one", t2)


class TestRouting(Scratch):
    def test_alias(self):
        hits, _ = self.m.resolve("ledger")
        self.assertEqual([c.id for c in hits], ["lumen-ledger"])

    def test_repo_folder(self):
        hits, how = self.m.resolve(cwd=str(self.world["orbit"]))
        self.assertEqual([c.id for c in hits], ["orbit-queue"])
        self.assertEqual(how, "git repository")

    def test_worktree_maps_to_main_repo(self):
        hits, how = self.m.resolve(cwd=str(self.world["lumen_wt"]))
        self.assertEqual([c.id for c in hits], ["lumen-ledger"])
        self.assertEqual(how, "git repository")

    def test_card_repo_placeholder_expands(self):
        c = self.m.resolve("lumen-ledger")[0][0]
        self.assertEqual(self.m.npath(c.repo()), self.m.npath(self.world["lumen"]))

    def test_unknown(self):
        hits, _ = self.m.resolve("definitely-not-a-project-xyz")
        self.assertEqual(hits, [])


class TestSave(Scratch):
    def payload(self, **kw):
        d = {"project": "myos-sandbox", "agent": "test", "session_id": "s1", "summary": "First save",
             "changes": ["added X"], "tests": [{"command": "pytest", "result": "passed", "evidence": "3 passed"},
                                               {"command": "npm test", "result": "passed", "evidence": ""}],
             "decisions": [{"decision": "use Y", "rationale": "owner confirmed"}],
             "blockers": ["waiting on Z"], "next_actions": ["do the next thing"], "gaps": []}
        d.update(kw)
        f = self.tmp / "in.json"
        f.write_text(json.dumps(d), encoding="utf-8")
        return str(f)

    def session_file(self):
        files = list((self.vault / "03-PROJECTS" / "_myOS-Pilot" / "sessions").glob("*.md"))
        self.assertEqual(len(files), 1)
        return files[0]

    def test_save_creates_note_and_updates_card(self):
        run(self.m, "--cwd", str(ROOT), "save", "--input", self.payload())
        text = self.session_file().read_text(encoding="utf-8")
        self.assertIn("<!-- myos:session:begin id=s1 -->", text)
        self.assertIn("**passed**", text)
        self.assertIn("claimed-passed-NO-EVIDENCE", text)  # passed without evidence is downgraded
        card = (self.cards / "myos-sandbox.md").read_text(encoding="utf-8")
        self.assertIn("do the next thing", card)
        self.assertIn("waiting on Z", card)
        # hub was created because the scratch vault had no pilot folder
        self.assertTrue((self.vault / "03-PROJECTS" / "_myOS-Pilot" / "00-Overview.md").exists())

    def test_repeat_save_is_idempotent(self):
        run(self.m, "--cwd", str(ROOT), "save", "--input", self.payload())
        run(self.m, "--cwd", str(ROOT), "save", "--input", self.payload(summary="Second save, same session"))
        text = self.session_file().read_text(encoding="utf-8")
        self.assertEqual(text.count("myos:session:begin id=s1"), 1)
        self.assertIn("Second save", text)
        self.assertNotIn("First save", text)
        card = (self.cards / "myos-sandbox.md").read_text(encoding="utf-8")
        sessions = self.m.get_block(card, "sessions")
        self.assertEqual(sum("`s1`" in l for l in sessions.splitlines()), 1)  # one list entry for s1
        self.assertEqual(card.count("myos:handoff:begin"), 1)

    def test_identical_resave_is_noop(self):
        f = self.payload()
        run(self.m, "--cwd", str(ROOT), "save", "--input", f)
        before = self.session_file().read_text(encoding="utf-8")
        out = run(self.m, "--cwd", str(ROOT), "save", "--input", f)
        self.assertIn("nothing to do", out)
        self.assertEqual(before, self.session_file().read_text(encoding="utf-8"))

    def test_concurrent_saves_both_recorded(self):
        import subprocess
        files = [self.payload(session_id=f"par{i}", summary=f"parallel {i}") for i in (1, 2)]
        # payload() reuses one file name; give each process its own copy
        paths = []
        for i, f in enumerate(files):
            q = self.tmp / f"in{i}.json"
            q.write_text(json.dumps({**json.loads(Path(f).read_text(encoding="utf-8")), "session_id": f"par{i}"}), encoding="utf-8")
            paths.append(q)
        env = {**os.environ, **self.env}
        procs = [subprocess.Popen([sys.executable, str(ROOT / "scripts" / "myos.py"), "--cwd", str(ROOT), "save", "--input", str(q)],
                                  env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for q in paths]
        for pr in procs:
            pr.communicate(timeout=120)
            self.assertEqual(pr.returncode, 0)
        sessions = self.m.get_block((self.cards / "myos-sandbox.md").read_text(encoding="utf-8"), "sessions")
        self.assertIn("`par0`", sessions)
        self.assertIn("`par1`", sessions)
        self.assertEqual(self.session_file().read_text(encoding="utf-8").count("myos:session:begin id=par"), 2)

    def test_windows_backslashes_in_json_tolerated(self):
        f = self.tmp / "bs.json"
        f.write_text('{"project": "myos-sandbox", "agent": "t", "session_id": "bs", "summary": "path C:' + chr(92) + 'projects' + chr(92) + 'myOS ok"}', encoding="utf-8")
        run(self.m, "--cwd", str(ROOT), "save", "--input", str(f))
        self.assertIn("myOS ok", self.session_file().read_text(encoding="utf-8"))

    def test_new_session_appends(self):
        run(self.m, "--cwd", str(ROOT), "save", "--input", self.payload())
        run(self.m, "--cwd", str(ROOT), "save", "--input", self.payload(session_id="s2", summary="other"))
        text = self.session_file().read_text(encoding="utf-8")
        self.assertEqual(text.count("myos:session:begin"), 2)

    def test_recover_replays_interrupted_write(self):
        target = self.tmp / "half-written.md"
        j = Path(self.env["MYOS_JOURNAL_DIR"])
        j.mkdir(parents=True, exist_ok=True)
        (j / "x.pending.json").write_text(json.dumps({"label": "t", "writes": [{"path": str(target), "content": "complete"}]}), encoding="utf-8")
        out = run(self.m, "recover")
        self.assertIn("1 interrupted", out)
        self.assertEqual(target.read_text(encoding="utf-8"), "complete")
        self.assertFalse(list(j.glob("*.pending.json")))


class TestSearchAndPolicy(Scratch):
    def test_search_finds_decision(self):
        out = run(self.m, "search", "event sourcing journal", "--type", "decision")
        self.assertIn("ADR-001 Use event sourcing for journal.md", out.splitlines()[3])

    def test_search_redacts_secrets(self):
        out = run(self.m, "search", "leaky login token")
        self.assertNotIn("ghp_FAKE", out)
        self.assertIn("[REDACTED]", out)

    def test_stage_excludes_sensitive(self):
        man = self.m.stage("synthetic")
        inc = {f["path"] for f in man["files"]}
        exc = {e["path"]: e["reason"] for e in man["excluded"]}
        self.assertEqual(len(inc), 5)
        self.assertNotIn("03-PROJECTS/LumenLedger/.env", inc)  # outside the *.md scope, never staged
        self.assertIn("03-PROJECTS/LumenLedger/private/credentials-note.md", exc)
        self.assertTrue(exc["03-PROJECTS/LumenLedger/leaky-session.md"].startswith("content:"))
        staged = Path(self.m.GRAPH_DIR / "synthetic" / "corpus")
        self.assertFalse((staged / "03-PROJECTS/LumenLedger/leaky-session.md").exists())

    def test_unapproved_corpus_refused(self):
        with self.assertRaises(SystemExit) as cm:
            run(self.m, "graph", "build", "vault-pilot")
        self.assertEqual(cm.exception.code, 5)

    def test_agent_cannot_approve(self):
        with self.assertRaises(SystemExit) as cm:
            run(self.m, "graph", "approve", "vault-pilot")  # stdin is not a TTY under the test runner
        self.assertEqual(cm.exception.code, 5)


class TestCorporaDefinitions(Scratch):
    """Corpus scopes stay separate (checked against the scratch vault)."""

    def scope(self, m, name):
        cc = m.cfg()["graph"]["corpora"][name]
        src = m.corpus_source(cc)
        out = set()
        for base in m.include_bases(src, cc["include"]):
            files = [base] if base.is_file() else (base.rglob("*") if base.is_dir() else [])
            for f in files:
                rel = f.relative_to(src).as_posix()
                if any(m.glob_match(rel, g) for g in cc["include"]) and not any(m.glob_match(rel, g) for g in cc.get("exclude", [])):
                    out.add(rel)
        return out

    def test_engagement_corpora_disjoint_and_private_excluded(self):
        m = fresh_myos()
        lumen, orbit = self.scope(m, "lumen-ledger"), self.scope(m, "orbit-queue")
        self.assertTrue(lumen and orbit)
        self.assertEqual(lumen & orbit, set())
        self.assertFalse(any("/private/" in f for f in lumen))
        self.assertIn("03-PROJECTS/LumenLedger/00-Overview.md", lumen)

    def test_every_real_corpus_requires_approval(self):
        m = fresh_myos()
        for name, cc in m.cfg()["graph"]["corpora"].items():
            if name != "synthetic":
                self.assertTrue(cc.get("requires_approval"), name)


if __name__ == "__main__":
    unittest.main()
