#!/usr/bin/env python3
"""Compare local Ollama models without changing editor-review data."""

import argparse
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List

import database
from web_server import build_editor_profile_context, refine_editor_review_item_ollama


ANCHOR_TITLE_TERMS = (
    "AI 인재 양성",
    "13년 만에 풀린 금융 망분리 규제가 던진 숙제",
)


def load_trend_candidates(profile_id: int) -> List[Dict[str, Any]]:
    conn = database.get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT
                ar.id AS ai_review_id,
                ar.item_type,
                ar.item_id,
                ar.primary_bucket AS existing_bucket,
                ar.score AS existing_score,
                ar.confidence AS existing_confidence,
                ar.classification_source,
                t.title,
                t.source AS source_name,
                t.keyword AS category,
                t.link,
                t.summary,
                t.published_at,
                t.created_at AS item_created_at
            FROM ai_editor_reviews ar
            JOIN scanned_trends t
              ON ar.item_type = 'trend' AND ar.item_id = t.id
            WHERE ar.profile_id = ?
              AND ar.is_active = 1
              AND ar.classification_source != 'llm'
            ORDER BY ar.score DESC, ar.confidence ASC, t.created_at DESC
            """,
            (profile_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def choose_pilot_items(candidates: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    for term in ANCHOR_TITLE_TERMS:
        match = next((item for item in candidates if term in item.get("title", "")), None)
        if match and match["ai_review_id"] not in selected_ids:
            selected.append(match)
            selected_ids.add(match["ai_review_id"])

    remaining = [item for item in candidates if item["ai_review_id"] not in selected_ids]
    if not remaining:
        return selected[:limit]

    # Keep the pilot representative even when rule scores are clustered.
    groups = [
        remaining[: max(1, len(remaining) // 3)],
        remaining[len(remaining) // 3: max(len(remaining) // 3 + 1, 2 * len(remaining) // 3)],
        remaining[max(2 * len(remaining) // 3, 1):],
    ]
    group_index = 0
    while len(selected) < limit and any(groups):
        group = groups[group_index % len(groups)]
        if group:
            item = group.pop(0)
            if item["ai_review_id"] not in selected_ids:
                selected.append(item)
                selected_ids.add(item["ai_review_id"])
        group_index += 1

    return selected[:limit]


def run_pilot(profile_id: int, models: List[str], limit: int) -> Dict[str, Any]:
    candidates = load_trend_candidates(profile_id)
    items = choose_pilot_items(candidates, limit)
    profile_context = build_editor_profile_context(profile_id)
    model_results: Dict[str, List[Dict[str, Any]]] = {}

    for model in models:
        results = []
        for index, item in enumerate(items, start=1):
            started = time.perf_counter()
            try:
                classification = refine_editor_review_item_ollama(model, item, profile_context)
                elapsed = round(time.perf_counter() - started, 2)
                results.append({
                    "index": index,
                    "ai_review_id": item["ai_review_id"],
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "source_name": item.get("source_name", ""),
                    "existing_bucket": item.get("existing_bucket"),
                    "existing_score": item.get("existing_score"),
                    "elapsed_seconds": elapsed,
                    **classification,
                })
                print(f"[{model}] {index}/{len(items)} {elapsed:.2f}s {classification['primary_bucket']} - {item['title'][:55]}", flush=True)
            except Exception as exc:
                elapsed = round(time.perf_counter() - started, 2)
                results.append({
                    "index": index,
                    "ai_review_id": item["ai_review_id"],
                    "item_id": item["item_id"],
                    "title": item["title"],
                    "elapsed_seconds": elapsed,
                    "error": str(exc),
                })
                print(f"[{model}] {index}/{len(items)} ERROR - {exc}", flush=True)
        model_results[model] = results

    summaries = {}
    for model, results in model_results.items():
        completed = [result for result in results if "error" not in result]
        bucket_counts: Dict[str, int] = {}
        for result in completed:
            bucket = result.get("primary_bucket", "unknown")
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        summaries[model] = {
            "completed": len(completed),
            "errors": len(results) - len(completed),
            "average_seconds": round(sum(result["elapsed_seconds"] for result in completed) / len(completed), 2) if completed else None,
            "bucket_counts": bucket_counts,
        }

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "profile_id": profile_id,
        "limit": limit,
        "models": models,
        "database_writes": False,
        "selected_items": [
            {
                "ai_review_id": item["ai_review_id"],
                "item_id": item["item_id"],
                "title": item["title"],
                "existing_bucket": item.get("existing_bucket"),
                "existing_score": item.get("existing_score"),
            }
            for item in items
        ],
        "summaries": summaries,
        "results": model_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare local Ollama models on editor-classification items.")
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--models", nargs="+", default=["gemma4:latest", "llama3:latest"])
    args = parser.parse_args()

    result = run_pilot(args.profile_id, args.models, max(2, min(args.limit, 30)))
    os.makedirs(".state", exist_ok=True)
    output_path = os.path.join(".state", f"ollama_pilot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
    print(f"RESULT_FILE={output_path}")
    print(json.dumps(result["summaries"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
