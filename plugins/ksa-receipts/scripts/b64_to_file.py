#!/usr/bin/env python3
"""Decode a Drive download_file_content result (saved JSON, or a bare base64 string) to a binary file.

usage: b64_to_file.py <saved-result-or-base64-file> --out report.xlsx [--check-xlsx]
--check-xlsx opens the result with openpyxl and prints the data row count, so a corrupted copy is
caught before it is used as the basis for a new report.
"""
import argparse
import base64
import json
import re
import sys


def find_b64(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("content", "base64Content", "data", "fileContent", "contentBase64"):
            if isinstance(obj.get(k), str):
                return obj[k]
        for v in obj.values():
            r = find_b64(v)
            if r and len(r) > 100:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = find_b64(v)
            if r and len(r) > 100:
                return r
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--check-xlsx", action="store_true")
    a = ap.parse_args()
    text = open(a.src, encoding="utf-8").read().strip()
    try:
        b64 = find_b64(json.loads(text))
    except json.JSONDecodeError:
        b64 = text
    if not b64:
        sys.exit("no base64 content found")
    s = re.sub(r"\s", "", b64)
    s += "=" * (-len(s) % 4)
    data = base64.urlsafe_b64decode(s.replace("+", "-").replace("/", "_"))
    open(a.out, "wb").write(data)
    info = {"out": a.out, "bytes": len(data)}
    if a.check_xlsx:
        from openpyxl import load_workbook
        wb = load_workbook(a.out)
        ws = wb["Receipts"] if "Receipts" in wb.sheetnames else wb.active
        info["data_rows"] = sum(1 for r in ws.iter_rows(min_row=2, values_only=True) if any(r))
    print(json.dumps(info))


if __name__ == "__main__":
    main()
