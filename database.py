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
    
    conn.commit()
    
    # Alter profiles table to add template columns if missing
    cursor.execute("PRAGMA table_info(profiles)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'report_template_type' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN report_template_type TEXT DEFAULT 'basic'")
    if 'custom_report_template' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN custom_report_template TEXT DEFAULT ''")
    if 'auto_report_enabled' not in columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN auto_report_enabled INTEGER DEFAULT 1")
    
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
        
    conn.commit()
    
    # Populate or update default global templates
    default_templates = [
        ("basic", "[기본] 기술 신호 및 경쟁사 동향 보고서", 
         """You are a senior technology strategy analyst for the 솔루션전략팀.
Write a Korean strategic technology signal report from the collected competitor updates and industry news.

Your job is not to summarize every item one by one. Your job is to identify repeated signals, keyword frequency, competitor direction, and strategic implications.

Rules:
- Use only the evidence in the collected data below. If evidence is weak, say "현재 수집 데이터 기준".
- Treat repeated keywords, similar product updates, and recurring themes as market signals.
- Mention concrete competitors/products when available.
- Separate facts from interpretation.
- Keep the tone professional, concise, and useful for solution strategy work.

[Competitor Docs Updates]
{docs_context}

[Industry Tech Trends & News]
{trends_context}

Please structure the report exactly as follows:
# 기술 신호 및 경쟁사 동향 보고서 ({current_date})

## 1. Executive Summary
- 이번 기간 가장 중요한 기술/경쟁 신호를 3~5개 bullet로 요약합니다.
- 각 bullet은 "무슨 변화가 보이는지"와 "왜 중요한지"를 함께 설명합니다.

## 2. 자주 등장한 기술 키워드
- 수집 데이터에서 반복적으로 등장한 키워드를 빈도/중요도 기준으로 정리합니다.
- 각 키워드별로 "등장 맥락", "의미", "솔루션전략팀 관점의 해석"을 작성합니다.
- 가능하면 표 형식으로 작성합니다.

## 3. 경쟁사 동향 및 제품 방향성
- 경쟁사/제품별 업데이트를 묶어서 어떤 방향으로 움직이는지 분석합니다.
- 단순 기능 나열이 아니라 "AI 강화", "보안 내재화", "관리/거버넌스 강화", "비용 통제" 같은 방향성으로 해석합니다.

## 4. 반복 신호와 시장 해석
- 여러 항목에서 반복되는 신호를 3~5개 뽑습니다.
- 각 신호에 대해 "근거", "해석", "잠재 영향"을 구분해서 작성합니다.

## 5. 솔루션전략팀 시사점
- 우리 팀이 제품 전략, 제안 전략, 경쟁 분석, 로드맵 검토에서 참고해야 할 점을 구체적으로 작성합니다.
- 필요하면 위협 수준을 상/중/하로 평가합니다.

## 6. 다음 액션 제안
- 다음 달까지 추적할 키워드, 추가해야 할 RSS/경쟁사, 내부 검토 과제를 제안합니다.

Make the formatting clean and highly readable for Markdown."""),
        
        ("monthly", "[월간] 솔루션전략팀 월간 전략 보고서",
         """You are writing a monthly strategic report for the 솔루션전략팀.
Analyze collected competitor updates and technology news as strategic market intelligence.

Focus on:
- Which technology keywords appeared repeatedly
- What signals are emerging
- Which competitors are moving in which direction
- What this means for our solution strategy
- What should be tracked or acted on next

Rules:
- Do not write a generic news summary.
- Use evidence from the collected data.
- If the dataset is still small, explicitly state that the finding is based on limited accumulated data.

[Competitor Docs Updates]
{docs_context}

[Industry Tech Trends & News]
{trends_context}

Please structure the report exactly as follows:
# 솔루션전략팀 월간 전략 보고서 ({current_date})

## 1. 전략적 핵심 요약
- 이번 달 기술 시장과 경쟁사 움직임의 핵심 결론을 5개 이내로 정리합니다.

## 2. 기술 키워드 빈도 및 중요도 분석
- 반복 등장 키워드를 표로 정리합니다.
- 각 키워드에 대해 등장 맥락, 전략적 의미, 향후 추적 필요성을 설명합니다.

## 3. 경쟁사별 움직임
- 경쟁사/제품별 업데이트를 요약하고, 그 배후의 제품 전략을 추정합니다.
- 기능 개선, AI, 보안, DevSecOps, 거버넌스, 비용 관리 중 어떤 축에 집중하는지 분석합니다.

## 4. 이번 달의 핵심 신호
- 데이터에서 드러난 반복 신호를 3~5개 도출합니다.
- 각 신호별로 근거, 해석, 우리에게 주는 의미를 구분합니다.

## 5. 우리 솔루션 전략에 대한 영향
- 경쟁 위협 수준을 상/중/하로 평가합니다.
- 제품 로드맵, 영업 메시지, 제안서/RFP 대응, 파트너 전략 관점에서 시사점을 작성합니다.

## 6. 다음 달 추적 과제
- 반드시 추적해야 할 키워드
- 추가할 경쟁사/RSS
- 내부 논의가 필요한 제품/전략 과제

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

def update_profile(profile_id: int, name: str, gemini_api_key: str, discord_webhook_url: str, check_interval_hours: int, report_template_type: str = 'basic', custom_report_template: str = '', auto_report_enabled: int = 1):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE profiles SET name = ?, gemini_api_key = ?, discord_webhook_url = ?, check_interval_hours = ?, report_template_type = ?, custom_report_template = ?, auto_report_enabled = ? WHERE id = ?",
            (name, gemini_api_key, discord_webhook_url, check_interval_hours, report_template_type, custom_report_template, auto_report_enabled, profile_id)
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
            if name and url:
                cursor.execute(
                    "INSERT INTO profile_feeds (profile_id, name, feed_url) VALUES (?, ?, ?)",
                    (profile_id, name, url)
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

def save_scanned_doc(profile_id: int, competitor: str, title: str, link: str, date: str, summary: str, impact: str, keywords: List[str], published_at: str = "", analysis_status: str = "complete", analysis_error: str = "") -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    kw_str = ", ".join(keywords)
    try:
        cursor.execute(
            """INSERT INTO scanned_docs (profile_id, competitor, title, link, date, summary, impact, keywords, published_at, analysis_status, analysis_error) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (profile_id, competitor, title, link, date, summary, impact, kw_str, published_at, analysis_status, analysis_error)
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
           WHERE profile_id = ? AND analysis_status = 'pending'
           ORDER BY created_at ASC LIMIT ?""",
        (profile_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

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
           WHERE profile_id = ? AND analysis_status = 'pending'
           ORDER BY created_at ASC LIMIT ?""",
        (profile_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

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

def get_docs(profile_id: int, limit: int = 50, offset: int = 0, search: str = "", starred_only: bool = False, match_mode: str = "any") -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    conditions = ["profile_id = ?"]
    params = [profile_id]
    if starred_only:
        conditions.append("is_starred = 1")
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
        "SELECT 1 FROM reports WHERE profile_id = ? AND report_type = ? AND period_key = ? LIMIT 1",
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
