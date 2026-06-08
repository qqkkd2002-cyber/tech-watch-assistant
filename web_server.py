import sys
import os
import json
import asyncio
import platform
import ssl
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# First, make sure fastapi and uvicorn are importable. 
# We'll fail gracefully or print instructions if not installed.
try:
    from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Header
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("FastAPI or Uvicorn not installed. Please run setup first.")
    sys.exit(1)

import database
database.init_db()

try:
    from google.antigravity import Agent, LocalAgentConfig
except Exception:
    Agent = None
    LocalAgentConfig = None

app = FastAPI(title="Tech Watch Tracker Web Server")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables for background process management
active_process = None
active_logs: List[str] = []
scan_status = "idle"  # "idle" or "running"
active_profile_id: Optional[int] = None
auto_scheduler_task: Optional[asyncio.Task] = None
last_auto_scan_attempts: Dict[int, datetime] = {}

# Default Admin Passcode from config.json or fallback
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
def get_admin_passcode() -> str:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("admin_passcode", "admin123")
        except Exception:
            pass
    return "admin123"

# --- Models ---
class FeedItem(BaseModel):
    name: str
    feed_url: str

class KeywordItem(BaseModel):
    keyword: str
    folder: str

class ProfileUpdatePayload(BaseModel):
    name: str
    gemini_api_key: str
    discord_webhook_url: str
    check_interval_hours: int
    keywords: List[KeywordItem]
    feeds: List[FeedItem]
    report_template_type: str = 'basic'
    custom_report_template: str = ''
    auto_report_enabled: bool = True

class ProfileCreatePayload(BaseModel):
    name: str

class BoardPostPayload(BaseModel):
    profile_id: int
    title: str
    content: str

class KeywordSuggestionRequest(BaseModel):
    profile_id: int
    seed_keyword: str = ""
    keywords: List[KeywordItem] = []

class FeedSuggestionRequest(BaseModel):
    profile_id: int
    seed_topic: str = ""
    keywords: List[KeywordItem] = []
    feeds: List[FeedItem] = []

def extract_json_object(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)

def normalize_candidate_url(url: str) -> str:
    cleaned = (url or "").strip()
    if cleaned and not cleaned.startswith(("http://", "https://")):
        cleaned = "https://" + cleaned
    return cleaned

def validate_monitoring_url(url: str) -> Dict[str, Any]:
    """Fetches a small sample of a URL and classifies it as RSS/Atom, docs/blog page, or invalid."""
    target_url = normalize_candidate_url(url)
    if not target_url:
        return {"status": "invalid", "kind": "unknown", "message": "URL이 비어 있습니다."}

    parsed = urllib.parse.urlparse(target_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"status": "invalid", "kind": "unknown", "message": "URL 형식이 올바르지 않습니다."}

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) TechWatchTracker/1.0",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.8",
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(target_url, headers=headers, method="GET")
        with urllib.request.urlopen(req, context=ctx, timeout=12) as response:
            final_url = response.geturl()
            status_code = getattr(response, "status", 200)
            content_type = response.headers.get("content-type", "").lower()
            sample = response.read(120000).decode("utf-8", errors="ignore").strip()
    except Exception as e:
        return {
            "status": "invalid",
            "kind": "unknown",
            "url": target_url,
            "message": f"접속 검증 실패: {e}"
        }

    sample_lower = sample[:2000].lower()
    is_feed = (
        "rss+xml" in content_type
        or "atom+xml" in content_type
        or "<rss" in sample_lower
        or "<feed" in sample_lower
        or "<rdf:rdf" in sample_lower
    )
    is_html = "text/html" in content_type or "<html" in sample_lower

    if is_feed:
        return {
            "status": "verified",
            "kind": "rss",
            "url": final_url,
            "http_status": status_code,
            "message": "RSS/Atom 피드로 검증되었습니다."
        }
    if is_html:
        return {
            "status": "verified",
            "kind": "docs",
            "url": final_url,
            "http_status": status_code,
            "message": "접속 가능한 문서/블로그 페이지로 검증되었습니다. RSS가 아니므로 업데이트 감지는 제한적일 수 있습니다."
        }

    return {
        "status": "warning",
        "kind": "unknown",
        "url": final_url,
        "http_status": status_code,
        "message": "접속은 가능하지만 RSS/문서 페이지인지 명확하지 않습니다."
    }

