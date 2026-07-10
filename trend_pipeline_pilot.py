#!/usr/bin/env python3
"""Run the new-trend content pipeline without writing to the operational database."""

import argparse
import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import database
import monitors
import trend_pipeline


def collect_fresh_samples(
    profile_id: int,
    limit: Optional[int],
    items_per_keyword: int,
) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    seen_links = set()
    raw_candidates = 0
    source_duplicates = 0
    existing_source_duplicates = 0
    keywords = database.get_profile_keywords(profile_id)
    for keyword_item in keywords:
        keyword = keyword_item.get("keyword", "").strip()
        if not keyword:
            continue
        for article in monitors.search_trend_news(keyword, recency_days=2)[:items_per_keyword]:
            raw_candidates += 1
            link = article.get("link", "")
            if not link:
                continue
            if link in seen_links:
                source_duplicates += 1
                continue
            seen_links.add(link)
            if database.find_scanned_trend_by_url(profile_id, link=link):
                existing_source_duplicates += 1
                continue
            samples.append({**article, "keyword": keyword})
            if limit is not None and len(samples) >= limit:
                return {
                    "samples": samples,
                    "keyword_count": len(keywords),
                    "raw_candidates": raw_candidates,
                    "source_duplicates": source_duplicates,
                    "existing_source_duplicates": existing_source_duplicates,
                    "limit_reached": True,
                }
    return {
        "samples": samples,
        "keyword_count": len(keywords),
        "raw_candidates": raw_candidates,
        "source_duplicates": source_duplicates,
        "existing_source_duplicates": existing_source_duplicates,
        "limit_reached": False,
    }


