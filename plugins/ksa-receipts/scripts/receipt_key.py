#!/usr/bin/env python3
"""Build the duplicate-detection key for one receipt/invoice.

Reads a JSON object on stdin (or --json FILE) with the extracted fields and prints JSON:
  vendor_token, amount_token, ref_tokens, msg_token, group_id,
  drive_queries (list of Drive search strings), description (block to store on the Drive file),
  file_name_stem (suggested "Vendor.Name MMDDYY").

Tokens are plain alphanumerics so Google Drive full-text search matches them as whole words.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation

SUFFIXES = {"inc", "llc", "ltd", "pbc", "corp", "corporation", "co", "company", "the",
            "lp", "llp", "plc", "gmbh", "sa", "com", "www", "us", "usa"}


def vendor_words(vendor: str):
    v = vendor.lower().replace("&", " and ").replace("'", "")
    words = [w for w in re.split(r"[^a-z0-9]+", v) if w and w not in SUFFIXES]
    return words or ["unknown"]


def vendor_token(vendor: str) -> str:
    return "".join(vendor_words(vendor)[:3])[:24]


def vendor_display(vendor: str) -> str:
    """Existing folder style: words joined by dots, original capitalization, no punctuation."""
    v = vendor.replace("&", "and").replace("'", "")
    words = [w for w in re.split(r"[^A-Za-z0-9]+", v) if w and w.lower() not in SUFFIXES]
    return ".".join(words[:4]) or "Unknown"


def amount_cents(total) -> str:
    s = re.sub(r"[^0-9.\-]", "", str(total or ""))
    try:
        return str(int((Decimal(s) * 100).quantize(Decimal("1"))))
    except (InvalidOperation, ValueError):
        return "0"


def alnum(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s or "").upper()


def parse_date(d: str):
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(d.strip(), fmt)
        except (ValueError, AttributeError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", help="read fields from this file instead of stdin")
    args = ap.parse_args()
    data = json.load(open(args.json) if args.json else sys.stdin)

    vendor = data.get("vendor", "")
    vt = vendor_token(vendor)
    cents = amount_cents(data.get("total"))
    dt = parse_date(data.get("transaction_date", ""))
    date_iso = dt.strftime("%Y-%m-%d") if dt else ""
    mmddyy = dt.strftime("%m%d%y") if dt else "000000"

    refs_raw = data.get("ref") or ""
    refs = [r for r in re.split(r"[,;]\s*", refs_raw) if alnum(r)]
    ref_tokens = ["KSAREF" + alnum(r) for r in refs]

    msgid = (data.get("rfc822_message_id") or "").strip().strip("<>").lower()
    msg_token = "KSAMSG" + hashlib.sha1(msgid.encode()).hexdigest()[:16].upper() if msgid else ""

    va_token = f"KSAVA{vt.upper()}X{cents}"
    basis = f"{vt}|{date_iso}|{cents}|{alnum(refs[0]) if refs else ''}|{data.get('card_last4','')}"
    group_id = "G" + hashlib.sha1(basis.encode()).hexdigest()[:10].upper()

    queries = []
    for r, t in zip(refs, ref_tokens):
        queries.append(f"fullText contains '{t}'")
        queries.append(f"fullText contains '{r.strip()}'")
    if msg_token:
        queries.append(f"fullText contains '{msg_token}'")
    queries.append(f"fullText contains '{va_token}'")

    desc_lines = [
        "KSA-RECEIPT v1",
        f"GROUP: {group_id}",
        f"VENDOR: {vendor}",
        f"DATE: {date_iso}",
        f"TOTAL: {data.get('total','')}",
        f"DOC: {data.get('doc_type','receipt')}",
        f"REF: {refs_raw}",
        f"CARD: {data.get('card_last4','')}",
        f"ITEMS: {str(data.get('items',''))[:200]}",
        f"FOUND_BY: {data.get('found_by','')}",
        f"GMAIL_ID: {data.get('gmail_message_id','')}",
        "TOKENS: " + " ".join(ref_tokens + ([msg_token] if msg_token else []) + [va_token]),
    ]
    out = {
        "vendor_token": vt,
        "amount_cents": cents,
        "ref_tokens": ref_tokens,
        "msg_token": msg_token,
        "vendor_amount_token": va_token,
        "group_id": group_id,
        "drive_queries": queries,
        "description": "\n".join(desc_lines),
        "file_name_stem": f"{vendor_display(vendor)} {mmddyy}",
        "year": dt.strftime("%Y") if dt else "",
    }
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
