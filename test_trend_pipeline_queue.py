import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import agent
import database
import trend_pipeline


class TrendPipelineQueueTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.original_db_file = database.DB_FILE
        database.DB_FILE = self.db_path
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE scanned_trends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                keyword TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                summary TEXT,
                source TEXT,
                published_at TEXT DEFAULT '',
                analysis_status TEXT DEFAULT 'pending',
                analysis_error TEXT DEFAULT '',
                original_url TEXT DEFAULT '',
                source_url TEXT DEFAULT '',
                content_status TEXT DEFAULT 'not_attempted',
                content_error TEXT DEFAULT '',
                content_chars INTEGER DEFAULT 0,
                content_extractor TEXT DEFAULT '',
                content_resolver TEXT DEFAULT '',
                summary_model TEXT DEFAULT '',
                summary_evidence TEXT DEFAULT '[]',
                matched_keywords TEXT DEFAULT '',
                manual_saved INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(profile_id, title)
            );
            CREATE TABLE editor_judgments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                item_type TEXT,
                item_id INTEGER,
                label TEXT
            );
            """
        )
        for index in range(1, 4):
            conn.execute(
                """
                INSERT INTO scanned_trends (
                    profile_id, keyword, title, link, summary, source,
                    source_url, content_status, matched_keywords, manual_saved
                ) VALUES (1, 'AI Agent', ?, ?, 'RSS description', 'Test News', ?, 'queued', 'AI Agent', ?)
                """,
                (f"[AI Agent] queued {index}", f"https://news.test/{index}", f"https://news.test/{index}", 1 if index == 1 else 0),
            )
        conn.execute(
            """
            INSERT INTO scanned_trends (
                profile_id, keyword, title, link, summary, source,
                source_url, content_status, matched_keywords
            ) VALUES (1, 'AI Agent', '[AI Agent] historical backlog', 'https://news.test/old',
                      'old', 'Test News', 'https://news.test/old', 'not_attempted', 'AI Agent')
            """
        )
        conn.execute(
            "INSERT INTO editor_judgments (profile_id, item_type, item_id, label) VALUES (1, 'trend', 1, 'important')"
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_FILE = self.original_db_file
        os.unlink(self.db_path)

    @staticmethod
    def fake_content_result(profile_id, article, keyword, existing_id=0):
        return {
            "status": "summarized",
            "analysis": {
                "title": f"summary {existing_id}",
                "summary": f"verified summary {existing_id}",
                "source": article.get("source", "Test News"),
                "analysis_status": "complete",
                "analysis_error": "",
            },
            "metadata": {
                "original_url": f"https://origin.test/{existing_id}",
                "source_url": article["link"],
                "content_status": "summarized",
                "content_error": "",
                "content_chars": 1200,
                "content_extractor": "article",
                "content_resolver": "test",
                "summary_model": "ollama:test",
                "summary_evidence": ["verified evidence"],
            },
        }

    def test_cap_overflow_is_drained_across_two_cycles(self):
        with mock.patch.object(agent, "process_trend_article_content", side_effect=self.fake_content_result):
            first_cycle = agent.drain_queued_trend_content(1, limit=2)
            self.assertEqual(first_cycle["summarized"], 2)
            self.assertEqual(len(database.get_queued_trends(1, limit=10)), 1)

            second_cycle = agent.drain_queued_trend_content(1, limit=2)
            self.assertEqual(second_cycle["summarized"], 1)
            self.assertEqual(database.get_queued_trends(1, limit=10), [])

        conn = sqlite3.connect(self.db_path)
        statuses = dict(conn.execute("SELECT id, content_status FROM scanned_trends").fetchall())
        self.assertEqual([statuses[index] for index in (1, 2, 3)], ["summarized"] * 3)
        self.assertEqual(statuses[4], "not_attempted")
        self.assertEqual(conn.execute("SELECT manual_saved FROM scanned_trends WHERE id = 1").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM editor_judgments").fetchone()[0], 1)
        conn.close()

    def test_obvious_noise_is_filtered_conservatively(self):
        self.assertEqual(
            trend_pipeline.detect_obvious_search_noise({"title": "남규리 음악방송 대기실 인증"}),
            "음악방송",
        )
        self.assertEqual(
            trend_pipeline.detect_obvious_search_noise({"title": "올해 41세 맞아? [스타★샷]"}),
            "스타★샷",
        )
        self.assertEqual(
            trend_pipeline.detect_obvious_search_noise({"title": "금감원, 금융권 IT 기본통제 집중 점검"}),
            "",
        )

    def test_keyword_mismatch_noise_is_filtered_before_summary(self):
        self.assertEqual(
            trend_pipeline.detect_keyword_mismatch_noise(
                {
                    "title": "노주현, 서울 마곡 초호화 실버타운에 세컨드하우스 보유",
                    "description": "배우의 실버타운 생활을 소개한 기사",
                },
                "AI 거버넌스",
            ),
            "AI 거버넌스",
        )
        self.assertEqual(
            trend_pipeline.detect_keyword_mismatch_noise(
                {
                    "title": "현대차, 지속가능성 보고서 발간…AI 거버넌스 성과 담았다",
                    "description": "RE100과 AI 거버넌스 구축 계획을 소개했다.",
                },
                "AI 거버넌스",
            ),
            "",
        )
        self.assertEqual(
            trend_pipeline.detect_keyword_mismatch_noise(
                {
                    "title": "양자컴퓨팅이 금융산업의 경쟁력으로 부상",
                    "description": "규제 샌드박스와 투자 로드맵 필요성이 논의됐다.",
                },
                "금융 샌드박스",
            ),
            "",
        )

    def test_queued_items_do_not_inflate_failure_warning(self):
        stats = database.get_trend_content_pipeline_stats(1)
        self.assertEqual(stats["queued"], 3)
        self.assertEqual(stats["attempts"], 0)
        self.assertEqual(stats["failures"], 0)
        self.assertFalse(stats["warning"])


if __name__ == "__main__":
    unittest.main()
