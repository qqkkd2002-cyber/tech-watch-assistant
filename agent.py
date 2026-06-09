import sys
import platform
print(f"[Agent Debug] Executable: {sys.executable}")
print(f"[Agent Debug] Machine Arch: {platform.machine()}")
print(f"[Agent Debug] Platform: {platform.platform()}")

import asyncio
import os
import json
import argparse
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

# Import custom modules
import apple_notes
import monitors
import discord_notifier
import database

# Import Google Antigravity SDK
from google.antigravity import Agent, LocalAgentConfig

# Default folders in Apple Notes
FOLDER_DOCS = "Tech Watch - Docs"
FOLDER_TRENDS = "Tech Watch - Trends"
FOLDER_REPORTS = "Tech Watch - Reports"
NEWS_RECENCY_DAYS = 2
ALERT_FRESHNESS_HOURS = 168
ai_cooldown_until = None

def is_quota_error(error_text: str) -> bool:
    lowered = (error_text or "").lower()
    return "429" in lowered or "quota" in lowered or "rate-limit" in lowered or "rate limit" in lowered

def get_retry_seconds(error_text: str, default_seconds: int = 300) -> int:
    match = re.search(r"retry in ([0-9]+(?:\.[0-9]+)?)s", error_text or "", re.IGNORECASE)
    if not match:
        return default_seconds
    return max(int(float(match.group(1))) + 5, 30)

def set_ai_cooldown(error_text: str):
    global ai_cooldown_until
    retry_seconds = get_retry_seconds(error_text)
    ai_cooldown_until = datetime.now() + timedelta(seconds=retry_seconds)
    print(f"[Gemini Quota] AI calls paused for about {retry_seconds}s. New items will be saved as 'AI 요약 대기'.")

def is_ai_cooling_down() -> bool:
    return ai_cooldown_until is not None and datetime.now() < ai_cooldown_until

def pending_doc_analysis(reason: str = "") -> dict:
    return {
        "summary": "AI 요약 대기 중입니다. Gemini 한도 또는 일시 오류로 원문만 먼저 수집했습니다.",
        "impact": "AI 분석 대기 중입니다. 다음 스캔에서 요약을 다시 시도합니다.",
        "keywords": ["AI 요약 대기"],
        "analysis_status": "pending",
        "analysis_error": reason[:300]
    }

def pending_trend_analysis(article: dict, reason: str = "") -> dict:
    return {
        "title": article.get("title", "제목 확인 필요"),
        "summary": "AI 요약 대기 중입니다. Gemini 한도 또는 일시 오류로 원문만 먼저 수집했습니다.",
        "source": "AI 요약 대기",
        "analysis_status": "pending",
        "analysis_error": reason[:300]
    }

def parse_source_datetime(date_text: str):
    """Parse common RSS/Atom date formats into a timezone-aware datetime."""
    if not date_text:
        return None
    value = date_text.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except Exception:
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed

def normalize_source_date(date_text: str) -> str:
    parsed = parse_source_datetime(date_text)
    return parsed.isoformat() if parsed else ""

def is_recent_source_item(date_text: str, freshness_hours: int = ALERT_FRESHNESS_HOURS) -> bool:
    parsed = parse_source_datetime(date_text)
    if not parsed:
        return False
    now = datetime.now(parsed.tzinfo)
    return parsed >= now - timedelta(hours=freshness_hours)

def format_source_date_for_note(date_text: str) -> str:
    parsed = parse_source_datetime(date_text)
    if not parsed:
        return date_text or "Unknown"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")

def get_apple_notes_folders(profile_name: str):
    """Returns the Apple Notes folder names, customized by profile."""
    if profile_name in ["기본 프로필", "Default"]:
        return FOLDER_DOCS, FOLDER_TRENDS, FOLDER_REPORTS
    return f"{FOLDER_DOCS} ({profile_name})", f"{FOLDER_TRENDS} ({profile_name})", f"{FOLDER_REPORTS} ({profile_name})"

