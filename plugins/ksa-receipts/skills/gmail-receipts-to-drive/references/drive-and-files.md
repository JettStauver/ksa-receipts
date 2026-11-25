# Getting files out of Gmail and into Drive

**Standard path (v1.1):** `receipt-builder` helper agents (5 receipts each) download the vendor's original attachment byte-for-byte with Gmail's `download_gmail_attachment` tool, or build the transaction-record PDF (summary + the email's text) from a `PLAIN_TEXT` read, and stage the file locally. They never depend on `RAW`: on claude.ai there are no transcript files for `raw_from_transcript.py` to search, so an inline raw email cannot reach disk. Routes B/C below (raw email, printed HTML copy) remain for Claude Code, where large results are saved to files; the main run then uploads the staged files through Drive in Chrome. Raw emails never enter the main conversation, which keeps the run fast and its token use low. The steps below describe what the helper and the upload do; Route A (Gmail's "Add to Drive") is kept as an alternative for when helper agents are unavailable.

Load the `chrome-browser` skill before the first browser step of a run, and follow it (tab context first, work in a new tab, close it at the end).

## Route A - Chrome "Add to Drive" (primary)

Do this once per transaction that passed the dedupe check, after the destination folder and file name are known.

1. **Open the email.** In the run's Chrome tab, `navigate` to the message's full `viewUrl` from `get_message` (it must include the `|msg-...` part; a thread-only URL leaves Gmail on a blank pane). Wait ~4 seconds for the message to render before using `find`. Gmail must be signed in to the same account as the Gmail connector (the `authuser=` in the link). If a different account or a sign-in page appears, stop and ask the user to sign in; never enter a password.
2. **Find the attachment.** `find` or `read_page` for the attachment chip whose name matches the chosen file (prefer `Receipt-*` over `Invoice-*` when both exist). Note the exact displayed filename.
3. **Click "Add to Drive".** Hover the attachment chip; click the Drive icon / "Add to Drive" button (tooltip "Add to Drive" or "Save to Drive"). Take a screenshot to confirm the "Added to My Drive" (or similar) message. If Gmail offers "Organize in Drive", ignore it - placement is done next with the connector.
   - Do **not** click Download, Print, Delete, Archive, Reply, Forward, or anything else on the message.
   - Do not open links inside the email.
4. **Locate the new file in Drive.** `search_files` with `owner = 'me' and parentId = 'root' and title contains '<distinctive part of the filename>'`. Note: Drive sets the saved file's createdTime to the email's date, not the time of the click, so do not filter on createdTime. If several match, pick the one whose createdTime equals the email date. If none appears after two checks ~10 seconds apart, treat Route A as failed for this attachment.
5. **Confirm it is the receipt.** `read_file_content` on the new file; check vendor, amount, date and order number agree with the email. Use it to fill any fields the email body lacked.
6. **Place and rename.** `update_file` with `parentId` = destination category folder id and `title` = final file name (keep the original extension: `.pdf`, `.jpg`, `.png`). Then `update_file` again with `description` = the block from `receipt_key.py`.
   - If the move into the shared drive is refused, `copy_file` to the destination folder with the final title instead, set the description on the copy, and move the My Drive original into a My Drive folder named `Claude receipt staging` (search first, create if missing). Mention that folder in the final message so the user can empty it. Never trash it.
7. `get_file_metadata` to confirm parent, title, and description.

Photos of paper receipts (JPG/PNG) are saved as the original image - no conversion - so the file is exactly what was emailed.

## Route B - raw email fallback

Use only when Chrome is unavailable (extension not connected, unattended run with Chrome closed) or Route A failed for an attachment.

1. Fetch the message with `get_message` `messageFormat: "RAW"`.
2. If the app saved the large result to a file, run
   `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/extract_attachment.py <saved-result-path> --out <scratch-dir> [--name "<attachment filename>"]`.
   If the result came back inline, save it with `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/raw_from_transcript.py <message id> --out msg.raw.json` and run the same script on that file. Never retype a base64 block by hand.
3. Upload with **Upload through Drive in Chrome** (below). Only if Chrome is unavailable: `base64 -w0 file > file.b64`; `create_file` with `title`, `parentId`, `contentMimeType`, `disableConversionToGoogleType: true`, `base64Content` (slow - every byte passes through the conversation; keep to small files). Then set the description as above.
4. If this also fails or the file is too large, use Route C.

Route B is also fine as the main route when a run has many attachments: the file is byte-for-byte the one in the email, and it needs no clicks in Gmail.

