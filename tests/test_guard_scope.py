"""Guard: cross-engagement knowledge queries and vault-wide searches. Decision tests only, in a demo world."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
from demo_world import EnvPatch, destroy, make_world  # noqa: E402

import guard  # noqa: E402

W = make_world("myos-scope-")
_PATCH = EnvPatch(W["env"])

ORBIT = str(W["orbit"])               # globex session
LUMEN = str(W["lumen_wt"])            # acme session
VAULT = str(W["vault"])
MYOS = f'python "{ROOT / "scripts" / "myos.py"}"'


def setUpModule():
    _PATCH.__enter__()
    sys.modules.pop("myos", None)  # re-read MYOS_* paths for this module's world


def tearDownModule():
    _PATCH.__exit__()
    sys.modules.pop("myos", None)
    destroy(W)


def d(tool, cwd, **ti):
    r = guard.decide(tool, ti, cwd)
    return r[0] if r else "allow"


class TestCrossEngagementQueries(unittest.TestCase):
    def test_cd_into_myos_then_query_other_project_is_gated(self):
        cmd = f'cd "{ROOT.as_posix()}"; python scripts/myos.py search "idempotency key" --project lumen-ledger 2>&1 | head -60'
        self.assertEqual(d("Bash", ORBIT, command=cmd), "ask")

    def test_other_bypasses(self):
        for cmd in [f'{MYOS} search "journal" --project lumen-ledger', f"{MYOS} resume lumen-ledger",
                    f'{MYOS} search "journal" --all-engagements', f"{MYOS} brief",
                    f'cd "{ROOT}" && python scripts/myos.py search "journal"',  # wherever myOS lives
                    f'{MYOS} --cwd "{LUMEN}" search "journal"']:
            self.assertEqual(d("Bash", ORBIT, command=cmd), "ask", cmd)

    def test_vault_wide_search_from_project_session(self):
        self.assertEqual(d("Grep", ORBIT, path=VAULT), "ask")
        self.assertEqual(d("Grep", ORBIT, path=VAULT + r"\03-PROJECTS"), "ask")
        self.assertEqual(d("Bash", ORBIT, command=f'grep -rn journal "{VAULT}"'), "ask")
        self.assertEqual(d("Glob", ORBIT, path=str(W["projects"])), "ask")

    def test_in_scope_work_untouched(self):
        self.assertEqual(d("Bash", ORBIT, command=f'{MYOS} search "relay"'), "allow")
        self.assertEqual(d("Bash", ORBIT, command=f"{MYOS} resume orbit-queue"), "allow")
        self.assertEqual(d("Bash", LUMEN, command=f"{MYOS} resume lumen-ledger"), "allow")
        self.assertEqual(d("Grep", ORBIT, path=VAULT + r"\03-PROJECTS\OrbitQueue"), "allow")
        self.assertEqual(d("Grep", ORBIT, path=VAULT + r"\05-TECH-RUNBOOKS"), "allow")
        self.assertEqual(d("Bash", str(ROOT), command="python scripts/myos.py brief"), "allow")  # owner view


if __name__ == "__main__":
    unittest.main()
