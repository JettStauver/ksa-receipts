---
name: gmail-receipts-to-drive
description: Searches the user's Gmail for receipts and invoices, separates business from personal, and saves exactly one PDF per transaction into the KSA Business Documents shared drive by year and expense category (the "Receipt archive" folder). Use when the user says "file my receipts", "find receipts in my email", "save receipts to Drive", "run the receipt finder", "scan Gmail for invoices", or runs /gmail-receipts-to-drive.
model: sonnet
---

# Gmail receipts to Drive

File every receipt and invoice found in the running user's Gmail into Google Drive, one copy per transaction, so KSA has audit-ready records. Several team members run this against their own mailboxes into the same folders, so duplicate control is the most important rule in this skill.

## How the work is split (read first)

This run is the **coordinator (Sonnet)**. It never reads email bodies or raw emails itself and keeps its own context small. Work goes to the cheapest step that can do it *correctly*:

| Step | Who | Why |
|---|---|---|
| Find candidate emails (search queries, ids only) | coordinator, `MINIMAL` / `METADATA_ONLY` | cheap, needs the merged id list |
| Read each email and copy out the facts | `receipt-scout` agents (**Haiku**), 8 emails each | pure extraction |
| Business/personal + category from cards, addresses, vendor lists, settings | `classify.py` (**no model**) | rule-based; has one right answer |
| Items `classify.py` marks `medium` | coordinator | one missing piece; needs a little judgment |
| Duplicate search + fixed duplicate table | `dedupe-checker` agents (**Haiku**) + `dedupe_decide.py` | searches + rules |
| Everything still unclear (`low`, `adjudicate`, extraction mismatches) | `receipt-adjudicator` (**Opus**), **one call per run** | the only real judgment calls |
| Build each filing PDF and check it against the extraction | `receipt-builder` agents (**Haiku**), 5 receipts each | scripts + a text check |
| Upload, descriptions, report, final check | coordinator + `receipts-report` | needs the whole run's state |

Quality rules that make this safe:
- Haiku only **copies** facts; scripts and Opus make the decisions. Haiku marks anything it is unsure of in `uncertain`, and those fields never get filed on Haiku's word alone.
- Every filed amount/date/ref is checked twice: once by the scout, once by `receipt-builder` reading the finished PDF. If they disagree, the item goes to the adjudicator, not the archive.
- No step ever downgrades "unclear" to "new" or "business". Unclear goes up a tier (Haiku → script → Sonnet → Opus → user).

**Agent types:** `ksa-receipts:receipt-scout`, `ksa-receipts:dedupe-checker`, `ksa-receipts:receipt-builder`, `ksa-receipts:receipt-adjudicator`. If a plugin agent type is not available, use `subagent_type: "general-purpose"` with the matching `model` (`haiku` / `haiku` / `haiku` / `opus`) and paste the body of the agent's file from `agents/` above the job in the prompt. Launch up to 5 agents in one message so they run in parallel.

## Fixed settings

