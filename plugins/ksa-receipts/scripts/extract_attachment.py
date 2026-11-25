#!/usr/bin/env python3
"""Extract attachments from a Gmail RAW message.

Input: a file holding either
  - the JSON result of Gmail get_message(messageFormat=RAW) (any JSON containing a "raw" field), or
  - raw RFC 822 / MIME text, or
  - base64url-encoded MIME.
Writes each attachment into --out and prints JSON lines: {"path", "filename", "mime", "bytes", "sha256"}.
Use --name to keep only attachments whose filename matches (case-insensitive substring).
Also prints the RFC822 Message-ID header (useful for dedupe).
"""
import argparse
import base64
import email
import hashlib
import json
import os
import re
import sys
from email import policy


def find_raw(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("raw", "rawcontent", "raw_content") and isinstance(v, str):
                return v
            r = find_raw(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_raw(v)
            if r:
                return r
    return None


def to_mime_bytes(text: str) -> bytes:
    t = text.strip()
    try:
        obj = json.loads(t)
        raw = find_raw(obj)
        if raw:
            t = raw.strip()
    except json.JSONDecodeError:
        pass
    if re.match(r"^[A-Za-z0-9_\-+/=\s]+$", t[:2000]) and ":" not in t[:200]:
        s = re.sub(r"\s", "", t)
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s.replace("+", "-").replace("/", "_"))
    return t.encode("utf-8", "surrogateescape")


def safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "attachment"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", help="only attachments whose filename contains this text")
    a = ap.parse_args()

    with open(a.src, "r", encoding="utf-8", errors="surrogateescape") as f:
        mime = to_mime_bytes(f.read())
    msg = email.message_from_bytes(mime, policy=policy.default)
    os.makedirs(a.out, exist_ok=True)
    print(json.dumps({"message_id": msg.get("Message-ID", ""), "subject": msg.get("Subject", ""),
                      "from": msg.get("From", ""), "date": msg.get("Date", "")}))
    n = 0
    for part in msg.walk():
        fn = part.get_filename()
        if not fn or part.is_multipart():
            continue
        if a.name and a.name.lower() not in fn.lower():
            continue
        payload = part.get_payload(decode=True) or b""
        path = os.path.join(a.out, safe(fn))
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(path):
            path = f"{base}_{i}{ext}"
            i += 1
        with open(path, "wb") as out:
            out.write(payload)
        n += 1
        print(json.dumps({"path": path, "filename": fn, "mime": part.get_content_type(),
                          "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}))
    if n == 0:
        print(json.dumps({"warning": "no attachments found"}))
        sys.exit(2)


if __name__ == "__main__":
    main()
