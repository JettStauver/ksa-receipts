---
name: receipts-backfill
description: Works through past years of the user's Gmail one month at a time (newest first, default 6 years) and files the receipts with the gmail-receipts-to-drive workflow, checkpointing each month in Drive so a usage limit or closed session loses at most one month. Use when the user says "backfill receipts", "file old receipts", "do the backlog", "continue the backfill", "how far is the backfill", or runs /receipts-backfill.
model: sonnet
---

# Receipts backfill

Fill the archive from past mail without ever losing more than one month of work. The real filing is the `gmail-receipts-to-drive` workflow; this skill only picks months, writes checkpoints, and decides when to stop.

Read `../gmail-receipts-to-drive/references/runs-and-state.md` first. Scripts are in `${CLAUDE_PLUGIN_ROOT}/scripts/`.

## Status only

If the user asks how far it is ("where's the backfill at?"), list `Receipt archive/_state/<email>/`, run `state.py --titles state_titles.json --email <me> status`, and answer in two lines: months done of the plan, the oldest month reached, any interrupted month, and whether someone holds the lock. Stop there.

## Loop

1. Identify the user (`found_by`). Do step 1.2 of `gmail-receipts-to-drive` once (it adds any missing folders/settings and asks for missing values), load `references/categories.md` and `settings.json`, and reuse them for every month.
2. List `_state` and `_state/<email>/` and run `state.py --titles state_titles.json --email <me> next-backfill --years <N>` (N = 6 unless the user says otherwise).
   - `complete` → tell the user the backfill is done and stop.
   - `create_plan` → before the first month, find this person's first nightly/normal run (oldest `nightly through` title, or their oldest report `Run date`); the plan's newest month is the month before that, if earlier than the suggested one. Create the plan title (`state.py ... title plan --oldest .. --newest ..`).
   - `interrupted - redo` → say so once ("Picking up 2023-04, which was cut off last time").
3. Take the lock (`runs-and-state.md`). Create the `started` title for the month.
4. Run `gmail-receipts-to-drive` steps 2-10 for that month's window (`window.gmail_query_suffix`), in **backfill mode**:
   - The user is usually present for the first months: ask the adjudicator's questions in one batch per month and offer to save rules - early rules make later months mostly automatic.
   - When the user is away or says "don't ask", leave `NEEDS REVIEW` rows instead and carry on.
   - Old mail often has expired links and missing images - the transaction-record PDF handles this; do not chase links.
5. After the month's report is published, create its `done` title (`state.py ... title backfill-done --month <YYYY-MM> --saved N --dup N --review N`) and release the lock.
6. Send the user a one-line progress note (`2024-08 done: 37 saved, 5 duplicates, 2 to review - 27 of 72 months`). Then go back to step 2.

## When to stop

Stop **between** months - never in the middle of one - when any of these happen, after finishing the current month cleanly (report published, `done` written, lock released):
- the user asks to stop;
- a usage-limit warning appears, or the conversation is getting long (roughly 6 months in one session is a good maximum; quality drops in very long sessions);
- three months in a row needed a question the user hasn't answered.

Then tell the user exactly how to continue: "Say **continue the backfill** (here or in a new chat) - it picks up at <next month>."

## Scheduled backfill (optional)

If the user wants it to run on its own, offer a scheduled task (see the `receipts-setup` skill) that runs "continue the backfill, at most 3 months, unattended" a few times a night, at times that do not overlap the nightly run. Unattended months leave questions as `NEEDS REVIEW`.
