# Duplicate control

Three people run this skill on their own mailboxes into one shared folder tree. The same receipt often reaches more than one mailbox (CC'd, forwarded to ksa@, forwarded from junk@, or sent once as an invoice and again as a receipt). Exactly one file per transaction may exist in the destination tree.

The Google Drive connector cannot rewrite a file's contents, so there is no shared ledger file. Instead, **every saved receipt carries its own key in its Drive description**, and Drive full-text search (which indexes descriptions and PDF text) finds it.

## 1. Build the transaction key

Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/receipt_key.py` with the extracted fields as JSON on stdin:

```json
{"vendor": "Anthropic, PBC", "transaction_date": "2026-10-23", "total": "21.00",
 "ref": "2377-9435-9427", "card_last4": "1234", "doc_type": "receipt",
 "rfc822_message_id": "<abc@mail.anthropic.com>", "gmail_message_id": "1a16bb471519070c",
 "found_by": "someone@ksanalytical.com", "items": "Claude Pro Oct 23-Nov 23"}
```

It prints the normalized vendor token, amount token, reference tokens, a `group_id`, the search queries to run, and the exact description block to store. Use its output; do not hand-normalize.

`ref` is the strongest identifier available: order number, invoice number, receipt number, confirmation number, booking number, or tracking number for shipping charges. Leave empty if none.

## 2. Search for an existing copy

This step and the decision below are done by `dedupe-checker` agents with `scripts/dedupe_decide.py`; the coordinator only reads their results. Run every query the script prints against Drive, scoped to the `Receipt archive` tree (search with `fullText contains '...'` and check that each hit's parent chain is inside the destination root). Typical queries:

1. `fullText contains 'KSAREF<ref token>'` and `fullText contains '<raw ref>'` (the second also catches the number printed inside an uploaded PDF).
2. `fullText contains 'KSAMSG<rfc822 token>'` - the identical email delivered to another team member has the same RFC822 Message-ID.
3. `fullText contains 'KSAVA<VENDORTOKEN>X<cents>'` - same vendor and amount, any date.

Also scan the current report (rows with the same vendor token and amount) - it holds duplicates and review items that have no Drive file.

Note: a file uploaded in the last few minutes may not be indexed yet. Before saving, also list the target category folder's files for that year and compare names (`Vendor MMDDYY`).

## 3. Decide

`dedupe_decide.py` applies this table; every case it cannot settle comes back as `adjudicate` for the Opus tie-breaker. Keep the script and this table in step: change both together.

| Situation | Decision |
|---|---|
| Same `ref` (any doc type) | Same transaction |
| Same RFC822 Message-ID | Same transaction |
| Same vendor + amount + date + card, and items/time agree or are absent from one side | Same transaction |
| Same vendor + amount, but different date, ref, card, items, ship-to, or time of day | Different transaction - save; note "similar to <file name>" |
| Same vendor + amount + date, no ref, nothing else to compare | **Ask the user** |
| Hit is an INVOICE file and the new one is the receipt for it | Save the receipt in the invoice's group (`PAYS_GROUP` in its description); rename the invoice ` (paid - see receipt)` only when this mailbox filed it (`rename_invoice`) |
| Hit is a receipt and the new one is the invoice for it | Do not save; duplicate row in the same group |
| Recurring charges (monthly subscriptions, tolls) | Different transaction when the date or billing period differs, even with identical amounts |

When in doubt between "same" and "different", ask; never silently drop a possibly separate expense, and never silently save a possible second copy.

## 4. Record

- New file: store the description block from `receipt_key.py` on the file. Its `group_id` is now the group for this transaction.
- Duplicate: do not save a file. Report row gets `Status = DUPLICATE - not saved`, the **existing file's** `group_id`, and `Duplicate of = <existing file name>`, plus where this copy was found (mailbox, sender, email date).

## 5. Same receipt in two mailboxes

The usual case: one email goes to two people (CC, a forward to ksa@). Both copies have the **same RFC822 Message-ID**, so whoever runs second finds the first person's file through `KSAMSG...` and logs a `DUPLICATE - not saved` row. The run lock makes the runs take turns, so the second run normally sees the first one's files.

A second copy still slips through when Drive's search index has not caught up with the first upload (runs close together, or a resumed run). The **sweep** catches it after the fact:

1. After the upload step, collect the files to sweep: every file this chunk saved, plus your own `SAVED` rows from the last 3 days in the current report (their Drive links). Read each one's description (`get_file_metadata`), and for each `KSAMSG...` and `KSAREF...` token in its `TOKENS` line run `fullText contains '<token>'`, keeping hits inside `Receipt archive`. Hand the batch to a `dedupe-checker` agent if it is more than ~10 files.
2. Save all hits (with `description` and `createdTime`) to `hits.json` and run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/dup_sweep.py --hits hits.json --email <found_by>`.
3. The **first-created copy is kept**. For each entry in `mine` (an extra copy *you* filed): rename it to `new_title` (`DUPLICATE of <keeper> - <name>`) with `update_file`, and pass its `report_row` to the report - it turns your `SAVED` row into a `DUPLICATE - extra copy set aside` row in the keeper's group. Never trash it; the summary asks a person to delete it in Drive.
4. Entries in `others` are extras a teammate filed. Do nothing to them (the connector would refuse it anyway) - their own next sweep sets them aside. Mention them in one line of the final summary.

An invoice and its receipt share an order number on purpose; the sweep does not treat them as duplicates.

## 6. Settings (cards, addresses, vendors, rules)

Settings live as tiny files whose **titles** hold the data, so no file is ever rewritten. Two layers:

- `Receipt archive/_settings/` - **company-wide**: the business address, vendor mappings, company cards and rules that hold for everyone.
- `Receipt archive/_settings/<email>/` - **one folder per person**: their own cards, their own home-office address (each person's home is different), and rules that are only about their purchases.

The person's own entries win over company ones. Other people's `CARD` lines are read too (cards only), so a receipt forwarded from a teammate's card is still recognised. Forms:

- `CARD 1234 business - <who/what>` or `CARD 5678 personal - <who/what>`
- `ADDRESS business <street, city>` - the business address (bill-to/service address → business)
- `ADDRESS home-office <street, city>` - household bills here go to `Home Office - Indirect`
- `VENDOR <vendor> -> <Category>` or `VENDOR <vendor> -> Personal` - a mapping that holds for every purchase from that vendor
- `RULE <short rule in plain words>` - e.g. `RULE personal on business card goes to Owners Draw`

List `_settings`, the person's own subfolder, and the other subfolders at the start of each run and parse them with `scripts/settings.py --shared .. --mine .. --others ..`. Company facts (addresses, cards) live only here - the plugin itself is public. When saving an answer as a setting, ask whether it is **for everyone** (company `_settings/`) or **just for you** (`_settings/<email>/`); default to just you for cards, home address and anything about personal purchases. To add a setting, create a new empty Google Doc with that title (`create_file`, mime `application/vnd.google-apps.document`). Only last-4 digits are ever stored. If two settings conflict, ask the user which is right.
