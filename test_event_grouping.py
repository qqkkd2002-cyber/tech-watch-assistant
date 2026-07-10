import os
import sqlite3
import tempfile
import unittest

import database
from web_server import _select_grouped_ollama_targets, apply_editor_reuse_guard


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

    def test_ollama_target_selection_keeps_event_group_together(self):
        eligible = [
            {"item_type": "trend", "item_id": 1, "event_group_key": "event:a", "summary": "짧음"},
            {"item_type": "trend", "item_id": 2, "event_group_key": "event:a", "summary": "더 긴 대표 요약"},
            {"item_type": "trend", "item_id": 3, "event_group_key": "", "summary": "단일 기사"},
        ]

        units = _select_grouped_ollama_targets(eligible, 3)

        self.assertEqual(len(units), 2)
        self.assertEqual([row["item_id"] for row in units[0]["members"]], [1, 2])
        self.assertEqual(units[0]["representative"]["item_id"], 2)

    def test_reuse_guard_demotes_generic_training_despite_high_confidence(self):
        review = {
            "primary_bucket": "learning_signal", "score": 80, "confidence": 95,
            "reason": "AI 교육 수요를 보여줍니다.", "evidence_points": ["의료AI 직무교육을 실시함"],
        }
        item = {
            "title": "보건의료인 대상 의료AI 직무교육 실시",
            "summary": "보건의료인을 대상으로 인공지능 활용 역량 강화를 위한 일반 직무교육을 실시했다는 행사 안내입니다. 교육 일정과 참여 대상이 소개됐습니다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "noise")
        self.assertEqual(guarded["guardrail"], "forced_noise")
        self.assertLess(guarded["score"], 40)

    def test_reuse_guard_preserves_concrete_architecture_and_calibrates_confidence(self):
        review = {
            "primary_bucket": "learning_signal", "score": 85, "confidence": 95,
            "reason": "구체적인 안전 설계 방법론입니다.",
            "evidence_points": ["하네스 아키텍처를 제시함", "멀티 에이전트 워크플로를 설명함"],
        }
        item = {
            "title": "AI 안전 통제를 위한 하네스 엔지니어링",
            "summary": "AI 에이전트의 행동을 제한하는 하네스 아키텍처와 멀티 에이전트 워크플로, 보안 검증 단계를 구체적으로 설명하는 기술 자료입니다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "learning_signal")
        self.assertEqual(guarded["guardrail"], "positive_evidence_checked")
        self.assertLess(guarded["confidence"], 90)

    def test_reuse_guard_preserves_supported_network_separation_change(self):
        review = {
            "primary_bucket": "review_queue", "score": 55, "confidence": 60,
            "reason": "판단 대기", "evidence_points": ["금융사 10곳에 망분리 의무 면제"],
        }
        item = {
            "title": "보안 목적 AI에 망분리 의무 적용 안 한다",
            "summary": "금융감독원은 보안 목적으로 AI를 활용하는 금융사 10곳에 망분리 의무를 면제하는 법령해석과 비조치의견서를 발급했다. 금융회사는 1년간 관련 테스트를 진행하며, 고성능 AI를 활용한 보안 분석과 취약점 점검을 수행할 수 있다. 이는 금융당국이 구체적인 보안 조건 아래 규제를 완화한 제도 변화다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "work_signal")
        self.assertEqual(guarded["guardrail"], "preserved_regulatory_work_signal")
        self.assertGreaterEqual(guarded["confidence"], 82)

    def test_trombone_guard_promotes_ai_coding_with_cicd_to_work(self):
        review = {
            "primary_bucket": "learning_signal", "score": 72, "confidence": 74,
            "reason": "AI 코딩 적용 사례입니다.",
            "evidence_points": ["AI 코딩 도구를 CI/CD 파이프라인과 연동해 생성 코드를 통제함"],
        }
        item = {
            "title": "금융권 AI 코딩 변경 통제 강화",
            "summary": "은행 개발팀이 AI 코딩 도구를 CI/CD 파이프라인과 연동했다. 생성 코드의 변경 이력을 추적하고 배포 전 보안 정책 검증과 감사 기록을 남긴다. 승인되지 않은 코드가 운영 환경으로 넘어가지 않도록 단계별 승인 절차와 취약점 검사를 자동화하고, 모든 변경 이력을 규제 대응 자료로 보관한다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "work_signal")
        self.assertEqual(guarded["guardrail"], "preserved_trombone_work_signal")
        self.assertGreaterEqual(guarded["score"], 82)

    def test_trombone_guard_demotes_pure_ai_model_news_to_learning(self):
        review = {
            "primary_bucket": "work_signal", "score": 86, "confidence": 91,
            "reason": "새 AI 모델 출시 소식입니다.",
            "evidence_points": ["새 대규모 언어 모델의 컨텍스트 길이를 공개함"],
        }
        item = {
            "title": "새 대규모 언어 모델 공개",
            "summary": "한 AI 기업이 새 대규모 언어 모델을 공개하고 컨텍스트 길이와 벤치마크 점수, 다국어 성능을 발표했다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "learning_signal")
        self.assertEqual(guarded["guardrail"], "demoted_pure_ai_to_learning")
        self.assertLessEqual(guarded["score"], 75)

    def test_trombone_guard_preserves_supported_pure_ai_as_learning(self):
        review = {
            "primary_bucket": "learning_signal", "score": 78, "confidence": 83,
            "reason": "새 AI 모델의 성능 특성을 설명합니다.",
            "evidence_points": ["대규모 언어 모델의 컨텍스트 길이와 벤치마크를 공개함"],
        }
        item = {
            "title": "차세대 대규모 언어 모델 공개",
            "summary": "AI 기업이 차세대 대규모 언어 모델을 공개하고 긴 컨텍스트 처리 성능과 다국어 벤치마크 결과를 발표했다. 이전 모델과 비교한 추론 정확도, 처리량, 지원 언어별 성능도 함께 제시해 모델 기술 동향을 비교할 수 있는 자료를 제공했다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "learning_signal")
        self.assertEqual(guarded["guardrail"], "positive_evidence_checked")

    def test_reuse_guard_calibrates_noise_confidence(self):
        review = {
            "primary_bucket": "noise", "score": 30, "confidence": 95,
            "reason": "일반 교육 공지", "evidence_points": ["직무교육을 실시함", "일정을 안내함"],
        }
        item = {
            "title": "보건의료인 AI 직무교육",
            "summary": "보건의료인을 대상으로 일반적인 AI 활용 직무교육을 진행하며 교육 일정과 참여 대상을 안내하는 내용입니다. 기술 아키텍처나 성과는 없습니다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "noise")
        self.assertLess(guarded["confidence"], 90)

    def test_reuse_guard_demotes_forum_announcement_without_results(self):
        review = {
            "primary_bucket": "learning_signal", "score": 75, "confidence": 90,
            "reason": "AI 거버넌스 방향을 공유합니다.",
            "evidence_points": ["포럼을 개최할 예정", "정책과 기술 방향을 공유할 예정"],
        }
        item = {
            "title": "서울시, AI 개인정보보호 포럼 개최",
            "summary": "서울시는 개인정보보호 포럼을 개최할 예정이며 정책, 법률, 기술, 거버넌스 방향을 공유한다고 밝혔다. 구체적인 제도 변경이나 실행 결과는 아직 발표되지 않았다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "noise")
        self.assertEqual(guarded["guardrail"], "forced_noise")

    def test_reuse_guard_does_not_treat_technical_collaboration_as_event_noise(self):
        review = {
            "primary_bucket": "learning_signal", "score": 72, "confidence": 82,
            "reason": "AI 실험 자동화의 기술 성과입니다.",
            "evidence_points": ["자율 AI 시스템이 반복 실험으로 화학 반응 수율을 개선함"],
        }
        item = {
            "title": "A near-autonomous AI chemist improves a challenging reaction",
            "summary": "여러 연구기관이 협력해 구축한 자율 AI 시스템이 실험 조건을 반복적으로 탐색했다. 시스템은 측정 결과를 다음 실험에 반영하는 폐쇄형 루프를 사용해 어려운 화학 반응의 수율을 개선했으며, 연구진은 구체적인 실험 결과와 자동화 방법을 공개했다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "learning_signal")
        self.assertEqual(guarded["guardrail"], "positive_evidence_checked")

    def test_reuse_guard_keeps_ai_surf_day_as_noise(self):
        review = {
            "primary_bucket": "learning_signal", "score": 70, "confidence": 82,
            "reason": "사내 AI 활용 행사입니다.",
            "evidence_points": ["구성원이 AI 프로토타입을 제작하는 행사를 진행함"],
        }
        item = {
            "title": "토스팀이 AI 파도를 마주하는 방법: AI Surf Day",
            "summary": "전사 구성원이 생성형 AI 아이디어를 공유하고 하루 동안 프로토타입을 제작하는 내부 행사를 진행했다. 구체적인 제품 출시나 운영 방식 변경 성과는 아직 발표되지 않았다.",
        }

        guarded = apply_editor_reuse_guard(review, item)

        self.assertEqual(guarded["primary_bucket"], "noise")
        self.assertEqual(guarded["guardrail"], "forced_noise")


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
