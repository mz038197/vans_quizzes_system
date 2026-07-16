import base64
import unittest

from app import normalize_question_data, validate_question_data_payload

TINY_PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)
VALID_PNG_DATA_URL = (
    'data:image/png;base64,'
    + base64.b64encode(TINY_PNG_BYTES).decode('ascii')
)


def make_image_payload(data_url=VALID_PNG_DATA_URL, filename='diagram.png'):
    return {
        'image': {
            'data_url': data_url,
            'mime_type': 'image/png',
            'filename': filename,
        }
    }


class QuestionImageNormalizationTests(unittest.TestCase):
    def test_keeps_valid_png_image(self):
        data = normalize_question_data(make_image_payload())
        self.assertIn('image', data)
        self.assertEqual(data['image']['mime_type'], 'image/png')
        self.assertEqual(data['image']['data_url'], VALID_PNG_DATA_URL)
        self.assertEqual(data['image']['filename'], 'diagram.png')

    def test_drops_missing_image(self):
        data = normalize_question_data({'correct_answer': 'A'})
        self.assertNotIn('image', data)

    def test_drops_empty_image_payload(self):
        data = normalize_question_data({'image': {'data_url': '   '}})
        self.assertNotIn('image', data)

    def test_drops_base64_with_whitespace(self):
        b64 = base64.b64encode(TINY_PNG_BYTES).decode('ascii')
        data_url = 'data:image/png;base64,' + b64[:10] + '\n' + b64[10:]
        data = normalize_question_data(make_image_payload(data_url=data_url))
        self.assertNotIn('image', data)

    def test_drops_invalid_mime_type(self):
        data_url = 'data:image/bmp;base64,' + base64.b64encode(TINY_PNG_BYTES).decode('ascii')
        data = normalize_question_data(make_image_payload(data_url=data_url))
        self.assertNotIn('image', data)

    def test_drops_oversized_image(self):
        oversized = b'x' * (2 * 1024 * 1024 + 1)
        data_url = 'data:image/png;base64,' + base64.b64encode(oversized).decode('ascii')
        data = normalize_question_data(make_image_payload(data_url=data_url))
        self.assertNotIn('image', data)

    def test_explanation_behavior_unchanged_with_image(self):
        payload = {
            'explanation': '  because A  ',
            **make_image_payload(),
        }
        data = normalize_question_data(payload)
        self.assertEqual(data['explanation'], 'because A')
        self.assertIn('image', data)

    def test_clearing_image_on_edit_removes_stored_value(self):
        updated = normalize_question_data({
            'options': ['A', 'B'],
            'correct_answer': 'A',
        })
        self.assertNotIn('image', updated)


class QuestionImageValidationTests(unittest.TestCase):
    def test_validate_accepts_valid_image(self):
        normalized, error = validate_question_data_payload(make_image_payload())
        self.assertIsNone(error)
        self.assertIn('image', normalized)

    def test_validate_rejects_invalid_image(self):
        normalized, error = validate_question_data_payload({'image': {'data_url': 'not-a-data-url'}})
        self.assertIsNone(normalized)
        self.assertEqual(error, '圖片格式不支援或超過 2MB')

    def test_validate_allows_missing_image(self):
        normalized, error = validate_question_data_payload({'correct_answer': 'A'})
        self.assertIsNone(error)
        self.assertNotIn('image', normalized)


if __name__ == '__main__':
    unittest.main()
