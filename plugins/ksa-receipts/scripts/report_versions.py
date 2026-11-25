#!/usr/bin/env python3
"""Pick the current yearly report and name the next version, without ever editing another
person's file.

The Drive connector can only rename or move files that the same person created through it, so a
report is never replaced in place. Each publish uploads a NEW file with the next version number:

  Receipts Report <YYYY> v<NNN> (<who>).xlsx        kind "report"
  Hotel Nights <YYYY> v<NNN> (<who>).xlsx           kind "nights"

<who> is the part of the publisher's email before the @. The highest version is the current
report; it always holds every row (each version is built from the one before). An old-style
`Receipts Report <YYYY>.xlsx` with no version counts as v000. Files whose title starts with
`OLD - ` are superseded versions their owner has already set aside, and are ignored.

Each person tidies only their OWN superseded versions: move them into `<YYYY>/_Report history`
when Drive allows it, otherwise rename them `OLD - <title>`. A teammate's superseded version stays
until that teammate's next run tidies it.

usage:
  report_versions.py --year-folder year_listing.json [--history history_listing.json]
                     --email me@x.com --year 2026 --kind report|nights
    listings: Drive search results (lists of {id, title|name, createdTime, ...}); nested is fine.

Prints JSON:
  current      {id, title, version, by} of the file to download and append to (null: none yet)
  conflict     other files with the same top version (two people published at once): download them
               too and pass them to report_append.py --also, so no rows are lost
  next_title   exact title for the new upload
  next_version
  tidy_mine    my superseded versions still in the year folder: [{id, title, old_title}]
               (move to _Report history, or rename to old_title if the move is refused)
  others_superseded  teammates' superseded versions still in the year folder (left for them)
"""
import argparse
import json
import re
import sys

PREFIX = {"report": "Receipts Report", "nights": "Hotel Nights"}


def entries(obj, out):
    if isinstance(obj, list):
        for x in obj:
            entries(x, out)
    elif isinstance(obj, dict):
        t = obj.get("title") or obj.get("name")
        if isinstance(t, str):
            out.append({"id": obj.get("id") or obj.get("fileId"), "title": t,
                        "createdTime": obj.get("createdTime") or ""})
        else:
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    entries(v, out)
    return out


def who_of(email):
    local = (email or "").split("@")[0].lower()
    return re.sub(r"[^a-z0-9._-]", "", local) or "unknown"


def parse(title, prefix, year):
    t = title.strip()
    if t.upper().startswith("OLD - "):
        return None
    m = re.match(rf"(?i)^{re.escape(prefix)} {year} v(\d{{1,4}}) \(([^)]*)\)\.xlsx$", t)
    if m:
        return {"version": int(m.group(1)), "by": m.group(2).lower()}
    if re.match(rf"(?i)^{re.escape(prefix)} {year}\.xlsx$", t):
        return {"version": 0, "by": None}  # 1.1 and earlier: unversioned
    return None


def plan(year_files, history_files, email, year, kind):
    prefix = PREFIX[kind]
    me = who_of(email)
    seen = []
    for f in year_files:
        p = parse(f["title"], prefix, year)
        if p:
            seen.append(dict(f, **p))
    top = max((f["version"] for f in seen), default=None)
    hist_top = max((p["version"] for p in (parse(f["title"], prefix, year) for f in history_files) if p),
                   default=-1)
    tops = sorted([f for f in seen if f["version"] == top], key=lambda f: (f["createdTime"], f["title"]))
    current = tops[-1] if tops else None  # same number twice: newest is current, the rest are merged in
    conflict = tops[:-1]
    nxt = max(top if top is not None else -1, hist_top) + 1
    nxt = max(nxt, 1)
    superseded = [f for f in seen if f["version"] < (top or 0)]
    clean = lambda f: {k: f[k] for k in ("id", "title", "version", "by")}  # noqa: E731
    return {
        "current": clean(current) if current else None,
        "conflict": [clean(f) for f in conflict],
        "next_version": nxt,
        "next_title": f"{prefix} {year} v{nxt:03d} ({me}).xlsx",
        "tidy_mine": [{"id": f["id"], "title": f["title"], "old_title": "OLD - " + f["title"]}
                      for f in superseded + conflict if f["by"] == me],
        "others_superseded": [clean(f) for f in superseded if f["by"] != me],
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year-folder", required=True)
    ap.add_argument("--history")
    ap.add_argument("--email", required=True)
    ap.add_argument("--year", required=True)
    ap.add_argument("--kind", choices=sorted(PREFIX), default="report")
    a = ap.parse_args()
    yf = entries(json.load(open(a.year_folder)), [])
    hf = entries(json.load(open(a.history)), []) if a.history else []
    json.dump(plan(yf, hf, a.email, a.year, a.kind), sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