async def analyze_doc_update(agent: Agent, competitor_name: str, update: dict) -> dict:
    """Uses Gemini to summarize the competitor update and identify technical impact."""
    prompt = f"""
Analyze the following release note update from {competitor_name}:
Title: {update['title']}
Link: {update['link']}
Description: {update['description']}

Please respond in Korean. Provide the output in the following format:
Summary: <A concise 2-3 sentence summary of the feature/update in Korean>
Impact: <Technical impact or value for developers/users in Korean>
Keywords: <Comma-separated keywords, e.g., Security, CI/CD, AI, Cloud>
"""
    try:
        print("Waiting 13 seconds before calling Gemini API to stay within free-tier rate limits...")
        await asyncio.sleep(13)
        response = await agent.chat(prompt)
        text = await response.text()
        
        # Robust parsing logic
        lines = text.strip().split("\n")
        summary = ""
        impact = ""
        keywords_str = ""
        current_section = None
        
        for line in lines:
            clean_line = line.replace("**", "").replace("__", "").replace("*", "").replace("-", "").strip()
            clean_line_lower = clean_line.lower()
            
            is_header = False
            if clean_line_lower.startswith("summary") or "요약" in clean_line:
                current_section = "summary"
                is_header = True
            elif clean_line_lower.startswith("impact") or "영향" in clean_line or "효과" in clean_line:
                current_section = "impact"
                is_header = True
            elif clean_line_lower.startswith("keywords") or "키워드" in clean_line:
                current_section = "keywords"
                is_header = True
                
            if is_header:
                if ":" in clean_line:
                    content = clean_line.split(":", 1)[1].strip()
                    if content:
                        if current_section == "summary":
                            summary = content
                        elif current_section == "impact":
                            impact = content
                        elif current_section == "keywords":
                            keywords_str = content
            else:
                if current_section == "summary":
                    summary += (" " + clean_line if summary else clean_line)
                elif current_section == "impact":
                    impact += (" " + clean_line if impact else clean_line)
                elif current_section == "keywords":
                    keywords_str += (" " + clean_line if keywords_str else clean_line)
                    
        summary = summary.strip() or "No summary generated."
        impact = impact.strip() or "No impact analysis generated."
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()] if keywords_str.strip() else ["General"]
        
        return {
            "summary": summary,
            "impact": impact,
            "keywords": keywords,
            "analysis_status": "complete",
            "analysis_error": ""
        }
    except Exception as e:
        print(f"Error analyzing doc update: {e}")
        return {
            "summary": "AI 요약 대기 중입니다. Gemini 한도 또는 일시 오류로 원문만 먼저 수집했습니다.",
            "impact": "AI 분석 대기 중입니다. 다음 스캔에서 요약을 다시 시도합니다.",
            "keywords": ["AI 요약 대기"],
            "analysis_status": "pending",
            "analysis_error": str(e)[:300]
        }

async def analyze_news_trend(agent: Agent, keyword: str, article: dict) -> dict:
    """Uses Gemini to filter noise and summarize trend news."""
    prompt = f"""
Evaluate the following news article for the keyword '{keyword}':
Title: {article['title']}
Description: {article['description']}
Link: {article['link']}

Determine if this news represents a significant technological trend, industry update, or relevant discussion (Yes/No).
If NO, reply ONLY with the word "SKIP" and nothing else.
If YES, respond in Korean in this format:
Title: <A translated or polished clean title in Korean>
Summary: <A 2-3 sentence summary of the trend/news in Korean>
Source: <The publisher or news channel if available, or 'Web'>
"""
    try:
        print("Waiting 13 seconds before calling Gemini API to stay within free-tier rate limits...")
        await asyncio.sleep(13)
        response = await agent.chat(prompt)
        text = await response.text()
        
        if text.strip().upper() == "SKIP" or "SKIP" in text.strip()[:10].upper():
            return None
            
        # Robust parsing logic
        lines = text.strip().split("\n")
        clean_title = article.get('title', '제목 확인 필요')
        summary = ""
        source = ""
        current_section = None
        
        for line in lines:
            clean_line = line.replace("**", "").replace("__", "").replace("*", "").replace("-", "").strip()
            clean_line_lower = clean_line.lower()
            
            is_header = False
            if clean_line_lower.startswith("title") or "제목" in clean_line:
                current_section = "title"
                is_header = True
            elif clean_line_lower.startswith("summary") or "요약" in clean_line:
                current_section = "summary"
                is_header = True
            elif clean_line_lower.startswith("source") or "출처" in clean_line:
                current_section = "source"
                is_header = True
                
            if is_header:
                if ":" in clean_line:
                    content = clean_line.split(":", 1)[1].strip()
                    if content:
                        if current_section == "title":
                            clean_title = content
                        elif current_section == "summary":
                            summary = content
                        elif current_section == "source":
                            source = content
            else:
                if current_section == "title":
                    clean_title = (" " + clean_line if clean_title != article.get('title') else clean_line)
                elif current_section == "summary":
                    summary += (" " + clean_line if summary else clean_line)
                elif current_section == "source":
                    source += (" " + clean_line if source else clean_line)
                    
        clean_title = clean_title.strip() or article.get('title', '제목 확인 필요')
        summary = summary.strip() or "No summary generated."
        source = source.strip() or "News"
        
        return {
            "title": clean_title,
            "summary": summary,
            "source": source,
            "analysis_status": "complete",
            "analysis_error": ""
        }
    except Exception as e:
        print(f"Error analyzing news trend: {e}")
        return {
            "title": article.get("title", "제목 확인 필요"),
            "summary": "AI 요약 대기 중입니다. Gemini 한도 또는 일시 오류로 원문만 먼저 수집했습니다.",
            "source": "AI 요약 대기",
            "analysis_status": "pending",
            "analysis_error": str(e)[:300]
        }

