import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tech_watch.db")
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """Initializes the database tables and migrates existing config if necessary."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create profiles table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        gemini_api_key TEXT,
        discord_webhook_url TEXT,
        check_interval_hours INTEGER DEFAULT 24,
        auto_scan_enabled INTEGER DEFAULT 1,
        auto_report_enabled INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. Create profile_keywords table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profile_keywords (
        profile_id INTEGER,
        keyword TEXT NOT NULL,
        PRIMARY KEY (profile_id, keyword),
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    
    # 3. Create profile_feeds table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS profile_feeds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        name TEXT NOT NULL,
        feed_url TEXT NOT NULL,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    
    # 4. Create scanned_docs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scanned_docs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        competitor TEXT NOT NULL,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        date TEXT,
        summary TEXT,
        impact TEXT,
        keywords TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
        UNIQUE(profile_id, title)
    )
    """)
    
    # 5. Create scanned_trends table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scanned_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        keyword TEXT NOT NULL,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        summary TEXT,
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
        UNIQUE(profile_id, title)
    )
    """)
    
    # 6. Create reports table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        report_type TEXT DEFAULT 'weekly',
        period_key TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    
    # 7. Create bulletin_board table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bulletin_board (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    
    # 8. Create global_templates table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS global_templates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        template_content TEXT NOT NULL
    )
    """)

    # 9. Create editor_judgments table for TWT v2 editor mode
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS editor_judgments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        ai_review_id INTEGER,
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        note TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE,
        FOREIGN KEY (ai_review_id) REFERENCES ai_editor_reviews(id) ON DELETE SET NULL,
        UNIQUE(profile_id, item_type, item_id, label)
    )
    """)

    # 10. Create ai_editor_reviews table for TWT v2 AI-first candidate classification
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_editor_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        profile_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        primary_bucket TEXT NOT NULL,
        secondary_buckets TEXT DEFAULT '',
        score INTEGER DEFAULT 0,
        confidence INTEGER DEFAULT 0,
        reason TEXT DEFAULT '',
        related_theme TEXT DEFAULT '',
        model_name TEXT DEFAULT 'rule-based-v1',
        prompt_version TEXT DEFAULT 'rules-2026-06-24',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_editor_reviews_one_active
    ON ai_editor_reviews(profile_id, item_type, item_id)
    WHERE is_active = 1
    """)
    
    conn.commit()
    
    # Alter profiles table to add template columns if missing
    cursor.execute("PRAGMA table_info(profiles)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'report_template_type' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN report_template_type TEXT DEFAULT 'basic'")
    if 'custom_report_template' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN custom_report_template TEXT DEFAULT ''")
    if 'auto_scan_enabled' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN auto_scan_enabled INTEGER DEFAULT 1")
    if 'auto_report_enabled' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN auto_report_enabled INTEGER DEFAULT 1")

    # Alter editor_judgments table to connect user decisions with AI review versions
    cursor.execute("PRAGMA table_info(editor_judgments)")
    judgment_cols = [row['name'] for row in cursor.fetchall()]
    if 'ai_review_id' not in judgment_cols:
        cursor.execute("ALTER TABLE editor_judgments ADD COLUMN ai_review_id INTEGER")
    
    # Alter scanned_docs table to add is_starred column if missing
    cursor.execute("PRAGMA table_info(scanned_docs)")
    doc_cols = [row['name'] for row in cursor.fetchall()]
    if 'is_starred' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN is_starred INTEGER DEFAULT 0")
    if 'published_at' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN published_at TEXT DEFAULT ''")
    if 'analysis_status' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN analysis_status TEXT DEFAULT 'complete'")
    if 'analysis_error' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN analysis_error TEXT DEFAULT ''")
    if 'retry_count' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN retry_count INTEGER DEFAULT 0")
        
    # Alter scanned_trends table to add is_starred column if missing
    cursor.execute("PRAGMA table_info(scanned_trends)")
    trend_cols = [row['name'] for row in cursor.fetchall()]
    if 'is_starred' not in trend_cols:
        cursor.execute("ALTER TABLE scanned_trends ADD COLUMN is_starred INTEGER DEFAULT 0")
    if 'published_at' not in trend_cols:
        cursor.execute("ALTER TABLE scanned_trends ADD COLUMN published_at TEXT DEFAULT ''")
    if 'analysis_status' not in trend_cols:
        cursor.execute("ALTER TABLE scanned_trends ADD COLUMN analysis_status TEXT DEFAULT 'complete'")
    if 'analysis_error' not in trend_cols:
        cursor.execute("ALTER TABLE scanned_trends ADD COLUMN analysis_error TEXT DEFAULT ''")
    if 'retry_count' not in trend_cols:
        cursor.execute("ALTER TABLE scanned_trends ADD COLUMN retry_count INTEGER DEFAULT 0")
        
    # Alter profile_keywords table to add folder column if missing
    cursor.execute("PRAGMA table_info(profile_keywords)")
    keyword_cols = [row['name'] for row in cursor.fetchall()]
    if 'folder' not in keyword_cols:
        cursor.execute("ALTER TABLE profile_keywords ADD COLUMN folder TEXT DEFAULT '미분류'")

    # Alter reports table to support weekly/monthly/starred archives
    cursor.execute("PRAGMA table_info(reports)")
    report_cols = [row['name'] for row in cursor.fetchall()]
    if 'report_type' not in report_cols:
        cursor.execute("ALTER TABLE reports ADD COLUMN report_type TEXT DEFAULT 'weekly'")
    if 'period_key' not in report_cols:
        cursor.execute("ALTER TABLE reports ADD COLUMN period_key TEXT DEFAULT ''")

    # Alter profile_feeds table to add feed_type column if missing
    cursor.execute("PRAGMA table_info(profile_feeds)")
    feed_cols = [row['name'] for row in cursor.fetchall()]
    if 'feed_type' not in feed_cols:
        cursor.execute("ALTER TABLE profile_feeds ADD COLUMN feed_type TEXT DEFAULT 'competitor'")

    # Alter scanned_docs table to add doc_type column if missing
    cursor.execute("PRAGMA table_info(scanned_docs)")
    doc_cols = [row['name'] for row in cursor.fetchall()]
    if 'doc_type' not in doc_cols:
        cursor.execute("ALTER TABLE scanned_docs ADD COLUMN doc_type TEXT DEFAULT 'competitor'")
        
    conn.commit()
    
    # Populate or update default global templates
    default_templates = [
        ("basic", "[기본] 기술 신호 및 경쟁사 동향 보고서", 
         """You are a senior technology strategy analyst for the 솔루션전략팀.
Write a Korean strategic intelligence report from collected competitor updates and industry news.

The report must be analytical, not a news digest.
Do not list collected items one by one in the main body.
Use the collected items only as evidence to infer repeated signals, competitor direction, technology trend momentum, and strategic implications.

Rules:
- Use only the evidence in the collected data below. If evidence is weak, say "현재 수집 데이터 기준".
- Treat repeated keywords, similar product updates, and recurring themes as strategic market signals.
- Mention concrete competitors/products when available.
- Separate facts, interpretation, and recommended actions.
- Avoid generic statements such as "지속 추적이 필요합니다" unless you explain exactly why.
- Main sections 2~5 must contain interpretation and synthesis, not raw item lists.
- Raw evidence may appear only in the final evidence appendix.
- Keep the tone professional, concise, and useful for solution strategy, competitive positioning, and proposal/RFP work.

[Competitor Docs Updates]
{docs_context}

[Industry Tech Trends & News]
{trends_context}

Please structure the report exactly as follows:
# 기술 신호 및 경쟁사 동향 보고서 ({current_date})

## 1. Executive Summary
- 이번 기간 가장 중요한 기술/경쟁 신호를 3~5개 bullet로 요약합니다.
- 각 bullet은 "무슨 변화가 보이는지", "왜 중요한지", "우리에게 어떤 판단을 요구하는지"를 함께 설명합니다.

## 2. 자주 등장한 기술 키워드
- 반복 키워드를 단순 빈도표로 끝내지 말고, 기술 흐름으로 묶어 해석합니다.
- 각 키워드별로 "등장 맥락", "전략적 의미", "우리 제품/제안 전략과의 연결점"을 표로 작성합니다.

## 3. 경쟁사 동향 및 제품 방향성
- 경쟁사/제품별 업데이트를 묶어 어떤 제품 전략으로 움직이는지 분석합니다.
- 단순 기능 나열 금지. "AI 내재화", "보안 자동화", "관리/거버넌스 강화", "비용 통제", "개발자 생산성" 같은 방향성으로 해석합니다.
- 각 경쟁사별로 우리 솔루션 포지션에 주는 압박 또는 기회를 작성합니다.

## 4. 반복 신호와 시장 해석
- 여러 항목에서 반복되는 신호를 3~5개 뽑습니다.
- 각 신호에 대해 "근거", "해석", "잠재 영향"을 구분해서 작성합니다.

## 5. 솔루션전략팀 시사점
- 우리 팀이 제품 전략, 제안 전략, 경쟁 분석, 로드맵 검토에서 참고해야 할 점을 구체적으로 작성합니다.
- 필요하면 위협 수준을 상/중/하로 평가합니다.

## 6. 다음 액션 제안
- 다음 달까지 추적할 키워드, 추가해야 할 RSS/경쟁사, 내부 검토 과제를 제안합니다.

## 7. 근거 데이터 부록
- 본문 분석에 사용한 대표 근거 5~10개만 짧게 나열합니다.
- 이 섹션을 제외한 본문에서는 수집 항목을 그대로 나열하지 마세요.

Make the formatting clean and highly readable for Markdown."""),
        
        ("monthly", "[월간] 솔루션전략팀 월간 전략 보고서",
         """You are writing a monthly strategic intelligence report for the 솔루션전략팀.
Analyze collected competitor updates and technology news to explain what is changing in the market and what it means for our solution strategy.

The audience does not need a list of articles. They need judgment:
- What latest movements are visible from the collected data?
- Which technology themes are gaining momentum?
- Which competitors or ecosystems are moving in which direction?
- What signals matter for product positioning, RFP/proposal messaging, and roadmap discussion?
- What should be watched next?

Rules:
- Do not write a generic news summary.
- Do not list collected items one by one in sections 2~5.
- Use evidence from the collected data, but synthesize it into themes and implications.
- If the dataset is still small, explicitly state that the finding is based on limited accumulated data.
- Distinguish "observed fact", "interpretation", and "recommended action".
- Raw article/release examples may appear only in the final evidence appendix.

[Competitor Docs Updates]
{docs_context}

[Industry Tech Trends & News]
{trends_context}

Please structure the report exactly as follows:
# 솔루션전략팀 월간 전략 보고서 ({current_date})

## 1. 전략적 핵심 요약
- 이번 달 기술 시장과 경쟁사 움직임의 핵심 결론을 5개 이내로 정리합니다.
- 각 bullet은 단순 요약이 아니라 "관측된 변화 → 전략적 의미" 형태로 작성합니다.

## 2. 기술 키워드 빈도 및 중요도 분석
- 반복 등장 키워드를 빈도와 중요도 기준으로 묶어 분석합니다.
- 각 키워드에 대해 "어떤 맥락에서 반복되는지", "왜 지금 중요한지", "우리 제품/전략에 어떤 질문을 던지는지"를 표로 작성합니다.

## 3. 경쟁사/생태계 최신 움직임 분석
- 경쟁사와 기술 생태계별 업데이트를 묶어 최신 움직임을 해석합니다.
- 단순 업데이트 요약 금지. "이 출처가 어떤 전략 축을 강화하고 있는지"를 분석합니다.
- 가능하면 경쟁사별로 다음 형식으로 작성합니다: 관측된 움직임 / 해석 / 우리에게 주는 의미.

## 4. 이번 달의 핵심 신호
- 데이터에서 드러난 반복 신호를 3~5개 도출합니다.
- 각 신호별로 근거, 해석, 우리에게 주는 의미, 추적 필요성을 구분합니다.

## 5. 우리 솔루션 전략에 대한 영향
- 경쟁 위협 수준을 상/중/하로 평가합니다.
- 제품 로드맵, 영업 메시지, 제안서/RFP 대응, 파트너 전략 관점에서 시사점을 작성합니다.

## 6. 다음 달 추적 과제
- 반드시 추적해야 할 키워드
- 추가할 경쟁사/RSS
- 내부 논의가 필요한 제품/전략 과제

## 7. 근거 데이터 부록
- 본문 분석에 사용한 대표 근거만 5~10개 나열합니다.
- 제목, 출처, 발행일 정도만 짧게 적고, 긴 요약 나열은 피합니다.

Make the formatting clean and highly readable for Markdown."""),
        
        ("detailed", "[상세] 경쟁사 기능 심층분석보고서",
         """Write a Competitor Feature Deep Dive Analysis Report (경쟁사 기능 심층분석보고서) in Korean, focusing on technical implementation and architectural details of competitor releases:

[Competitor Docs Updates]
{docs_context}

[Industry Tech Trends & News]
{trends_context}

Please structure the report using professional Korean business language as follows:
# 경쟁사 기능 심층분석보고서 ({current_date})

## 1. 심층 분석 대상 및 배경 (Target Feature Overview)
- 최근 가장 큰 변화가 감지된 경쟁사의 특정 핵심 신규 기능 또는 기술 아키텍처 업데이트를 선정하고 선정 배경을 설명합니다.

## 2. 기술 구현 방식 및 아키텍처 추정 (Technical Architecture & Mechanics)
- 수집된 정보와 기술 동향을 기반으로 경쟁사가 해당 기능을 구현한 방식(API 설계, 인프라 구조, AI 모델 연동 등)을 기술적으로 깊이 있게 분석 및 추정합니다.

## 3. 사용자 경험(UX) 및 개발자 생산성 영향도 (Developer & User Impact)
- 해당 기능이 실제 엔드 유저에게 제공하는 가치(UX 개선)와 개발자 생산성(Developer Experience)에 미치는 파급력을 정량적/정성적으로 평가합니다.

## 4. 우리 제품 아키텍처 도입 검토 및 개발 권고사항 (Technical Countermeasures)
- 경쟁사 구현 방식의 한계점 및 취약점을 파악하고, 우리 제품에 더 나은 방식으로 유사/개선 기능을 도입하기 위한 기술 설계 방향과 아키텍처적 조언을 개발 팀에 제안합니다.

Make the formatting clean and highly readable for Markdown.""")
    ]
    for tid, name, content in default_templates:
        cursor.execute(
            "INSERT OR REPLACE INTO global_templates (id, name, template_content) VALUES (?, ?, ?)",
            (tid, name, content)
        )
    conn.commit()
    
    # Check if we need to migrate from config.json
    cursor.execute("SELECT COUNT(*) FROM profiles")
    if cursor.fetchone()[0] == 0 and os.path.exists(CONFIG_FILE):
        print("[Database] Empty database detected. Migrating config.json to Default Profile...")
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # Create a default profile
            cursor.execute(
                "INSERT INTO profiles (name, gemini_api_key, discord_webhook_url, check_interval_hours) VALUES (?, ?, ?, ?)",
                ("기본 프로필", config.get("gemini_api_key", ""), config.get("discord_webhook_url", ""), config.get("check_interval_hours", 24))
            )
            profile_id = cursor.lastrowid
            
            # Migrate keywords
            for kw in config.get("keywords", []):
                cursor.execute(
                    "INSERT OR IGNORE INTO profile_keywords (profile_id, keyword) VALUES (?, ?)",
                    (profile_id, kw)
                )
                
            # Migrate RSS feeds
            for feed in config.get("docs_to_monitor", []):
                cursor.execute(
                    "INSERT INTO profile_feeds (profile_id, name, feed_url) VALUES (?, ?, ?)",
                    (profile_id, feed.get("name", "Unknown"), feed.get("feed_url", ""))
                )
                
            conn.commit()
            print(f"[Database] Migration completed successfully. Profile '기본 프로필' created with ID {profile_id}.")
        except Exception as e:
            print(f"[Database] Failed to migrate config.json: {e}")
            conn.rollback()
            
    conn.close()

