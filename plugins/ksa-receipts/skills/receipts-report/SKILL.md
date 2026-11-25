---
name: receipts-report
description: Creates or appends the yearly "Receipts Report YYYY.xlsx" spreadsheet (and the yearly Hotel Nights workbook) inside each year folder of Receipt archive, listing every receipt and invoice found, with duplicates on adjacent rows in color-coded groups. Use after each gmail-receipts-to-drive run, or when the user says "update the receipts report", "add these receipts to the spreadsheet", "show the receipts report", or runs /receipts-report.
model: sonnet
---

# Receipts report

Maintain one running Excel report per year of every transaction the receipt finder has processed, for every team member. Each run appends new rows to the report for the year each transaction happened in; nothing already in a report is removed.

## Location

Reports live in the year folder, next to that year's category folders:

- Year folder: `Receipt archive/<YYYY>/` in the KSA Business Documents shared drive (id `0AFwI_QSQxLp0Uk9PVA`; `Receipt archive` folder id `1NvMJZTXurJaImGjo8ORBSWxH782nIVaX`).
- Receipts report: `<YYYY>/Receipts Report <YYYY> v<NNN> (<who>).xlsx` - the **highest version number is the current report**. `<who>` is the publisher's email before the @. (An old `Receipts Report <YYYY>.xlsx` with no number counts as v000.)
- Hotel nights: `<YYYY>/Hotel Nights <YYYY> v<NNN> (<who>).xlsx`, versioned the same way.
- Earlier versions: `<YYYY>/_Report history/`, or left in the year folder as `OLD - ...`.

The year is the **transaction** year, not the run date or email date. A run that finds transactions from two years updates both years' reports; if a year folder or its reports do not exist yet, create them (search first so two users never make twin files).

The Drive connector cannot overwrite a file's contents, and it can only rename or move files that the same person created through it. So a report is never replaced or renamed in place: each update uploads a **new numbered version** built from the current one, and each person tidies only their **own** older versions. A teammate's older version stays in the year folder until their next run tidies it; the higher number is always the one to open. Never trash old versions.

## Input

A list of row objects from the current run (one per email/document processed, including duplicates and items needing review). Keys - see the docstring of `${CLAUDE_PLUGIN_ROOT}/scripts/report_append.py`:

`group_id, status, doc_type, transaction_date, vendor, total, business_personal, category, ref, card_last4, file_name, drive_url, duplicate_of, found_by, email_from, email_date, gmail_url, attachment_status, notes, gmail_message_id`

Status values: `SAVED`, `SAVED - INVOICE`, `PERSONAL - SAVED`, `DUPLICATE - not saved`, `NEEDS REVIEW`. `business_personal` is one of `Business`, `Personal`, `Home office (indirect)`. A duplicate row carries the `group_id` of the file that was kept. Only card last-4 digits ever appear.

If invoked on its own with no run data, open and summarize the current report instead (rows, latest run per person, open NEEDS REVIEW items).

## Steps

1. **Split the run by year.** Write all of the run's rows to `rows.json` and run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/report_append.py --rows rows.json --list-years`. A row's year is the transaction date of the copy that was filed in its group (so a duplicate stays with its receipt), else its own transaction date, else its email date. Do steps 2-5 once per year listed.
   Then **find that year's report**: list the year folder and its `_Report history` (search `parentId`, with `createdTime`; save each listing as JSON) and run
   `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/report_versions.py --year-folder year.json --history history.json --email <found_by> --year <YYYY> --kind report`.
   It gives `current` (the file to append to), `next_title`, any `conflict` (two people published the same number), and `tidy_mine`.
