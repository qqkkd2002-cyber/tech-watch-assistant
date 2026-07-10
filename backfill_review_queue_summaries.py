#!/usr/bin/env python3
"""One-off low-priority summary backfill for old review-queue trend candidates.

This script intentionally does not create judgments, move buckets, delete rows,
or touch manually saved/user-judged items. It only tries to fill missing article
summaries for legacy review-queue trend candidates so later event grouping and
Gemma classification have real content to work from.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import Any

import agent
import database
import trend_pipeline


@dataclass
class BackfillResult:
    review_id: int
    item_id: int
    title: str
    keyword: str
    status: str
    content_status: str = ""
    content_chars: int = 0
    content_resolver: str = ""
    content_extractor: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0


def get_legacy_review_queue_candidates(profile_id: int, limit: int) -> list[dict[str, Any]]:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                ar.id AS review_id,
                t.*
            FROM ai_editor_reviews ar
            JOIN scanned_trends t ON ar.item_type = 'trend' AND ar.item_id = t.id
            LEFT JOIN editor_judgments ej
              ON ej.profile_id = ar.profile_id
             AND ej.item_type = ar.item_type
             AND ej.item_id = ar.item_id
            WHERE ar.profile_id = ?
              AND ar.is_active = 1
              AND ar.primary_bucket = 'review_queue'
              AND ar.item_type = 'trend'
              AND t.analysis_status = 'pending'
              AND COALESCE(t.content_status, 'not_attempted') IN ('not_attempted', 'queued')
              AND COALESCE(t.manual_saved, 0) = 0
              AND ej.id IS NULL
            ORDER BY ar.score DESC, ar.confidence DESC, ar.created_at DESC, ar.id DESC
            LIMIT ?
            """,
            (profile_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def run_backfill(profile_id: int, limit: int, dry_run: bool = False) -> dict[str, Any]:
    started = time.time()
    candidates = get_legacy_review_queue_candidates(profile_id, limit)
    results: list[BackfillResult] = []

    for index, item in enumerate(candidates, start=1):
        item_started = time.time()
        keyword = item.get("matched_keywords") or item.get("keyword") or ""
        article = {
            "title": item.get("title") or "",
            "link": item.get("link") or "",
            "source": item.get("source") or "",
            "description": item.get("summary") or "",
            "published_at": item.get("published_at") or "",
        }
        print(f"[{index}/{len(candidates)}] {item.get('id')} {article['title'][:90]}", flush=True)

        if dry_run:
            results.append(
                BackfillResult(
                    review_id=int(item["review_id"]),
                    item_id=int(item["id"]),
                    title=article["title"],
                    keyword=keyword,
                    status="dry_run",
                    elapsed_seconds=round(time.time() - item_started, 2),
                )
            )
            continue

        outcome = agent.process_trend_article_content(
            profile_id=profile_id,
            article=article,
            keyword=keyword,
            existing_id=int(item["id"]),
        )
        metadata = outcome.get("metadata") or {}
        analysis = outcome.get("analysis") or {}
        status = str(outcome.get("status") or "unknown")
        error = ""

        if status == "summarized":
            saved = database.update_scanned_trend_content(
                int(item["id"]),
                keyword=keyword,
                title=article["title"],
                link=article["link"],
                summary=analysis.get("summary") or "",
                source=analysis.get("source") or article["source"],
                published_at=item.get("published_at") or "",
                analysis_status=analysis.get("analysis_status") or "complete",
                analysis_error=analysis.get("analysis_error") or "",
                original_url=metadata.get("original_url") or "",
                source_url=metadata.get("source_url") or article["link"],
                content_status=metadata.get("content_status") or "summarized",
                content_error=metadata.get("content_error") or "",
                content_chars=int(metadata.get("content_chars") or 0),
                content_extractor=metadata.get("content_extractor") or "",
                content_resolver=metadata.get("content_resolver") or "",
                summary_model=metadata.get("summary_model") or "",
                summary_evidence=metadata.get("summary_evidence") or [],
            )
            if saved:
                print(
                    f"  -> summarized chars={metadata.get('content_chars') or 0} "
                    f"resolver={metadata.get('content_resolver') or ''}",
                    flush=True,
                )
            else:
                status = "save_failed"
                error = "요약은 생성됐지만 DB 저장에 실패했습니다."
                print(f"  -> save_failed after summarize", flush=True)
        elif status == "failed":
            error = metadata.get("content_error") or analysis.get("analysis_error") or ""
            saved = database.update_scanned_trend_content(
                int(item["id"]),
                keyword=keyword,
                title=article["title"],
                link=article["link"],
                summary=item.get("summary") or "",
                source=item.get("source") or article["source"] or "본문 확보 대기",
                published_at=item.get("published_at") or "",
                analysis_status="pending",
                analysis_error=analysis.get("analysis_error") or error,
                original_url=metadata.get("original_url") or item.get("original_url") or "",
                source_url=metadata.get("source_url") or article["link"],
                content_status=metadata.get("content_status") or "extract_failed",
                content_error=error,
                content_chars=int(metadata.get("content_chars") or 0),
                content_extractor=metadata.get("content_extractor") or "",
                content_resolver=metadata.get("content_resolver") or "",
                summary_model="",
                summary_evidence=[],
            )
            if saved:
                print(f"  -> pending content_status={metadata.get('content_status')} error={error[:120]}", flush=True)
            else:
                status = "save_failed"
                error = f"본문 확보 실패 상태 저장 실패: {error}"
                print(f"  -> save_failed after pending update", flush=True)
        elif status == "duplicate":
            duplicate = outcome.get("duplicate") or {}
            duplicate_id = int(duplicate.get("id") or 0)
            duplicate_item = database.get_trend_by_id(duplicate_id) if duplicate_id else {}
            error = f"duplicate_of:{duplicate_id}"
            if (
                duplicate_item
                and duplicate_item.get("analysis_status") == "complete"
                and duplicate_item.get("content_status") == "summarized"
                and duplicate_item.get("summary")
            ):
                saved = database.update_scanned_trend_content(
                    int(item["id"]),
                    keyword=keyword,
                    title=article["title"],
                    link=article["link"],
                    summary=duplicate_item.get("summary") or "",
                    source=duplicate_item.get("source") or article["source"],
                    published_at=item.get("published_at") or "",
                    analysis_status="complete",
                    analysis_error="",
                    original_url=duplicate_item.get("original_url") or metadata.get("original_url") or "",
                    source_url=duplicate_item.get("source_url") or article["link"],
                    content_status="summarized",
                    content_error="",
                    content_chars=int(duplicate_item.get("content_chars") or 0),
                    content_extractor=duplicate_item.get("content_extractor") or "",
                    content_resolver=metadata.get("content_resolver") or duplicate_item.get("content_resolver") or "",
                    summary_model=duplicate_item.get("summary_model") or "",
                    summary_evidence=json.loads(duplicate_item.get("summary_evidence") or "[]"),
                )
                if saved:
                    status = "copied_duplicate_summary"
                    metadata["content_status"] = "summarized"
                    metadata["content_chars"] = int(duplicate_item.get("content_chars") or 0)
                    print(f"  -> copied summary from duplicate trend {duplicate_id}", flush=True)
                else:
                    status = "save_failed"
                    error = f"중복 요약 복사 저장 실패: duplicate_of:{duplicate_id}"
                    print(f"  -> save_failed after duplicate summary copy", flush=True)
            else:
                try:
                    resolved = trend_pipeline.resolve_article_url(article["link"])
                    extracted = trend_pipeline.extract_article_text(resolved["resolved_url"])
                    summarized = trend_pipeline.summarize_article_with_ollama(
                        title=article["title"],
                        source=article["source"] or "News",
                        keyword=keyword,
                        article_text=extracted["body_text"],
                    )
                    saved = database.update_scanned_trend_content(
                        int(item["id"]),
                        keyword=keyword,
                        title=article["title"],
                        link=article["link"],
                        summary=summarized["summary"] or "",
                        source=summarized["source"] or article["source"],
                        published_at=item.get("published_at") or "",
                        analysis_status="complete",
                        analysis_error="",
                        original_url=extracted["resolved_url"],
                        source_url=article["link"],
                        content_status="summarized",
                        content_error="",
                        content_chars=int(extracted["body_chars"] or 0),
                        content_extractor=extracted["extractor"],
                        content_resolver=resolved["resolver"],
                        summary_model=summarized["summary_model"],
                        summary_evidence=summarized["evidence_points"],
                    )
                    if saved:
                        status = "summarized"
                        metadata.update({
                            "content_status": "summarized",
                            "content_chars": int(extracted["body_chars"] or 0),
                            "content_resolver": resolved["resolver"],
                            "content_extractor": extracted["extractor"],
                        })
                        error = ""
                        print(
                            f"  -> summarized despite unsummarized duplicate trend {duplicate_id} "
                            f"chars={extracted['body_chars']}",
                            flush=True,
                        )
                    else:
                        status = "save_failed"
                        error = f"중복 대표 요약 저장 실패: duplicate_of:{duplicate_id}"
                        print(f"  -> save_failed after duplicate summarize", flush=True)
                except trend_pipeline.TrendPipelineError as exc:
                    status = "failed"
                    metadata["content_status"] = f"{exc.stage}_failed"
                    metadata["content_error"] = str(exc)[:300]
                    error = str(exc)[:300]
                    print(f"  -> duplicate target unavailable; pending error={error[:120]}", flush=True)
        else:
            error = json.dumps(outcome, ensure_ascii=False)[:300]
            print(f"  -> unknown status={status}", flush=True)

        results.append(
            BackfillResult(
                review_id=int(item["review_id"]),
                item_id=int(item["id"]),
                title=article["title"],
                keyword=keyword,
                status=status,
                content_status=str(metadata.get("content_status") or ""),
                content_chars=int(metadata.get("content_chars") or 0),
                content_resolver=str(metadata.get("content_resolver") or ""),
                content_extractor=str(metadata.get("content_extractor") or ""),
                error=error,
                elapsed_seconds=round(time.time() - item_started, 2),
            )
        )

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    return {
        "profile_id": profile_id,
        "limit": limit,
        "dry_run": dry_run,
        "candidate_count": len(candidates),
        "counts": counts,
        "elapsed_seconds": round(time.time() - started, 2),
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    report = run_backfill(args.profile_id, max(1, min(args.limit, 50)), dry_run=args.dry_run)
    print("\n=== SUMMARY ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