async def generate_strategic_report(agent: Agent, doc_notes: list, trend_notes: list, template_prompt: str) -> str:
    """Generates a strategic report summarizing docs and trends using a custom prompt template."""
    docs_context = "\n".join([
        (
            f"- Competitor/Product: {note.get('competitor', 'Unknown')}\n"
            f"  Title: {note['title']}\n"
            f"  Published: {note.get('published_at') or note.get('date', '')}\n"
            f"  Summary: {note['summary']}\n"
            f"  Impact: {note.get('impact', '')}\n"
            f"  Keywords: {note.get('keywords', '')}"
        )
        for note in doc_notes
    ])
    trends_context = "\n".join([
        (
            f"- Keyword: {note.get('keyword', '')}\n"
            f"  Folder: {note.get('folder', '미분류')}\n"
            f"  Source: {note.get('source', '')}\n"
            f"  Published: {note.get('published_at', '')}\n"
            f"  Title: {note['title']}\n"
            f"  Summary: {note['summary']}"
        )
        for note in trend_notes
    ])
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    # Replace placeholders in template prompt
    prompt = template_prompt.replace("{docs_context}", docs_context) \
                            .replace("{trends_context}", trends_context) \
                            .replace("{current_date}", current_date)
                            
    try:
        response = await agent.chat(prompt)
        return await response.text()
    except Exception as e:
        print(f"Error generating strategic report: {e}")
        return f"# Tech Watch 전략 보고서 ({current_date})\n\nFailed to generate report using AI: {e}"

async def retry_pending_ai_analysis(agent: Agent, profile_id: int):
    """Retries AI summaries that were saved while Gemini was unavailable or rate-limited."""
    pending_docs = database.get_pending_ai_docs(profile_id, limit=10)
    pending_trends = database.get_pending_ai_trends(profile_id, limit=10)
    
    if not pending_docs and not pending_trends:
        return
    
    print(f"\n--- 0. Retrying Pending AI Summaries ({len(pending_docs)} docs, {len(pending_trends)} trends) ---")
    
    for doc in pending_docs:
        print(f"Retrying doc AI summary: {doc.get('title', '')}")
        analysis = await analyze_doc_update(agent, doc.get("competitor", "Unknown"), {
            "title": doc.get("title", ""),
            "link": doc.get("link", ""),
            "description": doc.get("summary", "")
        })
        if analysis.get("analysis_status") == "complete":
            database.update_doc_analysis(
                doc["id"],
                analysis["summary"],
                analysis["impact"],
                analysis["keywords"],
                "complete",
                ""
            )
        else:
            print(f"Doc still pending: {doc.get('title', '')}")
            database.increment_doc_retry(doc["id"], analysis.get("analysis_error", "Unknown error"))
    
    for trend in pending_trends:
        print(f"Retrying trend AI summary: {trend.get('title', '')}")
        analysis = await analyze_news_trend(agent, trend.get("keyword", ""), {
            "title": trend.get("title", ""),
            "link": trend.get("link", ""),
            "description": trend.get("summary", "")
        })
        if analysis and analysis.get("analysis_status") == "complete":
            database.update_trend_analysis(
                trend["id"],
                analysis["title"],
                analysis["summary"],
                analysis["source"],
                "complete",
                ""
            )
        elif analysis is None:
            print(f"Trend item was skipped by AI (noise). Deleting: {trend.get('title', '')}")
            database.delete_scanned_trend(trend["id"])
        else:
            print(f"Trend still pending: {trend.get('title', '')}")
            database.increment_trend_retry(trend["id"], analysis.get("analysis_error", "Unknown error"))

