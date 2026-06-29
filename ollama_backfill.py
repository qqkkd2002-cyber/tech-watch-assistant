#!/usr/bin/env python3
"""Preview or explicitly execute the one-time operational Gemma backfill."""

import argparse
import json
import os
from datetime import datetime

from web_server import get_ollama_backfill_preview, get_ollama_status, run_ollama_backfill


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely backfill editor classifications with local Gemma.")
    parser.add_argument("--profile-id", type=int, default=1)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write classifications to the operational database. Omit for preview only.",
    )
    args = parser.parse_args()

    if args.execute:
        result = run_ollama_backfill(args.profile_id, args.limit)
    else:
        preview = get_ollama_backfill_preview(args.profile_id, limit=2000)
        result = {
            "executed": False,
            "message": "Preview only. No editor-review data was changed.",
            "ollama": get_ollama_status(),
            "profile_id": args.profile_id,
            "model": preview["model"],
            "candidate_count": preview["candidate_count"],
            "eligible_count": preview["eligible_count"],
            "insufficient_count": preview["insufficient_count"],
            "manual_saved_eligible_count": preview["manual_saved_eligible_count"],
            "eligible_sample": preview["eligible"][:20],
        }

    os.makedirs(".state", exist_ok=True)
    mode = "execute" if args.execute else "preview"
    output_path = os.path.join(".state", f"ollama_backfill_{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, ensure_ascii=False, indent=2)
    print(json.dumps({
        "executed": result.get("executed", args.execute),
        "model": result.get("model"),
        "candidate_count": result.get("candidate_count"),
        "eligible_count": result.get("eligible_count"),
        "insufficient_count": result.get("insufficient_count"),
        "completed": result.get("completed"),
        "bucket_counts": result.get("bucket_counts"),
        "result_file": output_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
