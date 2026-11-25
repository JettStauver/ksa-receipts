# Changelog

## ksa-receipts 1.0.0
- **Per-person settings and logs:** `_settings/<email>/` (own cards, home-office address, rules) on top of company `_settings/`; `_state/<email>/` for each person's state and a `RUN ...` log per chunk. Every run creates missing folders, the lock and the Gmail answer labels, and asks for missing values (unattended runs list them instead).
- **Team distribution:** published as a public plugin marketplace; teammates add it on claude.ai and receive updates automatically. Company facts (addresses, cards) moved out of the plugin into `Receipt archive/_settings` (`ADDRESS business ...`, `ADDRESS home-office ...`, new `VENDOR ... -> ...` mappings).
- **Model tiering:** new `receipt-scout` (Haiku) reads emails; `receipt-builder` moved to Haiku and now reports what the finished PDF says; new `dedupe-checker` (Haiku); new `receipt-adjudicator` (Opus), one batched call per chunk for conflicting evidence only. Coordinator stays on Sonnet and no longer reads email bodies.
- **Deterministic decisions:** new `classify.py` (cards, addresses, vendor hints, settings → proposal + confidence + route) and `dedupe_decide.py` (the duplicate table as code). Unclear cases always escalate; none default to "new" or "business".
- **Double-checked extraction:** amounts/dates/refs compared between the email and the built PDF; mismatches go to the adjudicator before upload.
- **Checkpoints:** `_state` folder with per-person nightly/backfill state and a shared run lock (`state.py`). Work happens in monthly chunks; the report is published every chunk.
- **Resume-safe:** a file already filed from the same email by the same mailbox is recognised (`already_saved_self`) and its report row restored, instead of being logged as a duplicate.
- **New skills:** `receipts-backfill` (6 years, newest first, resumable) and `receipts-setup` (onboarding, health check, nightly scheduled task).
- From the first benchmark (BENCHMARK.md): `refund`/`other` kinds, FULL_CONTENT fallback for link-only emails, no-evidence items go to Sonnet before Opus, shared unknown cards asked once, scout batches of 20, `REFUND ` file-name prefix.
- Self-test (`tests/selftest.py`) and a GitHub check on every push.
- Fixed: `dedupe.md` showed tokens with hyphens (`KSAREF-...`) that `receipt_key.py` never writes.

## ksa-receipts 0.11.0 and earlier
See Ken's notes in the 0.11 README: fixed category list, Receipt archive destination, Sonnet helper agents.
