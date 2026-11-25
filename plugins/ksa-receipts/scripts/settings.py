#!/usr/bin/env python3
"""Parse settings from `Receipt archive/_settings/` into JSON.

usage: settings.py --shared shared.json --mine mine.json [--others a.json b.json] --out settings.json

Two layers:
  _settings/                 company-wide: ADDRESS business, VENDOR mappings, company RULEs, company cards
  _settings/<email>/         one folder per person: their cards, their ADDRESS home-office, their RULEs
Merged with the person's own entries winning; other people's CARD lines are read too (cards only),
so a receipt forwarded from a teammate's card is still recognised. "missing" lists what this person
still needs, so the run can add it.

Each input: a JSON list of file titles (strings), or the raw search_files result (any JSON with
objects carrying "title" or "name"). Settings live in titles so no file is ever rewritten.
Recognised forms (case-insensitive keywords):

  CARD 1234 business - <who/what>
  CARD 5678 personal - <who/what>
  ADDRESS business <street, city>          e.g. ADDRESS business 123 Main St, Springfield
  ADDRESS home-office <street, city>       household bills here go to Home Office - Indirect
  ADDRESS home-office none                 this person has no home office (stops the 'missing' prompt)
  VENDOR <vendor name> -> <Category>       e.g. VENDOR Digi-Key -> Cost of Goods Sold
  VENDOR <vendor name> -> Personal
  RULE <plain-words rule>                  free text; passed to the model when it mentions the vendor
  MAILBOX <email> <display name>           optional: who runs the finder

Anything else is reported under "unparsed" so a typo is visible instead of silently ignored.
Card numbers: only the last 4 digits are accepted; longer digit runs are rejected.
"""
import argparse
import json
import re
import sys


def collect_titles(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for x in obj:
            collect_titles(x, out)
    elif isinstance(obj, dict):
        t = obj.get("title") or obj.get("name")
        if isinstance(t, str):
            out.append(t)
        else:
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    collect_titles(v, out)
    return out


def street_key(addr: str) -> str:
    """'123 Main St, Springfield TX' -> '123 main' (number + first street word)."""
    m = re.search(r"(\d{2,6})\s+([A-Za-z]+)", addr or "")
    return f"{m.group(1)} {m.group(2).lower()}" if m else ""


def parse(titles):
    s = {"cards": {}, "addresses": {"business": [], "home-office": []}, "vendors": [],
         "rules": [], "mailboxes": [], "unparsed": [], "conflicts": []}
    for raw in titles:
        t = raw.strip()
        if t.lower().endswith((".gdoc", ".txt")):
            t = t.rsplit(".", 1)[0]
        m = re.match(r"(?i)^CARD\s+(\d+)\s+(business|personal)\b\s*-?\s*(.*)$", t)
        if m:
            last4, kind, note = m.group(1), m.group(2).lower(), m.group(3)
            if len(last4) != 4:
                s["unparsed"].append(raw + "  (only last 4 digits allowed)")
                continue
            if last4 in s["cards"] and s["cards"][last4]["kind"] != kind:
                s["conflicts"].append(f"card {last4} is listed as both business and personal")
            s["cards"][last4] = {"kind": kind, "note": note}
            continue
        m = re.match(r"(?i)^ADDRESS\s+(business|home[- ]?office)\s+none\s*$", t)
        if m:
            kind = "business" if m.group(1).lower() == "business" else "home-office"
            s["addresses"][kind].append({"text": "none", "key": ""})
            continue
        m = re.match(r"(?i)^ADDRESS\s+(business|home[- ]?office)\s+(.+)$", t)
        if m:
            kind = "business" if m.group(1).lower() == "business" else "home-office"
            s["addresses"][kind].append({"text": m.group(2).strip(), "key": street_key(m.group(2))})
            continue
        m = re.match(r"(?i)^VENDOR\s+(.+?)\s*(?:->|=>|→)\s*(.+)$", t)
        if m:
            s["vendors"].append({"vendor": m.group(1).strip(), "target": m.group(2).strip()})
            continue
        m = re.match(r"(?i)^RULE\s+(.+)$", t)
        if m:
            s["rules"].append(m.group(1).strip())
            continue
        m = re.match(r"(?i)^MAILBOX\s+(\S+@\S+)\s*(.*)$", t)
        if m:
            s["mailboxes"].append({"email": m.group(1).lower(), "name": m.group(2).strip()})
            continue
        s["unparsed"].append(raw)
    return s


def merge(shared, mine, others):
    """Shared company settings + this person's own + other people's CARD lines (cards only)."""
    out = {"cards": {}, "addresses": {"business": [], "home-office": []}, "vendors": [], "rules": [],
           "mailboxes": shared["mailboxes"] + mine["mailboxes"], "unparsed": [], "conflicts": [],
           "missing": []}
    for scope, st in (("other", others), ("shared", shared), ("mine", mine)):  # later wins
        for last4, c in st["cards"].items():
            prev = out["cards"].get(last4)
            if prev and prev["kind"] != c["kind"] and scope != "other":
                out["conflicts"].append(f"card {last4}: {prev['scope']} says {prev['kind']}, {scope} says {c['kind']}")
            out["cards"][last4] = dict(c, scope=scope)
    for scope, st in (("shared", shared), ("mine", mine)):
        for kind in ("business", "home-office"):
            out["addresses"][kind] += [dict(a, scope=scope) for a in st["addresses"][kind]]
        out["vendors"] += [dict(v, scope=scope) for v in st["vendors"]]
        out["rules"] += st["rules"]
        out["unparsed"] += [f"{scope}: {u}" for u in st["unparsed"]]
        out["conflicts"] += [f"{scope}: {c}" for c in st["conflicts"]]
    if not out["addresses"]["business"]:
        out["missing"].append("shared: ADDRESS business <street, city>")
    if not [a for a in out["addresses"]["home-office"] if a["scope"] == "mine"]:
        out["missing"].append("mine: ADDRESS home-office <street, city>  (or 'ADDRESS home-office none')")
    if not [c for c in out["cards"].values() if c["scope"] == "mine"]:
        out["missing"].append("mine: CARD <last 4> business|personal - <what>  (at least the cards you use)")
    return out


def load(path):
    return collect_titles(json.load(open(path)), []) if path else []


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shared", help="titles in _settings/ (company-wide)")
    ap.add_argument("--mine", help="titles in _settings/<my email>/")
    ap.add_argument("--others", nargs="*", default=[], help="titles in other people's _settings/<email>/ (cards only are used)")
    ap.add_argument("--titles", help="(v1.0 compatibility) same as --shared")
    ap.add_argument("--out")
    a = ap.parse_args()
    shared = parse(load(a.shared or a.titles))
    mine = parse(load(a.mine))
    others = parse(sum((load(o) for o in a.others), []))
    res = merge(shared, mine, others)
    txt = json.dumps(res, indent=2)
    if a.out:
        open(a.out, "w").write(txt)
    print(json.dumps({"cards": {k: len([c for c in res["cards"].values() if c["scope"] == k]) for k in ("mine", "shared", "other")},
                      "addresses": {k: len(v) for k, v in res["addresses"].items()},
                      "vendors": len(res["vendors"]), "rules": len(res["rules"]),
                      "missing": res["missing"], "unparsed": res["unparsed"], "conflicts": res["conflicts"]}))


if __name__ == "__main__":
    main()
