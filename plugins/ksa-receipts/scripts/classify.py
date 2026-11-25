#!/usr/bin/env python3
"""Combine the evidence for each receipt into a business/personal + category proposal.

usage: classify.py --records records.json --settings settings.json [--hints data/vendor_hints.json]
                   --out classified.json

records.json: list of records from receipt-scout (keys used: gmail_message_id, vendor, sender_email,
  items, card_last4, bill_to, ship_to, service_address, kind, user_label, total, transaction_date).
settings.json: output of settings.py.

Each output record gets a "proposal":
  business_personal: Business | Personal | Home office (indirect) | null
  category:          a folder name from categories.md, "Personal", "Home Office - Indirect", or null
  confidence:        high | medium | low
  route:             file | sonnet | adjudicate | skip | review
  signals:           the evidence used, e.g. ["card 1234 business", "vendor hint Shipping & Freight"]
  conflicts:         evidence that disagrees
  rules_to_check:    free-text RULE settings that mention this vendor (a model must read them)

Routing, so the cheapest capable step decides:
  high   -> file (no model judgment needed)
  medium -> sonnet (one missing piece; Sonnet decides with the record + rules)
  low    -> adjudicate when evidence conflicts (Opus decides or writes the question for the user);
            sonnet when there is simply no evidence (Sonnet decides the obvious ones, escalates the rest)
A Gmail user label is always final (high). Non-receipts (kind order_ack/shipping/marketing/
ksa_issued) are routed to skip or review without classification.
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# A home address on an ordinary purchase (Steam, Apple, Amazon shipped home) says nothing about
# home-office use. It only counts for household bills: utilities, internet, lawn, home repairs.
HOUSEHOLD = re.compile(r"(?i)\b(electric\w*|energy|power|water|gas|utilit\w+|trash|waste|sewer|refuse|"
                       r"internet|fiber|broadband|cable|lawn|landscap\w*|pest|hvac|plumb\w*|roof\w*|"
                       r"city of|municipal|coserv|atmos|oncor|txu|reliant|spectrum|xfinity|comcast|"
                       r"frontier|hoa|homeowners)\b")
DEFAULT_HINTS = os.path.join(HERE, "..", "data", "vendor_hints.json")

LABELS = {
    "receipts/business": ("Business", None),
    "receipts/personal": ("Personal", "Personal"),
    "receipts/home office": ("Home office (indirect)", "Home Office - Indirect"),
    "receipts/home-office": ("Home office (indirect)", "Home Office - Indirect"),
    "receipts/skip": (None, None),
}


def norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9&+ ]", " ", (s or "").lower())).strip()


def words_match(needle, hay):
    return re.search(r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])", hay) is not None


def address_hit(text, addrs):
    t = (text or "").lower()
    for a in addrs:
        k = a.get("key")
        if k and k.split()[0] in t and k.split()[1] in t:
            return a["text"]
    return None


def classify(rec, st, hints):
    sig, conf, rules = [], [], []
    kind = (rec.get("kind") or "").lower()
    label = (rec.get("user_label") or "").lower().strip()

    if label in LABELS:
        bp, cat = LABELS[label]
        if label == "receipts/skip":
            return dict(business_personal=None, category=None, confidence="high", route="skip",
                        signals=["user label Receipts/Skip"], conflicts=[], rules_to_check=[])
        route = "file" if cat else "sonnet"  # Business label still needs a category
        hint_cat = _hint(rec, hints, st)[0] if not cat else None
        if hint_cat:
            cat, route = hint_cat, "file"
        return dict(business_personal=bp, category=cat, confidence="high" if cat else "medium",
                    route=route, signals=[f"user label {rec.get('user_label')}"], conflicts=[],
                    rules_to_check=[])

    if kind in ("marketing", "shipping", "ksa_issued", "quote"):
        return dict(business_personal=None, category=None, confidence="high", route="skip",
                    signals=[f"kind {kind}"], conflicts=[], rules_to_check=[])
    if kind in ("order_ack", "packing_slip_no_price"):
        return dict(business_personal=None, category=None, confidence="high", route="review",
                    signals=[f"kind {kind} - not proof of payment"], conflicts=[], rules_to_check=[])
    if kind not in ("receipt", "invoice", "refund", "customer_payment", "forwarded_photo"):
        return dict(business_personal=None, category=None, confidence="low", route="adjudicate",
                    signals=[f"kind '{kind or 'missing'}' - is this a record to keep?"], conflicts=[], rules_to_check=[])
    if kind == "customer_payment":
        return dict(business_personal="Business", category="Deposited Payment Records",
                    confidence="medium", route="sonnet", signals=["kind customer_payment"],
                    conflicts=[], rules_to_check=[])

    votes = []  # (bp, weight, why)
    card = str(rec.get("card_last4") or "").strip()
    if card and card in st.get("cards", {}):
        k = st["cards"][card]["kind"]
        votes.append(("Business" if k == "business" else "Personal", 3, f"card {card} {k}"))
    elif card:
        sig.append(f"card {card} not in _settings")

    addr_text = " ".join(str(rec.get(k) or "") for k in ("bill_to", "ship_to", "service_address"))
    biz = address_hit(addr_text, st.get("addresses", {}).get("business", []))
    home = address_hit(addr_text, st.get("addresses", {}).get("home-office", []))
    if biz:
        votes.append(("Business", 2, f"address matches business ({biz})"))
    household = bool(HOUSEHOLD.search(" ".join(str(rec.get(k) or "") for k in ("vendor", "items", "email_subject"))))
    home_service = address_hit(str(rec.get("service_address") or ""), st.get("addresses", {}).get("home-office", []))
    if home and (household or home_service):
        votes.append(("Home office (indirect)", 2, f"household bill at home-office address ({home})"))
    elif home:
        sig.append("bill/ship-to is the home address (ordinary purchase - not counted as home office)")
        home = None
    if re.search(r"(?i)ks\s*analytical|ksanalytical", addr_text):
        votes.append(("Business", 2, "bill/ship-to names KS Analytical"))

    hint_cat, hint_bp, hint_note, override = _hint(rec, hints, st)
    if override:
        sig.append(override)
    if hint_cat or hint_bp:
        sig.append(f"vendor hint {hint_cat or ''}{(' / ' + hint_bp) if hint_bp else ''}".strip())
    if hint_bp:
        votes.append((hint_bp, 2 if override else 1, f"vendor hint {hint_bp}"))
    if hint_note:
        sig.append("note: " + hint_note)

    vt = norm(rec.get("vendor"))
    for r in st.get("rules", []):
        rn = norm(r)
        if vt and any(w in rn for w in vt.split() if len(w) > 2):
            rules.append(r)

    sig += [v[2] for v in votes]
    tally = {}
    for bp, w, _ in votes:
        tally[bp] = tally.get(bp, 0) + w
    ranked = sorted(tally.items(), key=lambda x: -x[1])
    bp = ranked[0][0] if ranked else None
    if len(ranked) > 1:
        conf += [f"{b} ({w})" for b, w in ranked]

    category = None
    if bp == "Personal":
        category = "Personal"
    elif bp == "Home office (indirect)":
        category = "Home Office - Indirect"
    elif bp == "Business":
        category = hint_cat
    # Business card + home address -> could be a home-office bill paid with business funds
    if biz is None and home and bp == "Business":
        conf.append("business evidence but home-office address")

    top = ranked[0][1] if ranked else 0
    if conf:
        confidence = "low"
    elif bp and category and top >= 3:
        confidence = "high"
    elif bp and category and top >= 2 and len(votes) >= 2:
        confidence = "high"
    elif bp:
        confidence = "medium"
    else:
        confidence = "low"
    if rules and confidence == "high":
        confidence = "medium"  # a free-text rule mentions this vendor: a model must read it
    if hint_note and confidence == "high" and not override and not (card and card in st.get("cards", {})):
        confidence = "medium"

    if kind == "refund" and confidence == "high":
        confidence = "medium"  # a refund must be paired with its purchase: a model checks it
    route = {"high": "file", "medium": "sonnet", "low": "adjudicate"}[confidence]
    if confidence == "low" and not conf:
        route = "sonnet"  # no evidence at all (not conflicting evidence): Sonnet tries first, escalates if torn
    return dict(business_personal=bp, category=category, confidence=confidence, route=route,
                signals=sig, conflicts=conf, rules_to_check=rules)


def _hint(rec, hints, st):
    vt = norm(rec.get("vendor"))
    dom = (rec.get("sender_email") or "").lower().split("@")[-1]
    for v in st.get("vendors", []):
        if norm(v["vendor"]) and (norm(v["vendor"]) in vt or norm(v["vendor"]).replace(" ", "") in dom):
            tgt = v["target"]
            if tgt.lower() == "personal":
                return None, "Personal", None, f"VENDOR setting: {v['vendor']} -> Personal"
            return tgt, "Business", None, f"VENDOR setting: {v['vendor']} -> {tgt}"
    for h in hints:
        for m in h["match"]:
            if words_match(norm(m), vt) or (m.replace(" ", "").replace("-", "") in dom.replace("-", "")):
                return h.get("category"), h.get("bp"), h.get("note"), None
    return None, None, None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", required=True)
    ap.add_argument("--settings", required=True)
    ap.add_argument("--hints", default=DEFAULT_HINTS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    recs = json.load(open(a.records))
    st = json.load(open(a.settings))
    hints = json.load(open(a.hints))["hints"]
    out, counts = [], {}
    for r in recs:
        r = dict(r)
        r["proposal"] = classify(r, st, hints)
        counts[r["proposal"]["route"]] = counts.get(r["proposal"]["route"], 0) + 1
        out.append(r)
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({"records": len(out), "routes": counts}))


if __name__ == "__main__":
    main()
