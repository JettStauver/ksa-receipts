#!/usr/bin/env python3
"""Append transactions to the receipts report (.xlsx), keeping duplicate groups on adjacent rows.

usage: report_append.py --rows new_rows.json --out report.xlsx [--report previous.xlsx]
                        [--also other_version.xlsx ...] [--year YYYY]
       report_append.py --rows new_rows.json --list-years

One report per year. --list-years prints the years the run's rows belong to; then run once per
year with --year, which keeps only that year's rows. A row's year is its group's kept-receipt
transaction date (so duplicates stay with the copy that was filed), else its own transaction
date, else its email date.

new_rows.json: a list of objects with keys from COLUMNS below (keys are the snake_case ids).
Required per row: group_id, status, vendor, total, found_by, gmail_message_id.

Behavior
- Existing rows keep their order. A new row whose group_id already exists is inserted directly
  after the last row of that group; other new rows go to the end.
- Re-running over an overlapping date window is safe: a row with the same found_by +
  gmail_message_id + group_id is skipped. A NEEDS REVIEW row is replaced when a resolved row
  arrives for the same found_by + gmail_message_id.
- --also merges other report versions into --report first (two people published the same
  version number). Rows already present are skipped, so nothing is doubled and nothing is lost.
- A row with `supersedes_group` replaces the existing row with the same found_by +
  gmail_message_id and that group_id. The duplicate sweep uses this to turn a copy that was filed
  twice into a DUPLICATE row in the kept file's group.
- Every group with 2+ rows (duplicates, invoice+receipt pairs) gets one shared fill color, a bold
  border on its first row, and duplicate rows in italic grey text. Single-row groups stay white.
Prints a JSON summary.
"""
import argparse
import json
import re
import sys
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

COLUMNS = [
    ("group_id", "Group", 12),
    ("status", "Status", 22),
    ("doc_type", "Type", 9),
    ("transaction_date", "Transaction date", 13),
    ("vendor", "Vendor", 24),
    ("total", "Total", 11),
    ("business_personal", "Business / Personal", 12),
    ("category", "Category", 26),
    ("ref", "Order / Invoice / Ref", 20),
    ("card_last4", "Card last 4", 9),
    ("file_name", "Saved file", 34),
    ("drive_url", "Drive link", 14),
    ("duplicate_of", "Duplicate of", 30),
    ("found_by", "Found by", 22),
    ("email_from", "Email from", 26),
    ("email_date", "Email date", 13),
    ("gmail_url", "Gmail link", 12),
    ("attachment_status", "Attachment", 18),
    ("notes", "Notes", 40),
    ("run_date", "Run date", 16),
    ("gmail_message_id", "Gmail msg id", 18),
]
KEYS = [c[0] for c in COLUMNS]
SHEET = "Receipts"
PALETTE = ["FFF4CC", "DDEBF7", "E2EFDA", "FCE4D6", "EDE2F6", "D9F2F2", "F8E1EC", "EFEFD0"]
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
THIN = Side(style="thin", color="BFBFBF")
THICK = Side(style="medium", color="404040")


def read_existing(path):
    if not path:
        return []
    wb = load_workbook(path)
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.active
    headers = [c.value for c in ws[1]]
    label_to_key = {lbl: key for key, lbl, _ in COLUMNS}
    rows = []
    for r in ws.iter_rows(min_row=2):
        rec = {}
        for h, c in zip(headers, r):
            key = label_to_key.get(h)
            if not key:
                continue
            v = c.value
            if c.hyperlink and key in ("drive_url", "gmail_url"):
                v = c.hyperlink.target
            rec[key] = v
        if any(v not in (None, "") for v in rec.values()):
            rows.append(rec)
    return rows


def ident(r):
    return (str(r.get("found_by") or "").lower(), str(r.get("gmail_message_id") or ""),
            str(r.get("group_id") or ""))