async def run_monitoring_scan_for_profile(agent: Agent, profile: dict):
    """Runs a single monitoring scan for a specific profile."""
    profile_id = profile["id"]
    profile_name = profile["name"]
    webhook_url = profile.get("discord_webhook_url", "")
    
    print(f"\n==========================================")
    print(f"Running Monitoring Scan for Profile: '{profile_name}' (ID: {profile_id})")
    print(f"==========================================")
    
    # Resolve Apple Notes folder names for this profile
    folder_docs, folder_trends, _ = get_apple_notes_folders(profile_name)
    
    # Try to initialize folders in Apple Notes (macOS fallback)
    has_apple_notes = False
    try:
        apple_notes.ensure_folder_exists(folder_docs)
        apple_notes.ensure_folder_exists(folder_trends)
        has_apple_notes = True
    except Exception as e:
        print(f"[Apple Notes Warning] Could not connect to Apple Notes: {e}. Storing data in SQLite database only.")

    await retry_pending_ai_analysis(agent, profile_id)

    # Get feeds and keywords for this profile
    feeds = database.get_profile_feeds(profile_id)
    keywords = database.get_profile_keywords(profile_id)
    
    # Fetch existing item titles to avoid duplicates (from SQLite & Apple Notes if available)
    existing_docs = set(database.get_scanned_doc_titles(profile_id))
    if has_apple_notes:
        try:
            existing_docs.update(apple_notes.get_note_titles(folder_docs))
        except Exception:
            pass
            
    print("\n--- 1. Checking Competitor Documentation Feeds ---")
    for doc in feeds:
        name = doc.get("name", "Unknown")
        feed_url = doc.get("feed_url", "")
        if not feed_url:
            continue
            
        print(f"Checking {name} ({feed_url})...")
        updates = monitors.get_competitor_updates(feed_url)
        
        new_count = 0
        for update in updates[:5]: # Check latest 5 entries from feed to prevent flooding
            title = f"[{name}] {update['title']}"
            if title in existing_docs:
                continue
            published_at = normalize_source_date(update.get('date', ''))
            is_recent = is_recent_source_item(update.get('date', ''))
                
            print(f"New update found: {update['title']}")
            analysis = await analyze_doc_update(agent, name, update)
            
            # Save to Database (Main Storage)
            saved = database.save_scanned_doc(
                profile_id=profile_id,
                competitor=name,
                title=title,
                link=update['link'],
                date=update['date'],
                summary=update.get('description', '') if analysis.get("analysis_status") == "pending" else analysis['summary'],
                impact=analysis['impact'],
                keywords=analysis['keywords'],
                published_at=published_at,
                analysis_status=analysis.get("analysis_status", "complete"),
                analysis_error=analysis.get("analysis_error", ""),
                doc_type=doc.get("feed_type", "competitor")
            )
            
            if saved:
                new_count += 1
                
                # Save to Apple Notes (macOS Fallback)
                if has_apple_notes:
                    body_md = f"""# {title}
                    
**Published**: {format_source_date_for_note(update.get('date', ''))}
**Collected**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Original Link**: {update['link']}

### Summary
{analysis['summary']}

### Impact & Value
{analysis['impact']}

### Keywords
{', '.join(analysis['keywords'])}
"""
                    try:
                        apple_notes.create_note(folder_docs, title, body_md)
                    except Exception as e:
                        print(f"[Apple Notes Error] Failed to write note: {e}")
                
                # Send Discord Notification
                if webhook_url and is_recent and analysis.get("analysis_status") == "complete":
                    discord_notifier.send_doc_update_alert(
                        webhook_url,
                        name,
                        update['title'],
                        analysis['summary'],
                        analysis['keywords'],
                        update['link'],
                        format_source_date_for_note(update.get('date', ''))
                    )
                elif webhook_url and analysis.get("analysis_status") == "pending":
                    print("Skipping Discord doc alert because AI summary is pending.")
                elif webhook_url:
                    print(f"Skipping Discord doc alert because source date is older than {ALERT_FRESHNESS_HOURS} hours or missing: {update.get('date', '')}")
        print(f"-> Logged {new_count} new updates for {name}.")
        
    print("\n--- 2. Scanning Web for Trend Keywords ---")
    existing_trends = set(database.get_scanned_trend_titles(profile_id))
    if has_apple_notes:
        try:
            existing_trends.update(apple_notes.get_note_titles(folder_trends))
        except Exception:
            pass
            
    for item in keywords:
        keyword = item["keyword"]
        folder = item.get("folder", "미분류")
        print(f"Searching keyword: '{keyword}' (Folder: {folder})...")
        articles = monitors.search_google_news(keyword, recency_days=NEWS_RECENCY_DAYS)
        
        new_count = 0
        for article in articles[:5]: # Check top 5 news entries
            title = f"[News] {article['title']}"
            # Check length or clean title to match existing titles
            if any(t in title or title in t for t in existing_trends):
                continue
            published_at = normalize_source_date(article.get('date', ''))
            is_recent = is_recent_source_item(article.get('date', ''))
                
            analysis = await analyze_news_trend(agent, keyword, article)
            if not analysis:
                continue
                
            print(f"New trend match: {analysis['title']}")
            
            note_title = f"[{keyword}] {analysis['title']}"
            if len(note_title) > 100:
                note_title = note_title[:97] + "..."
                
            # Save to Database (Main Storage)
            saved = database.save_scanned_trend(
                profile_id=profile_id,
                keyword=keyword,
                title=note_title,
                link=article['link'],
                summary=article.get('description', '') if analysis.get("analysis_status") == "pending" else analysis['summary'],
                source=analysis['source'],
                published_at=published_at,
                analysis_status=analysis.get("analysis_status", "complete"),
                analysis_error=analysis.get("analysis_error", "")
            )
            
            if saved:
                new_count += 1
                
                # Save to Apple Notes (macOS Fallback)
                if has_apple_notes:
                    body_md = f"""# {analysis['title']}

**Keyword**: {keyword}
**Source**: {analysis['source']}
**Published**: {format_source_date_for_note(article.get('date', ''))}
**Collected**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Original Link**: {article['link']}

### Summary
{analysis['summary']}
"""
                    try:
                        apple_notes.create_note(folder_trends, note_title, body_md)
                    except Exception as e:
                        print(f"[Apple Notes Error] Failed to write note: {e}")
                
                # Send Discord Notification
                if webhook_url and is_recent and analysis.get("analysis_status") == "complete":
                    discord_notifier.send_trend_alert(
                        webhook_url,
                        keyword,
                        analysis['title'],
                        analysis['source'],
                        analysis['summary'],
                        article['link'],
                        format_source_date_for_note(article.get('date', ''))
                    )
                elif webhook_url and analysis.get("analysis_status") == "pending":
                    print("Skipping Discord trend alert because AI summary is pending.")
                elif webhook_url:
                    print(f"Skipping Discord trend alert because source date is older than {ALERT_FRESHNESS_HOURS} hours or missing: {article.get('date', '')}")
        print(f"-> Logged {new_count} new trend items for '{keyword}'.")

