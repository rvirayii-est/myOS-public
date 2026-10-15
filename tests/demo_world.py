"""A throwaway demo machine for tests: two git repos, one Orca-style worktree, a scratch vault and scratch cards.

Everything lives in one temp folder and is pointed to via MYOS_* environment variables, so tests never read or
write a real vault, real cards or real repositories.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_VAULT = ROOT / "tests" / "fixtures" / "synthetic-vault"


def _git(repo, *a):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                   capture_output=True, check=True)


def make_world(prefix="myos-test-"):
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    projects = tmp / "projects"
    for name in ("lumen-ledger", "orbit-queue"):
        repo = projects / name
        repo.mkdir(parents=True)
        _git(repo, "init", "-q", "-b", "main")
        (repo / "README.md").write_text(f"# {name}\n", encoding="utf-8")
        (repo / ".env").write_text("DEMO=1\n", encoding="utf-8")
        _git(repo, "add", "README.md")
        _git(repo, "commit", "-qm", "init")
    workspaces = tmp / "workspaces"
    (workspaces / "lumen-ledger").mkdir(parents=True)
    _git(projects / "lumen-ledger", "worktree", "add", "-q", "-b", "feature-x", str(workspaces / "lumen-ledger" / "feature-x"))
    vault = tmp / "vault"
    shutil.copytree(FIXTURE_VAULT, vault)
    acme = vault / "02-AREAS" / "Acme"
    acme.mkdir(parents=True)
    (acme / "Acme engagement notes.md").write_text("# Acme notes (SYNTHETIC)\nWeekly sync on Tuesdays.\n", encoding="utf-8")
    cards = tmp / "cards"
    shutil.copytree(ROOT / "projects", cards)
    env = {"MYOS_VAULT": str(vault), "MYOS_PROJECTS_ROOT": str(projects), "MYOS_ORCA_WORKSPACES": str(workspaces),
           "MYOS_PROJECTS_DIR": str(cards), "MYOS_APPROVALS": str(tmp / "approvals.json"),
           "MYOS_GRAPH_DIR": str(tmp / "graph"), "MYOS_JOURNAL_DIR": str(tmp / "journal"),
           "MYOS_GUARD_LOG": str(tmp / "guard.log")}
    return {"tmp": tmp, "projects": projects, "workspaces": workspaces, "vault": vault, "cards": cards, "env": env,
            "lumen": projects / "lumen-ledger", "orbit": projects / "orbit-queue",
            "lumen_wt": workspaces / "lumen-ledger" / "feature-x"}


class EnvPatch:
    """Apply a world's environment and restore the previous values afterwards."""

    def __init__(self, env):
        self.env, self.old = env, {k: os.environ.get(k) for k in env}

    def __enter__(self):
        os.environ.update(self.env)
        return self

    def __exit__(self, *exc):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def destroy(world):
    shutil.rmtree(world["tmp"], ignore_errors=True)
