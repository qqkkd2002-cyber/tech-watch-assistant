#!/usr/bin/env python3
"""Re-run a small, explicitly selected calibration set with rollback snapshot."""

import argparse
import json
import os
from datetime import datetime

import database
from web_server import (
    EDITOR_OLLAMA_MODEL,
    _prepare_operational_review,
    _select_grouped_ollama_targets,
    build_editor_profile_context,
    get_ollama_status,
    refine_editor_review_item_ollama,
)


DEFAULT_ITEM_IDS = [
    # 11 suspected over-promotions
    428, 432, 425, 407, 395, 374, 379, 349, 329, 396, 411,
    # 10 controls: clear work/learning/noise
    437, 434, 367, 436, 380, 378, 402, 397, 422, 405,
    # Unjudged network-separation regulation control: must remain work_signal.
    231,
]


def load_items(profile_id: int, item_ids: list[int]) -> list[dict]:
    marks = ",".join("?" for _ in item_ids)
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT ar.id AS ai_review_id, ar.*, t.title, t.source AS source_name,
                   t.keyword AS category, t.link, t.summary, t.published_at,
                   t.created_at AS item_created_at, t.analysis_status,
                   COALESCE(t.manual_saved, 0) AS manual_saved
            FROM ai_editor_reviews ar
            JOIN scanned_trends t ON ar.item_type='trend' AND ar.item_id=t.id
            WHERE ar.profile_id=? AND ar.is_active=1 AND ar.item_id IN ({marks})
              AND COALESCE(t.manual_saved, 0)=0
              AND NOT EXISTS (
                SELECT 1 FROM editor_judgments j
                WHERE j.profile_id=ar.profile_id AND j.item_type=ar.item_type AND j.item_id=ar.item_id
              )
            ORDER BY CASE ar.item_id {''.join(f' WHEN {item_id} THEN {index}' for index, item_id in enumerate(item_ids))} END
            """,
            [profile_id, *item_ids],
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def load_reviews(profile_id: int, review_ids: list[int]) -> list[dict]:
    items = []
    for review_id in review_ids:
        item = database.get_ai_editor_review_context(profile_id, review_id)
        if not item:
            continue
        if int(item.get("manual_saved") or 0) == 1:
            continue
        if database.has_user_editor_judgment(profile_id, item["item_type"], item["item_id"]):
            continue
        item["ai_review_id"] = int(item.get("ai_review_id") or item["id"])
        items.append(item)
    return items


def snapshot(items: list[dict]) -> str:
    os.makedirs(".state", exist_ok=True)
    path = os.path.join(".state", f"ollama_recalibration_before_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as output:
        json.dump(items, output, ensure_ascii=False, indent=2)
    return path


def run_selected(profile_id: int, items: list[dict], expected_count: int) -> dict:
    status = get_ollama_status()
    if not status["available"]:
        raise RuntimeError("Ollama 또는 Gemma 모델을 사용할 수 없습니다.")
    if len(items) != expected_count:
        raise RuntimeError(f"보호 조건 때문에 선택 항목 일부를 불러오지 못했습니다: expected={expected_count}, found={len(items)}")
    snapshot_path = snapshot(items)
    profile_context = build_editor_profile_context(profile_id)
    results = []
    units = _select_grouped_ollama_targets(items, len(items))
    for index, unit in enumerate(units, 1):
        representative = unit["representative"]
        review = refine_editor_review_item_ollama(EDITOR_OLLAMA_MODEL, representative, profile_context)
        review = _prepare_operational_review(review)
        for item in unit["members"]:
            saved = database.update_ai_editor_review_classification(
                profile_id=profile_id,
                ai_review_id=int(item["ai_review_id"]),
                review=review,
            )
            results.append({
                "item_id": item["item_id"], "title": item["title"],
                "before_bucket": item["primary_bucket"], "before_confidence": item["confidence"],
                "primary_bucket": review["primary_bucket"], "score": review["score"],
                "confidence": review["confidence"], "reason": review["reason"],
                "suggested_tags": review["suggested_tags"], "guardrail": review.get("guardrail", ""),
                "classified_via_representative": item["item_id"] != representative["item_id"],
                "saved_review_id": saved["id"],
            })
        print(
            f"[{index}/{len(units)}] {len(unit['members'])} item(s) "
            f"{review['primary_bucket']} {review['confidence']} {review.get('guardrail','')}",
            flush=True,
        )
    return {"model": EDITOR_OLLAMA_MODEL, "snapshot": snapshot_path, "results": results}


def run(profile_id: int, item_ids: list[int]) -> dict:
    return run_selected(profile_id, load_items(profile_id, item_ids), len(item_ids))


def run_reviews(profile_id: int, review_ids: list[int]) -> dict:
    return run_selected(profile_id, load_reviews(profile_id, review_ids), len(review_ids))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--item-ids", nargs="*", type=int, default=DEFAULT_ITEM_IDS)
    parser.add_argument("--review-ids", nargs="*", type=int, default=[])
    args = parser.parse_args()
    result = run_reviews(args.profile_id, args.review_ids) if args.review_ids else run(args.profile_id, args.item_ids)
    path = os.path.join(".state", f"ollama_recalibration_after_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(json.dumps({"completed": len(result["results"]), "result_file": path, "snapshot": result["snapshot"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
