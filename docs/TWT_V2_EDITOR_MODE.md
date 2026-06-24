# TWT v2 - Editor Mode

## One-Line Concept

Tech Watch Tracker v2 turns the app from a collection dashboard into an editorial research assistant.

The user is the editor-in-chief. The app is a junior researcher that collects signals, recommends candidates, explains why they may matter, and learns from the user's judgment over time.

## Why v2 Exists

v1 collects many articles, release notes, and trend signals. It can also generate weekly and monthly reports.

The remaining burden is editorial judgment:

- Which items are actually important?
- Which items are only keyword noise?
- Which items should become report evidence?
- Which items matter for competitors, product strategy, RFPs, or financial IT strategy?
- How can the app learn the user's taste and strategy lens?

v2 should reduce manual triage. The user should review a short list of AI-ranked candidates instead of scanning hundreds of collected items.

## Product Principle

Do not try to fully automate insight.

Instead:

1. The app collects continuously.
2. AI ranks and explains likely insight candidates.
3. The user makes quick editorial judgments.
4. The app stores those judgments.
5. Future recommendations and reports use the accumulated judgment pattern.

## Core Vocabulary

- **Collected Item**: A raw competitor update, reference, or news trend item.
- **Insight Candidate**: A collected item that AI thinks may deserve attention.
- **Editorial Judgment**: The user's decision about an item.
- **Learning Signal**: A stored judgment that improves future ranking and reports.
- **Editor Mode**: The v2 workspace where the user reviews and trains the assistant.

## Editorial Judgment Labels

Initial labels:

- `important`: Important signal
- `report_candidate`: Include in strategy report candidates
- `watch_competitor`: Competitor movement to watch
- `product_idea`: Product or solution idea
- `rfp_evidence`: Useful as proposal/RFP evidence
- `noise`: Not useful / keyword noise
- `later`: Save for later review

An item can have multiple positive labels, but `noise` should act as a negative judgment.

## MVP Scope

### MVP 1 - Editorial Judgment Storage

Add database support for saving user judgments on collected docs and trends.

Minimum fields:

- item type: `doc` or `trend`
- item id
- profile id
- judgment label
- optional note
- created at

### MVP 2 - Editor Queue

Add an API that returns candidate items for review.

First version can use simple scoring:

- pending or recent items first
- starred items higher
- recent collected date higher
- items with high-value keywords higher
- items already marked `noise` lower or excluded

### MVP 3 - Editor Mode UI

Add a new sidebar tab: `편집장 모드`.

Show cards with:

- title
- source/company/keyword
- published date and collected date
- current summary or "AI 요약 대기"
- why this may matter
- quick judgment buttons

Buttons:

- 중요
- 보고서 후보
- 경쟁사 주시
- 제품 아이디어
- 제안/RFP 근거
- 나중에
- 노이즈

### MVP 4 - Pattern Summary

Show a simple "What the assistant learned" panel:

- topics frequently marked important
- sources frequently marked noise
- keywords often promoted to report candidates
- recent themes gaining user interest

### MVP 5 - Report Integration

Reports should prioritize items marked:

- `report_candidate`
- `important`
- `watch_competitor`
- `rfp_evidence`

Noise items should be excluded unless explicitly searched.

## Future Direction

### AI Ranking

Later, each item can receive AI-generated fields:

- insight score: 0-100
- strategic relevance
- financial IT relevance
- competitor impact
- product implication
- noise likelihood
- recommendation reason

### Feedback-Based Learning

Use accumulated judgments to adjust ranking:

- keywords often marked important get a score boost
- sources often marked noise get a penalty
- topics often promoted to reports are shown earlier
- competitor/product signals are separated from generic news

### Editorial Briefing

Daily or weekly AI brief:

- must-read signals
- report candidates
- weak but emerging signals
- likely noise
- what changed compared with last week

## Non-Goals For The First v2 Slice

- Do not replace the current feed pages.
- Do not automatically resend old Discord alerts.
- Do not require perfect AI scoring before shipping.
- Do not remove star/archive behavior.
- Do not make the user read every collected article.

## Success Criteria

The user should feel:

- "I am approving and shaping insight, not manually searching."
- "The app is learning what I care about."
- "Reports reflect my editorial judgment, not only raw collection volume."
- "I can quickly mark noise and make the assistant less noisy next time."

