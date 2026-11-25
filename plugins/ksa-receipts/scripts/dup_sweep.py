#!/usr/bin/env python3
"""Find transactions that were filed more than once, and say who sets each extra copy aside.

The run lock and the dedupe search normally stop a second copy. One still gets through when two
mailboxes file the same receipt before Drive's search index has caught up (George and Ken both
get the same email and their runs come close together). This sweep runs after the upload step,
when the index has had time to catch up, and again over the files from the last few days.

Rules
- Two KSA files are the same transaction when they share the RFC822 Message-ID token (KSAMSG...)
  or, with the same document type, a reference token (KSAREF...). An invoice and its receipt share
  a ref on purpose and are not duplicates.
- The keeper is the copy created first (Drive createdTime; then file name). Every other copy is
  an extra.
- Nobody edits a teammate's file (the connector refuses it anyway). Each person handles only the
  extras they filed: rename to `DUPLICATE of <keeper> - <name>` and add a report row that turns
  their SAVED row into a DUPLICATE row in the keeper's group. Never trash. A teammate's extra is
  listed so the summary can mention it; their own next run sets it aside.

usage: dup_sweep.py --hits hits.json --email me@x.com
  hits.json: Drive search results for the tokens of the files being swept (lists of
             {id, title|name, description, createdTime, webViewLink}); nested lists are fine.

Prints JSON:
  mine:   [{file_id, name, new_title, keeper:{file_id,name,group_id,found_by}, report_row}]
          report_row has found_by, gmail_message_id, status, group_id (keeper's),
          supersedes_group (this file's), duplicate_of, notes - pass it to report_append.py
  others: [{file_id, name, found_by, keeper_name}]  extras a teammate filed (left for them)
  clusters: number of transactions found filed more than once
"""
import argparse
import json
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from dedupe_decide import parse_desc  # noqa: E402


def files(obj, out):
    if isinstance(obj, list):
        for x in obj:
            files(x, out)
    elif isinstance(obj, dict):
        if isinstance(obj.get("title") or obj.get("name"), str) and ("id" in obj or "fileId" in obj):
            out.append(obj)
        else:
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    files(v, out)
    return out


def sweep(hits, email):
    email = (email or "").lower()
    recs, seen = [], set()
    for h in files(hits, []):
        fid = h.get("id") or h.get("fileId")
        name = h.get("title") or h.get("name")
        if fid in seen or name.upper().startswith("DUPLICATE"):
            continue
        d = parse_desc(h.get("description"))
        if not d:
            continue
        seen.add(fid)
        toks = set((d.get("TOKENS") or "").split())
        doc = (d.get("DOC") or "receipt").lower()
        recs.append({"file_id": fid, "name": name, "created": h.get("createdTime") or "",
                     "group_id": d.get("GROUP"), "found_by": (d.get("FOUND_BY") or "").lower(),
                     "gmail_id": d.get("GMAIL_ID") or "", "doc": doc,
                     "keys": {t for t in toks if t.startswith("KSAMSG")}
                     | {f"{doc}|{t}" for t in toks if t.startswith("KSAREF")}})

    # union-find over shared keys
    parent = list(range(len(recs)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    owner = {}
    for i, r in enumerate(recs):
        for k in r["keys"]:
            if k in owner:
                parent[root(i)] = root(owner[k])
            else:
                owner[k] = i
    clusters = {}
    for i in range(len(recs)):
        clusters.setdefault(root(i), []).append(recs[i])

    mine, others, n = [], [], 0
    for members in clusters.values():
        if len(members) < 2:
            continue
        n += 1
        members.sort(key=lambda r: (r["created"], r["name"]))
        keep = members[0]
        for x in members[1:]:
            if x["found_by"] == email:
                mine.append({
                    "file_id": x["file_id"], "name": x["name"],
                    "new_title": f"DUPLICATE of {keep['name']} - {x['name']}",
                    "keeper": {k: keep[k] for k in ("file_id", "name", "group_id", "found_by")},
                    "report_row": {"found_by": x["found_by"], "gmail_message_id": x["gmail_id"],
                                   "status": "DUPLICATE - extra copy set aside", "group_id": keep["group_id"],
                                   "supersedes_group": x["group_id"], "duplicate_of": keep["name"],
                                   "notes": f"filed twice; this copy was renamed 'DUPLICATE of {keep['name']}"
                                            f" - {x['name']}' - delete it in Drive"}})
            else:
                others.append({"file_id": x["file_id"], "name": x["name"], "found_by": x["found_by"],
                               "keeper_name": keep["name"]})
    return {"mine": mine, "others": others, "clusters": n}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hits", required=True)
    ap.add_argument("--email", required=True)
    a = ap.parse_args()
    json.dump(sweep(json.load(open(a.hits)), a.email), sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
