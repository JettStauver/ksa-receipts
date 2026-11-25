#!/usr/bin/env python3
"""Print a whole email to PDF, the way it looks in the mail client ("print to PDF").

usage: email_print_pdf.py RAW_FILE --out email.pdf [--gmail-url URL]

RAW_FILE: the result of Gmail get_message(messageFormat=RAW) saved to a file (JSON with a "raw"
field), raw RFC 822 text, or base64url MIME (same inputs as extract_attachment.py).

Builds an HTML page with the email header block (From, To, Cc, Date, Subject, attachment names)
followed by the HTML body (or the plain-text body when there is no HTML part), with inline (cid:)
images embedded, and prints it to a Letter-size PDF with headless Chromium - the same engine
Chrome uses for "Save as PDF". Nothing is downloaded to the user's computer.

Remote images (logos and pictures hosted on the vendor's web server) cannot be fetched from this
workspace; they are left blank and the header block says so. Scripts and remote requests are
blocked. Prints JSON: {"out", "pages", "bytes", "remote_images_skipped"}.
"""
import argparse
import base64
import email
import html
import json
import os
import re
import sys
from email import policy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_attachment import to_mime_bytes  # noqa: E402

CSS = """
*{font-family:Arial,Helvetica,sans-serif !important}
body{font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#202124;margin:0}
.ksa-hdr{border-bottom:2px solid #1F3864;padding:0 0 8px;margin:0 0 14px}
.ksa-hdr h1{font-size:18px;margin:0 0 6px}
.ksa-hdr table{border-collapse:collapse;font-size:12px}
.ksa-hdr td{padding:1px 8px 1px 0;vertical-align:top}
.ksa-hdr td.k{color:#5f6368;white-space:nowrap}
.ksa-note{font-size:10.5px;color:#5f6368;margin-top:6px}
.ksa-body img{max-width:100%;height:auto}
.ksa-body table{max-width:100% !important}
.ksa-noimg{color:#80868b;font-size:11px;font-style:italic}
pre.ksa-plain{white-space:pre-wrap;font-family:Arial,Helvetica,sans-serif;font-size:13px}
"""


def part_text(part):
    try:
        return part.get_content()
    except Exception:
        payload = part.get_payload(decode=True) or b""
        return payload.decode(part.get_content_charset() or "utf-8", "replace")


def build_html(msg, gmail_url=None):
    html_body, text_body, cids, attach_names = None, None, {}, []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        disp = (part.get_content_disposition() or "").lower()
        cid = (part.get("Content-ID") or "").strip("<> ")
        if ctype == "text/html" and disp != "attachment" and html_body is None:
            html_body = part_text(part)
        elif ctype == "text/plain" and disp != "attachment" and text_body is None:
            text_body = part_text(part)
        elif ctype.startswith("image/") and cid:
            data = part.get_payload(decode=True) or b""
            cids[cid] = f"data:{ctype};base64,{base64.b64encode(data).decode()}"
            if disp == "attachment" and part.get_filename():
                attach_names.append(part.get_filename())
        elif part.get_filename():
            attach_names.append(part.get_filename())

    remote = 0
    if html_body:
        body = re.sub(r"(?is)<script.*?</script>", "", html_body)
        body = re.sub(r"(?i)cid:([^\"'\s>)]+)", lambda m: cids.get(m.group(1), m.group(0)), body)
        remote = 0

        def swap(m):  # remote images can't load here: show their alt text instead of a broken icon
            nonlocal remote
            remote += 1
            alt = re.search(r"(?i)\balt=[\"']([^\"']*)", m.group(0))
            return f'<span class="ksa-noimg">[image: {html.escape(alt.group(1))}]</span>' if alt and alt.group(1).strip() else ""
        body = re.sub(r"(?is)<img[^>]+src=[\"']?https?://[^>]*>", swap, body)
        body_html = f'<div class="ksa-body">{body}</div>'
    else:
        body_html = f'<pre class="ksa-plain">{html.escape(text_body or "(no message body)")}</pre>'

    rows = [("From", msg.get("From")), ("To", msg.get("To")), ("Cc", msg.get("Cc")),
            ("Date", msg.get("Date")), ("Subject", msg.get("Subject")),
            ("Attachments", ", ".join(attach_names) if attach_names else None),
            ("Gmail link", gmail_url)]
    hdr = "".join(f'<tr><td class="k">{k}</td><td>{html.escape(str(v))}</td></tr>' for k, v in rows if v)
    note = "Full copy of the original email, printed to PDF."
    if remote:
        note += f" {remote} image(s) hosted on the sender's website could not be loaded; their descriptions are shown in [brackets]."
    page = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"<div class='ksa-hdr'><h1>{html.escape(str(msg.get('Subject') or 'Email'))}</h1>"
            f"<table>{hdr}</table><div class='ksa-note'>{html.escape(note)}</div></div>"
            f"{body_html}</body></html>")
    return page, remote


def print_pdf(page_html, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(java_script_enabled=False)
        pg = ctx.new_page()
        pg.route("**/*", lambda route: route.abort() if route.request.url.startswith("http") else route.continue_())
        pg.set_content(page_html, wait_until="load", timeout=30000)
        pg.emulate_media(media="print")
        pg.pdf(path=out, format="Letter", print_background=True,
               margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"})
        browser.close()
    trim_blank_tail(out)


def trim_blank_tail(path):
    """Drop trailing pages with no text and no images (email spacer rows and tracking pixels)."""
    from pypdf import PdfReader, PdfWriter
    r = PdfReader(path)
    n = len(r.pages)
    while n > 1 and not (r.pages[n - 1].extract_text() or "").strip() and not r.pages[n - 1].images:
        n -= 1
    if n < len(r.pages):
        w = PdfWriter()
        for p in r.pages[:n]:
            w.add_page(p)
        w.write(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gmail-url")
    a = ap.parse_args()
    raw = to_mime_bytes(open(a.src, encoding="utf-8", errors="surrogateescape").read())
    msg = email.message_from_bytes(raw, policy=policy.default)
    page, remote = build_html(msg, a.gmail_url)
    print_pdf(page, a.out)
    from pypdf import PdfReader
    json.dump({"out": a.out, "pages": len(PdfReader(a.out).pages), "bytes": os.path.getsize(a.out),
               "remote_images_skipped": remote}, sys.stdout)
    print()


if __name__ == "__main__":
    main()
