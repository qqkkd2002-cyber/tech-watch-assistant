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
    feed_type: str = 'competitor'

class KeywordItem(BaseModel):
    keyword: str
    folder: str

class ProfileUpdatePayload(BaseModel):
    name: str
    gemini_api_key: str
    discord_webhook_url: str
    check_interval_hours: int
    auto_scan_enabled: bool = True
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

class EditorJudgmentPayload(BaseModel):
    profile_id: int
    ai_review_id: Optional[int] = None
    item_type: str
    item_id: int
    label: str
    note: str = ""

class EditorReviewGeneratePayload(BaseModel):
    profile_id: int
    limit: int = 80
    force: bool = False

class EditorReviewMovePayload(BaseModel):
    profile_id: int
    ai_review_id: int
    target_bucket: str
    note: str = ""

class EditorReviewRefinePayload(BaseModel):
    profile_id: int
    ai_review_id: int

class KeywordSuggestionRequest(BaseModel):
    profile_id: int
    seed_keyword: str = ""
    keywords: List[KeywordItem] = []

class FeedSuggestionRequest(BaseModel):
    profile_id: int
    seed_topic: str = ""
    keywords: List[KeywordItem] = []
    feeds: List[FeedItem] = []
    feed_type: str = 'competitor'

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

def parse_csv_keywords(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]

