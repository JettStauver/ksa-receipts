# Uncertain items: review workflow

Goal: the user decides in Gmail or in one batch of questions, each decision is made only once, and nothing is filed on a guess.

## Gmail labels (the user's answer)

| Label | Meaning |
|---|---|
| `Receipts/Business` | File as business. Category still comes from `categories.md`; ask only if the category is unclear. |
| `Receipts/Personal` | File in `<YYYY>/Personal/`. |
| `Receipts/Home Office` | File in `<YYYY>/Home Office - Indirect/`. |
| `Receipts/Skip` | Not a receipt to keep. Do not file; record as `SKIPPED (user label)` in the report. |

Labels exist per mailbox. If a label is missing in the running user's mailbox, do not create it unless that user asks (the `receipts-setup` skill offers to); fall back to asking in chat.

A label always overrides Claude's own classification and any rule. Claude never applies, removes, or changes these labels itself - they are the user's decisions. Claude only reads them.

## Each run

1. **Read labeled emails first.** Before the normal search, run `label:receipts-business OR label:receipts-personal OR label:receipts-home-office OR label:receipts-skip` with the run's date window **and** without a window for any email still listed as `NEEDS REVIEW` in the report. File or skip them per the label (dedupe still applies). A resolved item replaces its `NEEDS REVIEW` row in the report.
2. **Classify the rest** using `_settings` rules, cards and `categories.md`.
3. **Collect what is still uncertain** - business vs personal vs home office, category, receipt vs invoice, possible duplicate, unreadable key field.
4. **If the user is in the chat:** ask the `receipt-adjudicator`'s `ask` items at the end of the run in one batch with AskUserQuestion (up to 4 questions per call; group similar items). For each item offer the destinations that make sense, and add a second question or option: "Apply to future emails like this?"
   - Yes → create a `RULE` (or `CARD` / `VENDOR`) setting - in the person's own `_settings/<email>/` unless they say it is for everyone (`dedupe.md` section 6) - worded narrowly enough to be safe (vendor + kind of charge, e.g. "Verizon in-store purchases are personal"; never a whole vendor when the user's answer was about one kind of charge).
   - No → a one-time decision; file it and move on.
5. **If the user is not present (scheduled run):** file nothing uncertain. Leave the row as `NEEDS REVIEW` with a plain question in Notes and the Gmail link, and tell the user in the final message to label those emails or answer next time.

## Weekly sweep

At the start of each run, list `NEEDS REVIEW` rows older than 7 days (by Email date) and put them at the top of the final summary as "Still waiting on you" with their Gmail links. Never auto-decide them.

## Report wording

- Status for user-labeled items: the normal status (`SAVED`, `PERSONAL - SAVED`, etc.) with Notes `Decided by Gmail label <label>` or `Decided in chat <date>`.
- Status for skips: `SKIPPED (user label)` - no file.