| Setting | Value |
|---|---|
| Shared drive | KSA Business Documents (drive id `0AFwI_QSQxLp0Uk9PVA`) |
| Destination root | `Receipt archive` at the shared drive root (id `1NvMJZTXurJaImGjo8ORBSWxH782nIVaX`) |
| Settings | `Receipt archive/_settings/` (company-wide) + `_settings/<email>/` (each person's cards, home-office address, rules) - see `references/dedupe.md` section 6 |
| State and run log | `Receipt archive/_state/<email>/` per person; shared run lock in `_state/` - see `references/runs-and-state.md` |
| Layout | `Receipt archive/<YYYY>/<Category>/` plus `<YYYY>/Personal/` and `<YYYY>/Home Office - Indirect/` |
| First-run search window | last 30 days |
| Report (one per year) | `Receipt archive/<YYYY>/Receipts Report <YYYY> v<NNN> (<who>).xlsx` - highest version is current (built by the `receipts-report` skill) |
| Hotel nights (one per year) | `Receipt archive/<YYYY>/Hotel Nights <YYYY>.xlsx` |

Company- and person-specific facts (addresses, cards) live only in `_settings`, never in this plugin, because the plugin is published publicly. Access to the shared drive is what gates the data.

**Do not open, search, read or write `@KSA Scanned Documents`.** If the destination root cannot be opened by its id, stop: the user either lacks access to the KSA Business Documents shared drive (tell them to ask for it) or the folder moved; do not create a replacement.

## Tools

- Gmail connector: in this conversation use only `search_threads` and `get_message`/`get_thread` with `MINIMAL` or `METADATA_ONLY`. Never `PLAIN_TEXT` bodies here except to look at one item a user asks about, and **never `RAW`**.
- Google Drive connector: `search_files`, `create_file`, `update_file`, `copy_file`, `get_file_metadata`, `download_file_content`.
- Claude in Chrome: uploads staged files into Drive (`references/drive-and-files.md`, "Upload through Drive in Chrome"). Load the `chrome-browser` skill first. If Chrome is not connected, use the fallback in that file and say so in the final message.
- Bash + Python for `${CLAUDE_PLUGIN_ROOT}/scripts/` (if the variable is not set, locate it with `find / -path "*ksa-receipts/scripts/receipt_key.py" 2>/dev/null`). Work in the session scratchpad. Run scripts with `python3 -I`.
- Load deferred tools with ToolSearch first, in one call.

Read `references/categories.md` and `references/review-workflow.md` before the first decision of a run; `references/dedupe.md` and `references/drive-and-files.md` before the first write.

## Workflow

Create a task list: set up (state + lock) → find → scout → classify → dedupe → adjudicate → build → upload → report → check.

### 1. Set up

1. Identify the running user (their email). Record it as `found_by`. Decide the mode: **nightly/normal** (default), **range** (the user named dates) or **backfill** (use the `receipts-backfill` skill, which calls this workflow once per month). Read `references/runs-and-state.md`.
2. **Make sure this person is set up - add whatever is missing.** Open `Receipt archive` by id, then check and create (search first, never twins; folders and settings are empty Google Docs/folders created with `create_file`):
   - `_settings/` and `_settings/<found_by>/` (their own settings folder).
   - `_state/`, `_state/<found_by>/` (their own state and run log), (the run lock needs no set-up file: it is made of claim and release files, `references/runs-and-state.md`).
   Then list `_settings` (company), `_settings/<found_by>/` (theirs) and the other people's subfolders (titles only), save each listing, and run
   `python3 -I <scripts>/settings.py --shared shared.json --mine mine.json --others <other listings...> --out settings.json`.
   For each entry in `missing`:
   - **User present:** ask for it in one short batch with AskUserQuestion before the run starts ("What's your home-office address? Bills sent there are filed under Home Office - Indirect." - offer "I don't have one" → `ADDRESS home-office none`; "Which cards do you use for KSA purchases? Last 4 digits only."). Create each answer as a setting in their own folder (the business address goes in the company `_settings/`). Never ask for or store more than the last 4 digits of a card.
   - **Unattended:** create nothing that needs a value; carry on (classification falls back to asking via `NEEDS REVIEW`) and list what is missing at the top of the final message.
   Also mention any `unparsed` titles or `conflicts`. Check the Gmail answer labels (`Receipts/Business`, `Receipts/Personal`, `Receipts/Home Office`, `Receipts/Skip`) with `list_labels`; create any that are missing (creating labels is fine; this skill never applies labels to emails).
3. List `_state` and `_state/<found_by>/` (titles only) and run `python3 -I <scripts>/state.py --titles <both listings> --email <found_by> status`. Claim the run lock as described in `runs-and-state.md` (create a claim, confirm it is the earliest; never rename a lock file).
4. Search window: nightly/normal → `nightly_from` from the status (or the last 30 days if there is none); range → the user's dates; backfill → the month given by `receipts-backfill`. Windows longer than 31 days are processed as monthly chunks, each finished (report published, state written) before the next starts.
5. Download the current report(s) for the years in the window and export their rows to `report_rows.json` (`openpyxl`, one object per row with the report's snake_case keys) for the dedupe step. Start `<scratchpad>/run/<chunk>/progress.json` and update it after each phase.

### 2. Find candidates (ids only)

First the user's decisions: emails carrying `Receipts/Business`, `Receipts/Personal`, `Receipts/Home Office` or `Receipts/Skip`, with the window and also without one for any email still `NEEDS REVIEW` in the report (`references/review-workflow.md`). Note each one's label: it is final.

Then run these searches with the window (`after:YYYY/MM/DD`), page through all results, and merge message ids:

- `(receipt OR "order confirmation" OR "payment received" OR "payment confirmation" OR "thank you for your order" OR "your order")`
- `(invoice OR "amount due" OR "bill is ready" OR statement) -in:sent`
- `category:purchases` and `category:reservations`
- `(filename:pdf OR filename:jpg OR filename:png) (receipt OR invoice OR order)`
- `subject:(fwd receipt) OR subject:(fw receipt)`

Drop obvious non-receipts from the search snippets/subjects alone only when certain (newsletters, "your package was delivered" with no amount); everything else goes to the scouts.

### 3. Scout (Haiku)

Split the ids into batches of 20 (each agent has a fixed start-up cost, so fewer, larger batches are cheaper; use 8-10 only when there are fewer than 20) and launch `receipt-scout` agents (job format in `agents/receipt-scout.md`; `out_path` = `<scratchpad>/scout/<batch_id>.json`). Keep only each agent's one-line reply. Merge all batch files into `records.json`.

### 4. Classify (script, then Sonnet for medium)

`python3 -I <scripts>/classify.py --records records.json --settings settings.json --out classified.json`

Routes:
- `file` → decided. Use the proposal as is.
- `skip` → not a receipt; report row only if it carried a user label (`SKIPPED (user label)`).
- `review` → order acknowledgement / price-less slip: `NEEDS REVIEW` row ("no proof of payment"), not filed.
- `sonnet` → you decide, reading only that record's JSON, its `signals`, any `rules_to_check`, and `references/categories.md`. Apply the category rules (travel meals → Meals & Entertainment; monthly phone plan → Business/Software & Internet & IT Services; parts for a customer repair → Cost of Goods Sold; etc.). If after that you still see two reasonable answers, send it to the adjudicator - do not pick one.
- `adjudicate` → straight to the adjudicator (evidence conflicts).
- Before asking anything, if several items share one unknown card, ask that card once (user present) and re-run `classify.py`: one `CARD` setting usually settles them all without Opus.

Any record with a key field in `uncertain` (total, transaction_date, vendor) goes to the adjudicator as an `extraction` issue after the build step (step 7), so it can be checked against the PDF text.

### 5. Dedupe (Haiku + script)

For every record that will be filed (or might be), find or create the target year/category folder lazily (search first, `references/drive-and-files.md` "Folder creation") so its id can be passed as `target_folder_id`; for items still awaiting a decision pass `null`. Launch `dedupe-checker` agents with batches of up to 10 items (format in `agents/dedupe-checker.md`). Outcomes from `dedupe_decide.py`:

- `new` → save.
- `new_near_match` → save; put the reason in the report Notes.
- `duplicate` → do not save; report row `DUPLICATE - not saved` with the existing file's `group_id` and `duplicate_of`.
- `receipt_for_invoice` → save the receipt in the invoice's group and add `PAYS_GROUP: <group_id>` to the receipt's own description. Only if `rename_invoice` is true (this mailbox filed the invoice) also rename the invoice ` (paid - see receipt)` and add `PAID_BY_GROUP` to its description. A teammate's invoice is left exactly as it is: the connector refuses to edit it, and the report already shows the pair as one group.
- `already_saved_self` → this mailbox already filed this email in a run that stopped early: no upload; report row `SAVED` (or the matching status) with the existing file's name, link and group.
- `adjudicate` → to the adjudicator.

Also check the run against itself: two records in this run with the same `group_id`, ref, or RFC822 Message-ID are one transaction - keep the receipt (over the invoice) or the first one, and log the other as a duplicate.

### 6. Adjudicate (Opus, once)

Collect every item routed to the adjudicator from steps 4 and 5 into one job: `categories` (the text of `references/categories.md`), `settings` (settings.json), `items`, `user_present`. Launch **one** `receipt-adjudicator` agent. If there are more than 40 items, send them in batches of 40, still one agent at a time. Skip this step entirely when nothing needs it.

Apply `decide` answers. Collect `ask` answers for step 9 - those items are not built or filed yet.

### 7. Build (Haiku) and cross-check

Decide every file name first (`receipt_key.py`'s `file_name_stem`; pass `email_date` too, so a receipt with no readable transaction date is named by its email date and the report Notes say `named by email date`; `[INVOICE ]Vendor.Name MMDDYY[ short-detail].pdf` - see below), then launch `receipt-builder` agents with **5 jobs each** (each agent has a large fixed start-up cost, so never one agent per receipt), up to 5 agents at a time (format and modes in `agents/receipt-builder.md`; `mode: "attachment"` when the scout found a `receipt_attachment`, else `mode: "record"`; always pass the `record` fields from `references/drive-and-files.md`, Route C, since they are also the fallback). Keep only each reply line, then read the batch's `results.json`.

Cross-check each reply:
- `ok: false` → retry once; then build the record PDF without the original and set `attachment_status` = "not captured - original attached in Gmail".
- `problems` not empty, `filled` not empty (the builder found a total/date/ref the scout missed), or `found` disagrees with the record on total, date or ref, or the record had `uncertain` key fields → do **not** upload yet. Send these as `extraction` items in a second (small) adjudicator call with `builder_found`. Apply its answer; if it asks, the item waits for the user.

### 8. Upload

Upload the staged files folder by folder (`references/drive-and-files.md`, "Upload through Drive in Chrome"), get the new file ids, compare sizes, and write each file's description (the `receipt_key.py` block). Then run the duplicate sweep (`references/dedupe.md`, "Same receipt in two mailboxes") before the report. Hotel stays paid with business funds: add them to the Hotel Nights workbook (see the `receipts-report` skill) using the scout's `hotel` fields; skip stays already listed.

**File name:** `[INVOICE |REFUND ]Vendor.Name MMDDYY[ short-detail].pdf` - refunds go in the same category folder as the purchase they reverse, with the `REFUND ` prefix and a note naming the original file; vendor words joined with dots (e.g. `DFW.Parking 092426.pdf`, `USPS 102726.pdf`), date = transaction date. Add a short detail (order number tail, route, item) only when needed to keep names distinct. Never put card numbers in names.

### 9. Questions for the user

Follow `references/review-workflow.md`. If the user is present, ask the adjudicator's `ask` items in one batch (AskUserQuestion, up to 4 per call, grouping similar ones; use its `question` and `options`), and for each answer ask whether to apply it to future emails like it (yes → create the `RULE`/`CARD`/`VENDOR` setting, using `rule_suggestion` when it fits). Then build, dedupe-check (the answer may change the folder) and upload those items the same way. If unattended, file nothing uncertain; leave `NEEDS REVIEW` rows with the question and Gmail link. Put any `NEEDS REVIEW` older than 7 days at the top of the final summary. Never apply or remove `Receipts/...` labels yourself.

### 10. Report and finish

1. Pass every processed transaction - saved, duplicate, needs review, personal, skipped-by-label - plus the sweep's `report_row`s to the `receipts-report` skill.
2. Check the work: `get_file_metadata` on two or three saved files (folder, name, description); confirm each year's report row count grew by the number of new rows.
3. Write state and release the lock: nightly/normal → create the title from `state.py --email <found_by> title nightly --through <window end> --saved N --dup N --review N`; backfill → `receipts-backfill` writes the month's `done` title. Then release the lock by creating its `LOCK release ...` file (also when the run failed part-way).
4. Final message: counts (saved business / personal / home office / invoices / duplicates skipped / extra copies set aside by the sweep / needs review), any teammate extras the sweep saw (one line), how many items needed Sonnet and Opus, open questions, and a link to `Receipt archive`. Do not list every file.

## Never

- Open, search, read or write `@KSA Scanned Documents`.
- Save a second copy of a transaction, even if the second copy looks nicer.
- Rename, move, re-describe or trash a file a teammate filed or created (the connector refuses it anyway). Change only your own files; everything shared works by creating new files.
- File anything whose amount, date or business/personal status rests only on a guess.
- Put full card numbers, bank account numbers or passwords in files, names, descriptions, settings or the report.
- Trash or delete any Drive file. Renames and moves within `Receipt archive` are allowed.
- Send, reply to, label or archive emails.
