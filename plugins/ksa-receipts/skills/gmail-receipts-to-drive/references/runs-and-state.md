# Run modes, checkpoints and the run lock

A usage limit, a closed laptop or a crashed session can stop a run at any moment. Everything here exists so a stop costs at most **one chunk** (one month of mail), and so re-running that chunk is always safe.

## Where state lives

`Receipt archive/_state/` in the shared drive, with **one subfolder per person** (`_state/<their email>/`, created on their first run) for their own state and run log, and the shared run lock at the top of `_state/`. Like `_settings`, the data is in file **titles** (empty Google Docs created with `create_file`, mime `application/vnd.google-apps.document`), because the Drive connector cannot rewrite a file's contents. Files are only ever created (and a person's own files moved or renamed) - never trashed.

**Never edit a teammate's file.** The Drive connector can only rename or move files that the same person created through it; it refuses anyone else's, even in the shared drive. So everything shared - the lock, the yearly reports - works by each person *creating* new files, and readers work out the current state from all of them. `scripts/state.py` reads the titles and prints the exact title to create next; never hand-write a state title.

Per person, in `_state/<email>/`:
- `STATE <email> nightly through <date> | ...` - the newest date covered by a normal/nightly run.
- `STATE <email> backfill plan <oldest>..<newest>` - the months the backfill must cover.
- `STATE <email> backfill <YYYY-MM> started | ...` and `... done | ...` - one pair per month.

- `RUN <YYYY-MM-DD HHMM> <mode> <window> - saved N dup N review N` - a run log: one file per chunk, created at its end, with a short plain-text body (counts, items needing review with Gmail links, problems). It is the person's history of what ran when.

Shared by everyone, in `_state/` itself: lock claims `LOCK claim <email> <time> (<kind>)` and releases `LOCK release <email> <time>` (see below). Old `LOCK free` / `LOCK held by ...` files from plugin 1.1 are still understood and can be left alone.

Within one chat session, also keep `<scratchpad>/run/<chunk>/progress.json` with the phases finished (`scouted`, `classified`, `deduped`, `adjudicated`, `built`, `uploaded`, `reported`) and the paths of their outputs. If the user continues the same chat after a limit, resume from the first unfinished phase. A new session (or a scheduled run) does not have the scratchpad - it simply redoes the interrupted chunk.

## Why a redo is safe

- Uploaded files carry their key; `dedupe_decide.py` recognises a file this same mailbox already filed from this same email (`already_saved_self`) and logs it as SAVED with the existing file instead of uploading again or calling it a duplicate.
- `report_append.py` skips rows already present (same found_by + Gmail id + group).
- Folder creation always searches first.

## The run lock

The yearly report is published as a new version built from the one before, so two people publishing at the same moment would each leave out the other's rows. Every chunk therefore holds the lock while it runs. The lock is **create-only**: nobody renames or deletes a lock file, so it works even though nobody can edit a teammate's file.

1. **Look.** List `_state` (with `createdTime`) and `_state/<email>/`, and run `state.py --titles <both listings> --email <me> status`. Look at `lock`:
   - `free` or `missing` → go to step 2.
   - `held` and `mine` → you already hold it (a resumed chunk): carry on.
   - `held` by someone else → they are running. If the user is present, tell them who and since when, and offer to wait; unattended, wait 10 minutes and look again, up to 3 times, then stop with a note in the final message (the next night catches up). A claim older than 3 hours is stale and `state.py` already ignores it - no one has to clear it.
2. **Claim.** Create an empty Google Doc in `_state/` titled exactly what `state.py --email <me> title lock --lock-kind <nightly|backfill|range>` prints (`LOCK claim <email> <time> (<kind>)`). Note the time in it.
3. **Confirm.** Wait ~10 seconds, list `_state` again (with `createdTime`) and re-run `status`. If `lock.mine` is true, you hold the lock. If not, someone claimed first: release your claim (step 4) and go back to step 1 later. The earliest claim always wins (Drive's `createdTime` settles a same-second race), so two people can never both believe they hold it.
4. **Release** at the end of the chunk, even when the chunk failed: create the title from `state.py --email <me> title lock-release --claim <the time in your claim>`. A backfill releases and claims again between months so other people's nightly runs can slip in.
5. **Tidy your own** (optional, after releasing): `status` lists your old claim and release files under `lock.tidy`. Move them into `_state/<email>/` with `update_file` (`parentId`) if `get_file_metadata` shows `canMoveItemWithinDrive`; otherwise leave them - `state.py` ignores released and stale claims. Never touch anyone else's lock files.

## Modes

### Normal / nightly
Window: from `nightly_from` in `state.py status` (last covered date minus 3 days) to today; if there is no state yet, the last 30 days. If the window is longer than 31 days (a missed week of runs, a long vacation), process it as monthly chunks, oldest first. After the report is published, create the `nightly through <today>` title.

### Range
The user names dates. Process as monthly chunks. Do not write `nightly` or `backfill` state (the dedupe makes overlaps harmless), but do take the lock.

### Backfill
Use the `receipts-backfill` skill. It walks months **newest first** (recent years are most useful soonest), using `state.py ... next-backfill --years 6`:
1. If it returns `create_plan`, create the plan title first. The newest backfill month is the month before the person's first ever run, so backfill and nightly never fight over the same month.
2. Create the month's `started` title, run the full workflow for that month's window, publish the report, then create its `done` title.
3. Loop to the next month until `complete`, the user stops it, or a limit warning appears.

## Chunk discipline

- One chunk = one calendar month (Gmail `after:YYYY/MM/01 before:<next month>/01`). If a month has more than 80 candidates, process it in two halves and publish the report after each half; state still records the whole month.
- Never start a chunk you cannot finish cleanly: when the context is getting long or you are warned about a usage limit, finish the current chunk's report and `done` title, release the lock, and stop with a short note saying where the backfill is and how to continue.
- Publish the report at the end of **every** chunk, then create the chunk's `RUN ...` log file. A report that only exists in the scratchpad is lost when the session ends.
- One adjudicator (Opus) call per chunk at most (plus the small extraction re-check).

## Unattended (scheduled) runs

- Nobody can answer questions: file nothing uncertain; leave `NEEDS REVIEW` rows (see `review-workflow.md`).
- Chrome is often not available. Upload with the Drive connector instead (`create_file` with `base64Content`, `references/drive-and-files.md` Route B step 3). Nightly volumes are small, so this is fine; if a single file is over ~5 MB, build the transaction-record PDF instead and mark the attachment `not captured - original attached in Gmail`.
- Never run a backfill unattended unless the person set up a backfill schedule themselves.
