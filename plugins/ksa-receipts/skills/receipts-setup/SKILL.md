---
name: receipts-setup
description: First-time setup and health check for a KSA team member using the ksa-receipts plugin - checks Gmail and Drive connectors and shared-drive access, checks the _settings and _state folders, explains the Receipts/ Gmail labels, and sets up the nightly scheduled run that keeps their receipts filed. Use when someone says "set up receipts", "set up the receipt finder", "set up the nightly receipt run", "is my receipt setup working", or runs /receipts-setup.
model: sonnet
---

# Receipts setup

Get one person ready to run the receipt finder, then put it on a nightly schedule. Each check is quick; report results as a short checklist and fix what you can with the person's OK.

Folder ids are in `../gmail-receipts-to-drive/SKILL.md` ("Fixed settings").

## Checks

1. **Connectors.** Gmail and Google Drive must be connected. Load their tools with ToolSearch. If either is missing, tell the person to connect it from the connectors menu (search the registry and suggest it), then stop until it is.
2. **Who they are.** Get their email from the Gmail connector (`found_by`). The archive is shared, so this is how their runs are told apart.
3. **Shared-drive access.** Open `Receipt archive` by id and list one year folder. If it fails, they need edit access to the **KSA Business Documents** shared drive - tell them to ask whoever manages it (Ken). Stop until they have it.
4. **Their folders, settings, state and labels.** Do step 1.2 of `gmail-receipts-to-drive` exactly (it creates `_settings/<email>/`, `_state/<email>/` and the Gmail answer labels if missing, and asks for their home-office address and the last 4 of the cards they use). Explain the labels in one line each: they apply one to an email to answer a question the finder left in the report.
5. **History.** Run `state.py status` for them and say whether they have run before and how far any backfill got.
6. **Chrome (optional).** With Claude in Chrome connected, attachments upload faster and exactly as emailed. Without it, uploads go through the Drive connector - fine for nightly volumes.

## Nightly run

Offer to set it up. Use the session's scheduling tools (load them with ToolSearch; call it a "scheduled task"). Pick a time between 1 and 5 am in the person's time zone, staggered from teammates who already have one (check the other people's `_state/<email>/` `RUN ...` log times and leave at least 40 minutes between people, since they share the run lock). Ask only if the person cares about the time.

Scheduled task prompt (adjust the email):

> Run the ksa-receipts receipt finder (gmail-receipts-to-drive) for my mailbox in nightly mode, unattended: no questions - leave anything uncertain as NEEDS REVIEW in the report. Use the Drive connector for uploads if Chrome is not available. If another person holds the run lock, wait and retry as the plugin describes. When done, send me a short summary: counts saved, duplicates, and items needing my review with their Gmail links.

It does not need the person's computer unless they want Chrome uploads. Tell them in one sentence which approval setting the task got; if its runs will stop to ask for approvals, mention they can switch it to automatic approval in the task's settings.

Then offer the **backfill**: "Want to start filing the last 6 years? It works a month at a time and can stop and resume any time" (the `receipts-backfill` skill).

## Finish

A checklist with ✓ / ✗ per item, what was fixed, what the person still needs to do, and when the first nightly run will happen.

## Written instructions for new teammates

If someone asks for the instructions to share, give them `SETUP.md` from the plugin's repository (it says the same as this skill, step by step, for someone who has never used Claude plugins).
