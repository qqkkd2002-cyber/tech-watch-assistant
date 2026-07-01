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


if __name__ == "__main__":
    unittest.main()
