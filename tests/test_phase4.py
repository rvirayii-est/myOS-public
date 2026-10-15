"""Regression tests: content-bound approval, stale-card detection, graph-unavailable fallback.
All writes go to temp dirs (MYOS_* overrides); nothing is sent anywhere (no graphify run)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = ROOT / "tests" / "fixtures" / "synthetic-vault"
sys.path.insert(0, str(ROOT / "scripts"))


def fresh():
    sys.modules.pop("myos", None)
    import myos  # noqa: E402
    return myos


def run(m, *argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.main(list(argv))
    return buf.getvalue()


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="myos-p4-"))
        self.vault = self.tmp / "vault"
        shutil.copytree(FIXTURE_VAULT, self.vault)
        self.cards = self.tmp / "projects"
        shutil.copytree(ROOT / "projects", self.cards)
        self.env = {"MYOS_VAULT": str(self.vault), "MYOS_PROJECTS_DIR": str(self.cards),
                    "MYOS_JOURNAL_DIR": str(self.tmp / "journal"), "MYOS_APPROVALS": str(self.tmp / "approvals.json"),
                    "MYOS_GRAPH_DIR": str(self.tmp / "graph")}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.m = fresh()

    def tearDown(self):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)
        sys.modules.pop("myos", None)


class TestContentBoundApproval(Env):
    def approve_now(self, name):
        m = self.m.stage(name, write=False)
        cc = self.m.cfg()["graph"]["corpora"][name]
        aps = {name: {"approved_at": "test", "include": cc["include"], "exclude": cc.get("exclude", []),
                      "policy_sha256": m["policy_sha256"], "policy_snapshot": self.m.policy(),
                      "content_sha256_at_approval": m["content_sha256"], "files_at_approval": len(m["files"]),
                      "files": [{"path": f["path"], "sha256": f["sha256"]} for f in m["files"]]}}
        Path(self.env["MYOS_APPROVALS"]).write_text(json.dumps(aps), encoding="utf-8")

    def test_change_after_approval_requires_reapproval(self):
        pilot = self.vault / "03-PROJECTS" / "_myOS-Pilot"
        pilot.mkdir(parents=True)
        (pilot / "a.md").write_text("# A\nfirst version\n", encoding="utf-8")
        self.approve_now("vault-pilot")
        self.assertEqual(self.m.approval_state("vault-pilot")[0], "approved")
        (pilot / "a.md").write_text("# A\nedited after approval\n", encoding="utf-8")
        (pilot / "b.md").write_text("# B\nnew note\n", encoding="utf-8")
        state, changes = self.m.approval_state("vault-pilot")
        self.assertTrue(state.startswith("RE-APPROVAL"))
        self.assertIn("changed: 03-PROJECTS/_myOS-Pilot/a.md", changes)
        self.assertIn("added: 03-PROJECTS/_myOS-Pilot/b.md", changes)
        with self.assertRaises(SystemExit) as cm:
            run(self.m, "graph", "build", "vault-pilot")  # refused before any staging/transmission
        self.assertEqual(cm.exception.code, 5)
        self.assertFalse((Path(self.env["MYOS_GRAPH_DIR"]) / "vault-pilot" / "graphify-out").exists())


class TestStaleCardAndFallback(Env):
    def test_stale_card_detected_after_new_commit(self):
        repo = self.tmp / "repo"
        repo.mkdir()
        g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, check=True)  # noqa: E731
        g("init", "-q")
        (repo / "x.txt").write_text("1", encoding="utf-8")
        g("add", "-A")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")
        card = self.cards / "myos-sandbox.md"
        card.write_text(card.read_text(encoding="utf-8").replace('repo: "@myos"', f'repo: "{repo}"'), encoding="utf-8")
        self.m = fresh()
        inp = self.tmp / "s.json"
        inp.write_text(json.dumps({"project": "myos-sandbox", "agent": "t", "session_id": "st", "summary": "before"}), encoding="utf-8")
        run(self.m, "--cwd", str(repo), "save", "--input", str(inp))
        c = self.m.require_one("myos-sandbox")
        self.assertIn("record is current", self.m.session_delta(c))
        (repo / "x.txt").write_text("2", encoding="utf-8")
        g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two")
        self.assertIn("1 new commit(s)", self.m.session_delta(c))
        self.assertIn("may be stale", self.m.session_delta(c))

    def test_search_works_without_any_graph(self):
        out = run(self.m, "--cwd", str(ROOT), "search", "event sourcing journal", "--limit", "3")
        self.assertIn("ADR-001", out)
        self.assertIn("No built graph matched", out)  # graph dir is an empty temp dir

    def test_corrupt_graph_file_is_ignored(self):
        d = Path(self.env["MYOS_GRAPH_DIR"]) / "synthetic" / "graphify-out"
        d.mkdir(parents=True)
        (d / "graph.json").write_text("{not json", encoding="utf-8")
        out = run(self.m, "--cwd", str(ROOT), "search", "orbitqueue", "--limit", "2")
        self.assertIn("OrbitQueue", out)  # file search still answers


if __name__ == "__main__":
    unittest.main()
