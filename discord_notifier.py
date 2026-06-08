import urllib.request
import json
import ssl
from typing import List

def post_to_webhook(webhook_url: str, payload: dict) -> bool:
    """Posts a JSON payload to a Discord Webhook URL using built-in urllib."""
    if not webhook_url or webhook_url.startswith("YOUR_DISCORD_WEBHOOK"):
        print("Discord Webhook URL not configured. Skipping notification.")
        return False
        
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    
    # Disable SSL verification issues if running in some local environments
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            return response.status == 204 or response.status == 200
    except Exception as e:
        print(f"Failed to send Discord notification: {e}")
        return False

def send_doc_update_alert(webhook_url: str, competitor_name: str, feature_title: str, summary: str, keywords: List[str], doc_url: str, published_at: str = "") -> bool:
    """Sends a rich Discord embed card for a competitor documentation update."""
    color = 15418880  # Hex #EB6000 (Orange-ish)
    
    payload = {
        "username": "Tech Watch - Docs",
        "avatar_url": "https://img.icons8.com/color/96/gitlab.png" if "gitlab" in competitor_name.lower() else "https://img.icons8.com/fluency/96/code-fork.png",
        "embeds": [
          {
            "title": f"🆕 {competitor_name} Update: {feature_title}",
            "description": summary,
            "url": doc_url if doc_url else None,
            "color": color,
            "fields": [
              {
                "name": "🏷️ Keywords",
                "value": ", ".join(keywords) if keywords else "General",
                "inline": True
              },
              {
                "name": "🔗 Reference Link",
                "value": f"[View Original Documentation]({doc_url})" if doc_url else "N/A",
                "inline": True
              },
              {
                "name": "🗓️ Published",
                "value": published_at if published_at else "Unknown",
                "inline": True
              }
            ],
            "footer": {
              "text": "Tech Watch Assistant • Competitor Monitoring"
            }
          }
        ]
    }
    return post_to_webhook(webhook_url, payload)

def send_trend_alert(webhook_url: str, matched_keyword: str, article_title: str, source_name: str, summary: str, source_url: str, published_at: str = "") -> bool:
    """Sends a rich Discord embed card for a hot news/trend alert."""
    color = 3447003  # Hex #3498DB (Blue)
    
    payload = {
        "username": "Tech Watch - Trends",
        "avatar_url": "https://img.icons8.com/fluency/96/news.png",
        "embeds": [
          {
            "title": f"🔥 Hot Trend Topic: {article_title}",
            "description": summary,
            "url": source_url if source_url else None,
            "color": color,
            "fields": [
              {
                "name": "🎯 Keyword Match",
                "value": f"`{matched_keyword}`",
                "inline": True
              },
              {
                "name": "📰 Source",
                "value": source_name if source_name else "Web Search",
                "inline": True
              },
              {
                "name": "🗓️ Published",
                "value": published_at if published_at else "Unknown",
                "inline": True
              }
            ],
            "footer": {
              "text": "Tech Watch Assistant • Tech Trend Scan"
            }
          }
        ]
    }
    return post_to_webhook(webhook_url, payload)

def send_report_alert(webhook_url: str, report_title: str, report_summary: str) -> bool:
    """Sends an alert that a new weekly/monthly strategic report has been generated."""
    color = 10181046  # Hex #9B59B6 (Purple)
    
    payload = {
        "username": "Tech Watch - Reports",
        "avatar_url": "https://img.icons8.com/color/96/combo-chart.png",
        "embeds": [
          {
            "title": f"📊 New Strategic Analysis Generated",
            "description": f"**Title**: {report_title}\n\n**Executive Summary**:\n{report_summary}\n\n*The full report is now saved in your Apple Notes folder: **'Tech Watch - Reports'**.*",
            "color": color,
            "footer": {
              "text": "Tech Watch Assistant • Strategy Reports"
            }
          }
        ]
    }
    return post_to_webhook(webhook_url, payload)

if __name__ == "__main__":
    print("This module sends Discord notifications when called by the app.")
    print("Configure your webhook in the local config file or profile settings.")
