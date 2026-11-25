#!/usr/bin/env python3
"""Self-test for the deterministic parts of ksa-receipts. Run before every release:

    python3 -I tests/selftest.py

Uses made-up cards and addresses only. Exits non-zero on any failure.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
sys.path.insert(0, S)
import classify  # noqa: E402
import dedupe_decide  # noqa: E402
import settings  # noqa: E402
import state  # noqa: E402
import dup_sweep  # noqa: E402
import report_versions  # noqa: E402
import report_append  # noqa: E402

FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def key_for(rec):
    p = subprocess.run([sys.executable, "-I", os.path.join(S, "receipt_key.py")], input=json.dumps(rec),
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


st = settings.parse([
    "CARD 1234 business - company Visa", "CARD 5678 personal - owner Amex", "CARD 12345678 business - bad",
    "ADDRESS business 123 Main St, Springfield", "ADDRESS home-office 456 Oak Ln, Shelbyville",
    "VENDOR Acme Widgets -> Cost of Goods Sold", "RULE Verizon in-store purchases are personal", "hello",
])
check("settings cards", sorted(st["cards"]), ["1234", "5678"])
check("settings rejects long card", any("only last 4" in u for u in st["unparsed"]), True)
check("settings address key", st["addresses"]["business"][0]["key"], "123 main")
shared = settings.parse(["ADDRESS business 123 Main St, Springfield", "CARD 1234 business - company Visa"])
mine = settings.parse(["CARD 5678 personal - my Amex", "ADDRESS home-office 456 Oak Ln, Shelbyville"])
other = settings.parse(["CARD 9012 business - teammate card", "ADDRESS home-office 789 Elm St", "RULE x"])
mg = settings.merge(shared, mine, other)
check("merge: other people's cards are read", mg["cards"]["9012"]["scope"], "other")
check("merge: other people's home address is NOT", [a["text"] for a in mg["addresses"]["home-office"]],
      ["456 Oak Ln, Shelbyville"])
check("merge: other people's rules are NOT", mg["rules"], [])
check("merge: nothing missing", mg["missing"], [])
bare = settings.merge(settings.parse([]), settings.parse([]), settings.parse([]))
check("merge: new person -> 3 missing", len(bare["missing"]), 3)
check("merge: 'none' satisfies home office",
      len(settings.merge(shared, settings.parse(["ADDRESS home-office none", "CARD 1111 business - x"]),
                         settings.parse([]))["missing"]), 0)
none_home = settings.merge(shared, settings.parse(["ADDRESS home-office none"]), settings.parse([]))
check("'none' address never matches a bill", classify.address_hit("none", none_home["addresses"]["home-office"]), None)
hints = json.load(open(os.path.join(ROOT, "data", "vendor_hints.json")))["hints"]

c = lambda r: classify.classify(r, st, hints)  # noqa: E731
r = c({"vendor": "USPS", "card_last4": "1234", "kind": "receipt"})
check("business card + shipping vendor -> file", (r["route"], r["category"]), ("file", "Shipping & Freight"))
r = c({"vendor": "Target", "card_last4": "5678", "kind": "receipt"})
check("personal card -> Personal", (r["route"], r["category"]), ("file", "Personal"))
r = c({"vendor": "City Water", "service_address": "456 Oak Ln, Shelbyville TX", "kind": "invoice"})
check("home address -> home office (medium: one signal)", (r["business_personal"], r["route"]),
      ("Home office (indirect)", "sonnet"))
r = c({"vendor": "Steam", "bill_to": "456 Oak Ln, Shelbyville", "card_last4": "5678", "kind": "receipt"})
check("home address on an ordinary purchase is not home office", r["category"], "Personal")
r = c({"vendor": "Apple", "ship_to": "456 Oak Ln, Shelbyville", "kind": "receipt"})
check("home ship-to alone never votes home office", r["business_personal"] != "Home office (indirect)", True)
r = c({"vendor": "CoServ Electric", "bill_to": "456 Oak Ln, Shelbyville", "kind": "invoice"})
check("household bill at home address -> home office", r["business_personal"], "Home office (indirect)")
r = c({"vendor": "City Water", "service_address": "456 Oak Ln", "card_last4": "1234", "kind": "receipt"})
check("home address on business card -> adjudicate", r["route"], "adjudicate")
r = c({"vendor": "Hilton", "card_last4": "9999", "kind": "receipt"})
check("unknown card + travel vendor -> not filed blind", r["route"] in ("sonnet", "adjudicate"), True)
r = c({"vendor": "Steam (Valve)", "kind": "receipt"})
check("game store -> Personal hint, still a model look", (r["business_personal"], r["route"]), ("Personal", "sonnet"))
r = c({"vendor": "Verizon Wireless", "card_last4": "1234", "kind": "receipt"})
check("free-text RULE mentioning vendor forces a model look", r["route"], "sonnet")
r = c({"vendor": "Acme Widgets Inc", "kind": "receipt"})
check("VENDOR setting", r["category"], "Cost of Goods Sold")
r = c({"vendor": "Anything", "kind": "receipt", "user_label": "Receipts/Personal"})
check("user label final", (r["route"], r["category"]), ("file", "Personal"))
r = c({"vendor": "Anything", "kind": "order_ack"})
check("order ack -> review", r["route"], "review")
r = c({"vendor": "Apple", "kind": ""})
check("missing kind -> adjudicate, never filed", r["route"], "adjudicate")
r = c({"vendor": "Target", "card_last4": "5678", "kind": "refund"})
check("refund never auto-filed", r["route"], "sonnet")
r = c({"vendor": "Mystery LLC", "kind": "receipt"})
check("no evidence -> sonnet first (not Opus)", r["route"], "sonnet")

base = {"vendor": "Anthropic, PBC", "transaction_date": "2026-10-23", "total": "21.00", "ref": "2377-9435-9427",
        "card_last4": "1234", "doc_type": "receipt", "rfc822_message_id": "<abc@mail.example.com>",
        "gmail_message_id": "m1", "found_by": "a@x.com", "items": "Claude Pro Oct 23-Nov 23"}
k = key_for(base)


def hit(rec, **kw):
    kk = key_for(rec)
    return {"file_id": "F1", "name": kk["file_name_stem"] + ".pdf", "description": kk["description"], **kw}


D = lambda rec, hits=(), rows=(), names=(): dedupe_decide.decide(  # noqa: E731
    {"record": rec, "key": key_for(rec), "hits": list(hits), "report_rows": list(rows), "folder_names": list(names)})
check("no hits -> new", D(base)["decision"], "new")
other_mailbox = dict(base, gmail_message_id="m2", found_by="b@x.com")
check("same ref from another mailbox -> duplicate", D(other_mailbox, [hit(base)])["decision"], "duplicate")
check("same email same mailbox -> already_saved_self", D(base, [hit(base)])["decision"], "already_saved_self")
nxt = dict(base, transaction_date="2026-11-23", ref="", rfc822_message_id="<def@x>", gmail_message_id="m3")
check("monthly charge next month -> new_near_match", D(nxt, [hit(dict(base, ref=""))])["decision"], "new_near_match")
a = dict(base, ref="", rfc822_message_id="", card_last4="", items="", gmail_message_id="m4", found_by="b@x.com")
b = dict(a, gmail_message_id="m5", found_by="c@x.com")
check("same vendor/amount/date, nothing else -> adjudicate", D(a, [hit(b)])["decision"], "adjudicate")
inv = dict(base, doc_type="invoice", gmail_message_id="m6", found_by="b@x.com")
check("receipt for saved invoice", D(dict(base, gmail_message_id="m7"), [hit(inv)])["decision"], "receipt_for_invoice")
check("unindexed same-name file -> adjudicate",
      D(dict(base, ref="", rfc822_message_id=""), names=[k["file_name_stem"] + ".pdf"])["decision"], "adjudicate")
raw = {"file_id": "F9", "name": "scan.pdf", "description": "", "matched_query": "fullText contains '2377-9435-9427'"}
check("hand-filed PDF containing long ref -> duplicate", D(dict(base, gmail_message_id="m8"), [raw])["decision"], "duplicate")

titles = ["STATE a@x.com backfill plan 2020-11..2026-10", "STATE a@x.com backfill 2026-10 started | t",
          "STATE a@x.com backfill 2026-10 done | t", "STATE a@x.com backfill 2026-09 started | t",
          "STATE a@x.com nightly through 2026-11-20 | t", "LOCK free"]
s = state.status(titles, "a@x.com")
check("state interrupted month", s["interrupted"], ["2026-09"])
check("state nightly_from has 3-day overlap", s["nightly_from"], "2026-11-17")
check("next backfill redoes interrupted", state.next_backfill(s, 6, None)["month"], "2026-09")
s2 = state.status(titles[:3], "a@x.com")
check("next backfill goes newest-first", state.next_backfill(s2, 6, None)["month"], "2026-09")
check("other user unaffected", state.status(titles, "b@x.com")["nightly_from"], None)
check("legacy LOCK free reads as free", s["lock"]["state"], "free")

# create-only run lock
from datetime import datetime as _dt, timedelta as _td, timezone as _tz
_now = _dt.now(_tz.utc)
_iso = lambda m: (_now - _td(minutes=m)).strftime("%Y-%m-%dT%H%M%SZ")  # noqa: E731
L = lambda e, who: state.lock_status(e, who)  # noqa: E731
check("lock missing", L([], "a@x.com")["state"], "missing")
c_a, c_b = f"LOCK claim a@x.com {_iso(5)} (nightly)", f"LOCK claim b@x.com {_iso(4)} (backfill)"
r = L([(c_b, None), (c_a, None)], "b@x.com")
check("earliest claim holds the lock", (r["state"], r["by"], r["mine"]), ("held", "a@x.com", False))
check("later claimant is waiting", r["waiting"], [c_b])
r = L([(c_a, None), (c_b, None), (f"LOCK release a@x.com {_iso(5)}", None)], "b@x.com")
check("after release the next claim holds it", (r["by"], r["mine"]), ("b@x.com", True))
r = L([(f"LOCK claim a@x.com {_iso(200)} (nightly)", None)], "b@x.com")
check("stale claim (>3h) is ignored", r["state"], "free")
r = L([(f"LOCK claim a@x.com {_iso(200)} (nightly)", None), (c_a, None), (f"LOCK release a@x.com {_iso(5)}", None)], "a@x.com")
check("own stale/released files are listed to tidy", len(r["tidy"]), 3)
same = _iso(1)
r = L([(f"LOCK claim b@x.com {same} (n)", "2026-11-25T10:00:01.500Z"),
       (f"LOCK claim a@x.com {same} (n)", "2026-11-25T10:00:02.000Z")], "a@x.com")
check("Drive createdTime breaks a same-second race", r["by"], "b@x.com")
r = L([(f"LOCK held by a@x.com since {_iso(30)} (nightly)", None)], "b@x.com")
check("old-style held lock still blocks", (r["state"], r["by"]), ("held", "a@x.com"))
check("release title", subprocess.run([sys.executable, "-I", os.path.join(S, "state.py"), "--email", "A@x.com",
      "title", "lock-release", "--claim", "2026-11-25T101500Z"], capture_output=True, text=True).stdout.strip(),
      "LOCK release a@x.com 2026-11-25T101500Z")

# report versions
yf = [{"id": "1", "title": "Receipts Report 2026.xlsx", "createdTime": "2026-01-01T00:00:00Z"},
      {"id": "2", "title": "Receipts Report 2026 v001 (george).xlsx", "createdTime": "2026-11-01T00:00:00Z"},
      {"id": "3", "title": "Receipts Report 2026 v002 (ken).xlsx", "createdTime": "2026-11-02T00:00:00Z"},
      {"id": "4", "title": "Hotel Nights 2026 v004 (ken).xlsx", "createdTime": "2026-11-02T00:00:00Z"},
      {"id": "5", "title": "OLD - Receipts Report 2026 v000 (ken).xlsx", "createdTime": "2026-11-02T00:00:00Z"}]
v = report_versions.plan(yf, [], "george@x.com", "2026", "report")
check("highest version is current", v["current"]["id"], "3")
check("next title", v["next_title"], "Receipts Report 2026 v003 (george).xlsx")
check("only my superseded versions to tidy", [t["id"] for t in v["tidy_mine"]], ["2"])
check("teammate's superseded left alone", sorted(t["id"] for t in v["others_superseded"]), ["1"])
v = report_versions.plan(yf + [{"id": "6", "title": "Receipts Report 2026 v002 (george).xlsx",
                                "createdTime": "2026-11-02T00:05:00Z"}], [], "ken@x.com", "2026", "report")
check("same version twice -> conflict to merge", (v["current"]["id"], [c["id"] for c in v["conflict"]]), ("6", ["3"]))
check("nights kind kept separate", report_versions.plan(yf, [], "ken@x.com", "2026", "nights")["next_title"],
      "Hotel Nights 2026 v005 (ken).xlsx")
check("history versions count toward the number",
      report_versions.plan([], [{"title": "Receipts Report 2026 v007 (ken).xlsx"}], "ken@x.com", "2026", "report")["next_version"], 8)

# duplicate sweep: same email filed by two mailboxes
def kfile(fid, created, who, gid, tokens, doc="receipt", gmail="g"):
    return {"id": fid, "title": f"Vendor 112526 {fid}.pdf", "createdTime": created,
            "description": f"KSA-RECEIPT v1\nGROUP: {gid}\nDOC: {doc}\nFOUND_BY: {who}\nGMAIL_ID: {gmail}\nTOKENS: {tokens}"}
hits = [kfile("K", "2026-11-25T08:00:00Z", "ken@x.com", "G1", "KSAMSGabc KSAVAX1", gmail="gk"),
        kfile("G", "2026-11-25T08:01:00Z", "george@x.com", "G2", "KSAMSGabc KSAVAX1", gmail="gg"),
        kfile("I", "2026-11-20T08:00:00Z", "ken@x.com", "G3", "KSAREF99 KSAVAX1", doc="invoice"),
        kfile("R", "2026-11-24T08:00:00Z", "george@x.com", "G3", "KSAREF99 KSAVAX1")]
sw = dup_sweep.sweep(hits, "george@x.com")
check("sweep: later copy is mine to set aside", [m["file_id"] for m in sw["mine"]], ["G"])
check("sweep: report row moves to keeper group", (sw["mine"][0]["report_row"]["group_id"],
      sw["mine"][0]["report_row"]["supersedes_group"]), ("G1", "G2"))
check("sweep: invoice + receipt with same ref is not a duplicate", sw["clusters"], 1)
check("sweep: ken sees george's extra as someone else's", [o["file_id"] for o in dup_sweep.sweep(hits, "ken@x.com")["others"]], ["G"])

# report: supersedes_group turns a SAVED row into a duplicate row of the keeper
ex = [{"group_id": "G1", "status": "SAVED", "vendor": "V", "total": 5, "found_by": "ken@x.com", "gmail_message_id": "gk"},
      {"group_id": "G2", "status": "SAVED", "vendor": "V", "total": 5, "found_by": "george@x.com", "gmail_message_id": "gg"}]
rows, _, _, rep = report_append.merge(ex, [sw["mine"][0]["report_row"]])
check("supersedes_group replaces the SAVED row", ([r["group_id"] for r in rows], rep), (["G1", "G1"], 1))
rows, added, _, _ = report_append.merge([dict(ex[0], status="SAVED")],
                                        [dict(ex[0], status="NEEDS REVIEW", group_id="REVIEW-gk")])
check("resolved review row is not merged back in", added, 0)

# dedupe: never ask to rename a teammate's invoice
inv_t = dict(base, doc_type="invoice", gmail_message_id="m6", found_by="b@x.com")
res = D(dict(base, gmail_message_id="m7", found_by="a@x.com"), [hit(inv_t)])
check("teammate's invoice is not renamed", (res["decision"], res["rename_invoice"]), ("receipt_for_invoice", False))

print(f"\n{'ALL PASSED' if not FAIL else str(len(FAIL)) + ' FAILED'}")
sys.exit(1 if FAIL else 0)
