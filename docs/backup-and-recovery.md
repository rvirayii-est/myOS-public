# Backup and recovery (plain-language guide)

## Make a backup (do this weekly, and before big changes)
In PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\backup.ps1
```
You get `C:\projects\myOS\backups\myos-backup-<date-time>.zip`. To keep a copy somewhere else, such as a USB drive:
```powershell
powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\backup.ps1 -Destination E:\myOS-backups
```
Add `-IncludeGraphs` to also keep the built knowledge graphs. They can always be rebuilt, so this is optional.

**What is inside:**
- all of myOS (project cards, engagements, settings, schemas, workflows, skills, scripts, docs, tests)
- its full git history
- copies of your agent settings that myOS works with
- the vault notes myOS created
- an installation manifest (versions, PATH entries, approvals)
- a checksum for every file

**What is never inside:**
- your passwords or login tokens
- copies of your private notes that were staged for Graphify
- raw test transcripts

Every file is scanned for secrets before packing. Nothing is uploaded anywhere.

**Your Obsidian vault itself** is not in this backup. It has its own git history; commit it in Obsidian or with git, or use
Obsidian Sync.

## Check that a backup works (safe; changes nothing)
```powershell
powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\restore.ps1 -Zip C:\projects\myOS\backups\myos-backup-<date-time>.zip -Target C:\Temp\myos-restore-test -Verify
```
It checks every file's checksum, restores into the test folder, runs all myOS tests there, and checks that project routing works.
Delete `C:\Temp\myos-restore-test` afterwards.

## Recover after a problem
**A. Agents stopped "knowing" myOS** (skills, the guard or instructions are missing). The myOS folder is fine, so re-apply the integration:
```powershell
powershell -ExecutionPolicy Bypass -File C:\projects\myOS\scripts\install.ps1 -SkipVault
```
It is safe to run any time: it backs up first and only re-adds what is missing.

**B. The myOS folder is broken or deleted**
1. Rename the broken folder, e.g. `C:\projects\myOS` -> `C:\projects\myOS-broken`. Don't delete it yet.
2. Copy `scripts\restore.ps1` out of the backup zip, or from the broken folder.
3. Run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\path\to\restore.ps1 -Zip <backup.zip> -Target C:\projects\myOS -Verify -ReinstallAgents -RestoreVaultNotes
   ```
   - `-ReinstallAgents` re-applies the skills, instructions and guard.
   - `-RestoreVaultNotes` puts back myOS notes that are **missing** from your vault. It never overwrites a note.
4. Only if you build knowledge graphs, recreate the Graphify environment with the command the restore prints at the end.
5. Check: `python C:\projects\myOS\scripts\myos.py list`.

**C. A save was interrupted** (power cut, closed window): `python C:\projects\myOS\scripts\myos.py recover`.

**D. Undo myOS's agent integration entirely:** `scripts\uninstall.ps1`. The original files from before installation are in
`C:\projects\myOS\backups\<timestamp>\`.

## Verified 2026-10-15
- Backup: about 150 files, about 600 KB. The secret scan found no hits outside synthetic test fixtures.
- Restore into a scratch folder: all checksums matched, git history was restored, and routing returned the expected project card.
  The full test suite passes in the restored copy, after a test was made path-independent.
- The vault was unchanged by backup and restore. Restore never writes to the vault unless `-RestoreVaultNotes` is given, and
  even then it only adds missing myOS notes.
