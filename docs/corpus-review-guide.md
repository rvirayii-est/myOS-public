# Reviewing and approving knowledge corpora (owner only)

Building a graph sends the listed notes to the extraction model's provider. Nothing is sent until you approve,
and only you can approve, in your own interactive terminal.

## Guided review
```powershell
powershell -ExecutionPolicy Bypass -File scripts\review-corpora.ps1            # every pending corpus
powershell -ExecutionPolicy Bypass -File scripts\review-corpora.ps1 -Only lumen-ledger
```
For each corpus that is not approved, the script:
1. refreshes the transmission preview locally (nothing is sent);
2. shows how many files would be sent, to which provider, what was excluded and why, and which included files are
   flagged for your judgement (emails, IPs, phone numbers, credential words, production hosts; values are never shown);
3. lets you **[a]pprove** (you type the corpus name to confirm), **[s]kip**, **[o]pen** the full preview, or **[q]uit**;
4. after an approval, asks whether to build now. That is the moment data is sent.

## What to check before approving
- Open `data\graph\<corpus>\TRANSMISSION-PREVIEW.md` and read the file list, not just the counts.
- For every flagged file: is the flagged content safe to send? If not, add the file to the corpus `exclude` list in
  `config\myos.json` and re-run the plan.
- Order: start with the least sensitive corpus; leave live-client material for last.

## After approval
Any change to an included file (a new session note, an edit) voids the approval for that corpus. `myos graph list` then shows
`RE-APPROVAL needed` and names the changed files; review them and approve again before `myos graph update <corpus>`.
