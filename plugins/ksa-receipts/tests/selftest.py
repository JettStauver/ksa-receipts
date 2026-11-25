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
check("lock free", s["lock"]["state"], "free")

print(f"\n{'ALL PASSED' if not FAIL else str(len(FAIL)) + ' FAILED'}")
sys.exit(1 if FAIL else 0)
