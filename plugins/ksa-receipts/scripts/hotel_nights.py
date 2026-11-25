#!/usr/bin/env python3
"""Append business hotel stays to the Hotel Nights workbook and keep a running total.

usage: hotel_nights.py --rows stays.json --out nights.xlsx [--report previous.xlsx] [--year YYYY]
       hotel_nights.py --rows stays.json --list-years

One workbook per year. With --year, only nights slept in that year are counted. A stay that runs
across New Year (e.g. Dec 30 - Jan 2) appears in both years' workbooks with that year's nights;
its amount is listed only in the check-in year so totals are never counted twice.

stays.json: list of {check_in, check_out, city, state, hotel, nights, total, card_last4,
                     confirmation, trip, file_name, drive_url, found_by}
Only stays paid with business funds belong here. A stay whose confirmation (or hotel + check_in)
is already in the workbook is skipped, so overlapping runs never double-count nights.
Sheet "Stays" lists each stay sorted by check-in; sheet "Totals" sums nights by year and month.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

COLS = [("check_in", "Check-in", 12), ("check_out", "Check-out", 12), ("nights", "Nights", 8),
        ("city", "City", 16), ("state", "State", 7), ("hotel", "Hotel", 34), ("trip", "Trip / purpose", 24),
        ("total", "Total paid", 12), ("card_last4", "Card last 4", 10), ("confirmation", "Confirmation", 16),
        ("file_name", "Receipt file", 34), ("drive_url", "Drive link", 11), ("found_by", "Found by", 22)]
KEYS = [c[0] for c in COLS]
HDR = PatternFill("solid", fgColor="1F3864")


def d(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    return str(v or "")


def read(path):
    if not path:
        return []
    ws = load_workbook(path)["Stays"]
    labels = {lbl: k for k, lbl, _ in COLS}
    hdr = [labels.get(c.value) for c in ws[1]]
    out = []
    for row in ws.iter_rows(min_row=2):
        r = {}
        for k, c in zip(hdr, row):
            if k:
                r[k] = c.hyperlink.target if (k == "drive_url" and c.hyperlink) else c.value
        if isinstance(r.get("check_in"), (datetime, date)) or re.match(r"\d{4}-\d{2}-\d{2}", str(r.get("check_in") or "")):
            out.append(r)  # skips the TOTAL NIGHTS row and blanks
    return out


def ident(r):
    return str(r.get("confirmation") or "").strip() or f"{r.get('hotel')}|{d(r.get('check_in'))}"


def nights_of(r):
    if r.get("nights") not in (None, ""):
        return int(r["nights"])
    a, b = datetime.strptime(d(r["check_in"]), "%Y-%m-%d"), datetime.strptime(d(r["check_out"]), "%Y-%m-%d")
    return (b - a).days


def years_of(r):
    a = datetime.strptime(d(r["check_in"]), "%Y-%m-%d").date()
    n = nights_of(r)
    ys = {}
    for i in range(max(n, 1)):
        y = str((a + timedelta(days=i)).year)
        ys[y] = ys.get(y, 0) + (1 if n else 0)
    return ys


def for_year(r, year):
    """Copy of the stay limited to the nights slept in `year`, or None."""
    ys = years_of(r)
    if year not in ys:
        return None
    r = dict(r)
    full = nights_of(r)
    r["nights"] = ys[year]
    if len(ys) > 1:
        cin = d(r["check_in"])[:4]
        r["trip"] = f"{r.get('trip') or ''} ({ys[year]} of {full} nights in {year})".strip()
        if year != cin:
            r["total"] = f"(counted in {cin})"
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report")
    ap.add_argument("--rows", required=True)
    ap.add_argument("--out")
    ap.add_argument("--year")
    ap.add_argument("--list-years", action="store_true")
    a = ap.parse_args()
    incoming = json.load(open(a.rows))
    if a.list_years:
        ys = sorted({y for n in incoming for y in years_of(n)})
        json.dump({"years": ys}, sys.stdout)
        print()
        return
    if not a.out:
        ap.error("--out is required")
    rows = read(a.report)
    seen = {ident(r) for r in rows}
    added = 0
    for n in incoming:
        if ident(n) in seen:
            continue
        if a.year:
            n = for_year(n, str(a.year))
            if n is None:
                continue
        else:
            n["nights"] = nights_of(n)
        rows.append(n)
        seen.add(ident(n))
        added += 1
    rows.sort(key=lambda r: d(r["check_in"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "Stays"
    for i, (_, lbl, w) in enumerate(COLS, 1):
        c = ws.cell(row=1, column=i, value=lbl)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HDR
        ws.column_dimensions[get_column_letter(i)].width = w
    for r_i, r in enumerate(rows, 2):
        for c_i, k in enumerate(KEYS, 1):
            v = r.get(k)
            c = ws.cell(row=r_i, column=c_i)
            if k in ("check_in", "check_out") and v:
                c.value = datetime.strptime(d(v), "%Y-%m-%d").date()
                c.number_format = "yyyy-mm-dd"
            elif k == "total" and v not in (None, "") and not str(v).startswith("("):
                c.value = float(str(v).replace("$", "").replace(",", ""))
                c.number_format = '"$"#,##0.00'
            elif k == "drive_url" and v:
                c.value, c.hyperlink = "Open", str(v)
                c.font = Font(color="0563C1", underline="single")
            else:
                c.value = v
    last = len(rows) + 1
    tr = last + 1
    ws.cell(row=tr, column=1, value="TOTAL NIGHTS").font = Font(bold=True)
    ws.cell(row=tr, column=3, value=f"=SUM(C2:C{last})").font = Font(bold=True)
    ws.freeze_panes = "A2"

    t = wb.create_sheet("Totals")
    for i, lbl in enumerate(["Year", "Month", "Stays", "Nights"], 1):
        c = t.cell(row=1, column=i, value=lbl)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), HDR
        t.column_dimensions[get_column_letter(i)].width = 12
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        y, m = d(r["check_in"])[:4], d(r["check_in"])[5:7]
        if a.year and y != str(a.year):
            y, m = str(a.year), "01"
        agg[(y, m)][0] += 1
        agg[(y, m)][1] += int(r["nights"])
    ri = 2
    for y in sorted({k[0] for k in agg}):
        for (yy, m) in sorted(k for k in agg if k[0] == y):
            t.append([yy, m, agg[(yy, m)][0], agg[(yy, m)][1]])
            ri += 1
        t.append([y, "Year total", sum(v[0] for k, v in agg.items() if k[0] == y),
                  sum(v[1] for k, v in agg.items() if k[0] == y)])
        for c in t[ri]:
            c.font = Font(bold=True)
        ri += 1
    wb.save(a.out)
    json.dump({"out": a.out, "stays": len(rows), "added": added,
               "total_nights": sum(int(r["nights"]) for r in rows)}, sys.stdout)
    print()


if __name__ == "__main__":
    main()