def get_report_period(report_type: str) -> str:
    now = datetime.now()
    if report_type == "monthly":
        return now.strftime("%Y-%m")
    if report_type == "starred":
        return now.strftime("%Y-%m-%d-%H%M")
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"

async def check_and_generate_report_for_profile(agent: Agent, profile: dict, force: bool = False, starred_only: bool = False, report_type: str = "weekly", scope_folder: str = "", scope_keyword: str = "", keyword_match_mode: str = "any"):
    """Generates weekly, monthly, or starred strategic reports for a profile."""
    profile_id = profile["id"]
    profile_name = profile["name"]
    webhook_url = profile.get("discord_webhook_url", "")
    if starred_only:
        report_type = "starred"
    if report_type not in ("weekly", "monthly", "starred"):
        report_type = "weekly"
    period_key = get_report_period(report_type)
    scoped_report = bool(scope_folder or scope_keyword)
    
    if starred_only:
        print(f"\n--- 3. Compiling Starred-Only Strategic Report for '{profile_name}' ---")
        should_run = True
    elif scoped_report:
        print(f"\n--- 3. Compiling scoped {report_type} Strategic Report for '{profile_name}' ---")
        should_run = True
    else:
        print(f"\n--- 3. Checking {report_type} Strategic Report Schedule for '{profile_name}' ({period_key}) ---")
        should_run = force or not database.report_exists(profile_id, report_type, period_key)
            
    if not should_run:
        print(f"{report_type.title()} report already exists for '{profile_name}' period {period_key}. Skipping.")
        return
        
    print(f"Compiling {report_type} 전략 보고서 (Strategic Report) for profile: '{profile_name}'...")
    
    # Retrieve docs and trends from SQLite (much cleaner & cross-platform than Apple Notes HTML scraping)
    doc_search = scope_keyword if scope_keyword else ""
    doc_notes = [] if scope_folder and not scope_keyword else database.get_docs(profile_id, limit=50, search=doc_search, starred_only=starred_only, match_mode=keyword_match_mode)
    trend_notes = database.get_trends_for_report(profile_id, limit=50, starred_only=starred_only, folder=scope_folder, keyword=scope_keyword, match_mode=keyword_match_mode)
    
    if not doc_notes and not trend_notes:
        if starred_only:
            print("No starred updates or trends logged in Database yet. Cannot generate starred report.")
        else:
            print("No updates or trends logged in Database yet. Cannot generate report.")
        return
        
    # Fetch resolved template from database
    if report_type == "monthly":
        template_prompt = database.get_template_content("monthly")
    elif report_type == "weekly":
        template_prompt = database.get_template_content("basic")
    else:
        template_prompt = database.get_resolved_template_for_profile(profile_id)
    if not template_prompt:
        # Emergency fallback
        template_prompt = """# Tech Watch 전략 보고서 ({current_date})
        
[Competitor Updates]
{docs_context}

[Industry Trends]
{trends_context}

Please write a business summary in Korean."""

    if scoped_report:
        scope_lines = []
        if scope_folder:
            scope_lines.append(f"- 분석 폴더: {scope_folder}")
        if scope_keyword:
            scope_lines.append(f"- 분석 키워드: {scope_keyword}")
            scope_lines.append(f"- 키워드 조건: {'모두 포함(AND)' if keyword_match_mode == 'all' else '하나라도 포함(OR)'}")
        scope_note = "\n".join(scope_lines)
        template_prompt = template_prompt + f"\n\n[Report Scope]\n{scope_note}\n위 범위에 해당하는 데이터만 중심으로 분석하고, 범위 밖 데이터는 보조 근거로만 사용하세요."

    # Generate strategic analysis
    report_content = await generate_strategic_report(agent, doc_notes, trend_notes, template_prompt)
    
    # Save report to Database
    today_str = datetime.now().strftime("%Y-%m-%d")
    if starred_only:
        report_title = f"중요 보관함 기술 신호 보고서 ({today_str})"
    elif report_type == "monthly":
        report_title = f"솔루션전략팀 월간 전략 보고서 ({period_key})"
    else:
        report_title = f"주간 기술 신호 및 경쟁사 동향 보고서 ({period_key})"
    if scoped_report:
        scope_label = scope_folder or scope_keyword
        report_title = f"{report_title} - {scope_label}"
    
    saved = database.save_report(profile_id, report_title, report_content, report_type, period_key if not scoped_report else f"{period_key}-scoped-{today_str}")
    if saved:
        print(f"Strategic report '{report_title}' saved to SQLite database.")
        
        # Save report to Apple Notes (macOS Fallback)
        _, _, folder_reports = get_apple_notes_folders(profile_name)
        try:
            apple_notes.ensure_folder_exists(folder_reports)
            apple_notes.create_note(folder_reports, report_title, report_content)
            print(f"Strategic report saved to Apple Notes in '{folder_reports}'.")
        except Exception as e:
            print(f"[Apple Notes Warning] Failed to save report note: {e}")
            
        # Extract Executive Summary for Discord
        summary_section = ""
        lines = report_content.split("\n")
        in_summary = False
        summary_lines = []
        for line in lines:
            if "Executive Summary" in line or "핵심 요약" in line:
                in_summary = True
                continue
            elif in_summary and line.startswith("##"):
                break
            if in_summary:
                summary_lines.append(line)
        
        summary_text = "\n".join(summary_lines).strip()
        if not summary_text:
            summary_text = f"[{profile_name}] 보고서가 성공적으로 생성되었습니다. 웹 대시보드 및 맥북 메모 앱에서 확인하실 수 있습니다."
            
        # Send Discord notify
        if webhook_url:
            discord_notifier.send_report_alert(
                webhook_url,
                f"[{profile_name}] {report_title}",
                summary_text
            )
    else:
        print("Failed to save report to Database.")