def merge(existing, new):
    added, skipped, replaced = 0, 0, 0
    rows = list(existing)
    for n in new:
        sup = str(n.get("supersedes_group") or "")
        n = {k: n.get(k) for k in KEYS}
        if sup:
            old = [i for i, r in enumerate(rows)
                   if ident(r)[:2] == ident(n)[:2] and str(r.get("group_id") or "") == sup]
            for i in reversed(old):
                rows.pop(i)
            replaced += bool(old)
        n["run_date"] = n.get("run_date") or datetime.now().strftime("%Y-%m-%d %H:%M")
        if not n.get("group_id"):
            n["group_id"] = "REVIEW-" + str(n.get("gmail_message_id") or len(rows))
        if any(ident(r) == ident(n) for r in rows):
            skipped += 1
            continue
        if str(n.get("status", "")).upper().startswith("NEEDS REVIEW") and any(
                ident(r)[:2] == ident(n)[:2] and not str(r.get("status", "")).upper().startswith("NEEDS REVIEW")
                for r in rows):
            skipped += 1  # already resolved (e.g. merging an older version back in)
            continue
        # resolve an earlier NEEDS REVIEW row for the same email
        rev = [i for i, r in enumerate(rows)
               if str(r.get("status", "")).upper().startswith("NEEDS REVIEW")
               and ident(r)[:2] == ident(n)[:2]]
        if rev and not str(n.get("status", "")).upper().startswith("NEEDS REVIEW"):
            for i in reversed(rev):
                rows.pop(i)
            replaced += 1
        idx = [i for i, r in enumerate(rows) if r.get("group_id") == n["group_id"]]
        if idx:
            rows.insert(idx[-1] + 1, n)
        else:
            rows.append(n)
        added += 1
    fill_blanks(rows)
    return rows, added, skipped, replaced


UNREADABLE = "UNREADABLE - check source"
DUP_TOTAL = "(duplicate - not counted)"
PAID_INVOICE_TOTAL = "(paid - counted on receipt row)"
INHERIT = ("transaction_date", "doc_type", "business_personal", "category", "ref", "card_last4")
MUST_HAVE = ("transaction_date", "total", "vendor")


def fill_blanks(rows):
    """No silent blanks: duplicate rows inherit known fields from the kept row of their group;
    any key field still empty is marked UNREADABLE so a reader knows it was looked for.
    Each transaction's amount appears once, so the Total column can be summed: duplicate rows,
    and an invoice row whose receipt is in the same group, carry a text note instead of a number."""
    kept, has_receipt = {}, set()
    for r in rows:
        st = str(r.get("status") or "").upper()
        if st.startswith("SAVED") or st.startswith("PERSONAL"):
            kept.setdefault(r.get("group_id"), r)
        if st in ("SAVED", "PERSONAL - SAVED"):
            has_receipt.add(r.get("group_id"))
    for r in rows:
        st = str(r.get("status") or "").upper()
        g = r.get("group_id")
        if st.startswith("DUPLICATE"):
            if g in kept:
                src = kept[g]
                for k in INHERIT:
                    if r.get(k) in (None, "") and src.get(k) not in (None, ""):
                        r[k] = src[k]
            r["total"] = DUP_TOTAL
        elif st == "SAVED - INVOICE" and g in has_receipt:
            r["total"] = PAID_INVOICE_TOTAL
        for k in MUST_HAVE:
            if r.get(k) in (None, ""):
                r[k] = UNREADABLE


REPORT_YEAR = None