# --- Helper Functions ---
def is_localhost(request: Request) -> bool:
    """Checks if the request is originating from localhost."""
    client_host = request.client.host if request.client else "unknown"
    return client_host in ("127.0.0.1", "localhost", "::1")

def verify_admin_access(request: Request, x_admin_passcode: Optional[str] = Header(None)):
    """Verifies if the requester is either on localhost or has provided the correct admin passcode."""
    if is_localhost(request):
        return True
    
    expected_passcode = get_admin_passcode()
    if x_admin_passcode == expected_passcode:
        return True
        
    raise HTTPException(status_code=401, detail="Unauthorized: Administrative access passcode required.")

def parse_db_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace(" ", "T"))
    except Exception:
        return None

def is_profile_due_for_scan(profile: Dict[str, Any], now: datetime) -> bool:
    profile_id = profile["id"]
    interval_hours = max(int(profile.get("check_interval_hours") or 24), 1)
    interval = timedelta(hours=interval_hours)
    
    last_attempt = last_auto_scan_attempts.get(profile_id)
    if last_attempt and now - last_attempt < interval:
        return False
    
    latest_collection = parse_db_datetime(database.get_latest_collection_at(profile_id))
    if latest_collection and now - latest_collection < interval:
        return False
    
    return True

async def auto_scan_scheduler():
    """Runs profile scans on the configured interval while the web server is alive."""
    active_logs.append("[System] Auto scan scheduler started.\n")
    while True:
        try:
            if scan_status == "idle":
                now = datetime.now()
                for profile_row in database.get_profiles():
                    profile = dict(profile_row)
                    if not is_profile_due_for_scan(profile, now):
                        continue
                    profile_id = profile["id"]
                    last_auto_scan_attempts[profile_id] = now
                    active_logs.append(
                        f"[System] Auto scan due for profile '{profile['name']}' "
                        f"(interval: {profile.get('check_interval_hours') or 24}h).\n"
                    )
                    asyncio.create_task(run_agent_subprocess(["--profile-id", str(profile_id)], profile_id))
                    break
        except Exception as e:
            active_logs.append(f"[System] Auto scan scheduler error: {e}\n")
        await asyncio.sleep(60)

@app.on_event("startup")
async def start_auto_scan_scheduler():
    global auto_scheduler_task
    if auto_scheduler_task is None or auto_scheduler_task.done():
        auto_scheduler_task = asyncio.create_task(auto_scan_scheduler())

@app.on_event("shutdown")
async def stop_auto_scan_scheduler():
    if auto_scheduler_task and not auto_scheduler_task.done():
        auto_scheduler_task.cancel()

# --- Background Task ---
async def run_agent_subprocess(args: List[str], profile_id: Optional[int] = None):
    global active_process, active_logs, scan_status, active_profile_id
    
    scan_status = "running"
    active_profile_id = profile_id
    active_logs.clear()
    
    python_bin = sys.executable
    target_path = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    if os.path.exists(target_path):
        python_bin = target_path
        
    cmd = [python_bin, "-u", "agent.py"] + args
    
    # Handle M-series Apple Silicon ARM64 native architecture
    is_arm64 = False
    sysctl_paths = ["/usr/sbin/sysctl", "sysctl"]
    for sysctl_path in sysctl_paths:
        try:
            res = await asyncio.create_subprocess_exec(
                sysctl_path, "-n", "hw.optional.arm64",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await res.communicate()
            if stdout.decode().strip() == "1":
                is_arm64 = True
                break
        except Exception:
            pass
            
    if is_arm64 or platform.machine() == "arm64":
        arch_path = "/usr/bin/arch" if os.path.exists("/usr/bin/arch") else "arch"
        cmd = [arch_path, "-arm64"] + cmd
        
    active_logs.append(f"[System] Launching background agent command: {' '.join(cmd)}\n\n")
    
    try:
        active_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        
        # Read output line by line as it is streamed
        while True:
            line = await active_process.stdout.readline()
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='ignore')
            active_logs.append(decoded_line)
            # Cap log lines in memory
            if len(active_logs) > 5000:
                active_logs.pop(0)
                
        await active_process.wait()
        active_logs.append("\n[System] Scan process completed successfully.\n")
    except Exception as e:
        active_logs.append(f"\n[System] ERROR running agent process: {e}\n")
    finally:
        scan_status = "idle"
        active_process = None
        active_profile_id = None

# --- API Endpoints ---

