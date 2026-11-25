# Benchmark - 2026-11-24 (read-only dry run)

16 real emails from one mailbox (30 days: Apple receipts and a refund, campus dining paid with meal swipes, Best Buy, Steam, Epic, a forwarded AWS bill, AppleCare notices, marketing). Nothing was written to Gmail or Drive. Drive dedupe, PDF building and upload were not part of this test.

| Pipeline | Tokens (incl. each agent's fixed start-up cost) | Result |
|---|---|---|
| v0.11 style: one Sonnet reads and decides everything | 115k Sonnet | Refund labelled "other"; guessed a business category (Insurance) for a personal AppleCare plan |
| v1.0, brand-new user (no settings) | 205k Haiku + 83k Opus | Refund and meal-swipe charges extracted correctly; 13 items to Opus, 6 sensible questions (3 were the same unknown card) |
| v1.0 after one `CARD` setting + revised routing | Haiku as above + ~76k Sonnet + Opus for 3 items | 2 auto-filed, 8 decided by Sonnet (identical to Opus's answers), 3 to Opus |

What the test changed in the plugin:
- Scout gained `refund` and `other` kinds (Haiku had filed a refund as a purchase); a missing kind is never filed.
- Scout re-reads with FULL_CONTENT when the plain-text body is only links (Best Buy, Epic, Steam showed no amount).
- Items with no evidence now go to Sonnet first; Opus only gets conflicts and what Sonnet escalates.
- One unknown card is asked once, then classify re-runs (it settled 3 of Opus's 6 questions).
- Scout batches went from 8 to 20 emails: each agent costs ~55-60k tokens just to start, so a 16-email test overstates per-email cost.

At this size v1.0 is not cheaper in raw tokens - agent start-up dominates. The savings come with volume: the old design reads every email into one growing Sonnet conversation, so cost rises faster than the email count (and a month of backfill would not fit). In v1.0 the coordinator's context stays small, Haiku's per-email cost is about 5k tokens, and Opus runs once per month with only the hard cases. At the usual price ratio (Haiku : Sonnet : Opus ≈ 1 : 3 : 5), a 100-email month comes out at roughly half the cost of the old approach, with better accuracy. Re-measure on the first real backfill month.

## 2026-11-24 - first real month and builder re-measure (v1.1)

October 2026 backfill against a test archive: 15 candidates, 7 filed, 5 needing review. Helper-agent tokens were 1.2M (1.05M Haiku + 152k Opus), and PDF building was 724k of that (60%), because v1.0 started one builder agent per receipt at about 80-150k each.

v1.1 re-measure, read-only, using 5 body-only receipts in one builder agent: **102k tokens in total, about 20k per receipt (was about 100k)**. All 5 were built and checked against the extraction. A Steam receipt with the amount only in the HTML got its amount and invoice number on a re-run once the re-read rule was tightened. At v1.1 rates the October month would need roughly 0.6M helper tokens instead of 1.2M.