def write(rows, out):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    for col, (_, label, width) in enumerate(COLUMNS, 1):
        c = ws.cell(row=1, column=col, value=label)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.row_dimensions[1].height = 30

    counts = {}
    for r in rows:
        counts[r.get("group_id")] = counts.get(r.get("group_id"), 0) + 1
    color_of, nxt, prev = {}, 0, None
    for i, r in enumerate(rows, start=2):
        g = r.get("group_id")
        multi = counts.get(g, 0) > 1
        if multi and g not in color_of:
            color_of[g] = PALETTE[nxt % len(PALETTE)]
            nxt += 1
        is_dup = str(r.get("status", "")).upper().startswith("DUPLICATE")
        first_in_group = g != prev
        prev = g
        for col, key in enumerate(KEYS, 1):
            v = r.get(key)
            c = ws.cell(row=i, column=col)
            if key == "total" and v not in (None, ""):
                try:
                    v = float(str(v).replace("$", "").replace(",", ""))
                    c.number_format = '"$"#,##0.00'
                except ValueError:
                    pass
            if key in ("drive_url", "gmail_url") and v:
                c.value = "Open"
                c.hyperlink = str(v)
                c.font = Font(color="0563C1", underline="single", italic=is_dup)
            else:
                c.value = v
                c.font = Font(italic=is_dup, color="7F7F7F" if is_dup else "000000",
                              bold=(key == "status" and multi and not is_dup))
            if multi:
                c.fill = PatternFill("solid", fgColor=color_of[g])
            c.alignment = Alignment(vertical="top", wrap_text=key in ("notes", "file_name", "duplicate_of"))
            c.border = Border(left=THIN, right=THIN, bottom=THIN,
                              top=THICK if (multi and first_in_group) else THIN)
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(len(rows) + 1, 1)}"
    ws.column_dimensions[get_column_letter(KEYS.index("gmail_message_id") + 1)].hidden = True

    legend = wb.create_sheet("How to read")
    lines = [
        f"Receipts report {REPORT_YEAR or ''}".strip(),
        "",
        "One row per receipt or invoice found in a team member's Gmail. Only one file is saved per transaction.",
        "Group: transactions that are the same purchase share a Group id and sit on adjacent rows.",
        "Colored rows with a heavy top border = a group with more than one copy found (duplicates, or an invoice plus its receipt).",
        "Italic grey rows = DUPLICATE - not saved. The 'Duplicate of' column names the file that was kept.",
        "Status values: SAVED, SAVED - INVOICE, DUPLICATE - not saved, DUPLICATE - extra copy set aside (filed twice by two mailboxes; the extra file is renamed DUPLICATE ... and can be deleted), NEEDS REVIEW, PERSONAL - SAVED.",
        "Total is shown once per transaction, so the column can be summed: duplicate rows say '(duplicate - not counted)', "
        "and an invoice whose receipt was also found says '(paid - counted on receipt row)'.",
        "INVOICE in a file name means no proof of payment was found when it was filed.",
        "Attachment column: 'original attached' = vendor file saved; 'transaction record' = PDF generated from email text; "
        "'transaction record + printed email' = summary page followed by a full printed copy of the email; "
        "'not captured' = vendor file exists in Gmail but could not be copied.",
        "One report per year, by transaction date; a duplicate sits in the same year as the copy that was filed.",
        "Rows are appended each run; the newest run date is in the Run date column.",
    ]
    for i, t in enumerate(lines, 1):
        legend.cell(row=i, column=1, value=t).font = Font(bold=(i == 1), size=13 if i == 1 else 11)
    legend.column_dimensions["A"].width = 120
    wb.save(out)
    return len(color_of)


def _year(v):
    if isinstance(v, datetime):
        return str(v.year)
    m = re.search(r"\b(19|20)\d\d\b", str(v or ""))
    return m.group(0) if m else None


def year_of_rows(rows):
    """Map id(row) -> year, keeping each group in the year of the copy that was filed."""
    group_year = {}
    for r in rows:
        st = str(r.get("status") or "").upper()
        if (st.startswith("SAVED") or st.startswith("PERSONAL")) and _year(r.get("transaction_date")):
            group_year.setdefault(r.get("group_id"), _year(r.get("transaction_date")))
    out = {}
    for r in rows:
        out[id(r)] = (group_year.get(r.get("group_id")) or _year(r.get("transaction_date"))
                      or _year(r.get("email_date")) or _year(r.get("run_date")) or str(datetime.now().year))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", help="previous report .xlsx for this year (omit on first run of the year)")
    ap.add_argument("--also", action="append", default=[],
                    help="another report version to merge in (same version number published twice)")
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out")
    ap.add_argument("--year", help="keep only rows belonging to this year")
    ap.add_argument("--list-years", action="store_true")
    a = ap.parse_args()
    new = json.load(open(a.rows))
    if isinstance(new, dict):
        new = [new]
    years = year_of_rows(new)
    if a.list_years:
        counts = {}
        for r in new:
            counts[years[id(r)]] = counts.get(years[id(r)], 0) + 1
        json.dump({"years": dict(sorted(counts.items()))}, sys.stdout)
        print()
        return
    if not a.out:
        ap.error("--out is required")
    if a.year:
        new = [r for r in new if years[id(r)] == str(a.year)]
    global REPORT_YEAR
    REPORT_YEAR = a.year
    base = read_existing(a.report)
    merged_in = 0
    for extra in a.also:
        base, n_added, _, _ = merge(base, read_existing(extra))
        merged_in += n_added
    rows, added, skipped, replaced = merge(base, new)
    groups = write(rows, a.out)
    json.dump({"out": a.out, "total_rows": len(rows), "added": added,
               "skipped_already_present": skipped, "review_rows_resolved": replaced,
               "merged_from_other_versions": merged_in,
               "multi_row_groups": groups}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
