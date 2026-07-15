import json
import unittest

from app import normalize_question_data


class ExplanationNormalizationTests(unittest.TestCase):
    def test_keeps_non_empty_explanation(self):
        data = normalize_question_data({'correct_answer': 'A', 'explanation': '  because A  '})
        self.assertEqual(data['explanation'], 'because A')

    def test_drops_missing_explanation(self):
        data = normalize_question_data({'correct_answer': 'A'})
        self.assertNotIn('explanation', data)

    def test_drops_empty_explanation_string(self):
        data = normalize_question_data({'correct_answer': 'A', 'explanation': '   '})
        self.assertNotIn('explanation', data)

    def test_clearing_explanation_on_edit_replaces_stored_value(self):
        """Simulate PUT replacing question_data when user clears explanation."""
        stored = {'options': ['A', 'B'], 'correct_answer': 'A', 'explanation': 'old text'}
        payload = {'options': ['A', 'B'], 'correct_answer': 'A'}
        updated = normalize_question_data(payload)
        self.assertNotIn('explanation', updated)
        self.assertEqual(json.loads(json.dumps(updated)), updated)


if __name__ == '__main__':
    unittest.main()
