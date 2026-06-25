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

[검토 대기 12]
[인사이트 4]
[노이즈 18]
```

Each bucket contains cards with:

- title
- source / competitor / keyword
- published date and collected date
- current AI summary status
- inline AI summary or collected source snippet
- selected/manual AI summary action for pending cards
- why AI placed it in this stage
- suggested tags such as 보고서, 경쟁사, 제품 아이디어, RFP/제안 근거
- confidence or score
- quick editor actions

## AI First Editorial Buckets

Primary dashboard buckets should stay intentionally simple:

- `review_queue`: 검토 대기
- `insight`: 인사이트
- `noise`: 노이즈

Detailed usage categories should be tags, not board columns:

- `report`: 보고서
- `competitor`: 경쟁사
- `product_idea`: 제품 아이디어
- `rfp_evidence`: RFP/제안 근거
- `regulation`: 규제/시장 신호
- `technical_reference`: 기술 레퍼런스

This keeps the user's daily decision simple: hold, promote, or reject. The richer meaning remains visible on the card as tags.

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
- suggested_tags
- score
- confidence
- reason
- related_theme
- model_name
- prompt_version
- is_active
- created_at
- updated_at
```

This is the assistant's first draft.

The existing `editor_judgments` table remains useful as the user's correction and learning signal.

`editor_judgments.ai_review_id` should be nullable.

Why nullable:

- If the user approves or corrects an AI candidate, the judgment should reference the exact AI review.
- If the user later judges an item from a raw feed/search result, there may be no AI review yet.

This optional link allows accuracy analysis:

```text
AI said: review_queue + tag rfp_evidence
User said: noise
```

That mismatch is one of the most valuable learning signals.

## Reclassification Rule

One collected item can have multiple AI reviews over time.

Reasons:

- prompt changes
- model changes
- user manually requests reclassification
- better context becomes available

Rule:

- keep review history
- only one active review per `profile_id + item_type + item_id`
- dashboard uses only `is_active = 1`
- reclassification sets older active reviews to `is_active = 0` and inserts a new active review

This avoids painful future migrations and preserves the AI decision history.

## Score And Confidence Rules

Use `score` for sorting.

Use `confidence` for UX trust.

Initial rules:

- `score >= 70`: show as primary candidate
- `score 40-69`: show below the strongest candidates
- `score < 40`: keep in noise unless the user explicitly searches or opens noise
- low confidence candidates should be shown lower, even if the bucket is interesting

This prevents the dashboard from feeling like a random list.

## User Editorial Actions

The user should mainly review AI buckets, not raw feed cards.

Initial actions:

- `move_to_insight`
- `mark_later`
- `mark_noise`
- drag between 검토 대기, 인사이트, 노이즈

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
- active review version

### MVP 3 - Generate AI Editorial Reviews

Create a lightweight background task or manual button:

**AI 후보 분류**

It should classify recent or pending items into buckets.

The first version can process:

- latest 30 docs
- latest 50 trends
- items without an existing AI editorial review

First implementation can use rule-based classification to make the UI useful before spending Gemini quota. Later, the same table can store Gemini-powered reviews.

### MVP 4 - Dashboard Insight Candidates

Add an `인사이트 후보` section on the dashboard.

It should group reviewed items by AI bucket and show the strongest candidates first.

The user can approve or correct from this section.

Pending cards should support selected AI summarization directly inside this section so the user can judge without opening every source article.

For the first usable version, the dashboard groups into three stages:

- 검토 대기
- 인사이트
- 노이즈

Specific intent such as 보고서, 경쟁사, 제품 아이디어, or RFP/제안 근거 appears as card tags.

### MVP 5 - Reports Use Approved Signals

Defer report integration until the candidate flow is tested with real use.

Weekly/monthly reports should prioritize:

- cards moved to `insight`
- approved `report_candidate`
- cards tagged `rfp_evidence`
- cards tagged `competitor`

Noise should be excluded unless explicitly searched.

Do not merge report behavior changes into the main workflow until approved candidates prove useful in practice.

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
- `insight`, `report_candidate`, and `rfp_evidence` tags are boosted in reports.
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
