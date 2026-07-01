import os
import sqlite3
import tempfile
import unittest

import database


class EventGroupingTest(unittest.TestCase):
    def test_confirmed_event_members_fold_without_losing_links(self):
        items = [
            {
                "id": 1, "item_id": 10, "item_type": "trend", "title": "짧은 기사",
                "summary": "짧은 요약", "link": "https://a.example", "event_group_key": "event:x",
            },
            {
                "id": 2, "item_id": 11, "item_type": "trend", "title": "자세한 기사",
                "summary": "더 자세하고 긴 대표 요약입니다.", "link": "https://b.example", "event_group_key": "event:x",
            },
        ]

        folded, folded_count = database._dedupe_candidate_items(items, 30)

        self.assertEqual(len(folded), 1)
        self.assertEqual(folded_count, 1)
        self.assertEqual(folded[0]["event_group_count"], 2)
        self.assertEqual(folded[0]["title"], "자세한 기사")
        self.assertEqual(
            {member["link"] for member in folded[0]["event_group_items"]},
            {"https://a.example", "https://b.example"},
        )

    def test_url_and_event_folds_can_be_counted_separately(self):
        items = [
            {"id": 1, "item_id": 10, "item_type": "trend", "link": "https://same.example", "event_group_key": "event:x"},
            {"id": 2, "item_id": 11, "item_type": "trend", "link": "https://same.example", "event_group_key": "event:x"},
            {"id": 3, "item_id": 12, "item_type": "trend", "link": "https://other.example", "event_group_key": "event:x"},
        ]

        folded, folded_count = database._dedupe_candidate_items(items, 30)
        event_count = sum(max(0, int(item.get("event_group_count") or 1) - 1) for item in folded)

        self.assertEqual(folded_count, 2)
        self.assertEqual(event_count, 1)
        self.assertEqual(folded_count - event_count, 1)


class EventGroupJudgmentTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.original_db_file = database.DB_FILE
        database.DB_FILE = self.db_path
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE scanned_docs (
                id INTEGER PRIMARY KEY, manual_saved INTEGER DEFAULT 0, is_starred INTEGER DEFAULT 0
            );
            CREATE TABLE scanned_trends (
                id INTEGER PRIMARY KEY, manual_saved INTEGER DEFAULT 0, is_starred INTEGER DEFAULT 0
            );
            CREATE TABLE ai_editor_reviews (
                id INTEGER PRIMARY KEY, profile_id INTEGER, item_type TEXT, item_id INTEGER,
                primary_bucket TEXT, reason TEXT DEFAULT '', is_active INTEGER DEFAULT 1,
                event_group_key TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE editor_judgments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id INTEGER, ai_review_id INTEGER,
                item_type TEXT, item_id INTEGER, label TEXT, note TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(profile_id, item_type, item_id, label)
            );
            """
        )
        for item_id in range(1, 5):
            conn.execute("INSERT INTO scanned_trends (id) VALUES (?)", (item_id,))
            conn.execute(
                """INSERT INTO ai_editor_reviews
                   (id, profile_id, item_type, item_id, primary_bucket, event_group_key)
                   VALUES (?, 1, 'trend', ?, 'review_queue', 'event:test')""",
                (item_id, item_id),
            )
        conn.commit()
        conn.close()

    def tearDown(self):
        database.DB_FILE = self.original_db_file
        os.unlink(self.db_path)

    def test_one_click_applies_to_all_four_group_members(self):
        result = database.move_ai_editor_review_group(1, 1, "work_signal", "테스트 묶음 판단")

        self.assertEqual(result["applied_count"], 4)
        self.assertEqual(result["skipped_count"], 0)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM ai_editor_reviews WHERE primary_bucket='work_signal'").fetchone()[0], 4)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM editor_judgments WHERE label='work_signal'").fetchone()[0], 4)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM scanned_trends WHERE is_starred=1").fetchone()[0], 4)
        conn.close()

    def test_manual_saved_and_existing_judgment_are_preserved(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE scanned_trends SET manual_saved=1, is_starred=1 WHERE id=3")
        conn.execute(
            """INSERT INTO editor_judgments
               (profile_id, ai_review_id, item_type, item_id, label, note)
               VALUES (1, 4, 'trend', 4, 'learning_signal', '기존 개별 판단')"""
        )
        conn.commit()
        conn.close()

        result = database.move_ai_editor_review_group(1, 1, "noise", "테스트 묶음 판단")

        self.assertEqual(result["applied_count"], 2)
        self.assertEqual(result["skipped_count"], 2)
        conn = sqlite3.connect(self.db_path)
        self.assertEqual(conn.execute("SELECT primary_bucket FROM ai_editor_reviews WHERE id=3").fetchone()[0], "review_queue")
        self.assertEqual(conn.execute("SELECT primary_bucket FROM ai_editor_reviews WHERE id=4").fetchone()[0], "review_queue")
        self.assertEqual(conn.execute("SELECT manual_saved FROM scanned_trends WHERE id=3").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT label FROM editor_judgments WHERE item_id=4").fetchone()[0], "learning_signal")
        conn.close()


if __name__ == "__main__":
    unittest.main()
