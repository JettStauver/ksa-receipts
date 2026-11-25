#!/usr/bin/env python3
"""Apply the duplicate table (references/dedupe.md section 3) to one transaction.

usage: dedupe_decide.py --job job.json

job.json:
  {"record":  {...extracted fields: vendor, transaction_date, total, ref, card_last4, doc_type,
               items, rfc822_message_id, gmail_message_id...},
   "key":     {...output of receipt_key.py for that record...},
   "hits":    [{"file_id": "...", "name": "...", "description": "...", "matched_query": "...",
                "in_archive": true}],            # Drive search hits (any query)
   "report_rows": [{...rows from this year's report with the same vendor token + amount...}],
   "folder_names": ["USPS 102726.pdf", ...]}     # target category folder listing (unindexed uploads)

Prints one JSON object:
  decision: new | new_near_match | duplicate | receipt_for_invoice | already_saved_self | adjudicate
            already_saved_self = this very email was already filed by this mailbox (a run stopped
            after upload but before the report): log it as SAVED with the existing file, do not
            upload again and do not call it a duplicate.
  match:    {file_id, name, group_id} of the existing copy (when there is one)
  rename_invoice / invoice_owner (receipt_for_invoice only): rename the invoice only when this
            mailbox filed it - the connector cannot rename a teammate's file.
  reason:   plain words, for the report Notes
  evidence: compact field-by-field comparison (what an adjudicator needs, nothing more)

The script never says "new" when anything could be the same transaction: every unclear case is
"adjudicate", which goes to the Opus tie-breaker and, if still unclear, to the user.
"""
import argparse
import json
import re
import sys
from datetime import datetime

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from receipt_key import alnum, amount_cents, parse_date, vendor_token  # noqa: E402


def parse_desc(desc):
    d = {}
    if not desc or "KSA-RECEIPT" not in desc:
        return None
    for line in desc.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            d[k.strip().upper()] = v.strip()
    return d


def iso(s):
    dt = parse_date(s or "")
    return dt.strftime("%Y-%m-%d") if dt else ""


def item_words(s):
    return {w for w in re.findall(r"[a-z0-9]{3,}", (s or "").lower())} - {"the", "and", "for", "with"}


def items_relation(a, b):
    wa, wb = item_words(a), item_words(b)
    if not wa or not wb:
        return "absent"
    j = len(wa & wb) / max(1, len(wa | wb))
    return "agree" if j >= 0.5 else ("differ" if j < 0.2 else "partial")


def compare(rec, key, other):
    """other: dict with VENDOR, DATE, TOTAL, DOC, REF, CARD, ITEMS, TOKENS, GROUP, name, file_id"""
    ev = {}
    my_refs = {t for t in key.get("ref_tokens", [])}
    their_tokens = set((other.get("TOKENS") or "").split())
    their_refs = {"KSAREF" + alnum(r) for r in re.split(r"[,;]\s*", other.get("REF") or "") if alnum(r)}
    their_refs |= {t for t in their_tokens if t.startswith("KSAREF")}
    ev["ref"] = "same" if my_refs & their_refs else ("differ" if my_refs and their_refs else "absent")
    msg = key.get("msg_token")
    ev["message_id"] = "same" if msg and msg in their_tokens else "absent"
    ev["vendor"] = "same" if vendor_token(rec.get("vendor", "")) == vendor_token(other.get("VENDOR", "")) else "differ"
    ev["amount"] = "same" if amount_cents(rec.get("total")) == amount_cents(other.get("TOTAL")) else "differ"
    a, b = iso(rec.get("transaction_date")), iso(other.get("DATE"))
    ev["date"] = "absent" if not a or not b else ("same" if a == b else "differ")
    ca, cb = str(rec.get("card_last4") or ""), str(other.get("CARD") or "")
    ev["card"] = "absent" if not ca or not cb else ("same" if ca == cb else "differ")
    ev["items"] = items_relation(rec.get("items") if isinstance(rec.get("items"), str)
                                 else json.dumps(rec.get("items") or ""), other.get("ITEMS"))
    ev["their_doc"] = (other.get("DOC") or "receipt").lower()
    ev["my_doc"] = (rec.get("doc_type") or "receipt").lower()
    return ev


