#!/usr/bin/env python3
"""Conservatively group review-queue articles that describe the same event.

The source ledger is never deleted or rewritten. Lexical summary similarity is
used only to make a small candidate list; local Gemma makes the final same-event
decision before group metadata is written to ai_editor_reviews.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
import urllib.request
from collections import Counter
from datetime import datetime
from typing import Any

import database


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "gemma4:latest"
STOPWORDS = {
    "그리고", "그러나", "대한", "위한", "통해", "관련", "이번", "기반", "제공", "밝혔다",
    "있다", "한다", "했다", "되는", "있는", "기사", "요약", "기업", "시장", "기술", "서비스",
    "the", "and", "for", "with", "from", "that", "this", "into", "news", "said",
}


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"\[[^\]]{1,30}\]", " ", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def tokens(value: str) -> Counter[str]:
    words = re.findall(r"[가-힣]{2,}|[a-z][a-z0-9.+-]{2,}|\d{2,}", clean_text(value))
    return Counter(word for word in words if word not in STOPWORDS)


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = left.keys() & right.keys()
    dot = sum(left[word] * right[word] for word in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def parse_date(item: dict[str, Any]) -> datetime | None:
    raw = item.get("published_at") or item.get("item_created_at") or ""
    raw = str(raw).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw[:19])
    except ValueError:
        return None


def load_items(profile_id: int) -> list[dict[str, Any]]:
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT ar.id AS ai_review_id, ar.item_id, ar.primary_bucket,
                   t.title, t.summary, t.source AS source_name, t.link,
                   t.original_url, t.source_url, t.published_at,
                   t.created_at AS item_created_at
            FROM ai_editor_reviews ar
            JOIN scanned_trends t ON ar.item_type = 'trend' AND ar.item_id = t.id
            WHERE ar.profile_id = ? AND ar.is_active = 1
              AND ar.primary_bucket = 'review_queue'
              AND COALESCE(t.manual_saved, 0) = 0
              AND t.analysis_status = 'complete'
              AND LENGTH(TRIM(COALESCE(t.summary, ''))) >= 80
              AND NOT EXISTS (
                  SELECT 1 FROM editor_judgments j
                  WHERE j.profile_id = ar.profile_id
                    AND j.item_type = ar.item_type AND j.item_id = ar.item_id
              )
            ORDER BY COALESCE(NULLIF(t.published_at, ''), t.created_at) DESC
            """,
            (profile_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def shortlist_pairs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for item in items:
        prepared.append({
            **item,
            "title_tokens": tokens(item.get("title", "")),
            "summary_tokens": tokens(item.get("summary", "")),
            "event_date": parse_date(item),
        })

    pairs = []
    for index, left in enumerate(prepared):
        for right in prepared[index + 1:]:
            left_url = left.get("original_url") or left.get("source_url") or left.get("link")
            right_url = right.get("original_url") or right.get("source_url") or right.get("link")
            if left_url and left_url == right_url:
                continue
            if left["event_date"] and right["event_date"]:
                if abs((left["event_date"] - right["event_date"]).days) > 21:
                    continue
            shared = set(left["summary_tokens"]) & set(right["summary_tokens"])
            if len(shared) < 3:
                continue
            summary_score = cosine(left["summary_tokens"], right["summary_tokens"])
            title_score = cosine(left["title_tokens"], right["title_tokens"])
            if not (
                summary_score >= 0.56
                or (summary_score >= 0.40 and title_score >= 0.34)
                or (title_score >= 0.62 and summary_score >= 0.30)
            ):
                continue
            pairs.append({
                "pair_id": f"{left['item_id']}-{right['item_id']}",
                "left": left,
                "right": right,
                "lexical_score": round(max(summary_score, (summary_score + title_score) / 2), 4),
            })
    return sorted(pairs, key=lambda pair: pair["lexical_score"], reverse=True)


def verify_batch(pairs: list[dict[str, Any]], model: str) -> list[dict[str, Any]]:
    payload_pairs = []
    for pair in pairs:
        payload_pairs.append({
            "pair_id": pair["pair_id"],
            "article_a": {
                "title": pair["left"]["title"],
                "summary": pair["left"]["summary"][:900],
                "date": pair["left"].get("published_at", ""),
            },
            "article_b": {
                "title": pair["right"]["title"],
                "summary": pair["right"]["summary"][:900],
                "date": pair["right"].get("published_at", ""),
            },
        })
    prompt = f"""
아래 기사 쌍들이 '같은 구체적 사건'을 보도하는지 엄격하게 판정하라.
같은 분야/주제라는 이유만으로 묶지 마라. 동일 발표, 동일 제품 출시,
동일 규제 변경, 동일 계약·행사처럼 핵심 행위와 시점이 같아야 true다.
애매하면 false다. JSON만 반환하라.
형식: {{"results":[{{"pair_id":"...","same_event":true,"confidence":0,"reason":"짧은 한국어 근거"}}]}}

기사 쌍:
{json.dumps(payload_pairs, ensure_ascii=False)}
""".strip()
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": "기사의 동일 사건 여부를 보수적으로 판정하고 JSON만 반환한다.",
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = json.load(response)
    parsed = json.loads(raw.get("response") or "{}")
    result_rows = parsed.get("results", parsed.get("pairs", []))
    if isinstance(result_rows, dict):
        result_rows = list(result_rows.values())
    by_id = {str(row.get("pair_id", row.get("id", ""))).strip(): row for row in result_rows if isinstance(row, dict)}
    verified = []
    for pair in pairs:
        result = by_id.get(pair["pair_id"], {})
        same_value = result.get("same_event", result.get("is_same_event", False))
        is_same = same_value is True or str(same_value).strip().lower() in {"true", "yes", "same", "동일"}
        try:
            confidence_value = float(result.get("confidence") or 0)
        except (TypeError, ValueError):
            confidence_match = re.search(r"\d+(?:\.\d+)?", str(result.get("confidence") or "0"))
            confidence_value = float(confidence_match.group(0)) if confidence_match else 0
        confidence = round(confidence_value * 100) if 0 < confidence_value <= 1 else round(confidence_value)
        if is_same and confidence >= 80:
            verified.append({
                **pair,
                "confidence": confidence,
                "reason": str(result.get("reason") or "Gemma 동일 사건 확인"),
            })
    if not verified and pairs:
        print(f"Gemma batch parsed but accepted 0/{len(pairs)}: {json.dumps(parsed, ensure_ascii=False)[:500]}", flush=True)
    return verified


def build_groups(pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parent: dict[int, int] = {}

    def find(value: int) -> int:
        parent.setdefault(value, value)
        if parent[value] != value:
            parent[value] = find(parent[value])
        return parent[value]

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[b] = a

    for pair in pairs:
        union(int(pair["left"]["item_id"]), int(pair["right"]["item_id"]))
    members: dict[int, set[int]] = {}
    for item_id in parent:
        members.setdefault(find(item_id), set()).add(item_id)

    groups = []
    for item_ids in members.values():
        if len(item_ids) < 2:
            continue
        ordered = sorted(item_ids)
        related = [pair for pair in pairs if int(pair["left"]["item_id"]) in item_ids and int(pair["right"]["item_id"]) in item_ids]
        key = "event:" + hashlib.sha1(",".join(map(str, ordered)).encode()).hexdigest()[:12]
        groups.append({
            "key": key,
            "item_ids": ordered,
            "score": round(max(pair["confidence"] for pair in related) / 100, 2),
            "reason": " | ".join(dict.fromkeys(pair["reason"] for pair in related))[:500],
        })
    return groups


def apply_groups(profile_id: int, eligible_ids: list[int], groups: list[dict[str, Any]]) -> None:
    conn = database.get_db_connection()
    try:
        if eligible_ids:
            marks = ",".join("?" for _ in eligible_ids)
            conn.execute(
                f"""UPDATE ai_editor_reviews
                    SET event_group_key = '', event_group_score = 0, event_group_reason = ''
                    WHERE profile_id = ? AND item_type = 'trend' AND item_id IN ({marks})""",
                [profile_id, *eligible_ids],
            )
        for group in groups:
            marks = ",".join("?" for _ in group["item_ids"])
            conn.execute(
                f"""UPDATE ai_editor_reviews
                    SET event_group_key = ?, event_group_score = ?, event_group_reason = ?
                    WHERE profile_id = ? AND item_type = 'trend' AND item_id IN ({marks})""",
                [group["key"], group["score"], group["reason"], profile_id, *group["item_ids"]],
            )
        conn.commit()
    finally:
        conn.close()


def run(profile_id: int, model: str, execute: bool, batch_size: int = 8) -> dict[str, Any]:
    database.init_db()
    items = load_items(profile_id)
    candidates = shortlist_pairs(items)
    verified = []
    started = time.perf_counter()
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset:offset + batch_size]
        verified.extend(verify_batch(batch, model))
        print(f"verified {min(offset + batch_size, len(candidates))}/{len(candidates)} candidate pairs", flush=True)
    groups = build_groups(verified)
    if execute:
        apply_groups(profile_id, [int(item["item_id"]) for item in items], groups)
    return {
        "executed": execute,
        "profile_id": profile_id,
        "model": model,
        "eligible_items": len(items),
        "candidate_pairs": len(candidates),
        "verified_pairs": len(verified),
        "groups": groups,
        "grouped_items": sum(len(group["item_ids"]) for group in groups),
        "elapsed_seconds": round(time.perf_counter() - started, 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    result = run(args.profile_id, args.model, args.execute)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
