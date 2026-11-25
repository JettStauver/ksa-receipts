#!/usr/bin/env python3
"""Save a Gmail RAW message that came back inline in this session, without retyping it.

usage: raw_from_transcript.py MESSAGE_ID --out message.raw.json

Looks through this session's transcript files (~/.claude/projects/*/*.jsonl) and saved large
tool results (~/.claude/projects/*/*/tool-results/*.txt), newest first, for the
get_message(messageFormat=RAW) result with that message id and writes {"raw": "..."} to --out,
ready for email_print_pdf.py or extract_attachment.py. Exits 1 if it is not found (fetch the
message again with RAW, then re-run).
"""
import argparse
import glob
import json
import os
import re
import sys

RAW = r'(?:\\*)"raw(?:\\*)":(?:\\*)"([A-Za-z0-9_\-=]+)'


def pats(mid):
    # Anchor on this message's own "id" so a line holding several results (parallel calls)
    # never yields another message's raw. The id field comes just before "raw" in the result.
    q = r'(?:\\*)"'
    return [re.compile(q + r'id' + q + r':' + q + re.escape(mid) + q + r'(?:(?!' + q + r'id' + q + r':).){0,600}?' + RAW)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("message_id")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    # recursive: helper agents (subagents) keep their own transcripts in subfolders of the session
    root = os.path.expanduser("~/.claude/projects")
    files = sorted(glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
                   + glob.glob(os.path.join(root, "**", "tool-results", "*.txt"), recursive=True),
                   key=os.path.getmtime, reverse=True)
    PAT = pats(a.message_id)
    for f in files:
        found = None
        with open(f, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if a.message_id in line and "raw" in line:
                    for p in PAT:
                        m = p.search(line)
                        if m and len(m.group(1)) > len(found or ""):
                            found = m.group(1)
        if found:
            with open(a.out, "w") as out:
                json.dump({"raw": found}, out)
            print(json.dumps({"out": a.out, "chars": len(found), "source": f}))
            return
    print(json.dumps({"error": f"RAW result for {a.message_id} not found"}))
    sys.exit(1)


if __name__ == "__main__":
    main()