# --- PROFILE CRUD FUNCTIONS ---

def get_profiles() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_profile_by_id(profile_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_profile_by_name(name: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profiles WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_profile(name: str, gemini_api_key: str = "", discord_webhook_url: str = "", check_interval_hours: int = 24) -> int:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO profiles (name, gemini_api_key, discord_webhook_url, check_interval_hours, report_template_type, custom_report_template) VALUES (?, ?, ?, ?, ?, ?)",
            (name, gemini_api_key, discord_webhook_url, check_interval_hours, 'basic', '')
        )
        profile_id = cursor.lastrowid
        conn.commit()
        return profile_id
    except sqlite3.IntegrityError:
        raise ValueError(f"Profile with name '{name}' already exists.")
    finally:
        conn.close()

def update_profile(profile_id: int, name: str, gemini_api_key: str, discord_webhook_url: str, check_interval_hours: int, report_template_type: str = 'basic', custom_report_template: str = '', auto_report_enabled: int = 1, auto_scan_enabled: int = 1):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE profiles SET name = ?, gemini_api_key = ?, discord_webhook_url = ?, check_interval_hours = ?, report_template_type = ?, custom_report_template = ?, auto_report_enabled = ?, auto_scan_enabled = ? WHERE id = ?",
            (name, gemini_api_key, discord_webhook_url, check_interval_hours, report_template_type, custom_report_template, auto_report_enabled, auto_scan_enabled, profile_id)
        )
        conn.commit()
    finally:
        conn.close()

