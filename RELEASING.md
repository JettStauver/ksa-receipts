# Releasing a new version

Everyone's copy updates from this repository, so `main` must always work.

1. Make the change on a branch.
   - Category list → `plugins/ksa-receipts/skills/gmail-receipts-to-drive/references/categories.md` (and `data/vendor_hints.json` if vendors move).
   - Duplicate rules → change `scripts/dedupe_decide.py` **and** `references/dedupe.md` together, and add a case to `tests/selftest.py`.
   - Company facts (addresses, cards, vendor mappings, rules) are **not** released: they are titles in `Receipt archive/_settings/` in Drive.
2. `python3 -I plugins/ksa-receipts/tests/selftest.py` passes.
3. Bump the version in **both** `plugins/ksa-receipts/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` (GitHub checks they match). Patch = wording/fixes, minor = new behaviour, major = changes to Drive layout, state or report columns.
4. Add a line to `CHANGELOG.md`.
5. Merge to `main`. Copies sync to the new version.

Never commit real card numbers, addresses, emails or Drive exports. The repository is public.
