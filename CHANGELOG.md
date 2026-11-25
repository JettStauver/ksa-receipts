# Changelog

## ksa-receipts 1.2.0
The Drive connector can only rename or move files that the same person created through it, so any step that edited a teammate's file failed. Nothing shared is edited in place any more:
- **Run lock is create-only.** Each run creates `LOCK claim <email> <time> (<kind>)` and later `LOCK release <email> <time>`; the earliest open claim holds the lock (Drive's `createdTime` breaks same-second races) and claims go stale after 3 hours. No one renames a lock file. Old `LOCK free` / `LOCK held by ...` files are still read.
- **Yearly reports are numbered versions:** `Receipts Report <YYYY> v<NNN> (<who>).xlsx` and `Hotel Nights <YYYY> v<NNN> (<who>).xlsx`; the highest number is current. Each person tidies only their own older versions (into `_Report history`, or renamed `OLD - ...`). New `report_versions.py`; `report_append.py` / `hotel_nights.py --also` merge two versions published with the same number, so no rows are lost.
- **Duplicate sweep for the same receipt filed from two mailboxes** (e.g. George and Ken both get it and both runs file it before Drive's search index catches up). New `dup_sweep.py`: after upload, it re-searches each new file's Message-ID and ref tokens; the first-created copy is kept and the person who filed the later copy renames theirs `DUPLICATE of <keeper> - ...` and their report row becomes `DUPLICATE - extra copy set aside` in the keeper's group (`supersedes_group`). Never trashed; teammates' extras are left for them.
- **A teammate's invoice is no longer renamed** when its receipt arrives (`rename_invoice` in `dedupe_decide.py`); the receipt carries `PAYS_GROUP` and the report shows the pair as one group.

## ksa-receipts 1.1.0
From the first real backfill month (October 2026, test archive) and a re-measure:
- **Builder batches 5 receipts per agent** (was 1). Re-measured: about 20k tokens per receipt, down from about 100k; PDF building had been 60% of a month's cost.
- **No more dependence on raw emails.** Attachments now come through Gmail's `download_gmail_attachment` tool (byte-for-byte, straight to disk). Body-only receipts get a summary page plus the email's text from a plain-text read, re-reading the HTML when the amounts are only there (Steam, Best Buy, Epic). Before, 5 of 7 PDFs were missing their email copy, because claude.ai has no transcript files for `raw_from_transcript.py`. A builder job can no longer end with no file.
- The builder fills a missing total/date/ref from the email (listed in `filled`, then re-checked by the adjudicator before upload).
- **Home-office address only counts for household bills** (utilities, internet, lawn, home repairs, or a matching service address). A Steam or Apple purchase billed to the home address is no longer pushed toward Home Office.
- **File names:** web domains, parentheticals and "via ..." are dropped from vendor names (`The.Den`, not `The.Den.thedenwaco.prospectportal`; `Amazon.com` → `Amazon`). With no readable transaction date, the email date is used instead of `000000`.
- Refund record PDFs are labelled REFUND.

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