@app.get("/api/status")
async def get_status(request: Request):
    """Returns the status and current live logs."""
    tail_logs = active_logs[-300:]
    return {
        "status": scan_status,
        "active_profile_id": active_profile_id,
        "is_admin": is_localhost(request),
        "log_line_count": len(active_logs),
        "logs": "".join(tail_logs)
    }

@app.post("/api/scan")
async def trigger_scan(profile_id: Optional[int] = None, background_tasks: BackgroundTasks = BackgroundTasks()):
    """Triggers an async competitor scan."""
    global scan_status
    if scan_status == "running":
        raise HTTPException(status_code=400, detail="Scan process is already running.")
        
    args = []
    if profile_id:
        args += ["--profile-id", str(profile_id)]
        
    background_tasks.add_task(run_agent_subprocess, args, profile_id)
    return {"message": "Scan started in background."}

@app.post("/api/report/generate")
async def trigger_report(profile_id: int, starred_only: bool = False, report_type: str = "weekly", scope_folder: str = "", scope_keyword: str = "", keyword_match_mode: str = "any", background_tasks: BackgroundTasks = BackgroundTasks()):
    """Triggers an immediate strategic report generation."""
    global scan_status
    if scan_status == "running":
        raise HTTPException(status_code=400, detail="Another process is already running.")
        
    args = ["--profile-id", str(profile_id), "--report-only"]
    if starred_only:
        args.append("--starred-only")
    elif report_type in ("weekly", "monthly"):
        args += ["--report-type", report_type]
    if scope_folder:
        args += ["--scope-folder", scope_folder]
    if scope_keyword:
        args += ["--scope-keyword", scope_keyword]
        if keyword_match_mode in ("any", "all"):
            args += ["--keyword-match-mode", keyword_match_mode]
        
    background_tasks.add_task(run_agent_subprocess, args, profile_id)
    return {"message": "Report generation started in background."}

