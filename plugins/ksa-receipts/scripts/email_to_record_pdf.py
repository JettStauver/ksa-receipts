#!/usr/bin/env python3
"""Make a PDF for a receipt that has no usable attachment.

  --json record.json --out file.pdf [--email-pdf email.pdf]
        Transaction record built from an email (see drive-and-files.md for fields). With --email-pdf
        (made by email_print_pdf.py) the full printed email is appended after the summary page.
  --image photo.jpg --out file.pdf    Wrap a photo/scan of a paper receipt in a one-page PDF
"""
import argparse
import json
import os
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)


def p(text, style):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def record_pdf(rec, out, has_email=False):
    ss = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.grey)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=9.5, leading=12)
    body = ParagraphStyle("body", parent=ss["Code"], fontSize=7.5, leading=9.5)
    doc = SimpleDocTemplate(out, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            title=f"Transaction record - {rec.get('vendor','')}")
    kind = "INVOICE (no payment confirmation found)" if rec.get("doc_type") == "invoice" else "Receipt / payment"
    story = [
        Paragraph("Transaction Record (generated from email)", ss["Title"]),
        p("Created by Claude from the email below because no receipt file was attached or retrievable. "
          "The original email remains in Gmail at the link shown.", small),
        Spacer(1, 10),
    ]
    rows = [
        ("Vendor", rec.get("vendor")),
        ("Transaction date", rec.get("transaction_date")),
        ("Total", f"{rec.get('currency','USD')} {rec.get('total','')}"),
        ("Document type", kind),
        ("Order / invoice / ref no.", rec.get("ref")),
        ("Payment method", rec.get("payment_method")),
        ("Bill to", rec.get("bill_to")),
        ("Ship to", rec.get("ship_to")),
        ("Notes", rec.get("notes")),
    ]
    t = Table([[p(k, cell), p(v, cell)] for k, v in rows if v], colWidths=[1.8 * inch, 5.1 * inch])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F4F7")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 12)]

    items = rec.get("items")
    if items:
        story.append(Paragraph("Items", ss["Heading3"]))
        if isinstance(items, list):
            data = [[p("Description", cell), p("Qty", cell), p("Amount", cell)]]
            for it in items:
                if isinstance(it, dict):
                    data.append([p(it.get("description"), cell), p(it.get("qty", ""), cell),
                                 p(it.get("amount", ""), cell)])
                else:
                    data.append([p(it, cell), "", ""])
            it_t = Table(data, colWidths=[4.6 * inch, 0.8 * inch, 1.5 * inch], repeatRows=1)
            it_t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                                      ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7"))]))
            story.append(it_t)
        else:
            story.append(p(items, cell))
        story.append(Spacer(1, 12))

    story.append(Paragraph("Source email", ss["Heading3"]))
    src = [("Subject", rec.get("email_subject")), ("From", rec.get("email_from")),
           ("To", rec.get("email_to")), ("Date", rec.get("email_date")),
           ("Gmail link", rec.get("gmail_url")), ("Found by", rec.get("found_by"))]
    st = Table([[p(k, cell), p(v, cell)] for k, v in src if v], colWidths=[1.8 * inch, 5.1 * inch])
    st.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                            ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [st, Spacer(1, 10)]
    if has_email:
        story.append(p("The complete original email follows on the next page(s).", cell))
    elif rec.get("body_text"):
        story.append(Paragraph("Email body (text)", ss["Heading3"]))
        story.append(Preformatted(str(rec["body_text"])[:20000], body, maxLineLength=110))
    story += [Spacer(1, 10), p(f"Record generated {datetime.now():%Y-%m-%d %H:%M}", small)]
    doc.build(story)


def image_pdf(img_path, out):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(img_path).getSize()
    maxw, maxh = 7.2 * inch, 9.6 * inch  # frame minus padding
    scale = min(maxw / iw, maxh / ih)
    doc = SimpleDocTemplate(out, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            title=os.path.basename(img_path))
    doc.build([Image(img_path, width=iw * scale, height=ih * scale)])


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--json")
    g.add_argument("--image")
    ap.add_argument("--out", required=True)
    ap.add_argument("--email-pdf", help="printed email to append after the summary")
    a = ap.parse_args()
    if a.json:
        record_pdf(json.load(open(a.json)), a.out, has_email=bool(a.email_pdf))
        if a.email_pdf:
            from pypdf import PdfWriter
            w = PdfWriter()
            for f in (a.out, a.email_pdf):
                w.append(f)
            with open(a.out, "wb") as fh:
                w.write(fh)
    else:
        image_pdf(a.image, a.out)
    print(a.out, os.path.getsize(a.out), "bytes")


if __name__ == "__main__":
    main()
