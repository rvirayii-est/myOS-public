"""Engagement / project isolation of retrieval, in a throwaway demo world; graphs are fakes in a temp dir."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from demo_world import EnvPatch, destroy, make_world  # noqa: E402


def fresh_myos():
    sys.modules.pop("myos", None)
    import myos  # noqa: E402
    return myos


def run(m, *argv) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.main(list(argv))
    return buf.getvalue()


class TestEngagementIsolation(unittest.TestCase):
    def setUp(self):
        self.w = make_world("myos-iso-")
        self.p = EnvPatch(self.w["env"]).__enter__()

    def tearDown(self):
        self.p.__exit__()
        destroy(self.w)
        sys.modules.pop("myos", None)

    def search(self, *argv):
        return run(fresh_myos(), *argv)

    def test_acme_session_cannot_see_globex(self):
        out = self.search("--cwd", str(self.w["lumen_wt"]), "search", "at-least-once message relay partition", "--limit", "20")
        self.assertIn("Scope: engagement acme", out)
        self.assertNotIn("OrbitQueue/OrbitQueue.md", out)
        self.assertNotIn("orbit-queue.md", out)

    def test_globex_session_cannot_see_acme(self):
        out = self.search("--cwd", str(self.w["orbit"]), "search", "event sourcing journal reconciliation", "--limit", "20")
        self.assertIn("Scope: engagement globex", out)
        for leak in ("LumenLedger", "lumen-ledger.md", "Acme", "ADR-001"):
            self.assertNotIn(leak, out)

    def test_owner_view_is_explicit(self):
        out = self.search("--cwd", str(self.w["lumen_wt"]), "search", "message relay", "--all-engagements", "--limit", "20")
        self.assertIn("ALL engagements", out)
        self.assertIn("OrbitQueue", out)

    def test_myos_root_is_owner_view(self):
        out = self.search("--cwd", str(ROOT), "search", "message relay", "--limit", "5")
        self.assertIn("owner view", out)


class TestGraphScoping(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="myos-graph-"))
        self.old = os.environ.get("MYOS_GRAPH_DIR")
        os.environ["MYOS_GRAPH_DIR"] = str(self.tmp)
        for corpus, label in (("lumen-ledger", "LumenOnlyConcept"), ("orbit-queue", "OrbitOnlyConcept"),
                              ("acme-general", "AcmeWideConcept")):
            d = self.tmp / corpus / "graphify-out"
            d.mkdir(parents=True)
            g = {"nodes": [{"id": "a", "label": f"{label} widget", "source_file": "x.md"},
                           {"id": "b", "label": "shared widget", "source_file": "x.md"}],
                 "links": [{"source": "a", "target": "b", "relation": "references", "confidence": "EXTRACTED",
                            "confidence_score": 1.0, "source_file": "x.md"}]}
            (d / "graph.json").write_text(json.dumps(g), encoding="utf-8")
        self.m = fresh_myos()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("MYOS_GRAPH_DIR", None)
        else:
            os.environ["MYOS_GRAPH_DIR"] = self.old
        shutil.rmtree(self.tmp, ignore_errors=True)
        sys.modules.pop("myos", None)

    def ctx(self, **kw):
        return "\n".join(self.m.graph_context("widget", **kw))

    def test_projects_of_different_engagements_never_cross(self):
        lumen = self.ctx(project="lumen-ledger", engagement="acme")
        orbit = self.ctx(project="orbit-queue", engagement="globex")
        self.assertIn("LumenOnlyConcept", lumen)
        self.assertNotIn("OrbitOnlyConcept", lumen)
        self.assertIn("OrbitOnlyConcept", orbit)
        self.assertNotIn("LumenOnlyConcept", orbit)
        self.assertNotIn("AcmeWideConcept", orbit)

    def test_engagement_general_corpus_shared_within_engagement_only(self):
        self.assertIn("AcmeWideConcept", self.ctx(project="lumen-ledger", engagement="acme"))
        self.assertEqual(self.ctx(engagement="personal"), "")


if __name__ == "__main__":
    unittest.main()
