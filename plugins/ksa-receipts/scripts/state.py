#!/usr/bin/env python3
"""Run state for ksa-receipts, kept as file *titles* (Drive files are never rewritten - only created
or renamed - so titles are the durable, append-only log).

Where: each person's STATE titles live in their own folder `Receipt archive/_state/<email>/`
(created on their first run); the shared run lock lives in `Receipt archive/_state/`.
Pass both listings together in --titles (a list of lists is fine). Listing entries may be dicts with
"title"/"name" and "createdTime"; createdTime (Drive's clock) then orders lock claims.

Title formats (one person's mailbox = one email address):
  STATE <email> nightly through <YYYY-MM-DD> | <run ISO> | saved N dup N review N
  STATE <email> backfill <YYYY-MM> done | <run ISO> | saved N dup N review N
  STATE <email> backfill <YYYY-MM> started | <run ISO>
  STATE <email> backfill plan <YYYY-MM>..<YYYY-MM>          oldest..newest month to cover
  LOCK claim <email> <ISO> (<kind>)                          a claim on the shared run lock
  LOCK release <email> <ISO>                                 releases the claim with that same ISO

The lock is create-only: the Drive connector cannot rename or move a file another person created,
so nobody ever edits a lock file. The holder is the EARLIEST claim that has no release and is not
stale (over 3 hours). Each person tidies only their own old claim/release files.
Old-style `LOCK free` / `LOCK held by <email> since <ISO>` files (plugin 1.1 and earlier) are read
as: free = nothing; held = a claim with no release (it goes stale after 3 hours).

usage:
  state.py --titles titles.json --email me@x.com status
      -> JSON: nightly_from (YYYY-MM-DD), backfill plan, months done, next_month, interrupted month,
         lock state
  state.py --titles titles.json --email me@x.com next-backfill [--years 6] [--today YYYY-MM-DD]
      -> the next month to backfill (newest first), or "complete"; creates nothing
  state.py --email me@x.com title nightly --through 2026-11-24 --saved 3 --dup 1 --review 0
  state.py --email me@x.com title backfill-done --month 2021-03 --saved 40 --dup 6 --review 2
  state.py --email me@x.com title backfill-started --month 2021-03
  state.py --email me@x.com title plan --oldest 2020-12 --newest 2026-10
  state.py --email me@x.com title lock --lock-kind nightly
  state.py --email me@x.com title lock-release --claim <ISO of my claim>
      -> prints the exact title to create (the caller does the Drive call)

A month marked "started" with no "done" is the interrupted month: redo it (dedupe and the report
script make a redo safe).
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone

LOCK_STALE_HOURS = 3


def collect(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, list):
        for x in obj:
            collect(x, out)
    elif isinstance(obj, dict):
        t = obj.get("title") or obj.get("name")
        if isinstance(t, str):
            out.append(t)
        else:
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    collect(v, out)
    return out


def collect_entries(obj, out):
    """Like collect(), but keeps createdTime when the listing has it: [(title, created_or_None)]."""
    if isinstance(obj, str):
        out.append((obj, None))
    elif isinstance(obj, list):
        for x in obj:
            collect_entries(x, out)
    elif isinstance(obj, dict):
        t = obj.get("title") or obj.get("name")
        if isinstance(t, str):
            out.append((t, obj.get("createdTime") or obj.get("created_time")))
        else:
            for v in obj.values():
                if isinstance(v, (list, dict)):
                    collect_entries(v, out)
    return out


def now_iso(seconds=False):
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ" if seconds else "%Y-%m-%dT%H%MZ")


def parse_iso(s):
    if not s:
        return None
    s = s.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})$", s):
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%dT%H%M%SZ", "%Y-%m-%dT%H%MZ", "%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def month_add(ym, n):
    y, m = map(int, ym.split("-"))
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y:04d}-{m:02d}"


def lock_status(entries, email, now=None):
    """entries: [(title, createdTime or None)]. Create-only lock; see the module docstring."""
    now = now or datetime.now(timezone.utc)
    claims, releases, legacy_free = [], set(), []
    for t, created in entries:
        t = t.strip()
        m = re.match(r"(?i)^LOCK claim (\S+@\S+) (\S+)(?: \((\w+)\))?", t)
        legacy = re.match(r"(?i)^LOCK held by (\S+@\S+) since (\S+)(?: \((\w+)\))?", t)
        if m or legacy:
            g = m or legacy
            since = parse_iso(g.group(2))
            order = parse_iso(created) or since
            claims.append({"by": g.group(1).lower(), "since": g.group(2), "kind": g.group(3),
                           "title": t, "legacy": bool(legacy), "_t": since, "_order": order})
            continue
        m = re.match(r"(?i)^LOCK release (\S+@\S+) (\S+)", t)
        if m:
            releases.add((m.group(1).lower(), m.group(2)))
            continue
        if re.match(r"(?i)^LOCK free", t):
            legacy_free.append(t)
    if not claims and not releases and not legacy_free:
        return {"state": "missing", "my_claims": [], "tidy": []}
    open_claims, tidy = [], []
    for c in claims:
        released = (c["by"], c["since"]) in releases
        age_h = (now - c["_t"]).total_seconds() / 3600 if c["_t"] else 99
        c["age_hours"] = round(age_h, 1)
        c["stale"] = age_h > LOCK_STALE_HOURS
        if released or c["stale"]:
            if c["by"] == email and not c["legacy"]:
                tidy.append(c["title"])
            continue
        open_claims.append(c)
    for who, since in releases:
        if who == email:
            tidy.append(f"LOCK release {who} {since}")
    far = datetime.max.replace(tzinfo=timezone.utc)
    open_claims.sort(key=lambda c: (c["_order"] or far, c["by"]))
    clean = lambda c: {k: v for k, v in c.items() if not k.startswith("_")}  # noqa: E731
    mine = [clean(c) for c in open_claims if c["by"] == email]
    out = {"state": "free", "my_claims": mine, "tidy": sorted(set(tidy))}
    if open_claims:
        h = clean(open_claims[0])
        out.update(state="held", by=h["by"], since=h["since"], kind=h["kind"], holder_claim=h["title"],
                   age_hours=h["age_hours"], mine=h["by"] == email, stale=False,
                   waiting=[clean(c)["title"] for c in open_claims[1:]])
    return out


def status(titles, email, today=None, entries=None):
    email = email.lower()
    e = re.escape(email)
    st = {"email": email, "nightly_through": None, "nightly_from": None, "plan": None,
          "done": [], "started": [], "interrupted": [], "lock": {"state": "missing"}}
    for t in titles:
        t = t.strip()
        m = re.match(rf"(?i)^STATE {e} nightly through (\d{{4}}-\d{{2}}-\d{{2}})", t)
        if m and (st["nightly_through"] is None or m.group(1) > st["nightly_through"]):
            st["nightly_through"] = m.group(1)
        m = re.match(rf"(?i)^STATE {e} backfill (\d{{4}}-\d{{2}}) done", t)
        if m:
            st["done"].append(m.group(1))
        m = re.match(rf"(?i)^STATE {e} backfill (\d{{4}}-\d{{2}}) started", t)
        if m:
            st["started"].append(m.group(1))
        m = re.match(rf"(?i)^STATE {e} backfill plan (\d{{4}}-\d{{2}})\.\.(\d{{4}}-\d{{2}})", t)
        if m:
            st["plan"] = {"oldest": m.group(1), "newest": m.group(2)}
    st["done"] = sorted(set(st["done"]), reverse=True)
    st["interrupted"] = sorted(set(st["started"]) - set(st["done"]), reverse=True)
    del st["started"]
    st["lock"] = lock_status(entries if entries is not None else [(t, None) for t in titles], email)
    if st["nightly_through"]:
        d = datetime.strptime(st["nightly_through"], "%Y-%m-%d").date() - timedelta(days=3)
        st["nightly_from"] = d.isoformat()  # 3-day overlap catches late mail; dedupe absorbs it
    return st


def next_backfill(st, years, today):
    if st["interrupted"]:
        return {"month": st["interrupted"][0], "why": "interrupted - redo"}
    plan = st["plan"]
    if not plan:
        newest = month_add(today.strftime("%Y-%m"), -1)
        oldest = month_add(today.strftime("%Y-%m"), -12 * years)
        return {"month": newest, "why": "no plan yet", "create_plan": {"oldest": oldest, "newest": newest}}
    m = plan["newest"]
    done = set(st["done"])
    while m >= plan["oldest"]:
        if m not in done:
            return {"month": m, "why": "next newest month not done"}
        m = month_add(m, -1)
    return {"month": None, "why": "complete"}


def month_window(ym):
    nxt = month_add(ym, 1)
    return {"after": ym.replace("-", "/") + "/01", "before": nxt.replace("-", "/") + "/01",
            "gmail_query_suffix": f"after:{ym.replace('-', '/')}/01 before:{nxt.replace('-', '/')}/01"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--titles")
    ap.add_argument("--email", required=True)
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--today")
    ap.add_argument("cmd", choices=["status", "next-backfill", "title"])
    ap.add_argument("kind", nargs="?")
    for k in ("through", "month", "oldest", "newest", "lock-kind", "claim"):
        ap.add_argument("--" + k)
    for k in ("saved", "dup", "review"):
        ap.add_argument("--" + k, type=int, default=0)
    a = ap.parse_args()
    today = datetime.strptime(a.today, "%Y-%m-%d").date() if a.today else date.today()
    em = a.email.lower()

    if a.cmd == "title":
        counts = f"saved {a.saved} dup {a.dup} review {a.review}"
        t = {"nightly": lambda: f"STATE {em} nightly through {a.through} | {now_iso()} | {counts}",
             "backfill-done": lambda: f"STATE {em} backfill {a.month} done | {now_iso()} | {counts}",
             "backfill-started": lambda: f"STATE {em} backfill {a.month} started | {now_iso()}",
             "plan": lambda: f"STATE {em} backfill plan {a.oldest}..{a.newest}",
             "lock": lambda: f"LOCK claim {em} {now_iso(seconds=True)} ({a.lock_kind or 'run'})",
             "lock-release": lambda: f"LOCK release {em} {a.claim}"}
        if a.kind not in t:
            sys.exit("title kinds: nightly, backfill-done, backfill-started, plan, lock, lock-release")
        if a.kind == "lock-release" and not a.claim:
            sys.exit("lock-release needs --claim <the ISO time in your LOCK claim title>")
        print(t[a.kind]())
        return

    data = json.load(open(a.titles)) if a.titles else []
    titles = collect(data, [])
    st = status(titles, em, today, entries=collect_entries(data, []))
    if a.cmd == "status":
        print(json.dumps(st, indent=1))
    else:
        nb = next_backfill(st, a.years, today)
        if nb.get("month"):
            nb["window"] = month_window(nb["month"])
        print(json.dumps(nb))


if __name__ == "__main__":
    main()