def delete_profile(profile_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
    conn.commit()
    conn.close()

# --- PROFILE KEYWORDS AND FEEDS FUNCTIONS ---

def get_profile_keywords(profile_id: int) -> List[Dict[str, str]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, folder FROM profile_keywords WHERE profile_id = ?", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"keyword": r['keyword'], "folder": r['folder'] or "미분류"} for r in rows]

def set_profile_keywords(profile_id: int, keywords: List[Dict[str, str]]):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM profile_keywords WHERE profile_id = ?", (profile_id,))
        for item in keywords:
            kw = item.get("keyword", "").strip()
            folder = item.get("folder", "미분류").strip() or "미분류"
            if kw:
                cursor.execute(
                    "INSERT INTO profile_keywords (profile_id, keyword, folder) VALUES (?, ?, ?)",
                    (profile_id, kw, folder)
                )
        conn.commit()
    finally:
        conn.close()

def get_profile_feeds(profile_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM profile_feeds WHERE profile_id = ?", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_profile_feeds(profile_id: int, feeds: List[Dict[str, str]]):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM profile_feeds WHERE profile_id = ?", (profile_id,))
        for feed in feeds:
            name = feed.get("name", "").strip()
            url = feed.get("feed_url", "").strip()
            feed_type = feed.get("feed_type", "competitor").strip() or "competitor"
            if name and url:
                cursor.execute(
                    "INSERT INTO profile_feeds (profile_id, name, feed_url, feed_type) VALUES (?, ?, ?, ?)",
                    (profile_id, name, url, feed_type)
                )
        conn.commit()
    finally:
        conn.close()

# --- DATA INGESTION & QUERY FUNCTIONS ---

def get_scanned_doc_titles(profile_id: int) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM scanned_docs WHERE profile_id = ?", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r['title'] for r in rows]

def save_scanned_doc(profile_id: int, competitor: str, title: str, link: str, date: str, summary: str, impact: str, keywords: List[str], published_at: str = "", analysis_status: str = "complete", analysis_error: str = "", doc_type: str = "competitor") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    kw_str = ", ".join(keywords)
    try:
        cursor.execute(
            """INSERT INTO scanned_docs (profile_id, competitor, title, link, date, summary, impact, keywords, published_at, analysis_status, analysis_error, doc_type) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile_id, competitor, title, link, date, summary, impact, kw_str, published_at, analysis_status, analysis_error, doc_type)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Already exists
        return False
    except Exception as e:
        print(f"[Database] Error saving doc update: {e}")
        return False
    finally:
        conn.close()

def get_scanned_trend_titles(profile_id: int) -> List[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM scanned_trends WHERE profile_id = ?", (profile_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r['title'] for r in rows]

def save_scanned_trend(profile_id: int, keyword: str, title: str, link: str, summary: str, source: str, published_at: str = "", analysis_status: str = "complete", analysis_error: str = "") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO scanned_trends (profile_id, keyword, title, link, summary, source, published_at, analysis_status, analysis_error) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile_id, keyword, title, link, summary, source, published_at, analysis_status, analysis_error)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Already exists
        return False
    except Exception as e:
        print(f"[Database] Error saving trend: {e}")
        return False
    finally:
        conn.close()

def get_pending_ai_docs(profile_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM scanned_docs
           WHERE profile_id = ? AND analysis_status = 'pending' AND retry_count < 5
           ORDER BY created_at ASC LIMIT ?""",
        (profile_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_doc_by_id(doc_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scanned_docs WHERE id = ?", (doc_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_doc_analysis(doc_id: int, summary: str, impact: str, keywords: List[str], analysis_status: str = "complete", analysis_error: str = "") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE scanned_docs
               SET summary = ?, impact = ?, keywords = ?, analysis_status = ?, analysis_error = ?
               WHERE id = ?""",
            (summary, impact, ", ".join(keywords), analysis_status, analysis_error, doc_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()

def get_pending_ai_trends(profile_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT * FROM scanned_trends
           WHERE profile_id = ? AND analysis_status = 'pending' AND retry_count < 5
           ORDER BY created_at ASC LIMIT ?""",
        (profile_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_trend_by_id(trend_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM scanned_trends WHERE id = ?", (trend_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

def update_trend_analysis(trend_id: int, title: str, summary: str, source: str, analysis_status: str = "complete", analysis_error: str = "") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE scanned_trends
               SET title = ?, summary = ?, source = ?, analysis_status = ?, analysis_error = ?
               WHERE id = ?""",
            (title, summary, source, analysis_status, analysis_error, trend_id)
        )
        conn.commit()
        return True
    finally:
        conn.close()

def increment_doc_retry(doc_id: int, error_msg: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE scanned_docs
               SET retry_count = retry_count + 1, analysis_error = ?
               WHERE id = ?""",
            (error_msg, doc_id)
        )
        conn.commit()
    finally:
        conn.close()

def increment_trend_retry(trend_id: int, error_msg: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE scanned_trends
               SET retry_count = retry_count + 1, analysis_error = ?
               WHERE id = ?""",
            (error_msg, trend_id)
        )
        conn.commit()
    finally:
        conn.close()

def delete_scanned_trend(trend_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM scanned_trends WHERE id = ?", (trend_id,))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Database] Error deleting scanned trend: {e}")
        return False
    finally:
        conn.close()

def reset_pending_retry_count(profile_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """UPDATE scanned_docs
               SET retry_count = 0
               WHERE profile_id = ? AND analysis_status = 'pending'""",
            (profile_id,)
        )
        cursor.execute(
            """UPDATE scanned_trends
               SET retry_count = 0
               WHERE profile_id = ? AND analysis_status = 'pending'""",
            (profile_id,)
        )
        conn.commit()
    finally:
        conn.close()

def get_docs(profile_id: int, limit: int = 50, offset: int = 0, search: str = "", starred_only: bool = False, match_mode: str = "any", doc_type: str = None) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = ["profile_id = ?"]
    params = [profile_id]
    if starred_only:
        conditions.append("is_starred = 1")
    if doc_type:
        conditions.append("doc_type = ?")
        params.append(doc_type)
    keywords = [k.strip() for k in search.split(",") if k.strip()]
    if keywords:
        keyword_clauses = []
        for keyword in keywords:
            keyword_clauses.append("(title LIKE ? OR competitor LIKE ? OR summary LIKE ? OR keywords LIKE ?)")
            like = f"%{keyword}%"
            params.extend([like, like, like, like])
        joiner = " AND " if match_mode == "all" else " OR "
        conditions.append("(" + joiner.join(keyword_clauses) + ")")
    params.extend([limit, offset])
    cursor.execute(
        f"""SELECT * FROM scanned_docs
           WHERE {' AND '.join(conditions)}
           ORDER BY COALESCE(NULLIF(published_at, ''), created_at) DESC LIMIT ? OFFSET ?""",
        params
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_trends(profile_id: int, limit: int = 50, offset: int = 0, search: str = "", starred_only: bool = False) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    star_cond = " AND is_starred = 1" if starred_only else ""
    if search:
        query = f"%{search}%"
        cursor.execute(
            f"""SELECT t.*, k.folder FROM scanned_trends t
               LEFT JOIN profile_keywords k ON t.profile_id = k.profile_id AND t.keyword = k.keyword
               WHERE t.profile_id = ?{star_cond} AND (t.title LIKE ? OR t.keyword LIKE ? OR t.summary LIKE ? OR t.source LIKE ?) 
               ORDER BY COALESCE(NULLIF(t.published_at, ''), t.created_at) DESC LIMIT ? OFFSET ?""",
            (profile_id, query, query, query, query, limit, offset)
        )
    else:
        cursor.execute(
            f"""SELECT t.*, k.folder FROM scanned_trends t
               LEFT JOIN profile_keywords k ON t.profile_id = k.profile_id AND t.keyword = k.keyword
               WHERE t.profile_id = ?{star_cond} ORDER BY COALESCE(NULLIF(t.published_at, ''), t.created_at) DESC LIMIT ? OFFSET ?""",
            (profile_id, limit, offset)
        )
    rows = cursor.fetchall()
    conn.close()
    
    res = []
    for r in rows:
        d = dict(r)
        if "folder" in d and d["folder"] is None:
            d["folder"] = "미분류"
        res.append(d)
    return res

def get_profile_stats(profile_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total docs (competitors) count
    cursor.execute("SELECT COUNT(*) FROM scanned_docs WHERE profile_id = ? AND doc_type = 'competitor'", (profile_id,))
    total_docs = cursor.fetchone()[0]
    
    # 1b. Total reference count
    cursor.execute("SELECT COUNT(*) FROM scanned_docs WHERE profile_id = ? AND doc_type = 'reference'", (profile_id,))
    total_references = cursor.fetchone()[0]
    
    # 2. Total trends count
    cursor.execute("SELECT COUNT(*) FROM scanned_trends WHERE profile_id = ?", (profile_id,))
    total_trends = cursor.fetchone()[0]
    
    # 3. Total starred docs count
    cursor.execute("SELECT COUNT(*) FROM scanned_docs WHERE profile_id = ? AND is_starred = 1", (profile_id,))
    starred_docs = cursor.fetchone()[0]
    
    # 4. Total starred trends count
    cursor.execute("SELECT COUNT(*) FROM scanned_trends WHERE profile_id = ? AND is_starred = 1", (profile_id,))
    starred_trends = cursor.fetchone()[0]
    
    # 5. Competitor stats (grouped by competitor, filtered by competitor doc_type)
    cursor.execute("""
        SELECT competitor, COUNT(*) as count 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'competitor'
        GROUP BY competitor 
        ORDER BY count DESC
    """, (profile_id,))
    competitors = [{"name": r["competitor"], "value": r["count"]} for r in cursor.fetchall()]
    
    # 5b. Reference stats (grouped by competitor, filtered by reference doc_type)
    cursor.execute("""
        SELECT competitor, COUNT(*) as count 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'reference'
        GROUP BY competitor 
        ORDER BY count DESC
    """, (profile_id,))
    references = [{"name": r["competitor"], "value": r["count"]} for r in cursor.fetchall()]
    
    # 6. Keyword stats
    cursor.execute("""
        SELECT keyword, COUNT(*) as count 
        FROM scanned_trends 
        WHERE profile_id = ? 
        GROUP BY keyword 
        ORDER BY count DESC
    """, (profile_id,))
    keywords = [{"name": r["keyword"], "value": r["count"]} for r in cursor.fetchall()]
    
    # 7. Daily activity (past 14 days)
    cursor.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM scanned_docs
        WHERE profile_id = ? AND created_at >= datetime('now', '-14 days')
        GROUP BY day
    """, (profile_id,))
    daily_docs = {r["day"]: r["count"] for r in cursor.fetchall()}
    
    cursor.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM scanned_trends
        WHERE profile_id = ? AND created_at >= datetime('now', '-14 days')
        GROUP BY day
    """, (profile_id,))
    daily_trends = {r["day"]: r["count"] for r in cursor.fetchall()}
    
    # Generate array of past 14 days dates to ensure we have all values
    from datetime import datetime, timedelta
    activity = []
    for i in range(13, -1, -1):
        day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        activity.append({
            "date": day_str,
            "docs": daily_docs.get(day_str, 0),
            "trends": daily_trends.get(day_str, 0)
        })
        
    # 8. Competitor AI tag stats (Sub-keywords)
    cursor.execute("SELECT keywords FROM scanned_docs WHERE profile_id = ? AND doc_type = 'competitor'", (profile_id,))
    tag_counts = {}
    for row in cursor.fetchall():
        kws = row["keywords"] or ""
        for kw in kws.split(","):
            kw_clean = kw.strip()
            if kw_clean and kw_clean != "General" and kw_clean != "AI 요약 대기" and kw_clean != "AI 요약 대기 중":
                tag_counts[kw_clean] = tag_counts.get(kw_clean, 0) + 1
    
    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    tags_stats = [{"name": name, "value": count} for name, count in sorted_tags[:10]]
    
    # 9. Stacked Bar Chart Tag distribution per competitor
    cursor.execute("""
        SELECT competitor, keywords 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'competitor'
    """, (profile_id,))
    
    competitor_tags = {}
    overall_tag_counts = {}
    for row in cursor.fetchall():
        comp = row["competitor"]
        kws = row["keywords"] or ""
        if comp not in competitor_tags:
            competitor_tags[comp] = {}
        for kw in kws.split(","):
            kw_clean = kw.strip()
            if kw_clean and kw_clean not in ("General", "AI 요약 대기", "AI 요약 대기 중", "미분류"):
                competitor_tags[comp][kw_clean] = competitor_tags[comp].get(kw_clean, 0) + 1
                overall_tag_counts[kw_clean] = overall_tag_counts.get(kw_clean, 0) + 1
                
    # Get top 8 tags overall
    top_tags = [t for t, c in sorted(overall_tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]]
    comp_names = [c["name"] for c in competitors]
    
    datasets = []
    for tag in top_tags:
        data_list = []
        for comp in comp_names:
            data_list.append(competitor_tags.get(comp, {}).get(tag, 0))
        datasets.append({
            "label": tag,
            "data": data_list
        })
        
    competitor_tag_stats = {
        "labels": comp_names,
        "datasets": datasets
    }
    
    # 10. Technical References Latest 3 Posts per blog
    cursor.execute("""
        SELECT DISTINCT competitor 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'reference'
    """, (profile_id,))
    ref_blogs = [r[0] for r in cursor.fetchall()]
    
    latest_references = []
    for blog in ref_blogs:
        cursor.execute("""
            SELECT title, link, COALESCE(NULLIF(published_at, ''), created_at) as date
            FROM scanned_docs
            WHERE profile_id = ? AND doc_type = 'reference' AND competitor = ?
            ORDER BY date DESC LIMIT 3
        """, (profile_id, blog))
        posts = [dict(r) for r in cursor.fetchall()]
        latest_references.append({
            "blog_name": blog,
            "posts": posts
        })
        
    # 11. Competitor Latest Releases (3 latest per competitor)
    cursor.execute("""
        SELECT DISTINCT competitor 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'competitor'
    """, (profile_id,))
    competitors_list = [r[0] for r in cursor.fetchall()]
    
    latest_competitor_releases = []
    for comp in competitors_list:
        cursor.execute("""
            SELECT title, link, summary, impact, keywords, COALESCE(NULLIF(published_at, ''), created_at) as date
            FROM scanned_docs
            WHERE profile_id = ? AND doc_type = 'competitor' AND competitor = ?
            ORDER BY date DESC LIMIT 3
        """, (profile_id, comp))
        releases = [dict(r) for r in cursor.fetchall()]
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM scanned_docs
            WHERE profile_id = ? AND doc_type = 'competitor' AND competitor = ?
        """, (profile_id, comp))
        total_count = cursor.fetchone()["count"]

        tag_counts = {}
        for rel in releases:
            for kw in (rel.get("keywords") or "").split(","):
                kw_clean = kw.strip()
                if kw_clean and kw_clean not in ("General", "AI 요약 대기", "AI 요약 대기 중", "미분류"):
                    tag_counts[kw_clean] = tag_counts.get(kw_clean, 0) + 1
        top_keywords = [
            {"name": name, "value": count}
            for name, count in sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        ]

        latest_release = releases[0] if releases else {}
        latest_competitor_releases.append({
            "competitor_name": comp,
            "total_count": total_count,
            "top_keywords": top_keywords,
            "latest_release": latest_release,
            "signal": latest_release.get("impact", "") if latest_release else "",
            "releases": releases
        })
        
    # 11b. Technical Trends Latest News (5 latest)
    cursor.execute("""
        SELECT keyword, title, link, summary, source, COALESCE(NULLIF(published_at, ''), created_at) as date
        FROM scanned_trends
        WHERE profile_id = ?
        ORDER BY date DESC LIMIT 5
    """, (profile_id,))
    latest_trends = [dict(r) for r in cursor.fetchall()]
    
    # Calculate top theme, top keyword, and most active competitor
    top_theme = f"{tags_stats[0]['name']} ({tags_stats[0]['value']}건)" if tags_stats else "없음"
    top_keyword = f"{keywords[0]['name']} ({keywords[0]['value']}건)" if keywords else "없음"
    
    cursor.execute("""
        SELECT competitor, COUNT(*) as count 
        FROM scanned_docs 
        WHERE profile_id = ? AND doc_type = 'competitor' AND created_at >= datetime('now', '-14 days')
        GROUP BY competitor 
        ORDER BY count DESC LIMIT 1
    """, (profile_id,))
    row_active = cursor.fetchone()
    most_active_competitor = f"{row_active['competitor']} ({row_active['count']}건)" if row_active else "없음"
    
    conn.close()
        
    return {
        "total_docs": total_docs,
        "total_references": total_references,
        "total_trends": total_trends,
        "total_starred": starred_docs + starred_trends,
        "competitor_stats": competitors,
        "reference_stats": references,
        "keyword_stats": keywords,
        "activity_stats": activity,
        "tag_stats": tags_stats,
        "competitor_tag_stats": competitor_tag_stats,
        "latest_references": latest_references,
        "latest_competitor_releases": latest_competitor_releases,
        "latest_trends": latest_trends,
        "top_theme": top_theme,
        "top_keyword": top_keyword,
        "most_active_competitor": most_active_competitor
    }

def get_trends_for_report(profile_id: int, limit: int = 50, starred_only: bool = False, folder: str = "", keyword: str = "", match_mode: str = "any") -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    params = [profile_id]
    conditions = ["t.profile_id = ?"]
    
    if starred_only:
        conditions.append("t.is_starred = 1")
    folders = [f.strip() for f in folder.split(",") if f.strip()]
    if folders:
        placeholders = ", ".join(["?"] * len(folders))
        conditions.append(f"COALESCE(k.folder, '미분류') IN ({placeholders})")
        params.extend(folders)
    keywords = [k.strip() for k in keyword.split(",") if k.strip()]
    if keywords:
        keyword_clauses = []
        for kw in keywords:
            keyword_clauses.append("(t.keyword LIKE ? OR t.title LIKE ? OR t.summary LIKE ? OR t.source LIKE ?)")
            like = f"%{kw}%"
            params.extend([like, like, like, like])
        joiner = " AND " if match_mode == "all" else " OR "
        conditions.append("(" + joiner.join(keyword_clauses) + ")")
        
    params.append(limit)
    query = f"""
        SELECT t.*, k.folder FROM scanned_trends t
        LEFT JOIN profile_keywords k ON t.profile_id = k.profile_id AND t.keyword = k.keyword
        WHERE {' AND '.join(conditions)}
        ORDER BY COALESCE(NULLIF(t.published_at, ''), t.created_at) DESC LIMIT ?
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        item = dict(row)
        item["folder"] = item.get("folder") or "미분류"
        result.append(item)
    return result

# --- STRATEGIC REPORTS ---

def save_report(profile_id: int, title: str, content: str, report_type: str = "weekly", period_key: str = "") -> bool:
    if not (content or "").strip():
        print("[Database] Refusing to save empty report content.")
        return False

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO reports (profile_id, title, content, report_type, period_key) VALUES (?, ?, ?, ?, ?)",
            (profile_id, title, content, report_type, period_key)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[Database] Error saving report: {e}")
        return False
    finally:
        conn.close()

def get_reports(profile_id: int, report_type: str = "all") -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    if report_type and report_type != "all":
        cursor.execute(
            "SELECT id, profile_id, title, report_type, period_key, created_at FROM reports WHERE profile_id = ? AND report_type = ? ORDER BY created_at DESC",
            (profile_id, report_type)
        )
    else:
        cursor.execute(
            "SELECT id, profile_id, title, report_type, period_key, created_at FROM reports WHERE profile_id = ? ORDER BY created_at DESC",
            (profile_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def report_exists(profile_id: int, report_type: str, period_key: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM reports WHERE profile_id = ? AND report_type = ? AND period_key = ? AND LENGTH(TRIM(content)) > 0 LIMIT 1",
        (profile_id, report_type, period_key)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def get_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_template_content(template_id: str) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT template_content FROM global_templates WHERE id = ?", (template_id,))
    row = cursor.fetchone()
    conn.close()
    return row['template_content'] if row else ""

# --- BULLETIN BOARD FUNCTIONS ---

def save_board_post(profile_id: int, title: str, content: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO bulletin_board (profile_id, title, content) VALUES (?, ?, ?)",
            (profile_id, title, content)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"[Database] Error saving board post: {e}")
        return False
    finally:
        conn.close()

def get_board_posts() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, b.profile_id, b.title, b.content, b.created_at, p.name as author
        FROM bulletin_board b
        JOIN profiles p ON b.profile_id = p.id
        ORDER BY b.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_board_post(post_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM bulletin_board WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()

# --- GLOBAL TEMPLATE FUNCTIONS ---

def get_global_templates() -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM global_templates")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_global_template(template_id: str, content: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE global_templates SET template_content = ? WHERE id = ?",
        (content, template_id)
    )
    conn.commit()
    conn.close()

def get_resolved_template_for_profile(profile_id: int) -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT report_template_type, custom_report_template FROM profiles WHERE id = ?", (profile_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return ""
        
    template_type = row['report_template_type'] or 'basic'
    custom_template = row['custom_report_template']
    
    if template_type == 'custom':
        conn.close()
        return custom_template or ""
        
    cursor.execute("SELECT template_content FROM global_templates WHERE id = ?", (template_type,))
    t_row = cursor.fetchone()
    conn.close()
    
    if t_row:
        return t_row['template_content']
        
    return ""

def toggle_doc_star(doc_id: int, is_starred: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE scanned_docs SET is_starred = ? WHERE id = ?", (is_starred, doc_id))
    conn.commit()
    conn.close()

def toggle_trend_star(trend_id: int, is_starred: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE scanned_trends SET is_starred = ? WHERE id = ?", (is_starred, trend_id))
    conn.commit()
    conn.close()

# --- TWT v2 EDITOR MODE FUNCTIONS ---

EDITOR_LABELS = {
    "important",
    "report_candidate",
    "watch_competitor",
    "product_idea",
    "rfp_evidence",
    "noise",
    "later",
}

EDITOR_BUCKETS = {
    "strategy_report",
    "watch_competitor",
    "product_idea",
    "rfp_evidence",
    "likely_noise",
}

BUCKET_LABELS = {
    "strategy_report": "전략 보고서 후보",
    "watch_competitor": "경쟁사 주시 후보",
    "product_idea": "제품/솔루션 아이디어 후보",
    "rfp_evidence": "제안/RFP 근거 후보",
    "likely_noise": "노이즈 가능성 높음",
}

def save_editor_judgment(profile_id: int, item_type: str, item_id: int, label: str, note: str = "", ai_review_id: Optional[int] = None) -> Dict[str, Any]:
    if item_type not in ("doc", "trend"):
        raise ValueError("item_type must be 'doc' or 'trend'")
    if label not in EDITOR_LABELS:
        raise ValueError(f"Unsupported editor label: {label}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO editor_judgments (profile_id, ai_review_id, item_type, item_id, label, note)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, item_type, item_id, label)
            DO UPDATE SET ai_review_id = excluded.ai_review_id, note = excluded.note, updated_at = CURRENT_TIMESTAMP
            """,
            (profile_id, ai_review_id, item_type, item_id, label, note)
        )
        conn.commit()
        cursor.execute(
            """
            SELECT * FROM editor_judgments
            WHERE profile_id = ? AND item_type = ? AND item_id = ? AND label = ?
            """,
            (profile_id, item_type, item_id, label)
        )
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def classify_editor_candidate(item: Dict[str, Any]) -> Dict[str, Any]:
    title = (item.get("title") or "").lower()
    category = (item.get("category") or "").lower()
    source_name = (item.get("source_name") or "").lower()
    summary = (item.get("summary") or "").lower()
    haystack = " ".join([title, category, source_name, summary])

    bucket = "strategy_report"
    score = 52
    confidence = 58
    theme = item.get("category") or item.get("source_name") or "기술 신호"
    reason = "최근 수집된 항목으로 전략 검토 후보에 올렸습니다."

    noise_terms = ["backstage", "concert", "golf", "travel", "sortir", "연예", "공연", "카르네발", "재생에너지 투자"]
    rfp_terms = ["금융", "은행", "증권", "보험", "망분리", "보안", "규제", "거버넌스", "ai보안", "차세대", "코어뱅킹"]
    product_terms = ["developer experience", "개발자 생산성", "platform engineering", "플랫폼 엔지니어링", "idp", "devops", "devsecops", "gitops", "llmops", "rag"]
    competitor_terms = ["github", "gitlab", "atlassian", "jira", "azure devops", "harness", "copilot"]

    if any(term in haystack for term in noise_terms):
        bucket = "likely_noise"
        score = 35
        confidence = 62
        reason = "등록 키워드와는 맞지만 기술/경쟁사 전략과 직접 관련이 낮아 보입니다."
    elif any(term in haystack for term in rfp_terms):
        bucket = "rfp_evidence"
        score = 78
        confidence = 72
        reason = "금융권, 보안, 규제, 차세대 키워드와 연결되어 제안/RFP 근거 후보로 볼 수 있습니다."
    elif any(term in haystack for term in competitor_terms) or item.get("item_type") == "doc":
        bucket = "watch_competitor"
        score = 72
        confidence = 70
        reason = "경쟁사 또는 개발 플랫폼 변화와 연결되어 추적 후보로 볼 수 있습니다."
    elif any(term in haystack for term in product_terms):
        bucket = "product_idea"
        score = 68
        confidence = 66
        reason = "제품/솔루션 기획에 참고할 수 있는 기술 운영 패턴으로 보입니다."

    if int(item.get("is_starred") or 0) == 1:
        score += 12
        confidence += 6
        reason += " 이미 중요 보관함에 포함된 항목이라 우선순위를 높였습니다."
    if item.get("analysis_status") == "pending":
        reason += " 현재 AI 요약 대기 상태이므로 원문 확인 또는 요약 생성이 필요합니다."

    score = max(0, min(score, 100))
    confidence = max(0, min(confidence, 100))
    return {
        "primary_bucket": bucket,
        "secondary_buckets": "",
        "score": score,
        "confidence": confidence,
        "reason": reason,
        "related_theme": theme,
        "model_name": "rule-based-v1",
        "prompt_version": "rules-2026-06-24",
    }

def save_ai_editor_review(profile_id: int, item_type: str, item_id: int, review: Dict[str, Any]) -> Dict[str, Any]:
    if item_type not in ("doc", "trend"):
        raise ValueError("item_type must be 'doc' or 'trend'")
    bucket = review.get("primary_bucket") or "strategy_report"
    if bucket not in EDITOR_BUCKETS:
        raise ValueError(f"Unsupported editor bucket: {bucket}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE ai_editor_reviews
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = ? AND item_type = ? AND item_id = ? AND is_active = 1
            """,
            (profile_id, item_type, item_id)
        )
        cursor.execute(
            """
            INSERT INTO ai_editor_reviews (
                profile_id, item_type, item_id, primary_bucket, secondary_buckets,
                score, confidence, reason, related_theme, model_name, prompt_version, is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                profile_id,
                item_type,
                item_id,
                bucket,
                review.get("secondary_buckets", ""),
                int(review.get("score") or 0),
                int(review.get("confidence") or 0),
                review.get("reason", ""),
                review.get("related_theme", ""),
                review.get("model_name", "rule-based-v1"),
                review.get("prompt_version", "rules-2026-06-24"),
            )
        )
        review_id = cursor.lastrowid
        conn.commit()
        cursor.execute("SELECT * FROM ai_editor_reviews WHERE id = ?", (review_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def move_ai_editor_review(profile_id: int, ai_review_id: int, target_bucket: str, note: str = "") -> Dict[str, Any]:
    if target_bucket not in EDITOR_BUCKETS:
        raise ValueError(f"Unsupported editor bucket: {target_bucket}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT *
            FROM ai_editor_reviews
            WHERE id = ? AND profile_id = ? AND is_active = 1
            """,
            (ai_review_id, profile_id)
        )
        review = cursor.fetchone()
        if not review:
            raise ValueError("Active AI review not found.")

        old_bucket = review["primary_bucket"]
        move_note = note or f"사용자가 {BUCKET_LABELS.get(old_bucket, old_bucket)}에서 {BUCKET_LABELS.get(target_bucket, target_bucket)}로 이동"
        reason = review["reason"] or ""
        if old_bucket != target_bucket:
            reason = f"{reason}\n[편집장 수정] {move_note}".strip()

        cursor.execute(
            """
            UPDATE ai_editor_reviews
            SET primary_bucket = ?, reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND profile_id = ? AND is_active = 1
            """,
            (target_bucket, reason, ai_review_id, profile_id)
        )
        conn.commit()
        cursor.execute("SELECT * FROM ai_editor_reviews WHERE id = ?", (ai_review_id,))
        row = cursor.fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()

def get_items_for_ai_editor_review(profile_id: int, limit: int = 80, force: bool = False) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 80), 150))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        active_filter = "" if force else "AND ar.id IS NULL"
        cursor.execute(
            f"""
            SELECT * FROM (
                SELECT
                    'doc' AS item_type,
                    d.id AS item_id,
                    d.profile_id,
                    d.title,
                    d.competitor AS source_name,
                    d.doc_type AS category,
                    d.link,
                    d.summary,
                    d.published_at,
                    d.created_at,
                    d.analysis_status,
                    d.is_starred
                FROM scanned_docs d
                LEFT JOIN ai_editor_reviews ar
                    ON ar.profile_id = d.profile_id
                    AND ar.item_type = 'doc'
                    AND ar.item_id = d.id
                    AND ar.is_active = 1
                WHERE d.profile_id = ? {active_filter}

                UNION ALL

                SELECT
                    'trend' AS item_type,
                    t.id AS item_id,
                    t.profile_id,
                    t.title,
                    t.source AS source_name,
                    t.keyword AS category,
                    t.link,
                    t.summary,
                    t.published_at,
                    t.created_at,
                    t.analysis_status,
                    t.is_starred
                FROM scanned_trends t
                LEFT JOIN ai_editor_reviews ar
                    ON ar.profile_id = t.profile_id
                    AND ar.item_type = 'trend'
                    AND ar.item_id = t.id
                    AND ar.is_active = 1
                WHERE t.profile_id = ? {active_filter}
            )
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (profile_id, profile_id, limit)
        )
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def generate_rule_based_ai_editor_reviews(profile_id: int, limit: int = 80, force: bool = False) -> List[Dict[str, Any]]:
    items = get_items_for_ai_editor_review(profile_id, limit=limit, force=force)
    reviews = []
    for item in items:
        review = classify_editor_candidate(item)
        saved = save_ai_editor_review(profile_id, item["item_type"], item["item_id"], review)
        saved["title"] = item.get("title", "")
        saved["source_name"] = item.get("source_name", "")
        saved["category"] = item.get("category", "")
        reviews.append(saved)
    return reviews

def get_ai_insight_candidates(profile_id: int, limit_per_bucket: int = 8, include_noise: bool = True) -> Dict[str, Any]:
    limit_per_bucket = max(1, min(int(limit_per_bucket or 8), 30))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        noise_filter = "" if include_noise else "AND ar.primary_bucket != 'likely_noise'"
        cursor.execute(
            f"""
            WITH active_reviews AS (
                SELECT *
                FROM ai_editor_reviews ar
                WHERE ar.profile_id = ? AND ar.is_active = 1 {noise_filter}
            ),
            candidates AS (
                SELECT
                    ar.*,
                    d.title,
                    d.competitor AS source_name,
                    d.doc_type AS category,
                    d.link,
                    d.summary,
                    d.published_at,
                    d.created_at AS item_created_at,
                    d.analysis_status,
                    d.is_starred
                FROM active_reviews ar
                JOIN scanned_docs d ON ar.item_type = 'doc' AND ar.item_id = d.id

                UNION ALL

                SELECT
                    ar.*,
                    t.title,
                    t.source AS source_name,
                    t.keyword AS category,
                    t.link,
                    t.summary,
                    t.published_at,
                    t.created_at AS item_created_at,
                    t.analysis_status,
                    t.is_starred
                FROM active_reviews ar
                JOIN scanned_trends t ON ar.item_type = 'trend' AND ar.item_id = t.id
            ),
            ranked AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY primary_bucket
                        ORDER BY score DESC, confidence DESC, item_created_at DESC
                    ) AS bucket_rank
                FROM candidates
            )
            SELECT *
            FROM ranked
            WHERE bucket_rank <= ?
            ORDER BY
                CASE primary_bucket
                    WHEN 'strategy_report' THEN 1
                    WHEN 'watch_competitor' THEN 2
                    WHEN 'product_idea' THEN 3
                    WHEN 'rfp_evidence' THEN 4
                    WHEN 'likely_noise' THEN 5
                    ELSE 9
                END,
                score DESC,
                item_created_at DESC
            """,
            (profile_id, limit_per_bucket)
        )
        rows = [dict(r) for r in cursor.fetchall()]
        buckets = []
        for bucket in ["strategy_report", "watch_competitor", "product_idea", "rfp_evidence", "likely_noise"]:
            items = [r for r in rows if r.get("primary_bucket") == bucket]
            buckets.append({
                "bucket": bucket,
                "label": BUCKET_LABELS[bucket],
                "count": len(items),
                "items": items,
            })
        cursor.execute(
            """
            SELECT primary_bucket, COUNT(*) AS total
            FROM ai_editor_reviews
            WHERE profile_id = ? AND is_active = 1
            GROUP BY primary_bucket
            """,
            (profile_id,)
        )
        totals = {r["primary_bucket"]: r["total"] for r in cursor.fetchall()}
        for bucket in buckets:
            bucket["total"] = totals.get(bucket["bucket"], 0)
        return {"buckets": buckets, "total_active_reviews": sum(totals.values())}
    finally:
        conn.close()

def get_editor_queue(profile_id: int, limit: int = 30, include_noise: bool = False) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit or 30), 100))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        noise_filter = "" if include_noise else "WHERE COALESCE(has_noise, 0) = 0"
        cursor.execute(
            f"""
            WITH judgment_summary AS (
                SELECT
                    item_type,
                    item_id,
                    GROUP_CONCAT(label) AS labels,
                    MAX(updated_at) AS last_judged_at,
                    MAX(CASE WHEN label = 'noise' THEN 1 ELSE 0 END) AS has_noise,
                    MAX(CASE WHEN label IN ('important', 'report_candidate', 'watch_competitor', 'product_idea', 'rfp_evidence') THEN 1 ELSE 0 END) AS has_positive
                FROM editor_judgments
                WHERE profile_id = ?
                GROUP BY item_type, item_id
            ),
            candidates AS (
                SELECT
                    'doc' AS item_type,
                    d.id AS item_id,
                    d.profile_id,
                    d.title,
                    d.competitor AS source_name,
                    d.doc_type AS category,
                    d.link,
                    d.summary,
                    d.published_at,
                    d.created_at,
                    d.analysis_status,
                    d.is_starred,
                    COALESCE(js.labels, '') AS labels,
                    COALESCE(js.has_noise, 0) AS has_noise,
                    COALESCE(js.has_positive, 0) AS has_positive,
                    (
                        CASE WHEN d.is_starred = 1 THEN 30 ELSE 0 END +
                        CASE WHEN d.analysis_status = 'pending' THEN 12 ELSE 6 END +
                        CASE WHEN d.created_at >= datetime('now', '-7 days') THEN 20 ELSE 0 END +
                        CASE WHEN d.created_at >= datetime('now', '-2 days') THEN 15 ELSE 0 END +
                        CASE WHEN COALESCE(js.has_positive, 0) = 1 THEN 25 ELSE 0 END
                    ) AS editor_score
                FROM scanned_docs d
                LEFT JOIN judgment_summary js ON js.item_type = 'doc' AND js.item_id = d.id
                WHERE d.profile_id = ?

                UNION ALL

                SELECT
                    'trend' AS item_type,
                    t.id AS item_id,
                    t.profile_id,
                    t.title,
                    t.source AS source_name,
                    t.keyword AS category,
                    t.link,
                    t.summary,
                    t.published_at,
                    t.created_at,
                    t.analysis_status,
                    t.is_starred,
                    COALESCE(js.labels, '') AS labels,
                    COALESCE(js.has_noise, 0) AS has_noise,
                    COALESCE(js.has_positive, 0) AS has_positive,
                    (
                        CASE WHEN t.is_starred = 1 THEN 30 ELSE 0 END +
                        CASE WHEN t.analysis_status = 'pending' THEN 12 ELSE 6 END +
                        CASE WHEN t.created_at >= datetime('now', '-7 days') THEN 20 ELSE 0 END +
                        CASE WHEN t.created_at >= datetime('now', '-2 days') THEN 15 ELSE 0 END +
                        CASE WHEN COALESCE(js.has_positive, 0) = 1 THEN 25 ELSE 0 END
                    ) AS editor_score
                FROM scanned_trends t
                LEFT JOIN judgment_summary js ON js.item_type = 'trend' AND js.item_id = t.id
                WHERE t.profile_id = ?
            )
            SELECT * FROM candidates
            {noise_filter}
            ORDER BY editor_score DESC, created_at DESC
            LIMIT ?
            """,
            (profile_id, profile_id, profile_id, limit)
        )
        rows = cursor.fetchall()
        queue = []
        for row in rows:
            item = dict(row)
            item["labels"] = [label for label in (item.get("labels") or "").split(",") if label]
            queue.append(item)
        return queue
    finally:
        conn.close()

def get_editor_learning_summary(profile_id: int) -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT label, COUNT(*) AS count
            FROM editor_judgments
            WHERE profile_id = ?
            GROUP BY label
            ORDER BY count DESC, label ASC
            """,
            (profile_id,)
        )
        labels = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT item_type, COUNT(*) AS count
            FROM editor_judgments
            WHERE profile_id = ?
            GROUP BY item_type
            ORDER BY item_type ASC
            """,
            (profile_id,)
        )
        item_types = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT label, note, updated_at
            FROM editor_judgments
            WHERE profile_id = ?
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            (profile_id,)
        )
        recent = [dict(r) for r in cursor.fetchall()]
        return {"labels": labels, "item_types": item_types, "recent": recent}
    finally:
        conn.close()

def get_latest_collection_at(profile_id: int) -> Optional[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT MAX(collected_at) AS latest_at
        FROM (
            SELECT created_at AS collected_at FROM scanned_docs WHERE profile_id = ?
            UNION ALL
            SELECT created_at AS collected_at FROM scanned_trends WHERE profile_id = ?
        )
        """,
        (profile_id, profile_id)
    )
    row = cursor.fetchone()
    conn.close()
    return row["latest_at"] if row and row["latest_at"] else None

if __name__ == "__main__":
    print("Initializing Database Schema...")
    init_db()
    print("Database Schema Checked/Created Successfully.")