Record which route was used in the report's Attachment column: `original attached (Chrome)`, `original attached (raw email)`, or the Route C value.

## Route C - transaction-record PDF

For emails with no attachment (the receipt is in the body), and as the last resort when the attachment cannot be captured.

The file is a one-page standard summary followed by a full printed copy of the original email, so the record is complete.

1. **Print the email.** `get_message` with `messageFormat: "RAW"`, save it as in Route B step 2 (`raw_from_transcript.py` when it came back inline), then
   `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/email_print_pdf.py msg.raw.json --gmail-url "<viewUrl>" --out email.pdf`
   This renders the email as it appears in the mail client (header block, HTML body, inline pictures) with headless Chromium, the same engine as Chrome's "Save as PDF". Nothing is downloaded to anyone's computer. Pictures hosted on the vendor's website cannot be loaded from the workspace; their descriptions appear in [brackets] and the header says how many were skipped.
2. **Build the summary and append the email.** Write the extracted record as JSON and run:
   `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/email_to_record_pdf.py --json record.json --email-pdf email.pdf --out "<file name>.pdf"`
   If step 1 fails, run the same command without `--email-pdf`; the summary then includes the plain-text body instead, and add `email copy not printed` to the report Notes.

JSON fields: `vendor`, `transaction_date`, `total`, `currency`, `doc_type`, `ref`, `payment_method` (brand + last 4 only), `items` (list of `{description, qty, amount}` or a string), `bill_to`, `ship_to`, `email_subject`, `email_from`, `email_date`, `email_to`, `gmail_url`, `body_text` (plain-text body, trimmed of tracking junk and unsubscribe footers), `found_by`, `notes`.

Upload it as in Route B step 3. Build all files for a run first, staged in scratch subfolders named after their destination category, then upload folder by folder. When used because an attachment could not be captured, set the Attachment column to `not captured - original attached in Gmail`.

## Upload through Drive in Chrome

Files built in the workspace (record PDFs, extracted attachments, the yearly reports) go into Drive through Drive's own upload, driven in Chrome. Nothing passes through the user's computer's Downloads, and nothing large passes through the conversation.

1. Stage the files in the session's scratchpad folder (the browser upload tool refuses other locations). Under 10 MB per call.
2. `navigate` the run's Chrome tab to the destination folder (`https://drive.google.com/drive/folders/<id>`). Uploads land in the folder that is open; moving files later inside the shared drive is refused, so always open the right folder first.
3. With `javascript_tool`, patch the page so Drive's hidden file input is exposed instead of opening the system file picker:
   `if(!window.__ksaPatched){const o=HTMLInputElement.prototype.click;HTMLInputElement.prototype.click=function(){if(this.type==='file'){this.id='ksa-drive-input';this.setAttribute('aria-label','KSA drive upload input');if(!this.isConnected){this.style.display='none';document.body.appendChild(this);}return;}return o.apply(this,arguments)};window.__ksaPatched=true;}`
   (A page reload removes the patch - repeat it after every `navigate`.)
4. Click **New** → **File upload**. No dialog opens. `find` "KSA drive upload input", then `file_upload` with that ref and the absolute paths of the files for this folder.
5. Wait until Drive's panel says "N uploads complete" before navigating (navigating early triggers "Leave site?" and cancels the rest). Uploads can be slow - allow ~15 seconds per file for larger batches.
6. Afterwards, `search_files` with `createdTime > '<start of upload>'` to get the new file ids, and compare each `fileSize` with the local file. Drive occasionally retries and creates a second copy with the same name: keep the first, rename the extra `DUPLICATE UPLOAD - please delete - <name>`, and tell the user (never trash it).
7. `update_file` each file's `description` with its `receipt_key.py` block.

## Folder creation

Always `search_files` for `title = '<name>' and parentId = '<parent>' and mimeType = 'application/vnd.google-apps.folder'` before creating. If two same-named folders exist (another user created one at the same moment), use the older one and tell the user about the twin; do not move or trash it.

## Renaming an invoice when its receipt arrives

Only when this mailbox filed the invoice (`dedupe_decide.py` says `rename_invoice: true`): `update_file` with the new `title` (append ` (paid - see receipt)` before the extension) and add `PAID_BY_GROUP: <group_id>` to its description. Same link, nothing deleted.

A teammate's invoice is never renamed - the connector refuses to edit a file someone else created. The receipt goes in the invoice's group with `PAYS_GROUP: <group_id>` in its own description, and the report shows the invoice row as `(paid - counted on receipt row)`.