@app.post("/api/keywords/suggest")
async def suggest_keywords(payload: KeywordSuggestionRequest):
    """Suggests related monitoring keywords, folders, and duplicate cleanup ideas using AI."""
    if Agent is None or LocalAgentConfig is None:
        raise HTTPException(status_code=500, detail="AI SDK is not available in this environment.")

    profile = database.get_profile_by_id(payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    api_key = profile.get("gemini_api_key", "")
    if not api_key or api_key == "••••••••":
        raise HTTPException(status_code=400, detail="Gemini API Key is required for AI keyword suggestions.")

    seed_keyword = payload.seed_keyword.strip()
    current_keywords = payload.keywords or database.get_profile_keywords(payload.profile_id)
    keyword_lines = "\n".join([
        f"- {item.keyword} (folder: {item.folder or '미분류'})" if isinstance(item, KeywordItem)
        else f"- {item.get('keyword', '')} (folder: {item.get('folder', '미분류')})"
        for item in current_keywords
    ])
    existing_names = {
        (item.keyword if isinstance(item, KeywordItem) else item.get("keyword", "")).strip().lower()
        for item in current_keywords
    }

    prompt = f"""
You are helping a Korean solution strategy team build a technology monitoring keyword taxonomy.

Seed keyword from the user:
{seed_keyword or "(none)"}

Current monitored keywords and folders:
{keyword_lines or "(none)"}

Please suggest keywords that reduce blind spots in monitoring competitor releases, DevOps/DevSecOps/platform engineering, financial IT modernization, AI engineering, governance, and developer productivity.

Rules:
- Respond ONLY as valid JSON.
- Do not include markdown fences.
- Do not include keywords that are already present in the current list.
- Prefer practical monitoring search terms, not vague categories.
- Mix Korean and English terms when both are useful for Korean news/RSS monitoring.
- Each suggestion must include keyword, folder, reason, priority.
- priority must be "high", "medium", or "low".
- Also identify duplicate or inconsistent existing keywords when useful.

JSON schema:
{{
  "suggestions": [
    {{"keyword": "string", "folder": "string", "reason": "short Korean reason", "priority": "high|medium|low"}}
  ],
  "folder_suggestions": [
    {{"folder": "string", "reason": "short Korean reason"}}
  ],
  "cleanup_suggestions": [
    {{"canonical": "string", "duplicates": ["string"], "reason": "short Korean reason"}}
  ]
}}
"""

    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions="You are a concise taxonomy assistant for technology strategy monitoring. Always output valid JSON only."
    )

    try:
        async with Agent(config=sdk_config) as ai_agent:
            response = await ai_agent.chat(prompt)
            text = await response.text()
        result = extract_json_object(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate keyword suggestions: {e}")

    suggestions = []
    seen = set(existing_names)
    for item in result.get("suggestions", []):
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({
            "keyword": keyword,
            "folder": str(item.get("folder", "미분류")).strip() or "미분류",
            "reason": str(item.get("reason", "")).strip(),
            "priority": str(item.get("priority", "medium")).strip() or "medium"
        })

    return {
        "suggestions": suggestions[:12],
        "folder_suggestions": result.get("folder_suggestions", [])[:6],
        "cleanup_suggestions": result.get("cleanup_suggestions", [])[:6]
    }

@app.post("/api/feeds/suggest")
async def suggest_feeds(payload: FeedSuggestionRequest):
    """Suggests competitor products, docs pages, changelogs, and RSS feeds, then verifies each URL."""
    if Agent is None or LocalAgentConfig is None:
        raise HTTPException(status_code=500, detail="AI SDK is not available in this environment.")

    profile = database.get_profile_by_id(payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    api_key = profile.get("gemini_api_key", "")
    if not api_key or api_key == "••••••••":
        raise HTTPException(status_code=400, detail="Gemini API Key is required for AI feed suggestions.")

    current_keywords = payload.keywords or database.get_profile_keywords(payload.profile_id)
    current_feeds = payload.feeds or database.get_profile_feeds(payload.profile_id)
    seed_topic = payload.seed_topic.strip()

    keyword_lines = "\n".join([
        f"- {item.keyword} (folder: {item.folder or '미분류'})" if isinstance(item, KeywordItem)
        else f"- {item.get('keyword', '')} (folder: {item.get('folder', '미분류')})"
        for item in current_keywords
    ])
    feed_lines = "\n".join([
        f"- {item.name}: {item.feed_url}" if isinstance(item, FeedItem)
        else f"- {item.get('name', '')}: {item.get('feed_url', '')}"
        for item in current_feeds
    ])
    existing_urls = {
        (item.feed_url if isinstance(item, FeedItem) else item.get("feed_url", "")).strip().lower()
        for item in current_feeds
    }

    prompt = f"""
You are helping a Korean solution strategy team configure competitor/product monitoring sources.

Seed topic from the user:
{seed_topic or "(none)"}

Current monitoring keywords:
{keyword_lines or "(none)"}

Current RSS/docs sources:
{feed_lines or "(none)"}

Suggest official or high-signal monitoring sources for competitor/product tracking.

Rules:
- Respond ONLY as valid JSON.
- Do not include markdown fences.
- Prefer official changelog, release notes, RSS/Atom feeds, developer blogs, docs pages, security advisory pages, and status/product update pages.
- Do not invent obscure URLs. Use URLs you are confident exist.
- Do not include URLs already present in the current source list.
- Include both direct RSS/Atom URLs and useful docs/blog pages when appropriate.
- For category, use one of: "release", "changelog", "docs", "blog", "security", "status", "community", "other".
- reason must be Korean and concise.

JSON schema:
{{
  "suggestions": [
    {{
      "name": "source display name",
      "url": "https://example.com/feed.xml",
      "category": "release|changelog|docs|blog|security|status|community|other",
      "reason": "short Korean reason",
      "priority": "high|medium|low"
    }}
  ]
}}
"""

    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions="You recommend reliable competitor monitoring sources. Always output valid JSON only."
    )

    try:
        async with Agent(config=sdk_config) as ai_agent:
            response = await ai_agent.chat(prompt)
            text = await response.text()
        result = extract_json_object(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate feed suggestions: {e}")

    suggestions = []
    seen_urls = set(existing_urls)
    for item in result.get("suggestions", []):
        name = str(item.get("name", "")).strip()
        url = normalize_candidate_url(str(item.get("url", "")).strip())
        if not name or not url:
            continue
        url_key = url.lower().rstrip("/")
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        validation = await asyncio.to_thread(validate_monitoring_url, url)
        suggestions.append({
            "name": name,
            "url": validation.get("url") or url,
            "category": str(item.get("category", "other")).strip() or "other",
            "reason": str(item.get("reason", "")).strip(),
            "priority": str(item.get("priority", "medium")).strip() or "medium",
            "validation": validation
        })

        if len(suggestions) >= 10:
            break

    verified_count = sum(1 for item in suggestions if item.get("validation", {}).get("status") == "verified")
    return {
        "suggestions": suggestions,
        "verified_count": verified_count,
        "total_count": len(suggestions)
    }

@app.post("/api/stop")
async def stop_scan():
    """Kills the active agent process."""
    global active_process, scan_status
    if not active_process:
        return {"message": "No active process to stop."}
        
    try:
        active_process.kill()
        active_logs.append("\n🛑 Process terminated by user request.\n")
        return {"message": "Process terminate signal sent."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to kill process: {e}")

# --- Profiles API ---

@app.get("/api/profiles")
async def api_get_profiles(request: Request):
    """Fetches all profiles with their settings, keywords, and feeds."""
    profiles = database.get_profiles()
    is_local = is_localhost(request)
    result = []
    for p in profiles:
        pid = p["id"]
        p_dict = dict(p)
        p_dict["keywords"] = database.get_profile_keywords(pid)
        p_dict["feeds"] = database.get_profile_feeds(pid)
        
        # Mask sensitive info if not localhost
        if not is_local:
            if p_dict.get("gemini_api_key"):
                p_dict["gemini_api_key"] = "••••••••"
            if p_dict.get("discord_webhook_url"):
                p_dict["discord_webhook_url"] = "••••••••"
                
        result.append(p_dict)
    return result

@app.post("/api/profiles")
async def api_create_profile(payload: ProfileCreatePayload, request: Request):
    """Creates a new empty profile."""
    # Let anyone create profiles, but lock settings updates
    try:
        pid = database.create_profile(name=payload.name)
        return {"id": pid, "message": "Profile created successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/api/profiles/{profile_id}")
async def api_update_profile(profile_id: int, payload: ProfileUpdatePayload, request: Request):
    """Updates settings, keywords, and feeds for a profile."""
    # Retrieve existing settings to check for changes to sensitive fields
    existing = database.get_profile_by_id(profile_id)
    has_sensitive_changes = False
    
    # Resolve values (supporting "••••••••" placeholder from remote clients)
    final_api_key = payload.gemini_api_key
    final_webhook = payload.discord_webhook_url
    final_interval = payload.check_interval_hours
    
    if existing:
        old_api_key = existing.get("gemini_api_key") or ""
        old_webhook = existing.get("discord_webhook_url") or ""
        old_interval = existing.get("check_interval_hours")
        if old_interval is None:
            old_interval = 24
            
        # If remote sent masked placeholder, keep existing value and do not mark as changed
        if final_api_key == "••••••••":
            final_api_key = old_api_key
        elif final_api_key != old_api_key:
            has_sensitive_changes = True
            
        if final_webhook == "••••••••":
            final_webhook = old_webhook
        elif final_webhook != old_webhook:
            has_sensitive_changes = True
            
        if final_interval != old_interval:
            has_sensitive_changes = True
    else:
        # Profile not found, but if they are setting secrets, require admin
        if (final_api_key and final_api_key != "••••••••") or (final_webhook and final_webhook != "••••••••") or final_interval != 24:
            has_sensitive_changes = True
            
    if has_sensitive_changes:
        # Verify Admin passcode unless localhost
        x_admin_passcode = request.headers.get("X-Admin-Passcode")
        verify_admin_access(request, x_admin_passcode)
        
    # 1. Update basic profile fields
    database.update_profile(
        profile_id=profile_id,
        name=payload.name,
        gemini_api_key=final_api_key,
        discord_webhook_url=final_webhook,
        check_interval_hours=final_interval,
        report_template_type=payload.report_template_type,
        custom_report_template=payload.custom_report_template,
        auto_report_enabled=1 if payload.auto_report_enabled else 0
    )
    
    # 2. Update keywords
    keyword_dicts = [{"keyword": kw.keyword, "folder": kw.folder} for kw in payload.keywords]
    database.set_profile_keywords(profile_id, keyword_dicts)
    
    # 3. Update feeds
    feed_list = [{"name": f.name, "feed_url": f.feed_url} for f in payload.feeds]
    database.set_profile_feeds(profile_id, feed_list)
    
    return {"message": "Profile updated successfully."}

@app.delete("/api/profiles/{profile_id}")
async def api_delete_profile(profile_id: int, request: Request):
    """Deletes a profile."""
    # Verify Admin passcode unless localhost
    x_admin_passcode = request.headers.get("X-Admin-Passcode")
    verify_admin_access(request, x_admin_passcode)
    
    database.delete_profile(profile_id)
    return {"message": "Profile deleted successfully."}

# --- Feeds and Reports Data API ---

@app.get("/api/docs")
async def api_get_docs(profile_id: int, search: str = "", limit: int = 50, offset: int = 0, starred_only: bool = False):
    """Retrieves competitor documentation updates for a profile."""
    docs = database.get_docs(profile_id=profile_id, limit=limit, offset=offset, search=search, starred_only=starred_only)
    return docs

@app.get("/api/trends")
async def api_get_trends(profile_id: int, search: str = "", limit: int = 50, offset: int = 0, starred_only: bool = False):
    """Retrieves trend keywords updates for a profile."""
    trends = database.get_trends(profile_id=profile_id, limit=limit, offset=offset, search=search, starred_only=starred_only)
    return trends

@app.put("/api/docs/{doc_id}/star")
async def api_toggle_doc_star(doc_id: int, is_starred: bool):
    """Toggles star bookmark status for a competitor doc update."""
    database.toggle_doc_star(doc_id, 1 if is_starred else 0)
    return {"message": "Doc star status updated successfully."}

@app.put("/api/trends/{trend_id}/star")
async def api_toggle_trend_star(trend_id: int, is_starred: bool):
    """Toggles star bookmark status for a tech trend news item."""
    database.toggle_trend_star(trend_id, 1 if is_starred else 0)
    return {"message": "Trend star status updated successfully."}

@app.get("/api/reports")
async def api_get_reports(profile_id: int, report_type: str = "all"):
    """Lists strategic reports for a profile."""
    reports = database.get_reports(profile_id=profile_id, report_type=report_type)
    return reports

@app.get("/api/reports/{report_id}")
async def api_get_report_detail(report_id: int):
    """Retrieves specific report content."""
    report = database.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report

# --- Bulletin Board API ---

@app.get("/api/board")
async def api_get_board_posts():
    """Retrieves all board posts."""
    return database.get_board_posts()

@app.post("/api/board")
async def api_create_board_post(payload: BoardPostPayload):
    """Creates a new board post."""
    saved = database.save_board_post(
        profile_id=payload.profile_id,
        title=payload.title,
        content=payload.content
    )
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to save post.")
    return {"message": "Post created successfully."}

@app.delete("/api/board/{post_id}")
async def api_delete_board_post(post_id: int, request: Request):
    """Deletes a board post."""
    x_admin_passcode = request.headers.get("X-Admin-Passcode")
    verify_admin_access(request, x_admin_passcode)
    
    database.delete_board_post(post_id)
    return {"message": "Post deleted successfully."}

# --- Global Templates API ---

class GlobalTemplateUpdate(BaseModel):
    template_content: str

@app.get("/api/global_templates")
async def api_get_global_templates():
    """Retrieves all system-wide global templates."""
    return database.get_global_templates()

@app.put("/api/global_templates/{template_id}")
async def api_update_global_template(template_id: str, payload: GlobalTemplateUpdate, request: Request):
    """Updates a system-wide standard template prompt (Admin only)."""
    x_admin_passcode = request.headers.get("X-Admin-Passcode")
    verify_admin_access(request, x_admin_passcode)
    
    database.update_global_template(template_id, payload.template_content)
    return {"message": f"Global template '{template_id}' updated successfully."}

# --- Server Status Check ---
@app.get("/api/auth/check")
async def auth_check(request: Request):
    """Simple check to tell the frontend if they are admin or need a password."""
    is_admin = is_localhost(request)
    return {
        "is_admin": is_admin,
        "message": "Localhost auto-authenticated" if is_admin else "Remote access, authentication required for edit"
    }

@app.post("/api/auth/login")
async def auth_login(payload: Dict[str, str]):
    """Verifies passcode."""
    passcode = payload.get("passcode", "")
    expected = get_admin_passcode()
    if passcode == expected:
        return {"authenticated": True}
    raise HTTPException(status_code=401, detail="Invalid admin passcode.")

# Mount static files directory if it exists
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
else:
    # If static dir doesn't exist yet, we serve a simple fallback HTML
    @app.get("/", response_class=HTMLResponse)
    async def fallback_root():
        return "<h1>Tech Watch Dashboard Web Server is running.</h1><p>Static folder not found.</p>"

if __name__ == "__main__":
    # Run the uvicorn web server
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=False)