2. **Get the previous version (if any).** `download_file_content` with `current`'s id. If there is a `conflict`, download those versions too (`conflict1.xlsx`, ...).
   - If the app saved the result to a file, run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/b64_to_file.py <saved path> --out prev.xlsx --check-xlsx`.
   - If the base64 came back inline, write it to a scratch file exactly as returned and run the same command.
   - Note `data_rows`. If decoding or the check fails, stop and tell the user; do not build a new report from nothing when one already exists.
3. **Write the new rows** to `rows.json` in the scratchpad and run:
   `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/report_append.py --report prev.xlsx --rows rows.json --year <YYYY> --out new.xlsx`
   (omit `--report` on the first run of that year; add `--also conflict1.xlsx` for each conflicting version so no one's rows are lost). `--year` keeps only that year's rows. The script keeps existing order, slots duplicates directly under their group, colors multi-row groups, italicizes duplicate rows, skips rows already present from an overlapping search window, and replaces resolved NEEDS REVIEW rows.
4. **Sanity check.** `total_rows` must be at least the previous `data_rows` minus `review_rows_resolved`. Open `new.xlsx` with openpyxl and confirm the header row and that each group's rows are contiguous. If anything is off, stop and report it.
5. **Publish the new version** (order matters so a report always exists):
   1. `base64 -w0 new.xlsx` and upload with `create_file`: title = `next_title` exactly, parent = the year folder, `contentMimeType` = `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `disableConversionToGoogleType: true`. Confirm the upload's size matches `new.xlsx`.
   2. Tidy **only your own** older versions (`tidy_mine`): find or create `<YYYY>/_Report history` (search first) and move each there with `update_file` (`parentId`) if `get_file_metadata` shows `canMoveItemWithinDrive`; otherwise rename it to its `old_title` (`OLD - ...`). If Drive refuses either, leave it and say so. Never touch `others_superseded` - those are teammates' files, which they tidy themselves.
5b. Publish at the end of **every** chunk (each month of a backfill, each nightly run) while the coordinator holds the run lock (`../gmail-receipts-to-drive/references/runs-and-state.md`). Rows that only exist in the scratchpad are lost when the session ends.
6. **Tell the user** in two or three lines: rows added per year, duplicates logged, NEEDS REVIEW count, and the report link(s). The run lock prevents two people publishing at once; if two files ever carry the same version number, the next publish merges them automatically (`conflict` + `--also`).

## Hotel Nights workbook

Business-paid hotel stays are also tallied in `<YYYY>/Hotel Nights <YYYY>.xlsx` so total nights on the road can be reported for each year. Each stay row: check-in, check-out, nights, city, state, hotel, trip/purpose, total paid, card last 4, confirmation, receipt file, Drive link, found by. A "Totals" sheet sums nights by month and year.

Update it the same way as the report: `report_versions.py ... --kind nights` for the current version and next title, download it (and any `conflict`, passed with `--also`), append, upload as `next_title`, and tidy only your own older versions:
`python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/hotel_nights.py --rows stays.json --list-years`, then for each year
`python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/hotel_nights.py --report prev_nights.xlsx --rows stays.json --year <YYYY> --out nights.xlsx`
Nights count in the year they are slept. A stay across New Year (e.g. Dec 30 - Jan 2) appears in both years' workbooks with that year's nights; its amount is shown only in the check-in year.
Stays already listed (same confirmation number, or same hotel + check-in) are skipped. Only include stays paid with business funds; read the night count from the folio rather than guessing from dates when the folio shows it.

## No silent blanks

Each transaction's amount is counted once so the Total column can be summed: duplicate rows show `(duplicate - not counted)` instead of an amount, and an invoice whose receipt is in the same group shows `(paid - counted on receipt row)` (the script does this). Never leave a key field empty. Duplicate rows inherit date, category and type from the receipt they matched; any date, amount or vendor that still cannot be read is written as `UNREADABLE - check source` (the script does this automatically, including for rows already in the report).

## Formatting rules (already applied by the script)

- Groups with more than one row share a fill color and a heavy top border; colors cycle through a light palette.
- Duplicate rows are italic grey; the kept row's Status is bold.
- Header row frozen, filters on, hidden Gmail message id column used for idempotency.
- A "How to read" sheet explains the colors and statuses.

Do not hand-edit cell formatting through other tools; change `report_append.py` instead so every version stays consistent.
