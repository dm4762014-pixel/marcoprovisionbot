import json
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image
from streamlit.testing.v1 import AppTest
from services import validate_chat_id, validate_image, clean_recap, send_telegram, friendly_error, TelegramError


class ServiceTests(unittest.TestCase):
    def test_authentication_error_is_specific_and_private(self):
        message = friendly_error(SimpleNamespace(code=401, message='private-key'))
        self.assertIn('GEMINI_API_KEY', message)
        self.assertIn('401', message)
        self.assertNotIn('private-key', message)

    def test_chat_validation(self):
        self.assertEqual(validate_chat_id(' 123456789 '), '123456789')
        self.assertEqual(validate_chat_id('-100123456789'), '-100123456789')
        for invalid in ('@student', '+919876543210', '0', 'hello'):
            with self.assertRaises(ValueError):
                validate_chat_id(invalid)

    def test_photo_validation(self):
        data = BytesIO()
        Image.new('RGB', (20, 20)).save(data, format='PNG')
        self.assertEqual(validate_image(data.getvalue()), 'image/png')
        with self.assertRaises(ValueError):
            validate_image(b'not an image')
        with self.assertRaises(ValueError):
            validate_image(b'x' * (10 * 1024 * 1024 + 1))

    def test_telegram_payload(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'ok': True, 'result': {'message_id': 42}}).encode()
        with patch('services.urlopen', return_value=response) as request:
            self.assertEqual(send_telegram('123456789:' + 'x' * 35, '123456789', 'Student', 'Revise fractions.'), 42)
            payload = json.loads(request.call_args.args[0].data)
            self.assertEqual(payload['chat_id'], '123456789')
            self.assertIn('Revise fractions.', payload['text'])
            self.assertNotIn('parse_mode', payload)
        self.assertEqual(len(clean_recap('x' * 2000)), 1500)
        with self.assertRaises(ValueError):
            clean_recap(' ')

    def test_telegram_error_does_not_expose_token(self):
        self.assertIn('bot token', friendly_error(TelegramError(401), service='Telegram'))
        self.assertIn('/start', friendly_error(TelegramError(400), service='Telegram'))



class AppTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_resource.clear()
        self.factory_patch = patch('google.genai.Client')
        self.factory = self.factory_patch.start()
        self.client = self.factory.return_value
        self.client.models.generate_content.return_value = SimpleNamespace(text='A force equals mass times acceleration.')
        self.at = AppTest.from_file('../app.py', default_timeout=20)
        self.at.secrets['GEMINI_API_KEY'] = 'test-key'
        self.at.secrets['TELEGRAM_BOT_TOKEN'] = ''

    def tearDown(self):
        self.factory_patch.stop()

    def onboard(self):
        self.at.run()
        self.at.text_input[0].set_value('Student')
        self.at.text_input[1].set_value('123456789')
        self.at.checkbox[0].check()
        self.at.button(key='onboard_submit').click().run()
        self.assertFalse(self.at.exception)

    def test_onboarding_and_reset(self):
        self.at.run()
        self.at.button(key='onboard_submit').click().run()
        self.assertTrue(self.at.warning)
        self.onboard()
        self.assertTrue(self.at.session_state.onboarded)
        self.assertTrue(self.at.button(key='recap').disabled)
        self.at.button(key='reset').click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.text_input), 2)

    def test_text_photo_memory_recap_and_send(self):
        self.onboard()
        self.at.chat_input[0].set_value('Explain Newton second law').run()
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.session_state.history), 2)
        data = BytesIO()
        Image.new('RGB', (20, 20)).save(data, format='PNG')
        self.at.session_state.pending = {'text': 'Explain this diagram', 'image': data.getvalue(),
                                         'mime_type': 'image/png', 'mode': 'Explain step by step'}
        self.at.run()
        self.assertFalse(self.at.exception)
        call = self.client.models.generate_content.call_args.kwargs
        self.assertEqual(len(call['contents']), 3)
        self.assertEqual(call['contents'][-1].parts[0].inline_data.mime_type, 'image/png')
        self.assertEqual(len(self.at.session_state.history), 4)
        self.client.models.generate_content.return_value = SimpleNamespace(text='Revise F = ma. Practise one force calculation.')
        self.at.button(key='recap').click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.session_state.history), 4)
        self.assertTrue(self.at.session_state.summary)
        self.assertTrue(self.at.button(key='send').disabled)
        self.at.secrets['TELEGRAM_BOT_TOKEN'] = '123456789:' + 'x' * 35
        self.at.run()
        with patch('services.telegram_request', return_value={'message_id': 42}) as request:
            self.at.button(key='send').click().run()
            self.assertFalse(self.at.exception)
            self.assertTrue(self.at.success)
            self.assertEqual(request.call_count, 1)
            self.assertIn('Revise F = ma', request.call_args.args[2]['text'])
        self.at.run()
        self.assertTrue(self.at.button(key='send').disabled)

    def test_failure_does_not_corrupt_history(self):
        self.onboard()
        self.client.models.generate_content.side_effect = RuntimeError('secret-data')
        self.at.chat_input[0].set_value('Explain a fraction').run()
        self.assertFalse(self.at.exception)
        self.assertTrue(self.at.error)
        self.assertNotIn('secret-data', self.at.error[0].value)
        self.assertEqual(len(self.at.session_state.history), 0)
        self.assertIsNotNone(self.at.session_state.pending)
        calls_after_error = self.client.models.generate_content.call_count
        self.at.selectbox[0].select('Give me a hint').run()
        self.assertEqual(self.client.models.generate_content.call_count, calls_after_error)
        self.client.models.generate_content.side_effect = None
        self.at.button(key='retry').click().run()
        self.assertFalse(self.at.exception)
        self.assertEqual(len(self.at.session_state.history), 2)


if __name__ == '__main__':
    unittest.main()
