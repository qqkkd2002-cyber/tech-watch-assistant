# TWT v2 - AI Editorial Intelligence

## One-Line Concept

Tech Watch Tracker v2 is not a mode.

It is the app's upgraded operating model:

1. The app continuously collects technology and competitor signals.
2. AI prepares a first editorial draft by grouping collected items into insight candidates.
3. The user acts as editor-in-chief, approving, correcting, or rejecting those candidates.
4. The app learns from those decisions and improves future dashboards, alerts, and reports.

## Product Positioning

v1 is a collection and reporting assistant.

v2 should become an editorial intelligence assistant.

The user should not manually inspect every feed card. That recreates the old research burden. Instead, AI should first organize the collected volume into a short editorial agenda.

The user's role is not "tag every article."

The user's role is:

- approve good candidates
- move items to the right bucket
- reject noise
- mark what must influence reports
- teach the assistant what "important" means for this team

## Core Product Flow

```text
Raw collection
↓
AI first editorial classification
↓
Insight candidate buckets
↓
User approval / correction / rejection
↓
Learning signal
↓
Better prioritization, reports, and alerts
```

## Main Screen Direction

The v2 entry point should be a dashboard-level section, not a separate optional feature.

Recommended user-facing name:

**인사이트 후보**

This section should appear near the top of the dashboard and show what AI thinks deserves editorial attention.

Example:

```text
인사이트 후보

[전략 보고서 후보 6]
[경쟁사 주시 후보 4]
[제품/솔루션 아이디어 후보 3]
[제안/RFP 근거 후보 5]
[노이즈 가능성 높음 18]
```

Each bucket contains cards with:

- title
- source / competitor / keyword
- published date and collected date
- current AI summary status
- why AI placed it in this bucket
- confidence or score
- quick editor actions

## AI First Editorial Buckets

Initial buckets:

- `strategy_report`: 전략 보고서 후보
- `watch_competitor`: 경쟁사 주시 후보
- `product_idea`: 제품/솔루션 아이디어 후보
- `rfp_evidence`: 제안/RFP 근거 후보
- `important_signal`: 중요 신호 후보
- `check_only`: 확인만 필요
- `likely_noise`: 노이즈 가능성 높음

AI can assign one primary bucket and optional secondary buckets.

## AI Review Fields

The system should store AI's first editorial judgment separately from the user's final judgment.

Proposed table:

```text
ai_editor_reviews
- id
- profile_id
- item_type: doc | trend
- item_id
- primary_bucket
- secondary_buckets
- score
- confidence
- reason
- related_theme
- created_at
- updated_at
```

This is the assistant's first draft.

The existing `editor_judgments` table remains useful as the user's correction and learning signal.

## User Editorial Actions

The user should mainly review AI buckets, not raw feed cards.

Initial actions:

- `approve`: AI classification is correct
- `move_to_strategy_report`
- `move_to_watch_competitor`
- `move_to_product_idea`
- `move_to_rfp_evidence`
- `mark_important`
- `mark_later`
- `mark_noise`

Shortcut labels can still map to existing internal labels:

- `important`
- `report_candidate`
- `watch_competitor`
- `product_idea`
- `rfp_evidence`
- `later`
- `noise`

## How This Differs From v1 Starred Items

Starred items are manual bookmarks.

v2 editorial intelligence is a feedback loop:

- AI recommends
- user corrects
- app learns
- reports prioritize approved signals
- noise is suppressed over time

The star/archive behavior should remain, but it should no longer be the main way to create insight.

## MVP Roadmap

### MVP 1 - Keep The Current Foundation

Already started:

- `editor_judgments` table
- `/api/editor/queue`
- `/api/editor/learning`
- `/api/editor/judgments`

This stores user decisions and can support the learning layer.

### MVP 2 - Add AI Editorial Review Storage

Add `ai_editor_reviews`.

This stores AI's first classification:

- bucket
- score
- reason
- theme
- confidence

### MVP 3 - Generate AI Editorial Reviews

Create a lightweight background task or manual button:

**AI 후보 분류**

It should classify recent or pending items into buckets.

The first version can process:

- latest 30 docs
- latest 50 trends
- items without an existing AI editorial review

### MVP 4 - Dashboard Insight Candidates

Add an `인사이트 후보` section on the dashboard.

It should group reviewed items by AI bucket and show the strongest candidates first.

The user can approve or correct from this section.

### MVP 5 - Reports Use Approved Signals

Weekly/monthly reports should prioritize:

- approved `strategy_report`
- approved `important_signal`
- `report_candidate`
- `rfp_evidence`
- `watch_competitor`

Noise should be excluded unless explicitly searched.

### MVP 6 - Learning Summary

Show what the assistant learned:

- topics often approved
- topics often marked noise
- sources often demoted
- candidate buckets with high approval rates
- themes gaining user interest

## Scoring And Learning Direction

Simple first version:

- AI bucket score ranks the candidate.
- User approval strengthens similar future candidates.
- `noise` weakens similar future candidates.
- `report_candidate` and `rfp_evidence` are boosted in reports.
- Repeated themes across multiple items get surfaced as higher-level signals.

No heavy machine learning is required at first.

Rules plus stored feedback are enough for the first v2 slice.

## Desired User Feeling

The user should feel:

- "The app brings me an editorial agenda."
- "I do not have to inspect every article."
- "I can quickly approve, correct, or reject AI's draft."
- "The assistant is learning my strategy lens."
- "Reports are based on what mattered, not only what was collected."

## Important Product Decision

Do not build v2 as a separate hidden tab first.

Build it as a core improvement to the dashboard:

```text
Dashboard
└── 인사이트 후보
    ├── 전략 보고서 후보
    ├── 경쟁사 주시 후보
    ├── 제품/솔루션 아이디어 후보
    ├── 제안/RFP 근거 후보
    └── 노이즈 가능성 높음
```

The current feed pages remain useful as raw evidence and search surfaces.

But the user's daily workflow should start with AI-organized insight candidates.