async def main():
    parser = argparse.ArgumentParser(description="Tech Watch Tracker Agent")
    parser.add_argument("--profile-id", type=int, help="Run only for the specified profile ID. If omitted, runs for all profiles.")
    parser.add_argument("--report-only", action="store_true", help="Generate the strategic report immediately and exit.")
    parser.add_argument("--retry-only", action="store_true", help="Retry pending AI analyses only and exit.")
    parser.add_argument("--report-type", choices=["weekly", "monthly"], default="weekly", help="Report type to generate when using --report-only or scheduled reporting.")
    parser.add_argument("--scope-folder", default="", help="Generate a manual report scoped to a keyword folder.")
    parser.add_argument("--scope-keyword", default="", help="Generate a manual report scoped to a specific keyword/search term.")
    parser.add_argument("--keyword-match-mode", choices=["any", "all"], default="any", help="Keyword filter mode for scoped reports.")
    parser.add_argument("--force-report", action="store_true", help="Force report generation during the scan.")
    parser.add_argument("--starred-only", action="store_true", help="Generate the strategic report using only starred items.")
    args = parser.parse_args()
    
    # Initialize the database schema and migrate config.json if database is empty
    database.init_db()
    
    # Select profiles to scan
    if args.profile_id:
        profile = database.get_profile_by_id(args.profile_id)
        if not profile:
            print(f"ERROR: Profile with ID {args.profile_id} not found in database.")
            return
        profiles = [profile]
    else:
        profiles = database.get_profiles()
        if not profiles:
            print("ERROR: No profiles found in database. Create at least one profile first.")
            return
            
    print(f"Loaded {len(profiles)} profiles for tech watch tracking.")
    
    for profile in profiles:
        api_key = profile.get("gemini_api_key", "")
        if not api_key:
            # Try to fall back to a global config.json api key if database API key is empty
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                        api_key = config_data.get("gemini_api_key", "")
                except Exception:
                    pass
                    
        if not api_key:
            print(f"ERROR: Gemini API Key is missing for profile '{profile['name']}'. Skipping scan.")
            continue
            
        # Configure the Google Antigravity Agent for this profile
        sdk_config = LocalAgentConfig(
            api_key=api_key,
            system_instructions=(
                "You are a professional tech watch analyst who helps developers and managers "
                "track competitor updates and technology trends. Summarize technical content in "
                "Korean, focusing on developer productivity, business impact, and action items."
            )
        )
        
        print(f"\nInitializing Google Antigravity Agent for '{profile['name']}' at {datetime.now()}...")
        
        try:
            async with Agent(config=sdk_config) as agent:
                if args.report_only:
                    await check_and_generate_report_for_profile(
                        agent,
                        profile,
                        force=True,
                        starred_only=args.starred_only,
                        report_type=args.report_type,
                        scope_folder=args.scope_folder.strip(),
                        scope_keyword=args.scope_keyword.strip(),
                        keyword_match_mode=args.keyword_match_mode
                    )
                elif args.retry_only:
                    await retry_pending_ai_analysis(agent, profile['id'])
                else:
                    # 1. Run the scanning process for competitor documentation and keyword news
                    await run_monitoring_scan_for_profile(agent, profile)
                    
                    # 2. Archive scheduled weekly and monthly strategic reports
                    if profile.get("auto_report_enabled", 1):
                        await check_and_generate_report_for_profile(agent, profile, force=args.force_report, report_type="weekly")
                        await check_and_generate_report_for_profile(agent, profile, force=args.force_report, report_type="monthly")
                    else:
                        print(f"Automatic report generation is disabled for profile '{profile['name']}'. Use manual report generation when needed.")
        except Exception as e:
            print(f"ERROR executing agent scan for profile '{profile['name']}': {e}")
            import traceback
            traceback.print_exc()
            
    print("\nScan completed.")

if __name__ == "__main__":
    # Execute the async main function
    asyncio.run(main())
