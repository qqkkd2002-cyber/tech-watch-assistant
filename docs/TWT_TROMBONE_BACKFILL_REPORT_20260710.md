# TROMBONE Backfill Report - 2026-07-10

## Summary

- Scope: resumed the interrupted `review_queue` expansion after tightening the TROMBONE developer-tool criteria.
- Completed this run: 147 evidence-sufficient candidates.
- Remaining evidence-sufficient candidates: 0.
- Remaining evidence-insufficient candidates: 353, intentionally kept in `review_queue`.
- User-protected data preserved: `editor_judgments` 155, `manual_saved` 15.
- New automatic classification was not enabled.

## Batch Results

| Batch result file | Completed | Work | Learning | Noise | Review queue |
|---|---:|---:|---:|---:|---:|
| `.state/ollama_backfill_execute_20260710_113013.json` | 50 | 24 | 21 | 3 | 2 |
| `.state/ollama_backfill_execute_20260710_113848.json` | 50 | 21 | 22 | 4 | 3 |
| `.state/ollama_backfill_execute_20260710_114833.json` | 47 | 18 | 21 | 8 | 0 |
| Total | 147 | 63 | 64 | 15 | 5 |

No new 90/95 confidence clustering appeared in the three resumed batches.

## Final LLM Distribution

| Bucket | Count | Confidence range | Average confidence |
|---|---:|---:|---:|
| Work signal | 113 | 71-95 | 80.2 |
| Learning signal | 188 | 71-88 | 76.6 |
| Noise | 77 | 70-88 | 78.4 |
| Review queue | 37 | 65-65 | 65.0 |

The remaining two confidence-95 items were pre-existing high-confidence work signals:

- `NH농협은행, 차세대 금융거래 연결망 시스템 개발 본격 착수`
- `금융권 AI 도입 시 내부통제 체계 선제적 정비 필수`

## Developer-Tool Criteria Tightening

Added a stricter TROMBONE rule:

- Developer-tool updates are not work signals merely because they mention GitHub, Copilot, GitLab, or another tool.
- Minor UI/convenience features, repository/issue settings, desktop point releases, billing/credit/budget changes, and free/student model policy changes should be learning or noise unless they materially affect development, deployment, operations, governance, audit, or workflow control.
- CI/CD runners, deployment pipelines, release/change gates, security scanning enforcement, developer workflow automation, and AI agents integrated into the software lifecycle remain work signals.

## Down-classified Items

| New bucket | Confidence | Item |
|---|---:|---|
| Noise | 82 | `[GitHub Changelog] Saved views for repository issues - Public Preview and adjustable row heights in projects` |
| Noise | 82 | `[GitHub Changelog] GitHub Desktop 3.6: Worktrees and deeper Copilot integration` |
| Noise | 82 | `[GitHub Changelog] Restrict issue creation to collaborators only` |
| Learning signal | 78 | `[GitHub Changelog] Cost centers now support AI credit pools` |
| Learning signal | 78 | `[GitHub Changelog] Hard budget limits now available for GitHub Advanced Security` |
| Learning signal | 78 | `[GitHub Changelog] Changes to model selection for Free and Student plans` |
| Learning signal | 78 | `[GitHub Changelog] Claude Opus 4.8 (fast mode) is now in preview for GitHub Copilot` |
| Learning signal | 78 | `[GitHub Changelog] Claude Sonnet 5 is generally available for GitHub Copilot` |
| Learning signal | 78 | `[GitHub Changelog] Upcoming deprecation of Gemini 2.5 Pro and Gemini 3 Flash` |

Down-classified total: 9.

## Boundary Work Signals To Review Later

These remain work signals because they connect to CI/CD, security enforcement, code review, AI-agent workflow, supply-chain controls, or measurable developer workflow changes. They are worth a quick later review, but they are not the same class as saved views, desktop point releases, or credit policy.

- `[GitHub Changelog] Bot-created pull requests can run workflows if approved`
- `[Azure DevOps Blog] Copilot Autofix for GitHub Advanced Security for Azure DevOps`
- `[GitHub Changelog] Dedicated security review command now available in Copilot CLI`
- `[GitHub Changelog] Upcoming breaking changes for npm v12`
- `[Azure DevOps Blog] Copilot Code Reviews for Azure Repos`
- `[GitHub Changelog] Periodic code scanning of inactive repositories`
- `[GitHub Changelog] Fix with Copilot for failing Actions now in Pro, Pro+, and Max`
- `[GitHub Changelog] Agent tasks REST API now available for Copilot Pro, Pro+, and Max`
- `[GitHub Changelog] Copilot Memory has more controls for deletion, scope, and the Copilot CLI`
- `[GitHub Changelog] CodeQL 2.25.5 improves query accuracy for GitHub Actions`
- `[GitHub Changelog] More control over your GitHub-hosted runners`
- `[GitHub Changelog] Copilot agent session streaming is now in public preview`

## Guardrail Checks

- `editor_judgments` remained 155.
- `manual_saved` remained 15.
- The backfill wrote only unconfirmed AI classifications in `ai_editor_reviews`.
- Evidence-insufficient items remained in `review_queue`.
- New automatic classification remains off.