def decide(job):
    rec, key = job["record"], job["key"]
    candidates = []
    for h in job.get("hits", []):
        if h.get("in_archive") is False:
            continue
        d = parse_desc(h.get("description"))
        if d is None:
            # Hit with no KSA description: found through PDF text (raw ref), or a file saved by hand.
            candidates.append(("raw", h, None))
        else:
            d.update(name=h.get("name"), file_id=h.get("file_id"))
            candidates.append(("desc", h, d))
    for r in job.get("report_rows", []):
        d = {"VENDOR": r.get("vendor"), "DATE": r.get("transaction_date"), "TOTAL": r.get("total"),
             "DOC": r.get("doc_type"), "REF": r.get("ref"), "CARD": r.get("card_last4"),
             "ITEMS": r.get("notes", ""), "GROUP": r.get("group_id"), "name": r.get("file_name"),
             "file_id": None, "TOKENS": ""}
        candidates.append(("row", r, d))

    best = None
    order = {"already_saved_self": -1, "duplicate": 0, "receipt_for_invoice": 1, "adjudicate": 2, "new_near_match": 3}
    for kind, h, d in candidates:
        if kind == "raw":
            raw_refs = [r for r in re.split(r"[,;]\s*", rec.get("ref") or "") if alnum(r)]
            strong = any(len(alnum(r)) >= 6 for r in raw_refs)
            q = h.get("matched_query", "")
            ref_hit = any(r.strip() in q for r in raw_refs)
            res = {"decision": "adjudicate",
                   "reason": f"'{h.get('name')}' contains the {'order number' if ref_hit else 'search text'} "
                             f"but has no KSA key (filed by hand or not indexed)",
                   "match": {"file_id": h.get("file_id"), "name": h.get("name"), "group_id": None},
                   "evidence": {"matched_query": q, "strong_ref": strong and ref_hit}}
            if strong and ref_hit:
                res["decision"] = "duplicate"
                res["reason"] = f"order/ref number appears in '{h.get('name')}'"
        else:
            ev = compare(rec, key, d)
            m = {"file_id": d.get("file_id"), "name": d.get("name"), "group_id": d.get("GROUP")}
            same_email = (kind == "desc" and rec.get("gmail_message_id")
                          and d.get("GMAIL_ID") == rec.get("gmail_message_id")
                          and (d.get("FOUND_BY") or "").lower() == (rec.get("found_by") or "").lower())
            if same_email:
                res = {"decision": "already_saved_self",
                       "reason": "this email was already filed from this mailbox (resumed run)"}
            elif ev["ref"] == "same" or ev["message_id"] == "same":
                if ev["their_doc"] == "invoice" and ev["my_doc"] == "receipt":
                    owner = (d.get("FOUND_BY") or "").lower()
                    mine = bool(owner) and owner == (rec.get("found_by") or "").lower()
                    res = {"decision": "receipt_for_invoice", "reason": "receipt for an invoice already saved",
                           "invoice_owner": owner or None,
                           # The connector can only rename files this person created; a teammate's
                           # invoice is left as is and the pairing lives in the report and the
                           # receipt's own description (PAYS_GROUP).
                           "rename_invoice": mine}
                else:
                    res = {"decision": "duplicate",
                           "reason": "same " + ("order/ref number" if ev["ref"] == "same" else "email (Message-ID)")}
            elif ev["vendor"] == "same" and ev["amount"] == "same":
                if ev["ref"] == "differ" or ev["date"] == "differ" or ev["card"] == "differ" or ev["items"] == "differ":
                    res = {"decision": "new_near_match",
                           "reason": f"similar to {d.get('name')} (same vendor and amount; "
                                     + ", ".join(k for k in ("ref", "date", "card", "items") if ev[k] == "differ")
                                     + " differ)"}
                elif ev["date"] == "same" and ev["card"] == "same" and ev["items"] in ("agree", "absent", "partial"):
                    res = {"decision": "duplicate", "reason": "same vendor, date, amount and card"}
                else:
                    res = {"decision": "adjudicate",
                           "reason": "same vendor, amount" + (" and date" if ev["date"] == "same" else "")
                                     + " with nothing else to tell them apart"}
            else:
                continue
            res.update(match=m, evidence=ev)
        if best is None or order[res["decision"]] < order[best["decision"]]:
            best = res

    stem = (key.get("file_name_stem") or "").lower()
    if best is None or best["decision"] == "new_near_match":
        for n in job.get("folder_names", []):
            if stem and n.lower().startswith(stem):
                return {"decision": "adjudicate", "reason": f"'{n}' in the target folder has the same name stem "
                        "(may be a recent upload not yet searchable)", "match": {"name": n}, "evidence": {}}
    return best or {"decision": "new", "reason": "no existing copy found", "match": None, "evidence": {}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--job", required=True)
    a = ap.parse_args()
    print(json.dumps(decide(json.load(open(a.job)))))


if __name__ == "__main__":
    main()