def run_pilot(profile_id: int, limit: Optional[int], items_per_keyword: int) -> Dict[str, Any]:
    collection_started = time.perf_counter()
    collection = collect_fresh_samples(profile_id, limit, items_per_keyword)
    samples = collection["samples"]
    collection_seconds = round(time.perf_counter() - collection_started, 2)
    results = []
    resolved_urls = set()
    original_url_duplicates = 0
    existing_original_duplicates = 0
    processing_started = time.perf_counter()

    for index, article in enumerate(samples, start=1):
        started = time.perf_counter()
        try:
            resolved = trend_pipeline.resolve_article_url(article.get("link", ""))
            original_url = resolved["resolved_url"]
            if original_url in resolved_urls:
                original_url_duplicates += 1
                elapsed = round(time.perf_counter() - started, 2)
                results.append({
                    "index": index,
                    "keyword": article["keyword"],
                    "source_title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "source_url": article.get("link", ""),
                    "original_url": original_url,
                    "resolver": resolved["resolver"],
                    "duplicate_in_sample": True,
                    "elapsed_seconds": elapsed,
                    "status": "duplicate",
                })
                print(f"[{index}/{len(samples)}] duplicate {elapsed:.2f}s {article['title'][:70]}", flush=True)
                continue
            if database.find_scanned_trend_by_url(profile_id, original_url=original_url):
                existing_original_duplicates += 1
                elapsed = round(time.perf_counter() - started, 2)
                results.append({
                    "index": index,
                    "keyword": article["keyword"],
                    "source_title": article.get("title", ""),
                    "source": article.get("source", ""),
                    "source_url": article.get("link", ""),
                    "original_url": original_url,
                    "resolver": resolved["resolver"],
                    "duplicate_in_database": True,
                    "elapsed_seconds": elapsed,
                    "status": "existing_duplicate",
                })
                print(f"[{index}/{len(samples)}] existing duplicate {elapsed:.2f}s {article['title'][:70]}", flush=True)
                continue
            resolved_urls.add(original_url)
            extracted = trend_pipeline.extract_article_text(original_url)
            summary = trend_pipeline.summarize_article_with_ollama(
                title=article.get("title", ""),
                source=article.get("source", "") or "News",
                keyword=article["keyword"],
                article_text=extracted["body_text"],
            )
            elapsed = round(time.perf_counter() - started, 2)
            results.append({
                "index": index,
                "keyword": article["keyword"],
                "source_title": article.get("title", ""),
                "source": article.get("source", ""),
                "source_url": article.get("link", ""),
                "original_url": original_url,
                "resolver": resolved["resolver"],
                "content_chars": extracted["body_chars"],
                "content_extractor": extracted["extractor"],
                "summary_model": summary["summary_model"],
                "summary_title": summary["title"],
                "summary": summary["summary"],
                "evidence_points": summary["evidence_points"],
                "duplicate_in_sample": False,
                "elapsed_seconds": elapsed,
                "status": "success",
            })
            print(f"[{index}/{len(samples)}] success {elapsed:.2f}s {article['title'][:70]}", flush=True)
        except trend_pipeline.TrendPipelineError as exc:
            elapsed = round(time.perf_counter() - started, 2)
            results.append({
                "index": index,
                "keyword": article["keyword"],
                "source_title": article.get("title", ""),
                "status": "content_pending",
                "failed_stage": exc.stage,
                "error": str(exc),
                "elapsed_seconds": elapsed,
            })
            print(f"[{index}/{len(samples)}] {exc.stage} failed {elapsed:.2f}s {exc}", flush=True)

    processing_seconds = round(time.perf_counter() - processing_started, 2)
    successful = [result for result in results if result["status"] == "success"]
    failed = [result for result in results if result["status"] == "content_pending"]
    attempted = len(successful) + len(failed)
    stage_failures: Dict[str, int] = {}
    for result in failed:
        stage = result.get("failed_stage", "unknown")
        stage_failures[stage] = stage_failures.get(stage, 0) + 1
    duplicate_check = {
        "first_url_accepted": False,
        "same_url_second_keyword_blocked": False,
    }
    if successful:
        seen = set()
        test_url = successful[0]["original_url"]
        duplicate_check["first_url_accepted"] = test_url not in seen
        seen.add(test_url)
        duplicate_check["same_url_second_keyword_blocked"] = test_url in seen

    failure_check: Dict[str, Any]
    try:
        trend_pipeline.extract_article_text("https://example.invalid/twt-content-pipeline-test")
        failure_check = {"status": "unexpected_success"}
    except trend_pipeline.TrendPipelineError as exc:
        failure_check = {
            "status": "content_pending",
            "failed_stage": exc.stage,
            "error": str(exc),
        }
    except Exception as exc:
        failure_check = {
            "status": "content_pending",
            "failed_stage": "extract",
            "error": str(exc),
        }

    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "profile_id": profile_id,
        "requested": limit if limit is not None else "all",
        "items_per_keyword": items_per_keyword,
        "keyword_count": collection["keyword_count"],
        "raw_candidates": collection["raw_candidates"],
        "collected": len(samples),
        "attempted": attempted,
        "successes": len(successful),
        "failures": len(failed),
        "success_rate": round(len(successful) / attempted, 3) if attempted else 0.0,
        "failure_rate": round(len(failed) / attempted, 3) if attempted else 0.0,
        "stage_failures": stage_failures,
        "duplicates": {
            "source_url_in_queue": collection["source_duplicates"],
            "source_url_in_database": collection["existing_source_duplicates"],
            "original_url_in_queue": original_url_duplicates,
            "original_url_in_database": existing_original_duplicates,
            "total_removed": (
                collection["source_duplicates"]
                + collection["existing_source_duplicates"]
                + original_url_duplicates
                + existing_original_duplicates
            ),
        },
        "collection_seconds": collection_seconds,
        "processing_seconds": processing_seconds,
        "total_seconds": round(collection_seconds + processing_seconds, 2),
        "average_seconds": round(processing_seconds / attempted, 2) if attempted else None,
        "limit_reached": collection["limit_reached"],
        "database_writes": False,
        "duplicate_check": duplicate_check,
        "failure_check": failure_check,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run the new-trend extraction and Gemma summary pipeline.")
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=5, help="Queue size. Use 0 for the full fresh queue.")
    parser.add_argument("--items-per-keyword", type=int, default=2)
    args = parser.parse_args()

    limit = None if args.limit == 0 else max(1, min(args.limit, 200))
    items_per_keyword = max(1, min(args.items_per_keyword, 10))
    result = run_pilot(args.profile_id, limit, items_per_keyword)
    os.makedirs(".state", exist_ok=True)
    output_path = os.path.join(".state", f"trend_pipeline_pilot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
    print(json.dumps({
        "collected": result["collected"],
        "attempted": result["attempted"],
        "successes": result["successes"],
        "failures": result["failures"],
        "success_rate": result["success_rate"],
        "failure_rate": result["failure_rate"],
        "stage_failures": result["stage_failures"],
        "duplicates": result["duplicates"],
        "collection_seconds": result["collection_seconds"],
        "processing_seconds": result["processing_seconds"],
        "total_seconds": result["total_seconds"],
        "average_seconds": result["average_seconds"],
        "duplicate_check": result["duplicate_check"],
        "failure_check": result["failure_check"],
        "result_file": output_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
