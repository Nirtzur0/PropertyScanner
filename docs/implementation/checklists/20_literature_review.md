# Prompt-12 Literature Review Checklist

- [x] Revalidate Prompt-12 artifacts on 2026-02-09 manual rerun.
  - AC: artifact index, claim-table structure, and bibliography table remain consistent after latest prompt-pack sync.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after prompt-03 alignment gate post prompt-14 packet.
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after latest prompt-03 rerun (post prompt-13 post prompt-07 sequence).
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after latest prompt-03 rerun (post prompt-13 packet-4 refresh).
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after latest prompt-03 rerun (post prompt-13 packet).
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after latest prompt-03 rerun.
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate Prompt-12 artifacts after prompt-03 trust-risk refresh.
  - AC: artifact index, claim-table structure, and bibliography table remain consistent.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set during this rerun (rejected: outside bounded packet scope)

- [x] Revalidate existing Prompt-12 packet after router-triggered rerun.
  - AC: prior deliverables remain internally consistent and artifact mapping is still valid.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate && rg -n "^## [1-7]\\.|\\| Claim \\| Source \\|" docs/manifest/20_literature_review.md && rg -n "\\| Key \\| Authors \\| Year \\| Identifier \\|" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`, `docs/implementation/checklists/20_literature_review.md`
  - Docs: same as Files
  - Alternatives: expanding citation set in this rerun (rejected: outside bounded packet scope)

- [x] Define scope and bounded research question cluster (3-7 questions).
  - AC: Review documents explicit scope/regimes and active question cluster.
  - Verify: `rg -n "^## 2\. Scope and regimes|Active research question cluster" docs/manifest/20_literature_review.md`
  - Files: `docs/manifest/20_literature_review.md`
  - Docs: `docs/manifest/20_literature_review.md`
  - Alternatives: N/A

- [x] Curate >=10 primary sources with stable identifiers.
  - AC: Included bibliography has at least 10 DOI/arXiv-backed sources.
  - Verify: `rg -n "\| .*\| .*\| .*\| (DOI|arXiv)" docs/implementation/reports/20_literature_review_log.md`
  - Files: `docs/manifest/20_literature_review.md`, `docs/implementation/reports/20_literature_review_log.md`
  - Docs: same as Files
  - Alternatives: Excluded weakly sourced web posts and off-topic methods papers.

- [x] Capture load-bearing external sources in local artifact index.
  - AC: `docs/artifacts/index.json` contains artifact IDs used in the review/log.
  - Verify: `python3 prompts/scripts/web_artifacts.py --repo-root . validate`
  - Files: `docs/artifacts/index.json`, `docs/artifacts/README.md`
  - Docs: `docs/implementation/reports/20_literature_review_log.md`
  - Alternatives: Metadata-only capture chosen over full PDF blobs for this packet.

- [x] Extract decision-relevant claims with assumptions/evidence/confidence.
  - AC: Review includes a Key Claims table with required columns.
  - Verify: `rg -n "^\| Claim \| Source \| Assumptions \| Evidence \| Confidence \| Implications \|" docs/manifest/20_literature_review.md`
  - Files: `docs/manifest/20_literature_review.md`
  - Docs: `docs/manifest/20_literature_review.md`
  - Alternatives: N/A

- [x] Produce project-facing synthesis and explicit build/avoid guidance.
  - AC: Review has "What this means for this project" and proposed validation checklist.
  - Verify: `rg -n "^## 6\. What this means for this project|^## 7\. Proposed validation checklist" docs/manifest/20_literature_review.md`
  - Files: `docs/manifest/20_literature_review.md`
  - Docs: `docs/manifest/20_literature_review.md`
  - Alternatives: N/A

- [x] Update implementation status/worklog for this packet.
  - AC: Current packet appears in status snapshot and append-only worklog.
  - Verify: `rg -n "Prompt-12 Literature Validation Packet|prompt-12 literature validation" docs/implementation/00_status.md docs/implementation/03_worklog.md`
  - Files: `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Docs: same as Files
  - Alternatives: N/A