async def summarize_doc_item(api_key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
Analyze this collected competitor/reference update for a Korean solution strategy team.

Title: {item.get('title', '')}
Source/Product: {item.get('competitor', '')}
Link: {item.get('link', '')}
Collected description/body:
{item.get('summary', '')}

Respond ONLY as valid JSON with this schema:
{{
  "summary": "핵심만 담은 한국어 2-3문장 요약",
  "impact": "전략/제품/개발 생산성 관점의 시사점 1-2문장",
  "keywords": ["keyword1", "keyword2", "keyword3"]
}}
"""
    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions="You summarize collected tech-watch items for a Korean strategy team. Return valid JSON only."
    )
    async with Agent(config=sdk_config) as ai_agent:
        response = await ai_agent.chat(prompt)
        text = await response.text()
    result = extract_json_object(text)
    return {
        "summary": str(result.get("summary", "")).strip() or item.get("summary", ""),
        "impact": str(result.get("impact", "")).strip() or "AI 요약은 생성되었지만 시사점이 비어 있습니다.",
        "keywords": [str(k).strip() for k in result.get("keywords", []) if str(k).strip()] or parse_csv_keywords(item.get("keywords", "")) or ["General"]
    }

async def summarize_trend_item(api_key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    prompt = f"""
Analyze this collected technology news item for a Korean solution strategy team.

Keyword: {item.get('keyword', '')}
Title: {item.get('title', '')}
Link: {item.get('link', '')}
Collected description/body:
{item.get('summary', '')}

Respond ONLY as valid JSON with this schema:
{{
  "title": "한국어로 정리한 간결한 제목",
  "summary": "핵심만 담은 한국어 2-3문장 요약",
  "source": "출처명 또는 News"
}}
"""
    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions="You summarize collected tech trend items for a Korean strategy team. Return valid JSON only."
    )
    async with Agent(config=sdk_config) as ai_agent:
        response = await ai_agent.chat(prompt)
        text = await response.text()
    result = extract_json_object(text)
    return {
        "title": str(result.get("title", "")).strip() or item.get("title", ""),
        "summary": str(result.get("summary", "")).strip() or item.get("summary", ""),
        "source": str(result.get("source", "")).strip() or "News"
    }

def build_editor_profile_context(profile_id: int) -> str:
    profile = database.get_profile_by_id(profile_id) or {}
    keywords = database.get_profile_keywords(profile_id)
    feeds = database.get_profile_feeds(profile_id)

    keyword_lines = []
    for keyword in keywords[:40]:
        folder = keyword.get("folder") or "미분류"
        keyword_lines.append(f"- [{folder}] {keyword.get('keyword', '')}")

    competitor_lines = []
    reference_lines = []
    for feed in feeds[:30]:
        name = feed.get("name") or "이름 없음"
        feed_type = feed.get("feed_type") or "competitor"
        if feed_type == "reference":
            reference_lines.append(f"- {name}")
        else:
            competitor_lines.append(f"- {name}")

    return "\n".join([
        f"Profile name: {profile.get('name', '')}",
        "Monitoring keywords and folders:",
        "\n".join(keyword_lines) if keyword_lines else "- No keywords configured",
        "Competitor/product feeds:",
        "\n".join(competitor_lines) if competitor_lines else "- No competitor feeds configured",
        "Reference/technology feeds:",
        "\n".join(reference_lines) if reference_lines else "- No reference feeds configured",
    ])

async def refine_editor_review_item(api_key: str, item: Dict[str, Any], profile_context: str = "") -> Dict[str, Any]:
    fixed_tag_lines = "\n".join([
        f"- {key}: {label}"
        for key, label in database.SUGGESTED_TAG_LABELS.items()
    ])
    summary_text = item.get("summary", "") or ""
    if len(summary_text) > 2600:
        summary_text = summary_text[:2600].rstrip() + "..."

    prompt = f"""
You are classifying one collected monitoring item for a Korean solution strategy team.

Product identity:
- This app is a pre-accumulation system, not primarily a report writer.
- The core question is whether this item should be kept as reusable strategic material for future reports, upper-level planning, competitor analysis, proposal/RFP evidence, or technology strategy.
- Noise should be demoted, not deleted, because the original item remains searchable in the collection ledger.

Current user's monitoring context:
{profile_context or "- No profile context available"}

Item:
Type: {item.get('item_type', '')}
Title: {item.get('title', '')}
Source: {item.get('source_name', '')}
Category/Keyword: {item.get('category', '')}
Published at: {item.get('published_at', '')}
Current summary/body:
{summary_text}

Allowed primary_bucket values:
- work_signal: directly useful for the user's assigned product/work, monitored competitors/products, proposals, customer response, competitor comparison, or strategy documents
- learning_signal: not directly tied to the user's current responsibility, but useful for technology literacy, strategic sense, or long-term knowledge growth
- noise: likely not useful for later strategy/planning, even if it matched a keyword
- review_queue: use only when there is not enough evidence to choose work_signal, learning_signal, or noise

Allowed suggested_tags. Pick up to 4 from this fixed list only:
{fixed_tag_lines}

Rules:
- Respond ONLY as valid JSON. Do not include markdown fences.
- Classify by reusable value, not simple keyword match.
- Use the profile context to judge whether the item is close to the user's actual work. If it is broadly educational but not close to the profile context, prefer learning_signal over work_signal.
- Do not over-promote generic finance news, personnel articles, award articles, investment/funding articles, events, or unrelated keyword matches.
- Use noise when the item lacks reusable strategy value, even if it mentions a monitored keyword.
- Use work_signal only when the item would plausibly help a later strategy memo, proposal, product positioning, competitor comparison, or customer discussion.
- Write a reason that cites concrete facts from this item, not a generic template.
- score means reusable strategic value, 0-100.
- confidence means confidence in the classification, 0-100.

JSON schema:
{{
  "primary_bucket": "review_queue|work_signal|learning_signal|noise",
  "score": 0,
  "confidence": 0,
  "reason": "한국어 1-2문장. 이 항목이 나중에 왜 쓸 만한지 또는 왜 노이즈인지 구체적으로 설명",
  "suggested_tags": ["competitor"],
  "related_theme": "짧은 한국어 테마"
}}
"""
    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions="You classify collected monitoring items for a Korean strategy team. Return valid JSON only."
    )
    async with Agent(config=sdk_config) as ai_agent:
        response = await ai_agent.chat(prompt)
        text = await response.text()

    result = extract_json_object(text)
    bucket = str(result.get("primary_bucket", "review_queue")).strip()
    if bucket == "insight":
        bucket = "work_signal"
    if bucket not in ("review_queue", "work_signal", "learning_signal", "noise"):
        bucket = "review_queue"

    def clamp_score(value: Any, default: int) -> int:
        try:
            return max(0, min(int(value), 100))
        except Exception:
            return default

    tags = database.normalize_editor_tags(result.get("suggested_tags", []), limit=4)
    if not tags:
        tags = ["technical_reference"]

    reason = str(result.get("reason", "")).strip()
    if not reason:
        reason = "이 항목의 재사용 가치 판단을 위해 정밀 분류를 실행했지만, 구체 이유가 비어 있어 검토 대기로 남겼습니다."

    return {
        "primary_bucket": bucket,
        "score": clamp_score(result.get("score"), 55),
        "confidence": clamp_score(result.get("confidence"), 60),
        "reason": reason,
        "suggested_tags": tags,
        "secondary_buckets": tags,
        "related_theme": str(result.get("related_theme", "")).strip() or item.get("category") or item.get("source_name") or "전략 신호",
        "classification_source": "llm",
        "model_name": "gemini",
        "prompt_version": "reuse-value-profile-v2",
    }

def is_profile_due_for_scan(profile: Dict[str, Any], now: datetime) -> bool:
    if int(profile.get("auto_scan_enabled", 1) or 0) != 1:
        return False

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

def get_profile_auto_scan_info(profile_id: Optional[int] = None) -> Dict[str, Any]:
    profiles = database.get_profiles()
    if not profiles:
        return {"enabled": False, "message": "등록된 프로필이 없습니다."}

    selected = None
    if profile_id:
        selected = next((p for p in profiles if p.get("id") == profile_id), None)
    if selected is None:
        selected = profiles[0]

    interval_hours = max(int(selected.get("check_interval_hours") or 24), 1)
    auto_scan_enabled = int(selected.get("auto_scan_enabled", 1) or 0) == 1
    interval = timedelta(hours=interval_hours)
    latest_collection = parse_db_datetime(database.get_latest_collection_at(selected["id"]))
    last_attempt = last_auto_scan_attempts.get(selected["id"])
    basis = max([dt for dt in [latest_collection, last_attempt] if dt], default=None)
    next_scan_at = basis + interval if basis else datetime.now()
    due_now = datetime.now() >= next_scan_at

    return {
        "enabled": auto_scan_enabled,
        "profile_id": selected["id"],
        "profile_name": selected["name"],
        "interval_hours": interval_hours,
        "latest_collection_at": latest_collection.isoformat() if latest_collection else None,
        "last_attempt_at": last_attempt.isoformat() if last_attempt else None,
        "next_scan_at": next_scan_at.isoformat(),
        "due_now": due_now,
        "scheduler_running": auto_scheduler_task is not None and not auto_scheduler_task.done(),
        "message": "프로필 설정에서 자동 수집이 꺼져 있습니다." if not auto_scan_enabled else "",
    }

auto_retry_task: Optional[asyncio.Task] = None

async def auto_retry_scheduler():
    """Periodically checks for pending AI summaries and runs retry-only agent runs."""
    active_logs.append("[System] Auto retry scheduler started.\n")
    while True:
        try:
            if scan_status == "idle":
                for profile_row in database.get_profiles():
                    profile = dict(profile_row)
                    profile_id = profile["id"]
                    
                    # Check if there are any pending docs or trends
                    pending_docs = database.get_pending_ai_docs(profile_id, limit=1)
                    pending_trends = database.get_pending_ai_trends(profile_id, limit=1)
                    
                    if pending_docs or pending_trends:
                        active_logs.append(
                            f"[System] Auto retry triggered for profile '{profile['name']}' "
                            f"({len(pending_docs) + len(pending_trends)} pending items found).\n"
                        )
                        asyncio.create_task(run_agent_subprocess(["--profile-id", str(profile_id), "--retry-only"], profile_id))
                        break
        except Exception as e:
            active_logs.append(f"[System] Auto retry scheduler error: {e}\n")
        # Run every 10 minutes (600 seconds)
        await asyncio.sleep(600)

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
    global auto_scheduler_task, auto_retry_task
    if auto_scheduler_task is None or auto_scheduler_task.done():
        auto_scheduler_task = asyncio.create_task(auto_scan_scheduler())
    # AI summaries are intentionally user-triggered so Gemini quota is not spent
    # just because many RSS/news items were collected in the background.
    active_logs.append("[System] Auto AI summary retry is disabled. Use selected/manual summary actions.\n")

@app.on_event("shutdown")
async def stop_auto_scan_scheduler():
    global auto_scheduler_task, auto_retry_task
    if auto_scheduler_task and not auto_scheduler_task.done():
        auto_scheduler_task.cancel()
    if auto_retry_task and not auto_retry_task.done():
        auto_retry_task.cancel()

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
async def get_status(request: Request, profile_id: Optional[int] = None):
    """Returns the status and current live logs."""
    tail_logs = active_logs[-300:]
    return {
        "status": scan_status,
        "active_profile_id": active_profile_id,
        "is_admin": is_localhost(request),
        "auto_scan": get_profile_auto_scan_info(profile_id),
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

@app.post("/api/scan/retry")
async def trigger_retry(profile_id: Optional[int] = None, background_tasks: BackgroundTasks = BackgroundTasks()):
    """Triggers an async retry for pending AI summaries."""
    global scan_status
    if scan_status == "running":
        raise HTTPException(status_code=400, detail="Another scan process is already running.")
        
    args = ["--retry-only"]
    if profile_id:
        args += ["--profile-id", str(profile_id)]
        # Reset retry counts so they get retried
        database.reset_pending_retry_count(profile_id)
        
    background_tasks.add_task(run_agent_subprocess, args, profile_id)
    return {"message": "AI summary retry started in background."}

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
    feed_type = payload.feed_type.strip().lower() or 'competitor'

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

    if feed_type == 'reference':
        prompt = f"""
You are helping a Korean solution strategy team configure technology reference and engineering blog monitoring sources.

Seed topic from the user:
{seed_topic or "(none)"}

Current monitoring keywords:
{keyword_lines or "(none)"}

Current RSS/docs sources:
{feed_lines or "(none)"}

Suggest official tech blogs, developer blogs, engineering blogs, research blogs (e.g. Netflix Tech Blog, Toss Tech Blog, CNCF Blog, Spotify Engineering Blog) relevant to the keywords.

Rules:
- Respond ONLY as valid JSON.
- Do not include markdown fences.
- Prefer official engineering blogs, research lab blogs, high-quality technical reference sites, and developer publications.
- Do not invent obscure URLs. Use URLs you are confident exist.
- Do not include URLs already present in the current source list.
- Include both direct RSS/Atom URLs and useful docs/blog pages when appropriate.
- For category, use one of: "blog", "reference", "community", "other".
- reason must be Korean and concise.

JSON schema:
{{
  "suggestions": [
    {{
      "name": "source display name",
      "url": "https://example.com/feed.xml",
      "category": "blog|reference|community|other",
      "reason": "short Korean reason",
      "priority": "high|medium|low"
    }}
  ]
}}
"""
        system_instruction = "You recommend reliable tech and engineering blog monitoring sources. Always output valid JSON only."
    else:
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
        system_instruction = "You recommend reliable competitor monitoring sources. Always output valid JSON only."

    sdk_config = LocalAgentConfig(
        api_key=api_key,
        system_instructions=system_instruction
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
            "feed_type": feed_type,
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
        auto_report_enabled=1 if payload.auto_report_enabled else 0,
        auto_scan_enabled=1 if payload.auto_scan_enabled else 0
    )
    
    # 2. Update keywords
    keyword_dicts = [{"keyword": kw.keyword, "folder": kw.folder} for kw in payload.keywords]
    database.set_profile_keywords(profile_id, keyword_dicts)
    
    # 3. Update feeds
    feed_list = [{"name": f.name, "feed_url": f.feed_url, "feed_type": f.feed_type} for f in payload.feeds]
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

@app.get("/api/stats")
async def api_get_stats(profile_id: int):
    """Retrieves aggregated statistics for the dashboard visualization charts."""
    try:
        stats = database.get_profile_stats(profile_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {e}")

@app.get("/api/docs")
async def api_get_docs(profile_id: int, search: str = "", limit: int = 50, offset: int = 0, starred_only: bool = False, doc_type: Optional[str] = None):
    """Retrieves competitor documentation updates for a profile."""
    docs = database.get_docs(profile_id=profile_id, limit=limit, offset=offset, search=search, starred_only=starred_only, doc_type=doc_type)
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

@app.get("/api/editor/queue")
async def api_get_editor_queue(profile_id: int, limit: int = 30, include_noise: bool = False):
    """Returns TWT v2 editor-mode candidates for quick judgment."""
    return database.get_editor_queue(profile_id=profile_id, limit=limit, include_noise=include_noise)

@app.get("/api/editor/learning")
async def api_get_editor_learning(profile_id: int):
    """Returns a simple summary of the user's accumulated editorial judgments."""
    return database.get_editor_learning_summary(profile_id=profile_id)

@app.get("/api/editor/insights")
async def api_get_editor_insights(profile_id: int, limit_per_bucket: int = 8, include_noise: bool = True):
    """Returns AI-organized insight candidate buckets for the v2 dashboard."""
    return database.get_ai_insight_candidates(
        profile_id=profile_id,
        limit_per_bucket=limit_per_bucket,
        include_noise=include_noise
    )

@app.post("/api/editor/reviews/generate")
async def api_generate_editor_reviews(payload: EditorReviewGeneratePayload):
    """Creates rule-based AI editorial reviews for recent unreviewed items."""
    reviews = database.generate_rule_based_ai_editor_reviews(
        profile_id=payload.profile_id,
        limit=payload.limit,
        force=payload.force
    )
    return {"success": True, "created": len(reviews), "reviews": reviews}

@app.post("/api/editor/reviews/move")
async def api_move_editor_review(payload: EditorReviewMovePayload):
    """Moves an active AI candidate card to a different editorial bucket."""
    try:
        moved = database.move_ai_editor_review(
            profile_id=payload.profile_id,
            ai_review_id=payload.ai_review_id,
            target_bucket=payload.target_bucket,
            note=payload.note
        )
        label = {
            "review_queue": "later",
            "work_signal": "work_signal",
            "learning_signal": "learning_signal",
            "noise": "noise"
        }.get(payload.target_bucket, "important")
        judgment = database.save_editor_judgment(
            profile_id=payload.profile_id,
            ai_review_id=payload.ai_review_id,
            item_type=moved["item_type"],
            item_id=moved["item_id"],
            label=label,
            note=payload.note or "드래그로 후보 카테고리 수정"
        )
        database.sync_starred_with_editor_label(moved["item_type"], moved["item_id"], label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "review": moved, "judgment": judgment}

@app.post("/api/editor/reviews/refine")
async def api_refine_editor_review(payload: EditorReviewRefinePayload):
    """Runs on-demand LLM precision classification for one active candidate."""
    if Agent is None or LocalAgentConfig is None:
        raise HTTPException(status_code=500, detail="AI SDK is not available in this environment.")

    profile = database.get_profile_by_id(payload.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    api_key = profile.get("gemini_api_key", "")
    if not api_key or api_key == "••••••••":
        raise HTTPException(status_code=400, detail="Gemini API Key is required for precision classification.")

    context = database.get_ai_editor_review_context(payload.profile_id, payload.ai_review_id)
    if not context:
        raise HTTPException(status_code=404, detail="Active AI review not found.")

    if database.has_user_editor_judgment(payload.profile_id, context["item_type"], context["item_id"]):
        raise HTTPException(status_code=400, detail="이미 사용자가 판단한 카드라 AI가 다시 덮어쓰지 않습니다.")

    try:
        profile_context = build_editor_profile_context(payload.profile_id)
        refined = await refine_editor_review_item(api_key, context, profile_context)
        updated = database.update_ai_editor_review_classification(
            profile_id=payload.profile_id,
            ai_review_id=payload.ai_review_id,
            review=refined
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"정밀 분류 실패: {exc}")

    return {"success": True, "review": updated}

@app.post("/api/editor/judgments")
async def api_save_editor_judgment(payload: EditorJudgmentPayload):
    """Stores one editor judgment label for a collected item."""
    try:
        updated_review = {}
        if payload.label in ("work_signal", "learning_signal", "noise"):
            updated_review = database.update_active_editor_review_bucket_by_item(
                profile_id=payload.profile_id,
                item_type=payload.item_type,
                item_id=payload.item_id,
                target_bucket=payload.label,
                note=payload.note or "보관함에서 편집장 판단 수정"
            )
        judgment = database.save_editor_judgment(
            profile_id=payload.profile_id,
            item_type=payload.item_type,
            item_id=payload.item_id,
            label=payload.label,
            note=payload.note,
            ai_review_id=payload.ai_review_id or updated_review.get("id")
        )
        database.sync_starred_with_editor_label(payload.item_type, payload.item_id, payload.label)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"success": True, "judgment": judgment, "review": updated_review}

@app.post("/api/summary/{item_type}/{item_id}")
async def api_summarize_item(item_type: str, item_id: int, profile_id: int):
    """Generates an AI summary for one selected collected item."""
    if Agent is None or LocalAgentConfig is None:
        raise HTTPException(status_code=500, detail="AI SDK is not available in this environment.")

    profile = database.get_profile_by_id(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found.")

    api_key = profile.get("gemini_api_key", "")
    if not api_key or api_key == "••••••••":
        raise HTTPException(status_code=400, detail="Gemini API Key is required for selected AI summaries.")

    try:
        if item_type == "doc":
            item = database.get_doc_by_id(item_id)
            if not item or item.get("profile_id") != profile_id:
                raise HTTPException(status_code=404, detail="Doc item not found.")
            analysis = await summarize_doc_item(api_key, item)
            database.update_doc_analysis(
                item_id,
                analysis["summary"],
                analysis["impact"],
                analysis["keywords"],
                "complete",
                ""
            )
            return {"message": "Doc summary generated.", "item": database.get_doc_by_id(item_id)}

        if item_type == "trend":
            item = database.get_trend_by_id(item_id)
            if not item or item.get("profile_id") != profile_id:
                raise HTTPException(status_code=404, detail="Trend item not found.")
            analysis = await summarize_trend_item(api_key, item)
            database.update_trend_analysis(
                item_id,
                analysis["title"],
                analysis["summary"],
                analysis["source"],
                "complete",
                ""
            )
            return {"message": "Trend summary generated.", "item": database.get_trend_by_id(item_id)}

        raise HTTPException(status_code=400, detail="item_type must be 'doc' or 'trend'.")
    except HTTPException:
        raise
    except Exception as e:
        if item_type == "doc":
            database.increment_doc_retry(item_id, str(e)[:300])
        elif item_type == "trend":
            database.increment_trend_retry(item_id, str(e)[:300])
        raise HTTPException(status_code=500, detail=f"Failed to generate selected AI summary: {e}")

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
