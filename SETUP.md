# Setting up the KSA receipt finder

For KSA team members. About 10 minutes, once. You need a paid Claude plan (Pro or higher) and edit access to the **KSA Business Documents** shared drive (ask Ken if you don't have it).

## 1. Add the plugin (claude.ai)

1. Open **claude.ai** and click **Customize**, then the **Plugins** tab.
2. Under **Personal plugins**, click **+** and choose **Add marketplace**.
3. Choose **Add from a repository** and paste: `https://github.com/JettStauver/ksa-receipts`
4. Find **ksa-receipts** in the list and turn it on.

Updates arrive on their own: when a new version is published here, your copy syncs to it. You never need to reinstall.

## 2. Connect Gmail and Google Drive

In a new chat, open the connectors menu and connect **Gmail** and **Google Drive** with your KSA Google account. (Optional: install **Claude in Chrome** for faster uploads.)

## 3. Run the setup check

In a new chat, type:

> set up the receipt finder

Claude checks your connectors and shared-drive access, creates your own settings and log folders, asks for the few things it needs (your home-office address, the last 4 digits of the cards you use for KSA), creates the Gmail answer labels, and offers to create your **nightly run**. Say yes. It picks a time overnight that doesn't clash with teammates.

## 4. First run

> file my receipts

(Every run does the same check, so if you skip setup, the first run will ask instead.) The first run looks at the last 30 days. It will ask you a few questions (business or personal? which card is this?) and offer to remember your answers. The more you answer early on, the less it asks later.

## 5. The backlog (optional)

> backfill my receipts

It works back through 6 years, one month at a time, newest first, and saves its place after every month. If you hit a usage limit or close the tab, just say **continue the backfill** later, in any chat. Ask **how far is the backfill?** any time.

## Day to day

- The nightly run files new receipts on its own and leaves anything uncertain as **NEEDS REVIEW** in `Receipt archive/<year>/Receipts Report <year>.xlsx`.
- To answer one, apply a Gmail label to that email: `Receipts/Business`, `Receipts/Personal`, `Receipts/Home Office` or `Receipts/Skip`. The next run files it.
- Never put full card numbers anywhere. The finder only uses the last 4 digits.
