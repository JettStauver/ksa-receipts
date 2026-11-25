# KSA Receipts

Finds receipts and invoices in Gmail and files one copy of each transaction in the **KSA Business Documents** shared drive (`Receipt archive/<year>/<category>/`), then keeps a yearly Excel report. Several people run it against their own mailboxes into the same folders; duplicate control across mailboxes is the core rule.

Originally built by Ken; v1.0 restructured for team distribution, model tiering, backfill and nightly runs.

## Skills

| Skill | What it does |
|---|---|
| `gmail-receipts-to-drive` | The finder. Searches the running user's Gmail, separates business / personal / home office, files one PDF per transaction, refuses second copies, asks about anything uncertain. |
| `receipts-report` | Appends every processed item to `<YYYY>/Receipts Report <YYYY>.xlsx` (duplicates in color-coded groups) and business hotel stays to `<YYYY>/Hotel Nights <YYYY>.xlsx`. |
| `receipts-backfill` | Works through the last 6 years one month at a time, newest first, checkpointing each month in Drive. "Continue the backfill" picks up where it stopped. |
| `receipts-setup` | First-time setup and health check for a teammate, and sets up their nightly scheduled run. |

## Who does what (models)

| Work | Done by |
|---|---|
| Reading emails, copying out vendor/date/amount/ref | `receipt-scout` agent - **Haiku** |
| Business vs personal, category (cards, addresses, vendor lists, settings) | `classify.py` - **no model** |
| Drive duplicate searches + the duplicate table | `dedupe-checker` agent (**Haiku**) + `dedupe_decide.py` |
| Building each filing PDF and re-reading it to check the amount/date/ref | `receipt-builder` agent - **Haiku** |
| Coordinating, uploads, the report, "medium" judgment calls | skills - **Sonnet** |
| Conflicting evidence, possible duplicates, extraction mismatches | `receipt-adjudicator` - **Opus**, one batched call per chunk |

Haiku never makes a decision that gets filed: it copies facts and flags what it is unsure of. Amounts, dates and refs are checked twice (email, then the finished PDF). Anything unclear moves up a tier, and finally to the user. Nothing is filed on a guess.

## Company data is not in this plugin

The plugin is public. Settings live as file titles in Drive, so only people with access to the shared drive can use them, and changing them never needs a release:

- `Receipt archive/_settings/` - company-wide: business address, vendor mappings, company cards and rules.
- `Receipt archive/_settings/<email>/` - each person's own cards (last 4 only), home-office address and personal rules.

Every run checks for these and creates whatever is missing (asking the person for values when they are there). Examples:

```
CARD 1234 business - company Visa
ADDRESS business <street>, <city>
ADDRESS home-office <street>, <city>
VENDOR Digi-Key -> Cost of Goods Sold
RULE Verizon in-store purchases are personal
```

## Checkpoints and resuming

Run state lives as file titles in `Receipt archive/_state/<email>/`, one folder per person (last nightly date, backfill plan, months started/done, and a `RUN ...` log file per chunk); one shared run lock sits in `_state/`. Work happens in chunks of one month. The report is published and the checkpoint written at the end of every chunk, so a usage limit or closed laptop loses at most the chunk in progress, and redoing it is safe (files already uploaded are recognised; report rows are not doubled). See `skills/gmail-receipts-to-drive/references/runs-and-state.md`.

## Requirements

- A paid Claude plan with Gmail and Google Drive connected.
- Edit access to the KSA Business Documents shared drive.
- Optional: Claude in Chrome (faster uploads of original attachments). Without it, uploads go through the Drive connector.

## Uncertain items

Claude never guesses. Answer by applying a Gmail label - `Receipts/Business`, `Receipts/Personal`, `Receipts/Home Office` or `Receipts/Skip` - and the next run files it; or answer in chat, and Claude offers to save the answer as a rule for everyone.

## Developing

`python3 -I tests/selftest.py` must pass before a release (GitHub runs it on every push). See `RELEASING.md` at the repository root.
