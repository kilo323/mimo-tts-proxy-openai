import base64
import unittest
from unittest.mock import MagicMock

from mimo_tts_proxy.transcribe import transcribe


class TranscribeTest(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.fake_audio = b"fake wav data"

    def _stub_response(self, text):
        """Configure the mock client to return *text* from the ASR model."""
        mock_msg = MagicMock()
        mock_msg.content = text
        mock_choice = MagicMock()
        mock_choice.message = mock_msg
        self.client.chat.completions.create.return_value.choices = [mock_choice]

    # --- happy path ---

    def test_returns_text_from_message_content(self):
        self._stub_response("你好世界今天天气真好")
        result = transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        self.assertEqual(result, "你好世界今天天气真好")

    def test_returns_empty_string_when_mimo_returns_empty(self):
        self._stub_response("")
        result = transcribe(self.client, b"", "wav", "mimo-v2.5-asr")
        self.assertEqual(result, "")

    # --- model selection ---

    def test_calls_chat_completions_with_correct_model(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        call_kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-asr")

    def test_model_name_is_configurable(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "mp3", "custom-asr-model")
        call_kwargs = self.client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "custom-asr-model")

    # --- message structure ---

    def test_user_message_has_one_role(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        messages = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")

    def test_content_is_two_part_array(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 2)

    def test_first_part_is_text_prompt(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("text", content[0])

    def test_second_part_is_audio_url(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "audio_url")
        self.assertIn("audio_url", content[1])

    # --- base64 data URL ---

    def test_audio_url_is_base64_data_url(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        url = content[1]["audio_url"]["url"]
        self.assertTrue(url.startswith("data:audio/wav;base64,"))
        encoded = url.split(",", 1)[1]
        self.assertEqual(base64.b64decode(encoded), self.fake_audio)

    def test_mp3_format_in_data_url_mime_type(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "mp3", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        url = content[1]["audio_url"]["url"]
        self.assertTrue(url.startswith("data:audio/mp3;base64,"))

    def test_flac_format_in_data_url_mime_type(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "flac", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        url = content[1]["audio_url"]["url"]
        self.assertTrue(url.startswith("data:audio/flac;base64,"))

    # --- language hint ---

    def test_language_none_uses_generic_prompt(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr", language=None)
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Transcribe this audio.")

    def test_language_zh_adds_chinese_hint(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr", language="zh")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Chinese", content[0]["text"])

    def test_language_en_adds_english_hint(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr", language="en")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("English", content[0]["text"])

    def test_unknown_language_code_falls_back_to_generic(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr", language="ja")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["text"], "Transcribe this audio.")

    # --- empty / edge ---

    def test_empty_audio_produces_valid_base64_url(self):
        self._stub_response("")
        transcribe(self.client, b"", "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        url = content[1]["audio_url"]["url"]
        self.assertTrue(url.endswith("base64,"))


if __name__ == "__main__":
    unittest.main()
