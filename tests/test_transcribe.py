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

    def test_single_user_message(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        messages = self.client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["role"], "user")

    def test_content_is_single_part_array(self):
        """MIMO gateway rejects text parts, so content must be only the audio."""
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 1)

    def test_content_part_is_input_audio(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "input_audio")
        self.assertIn("input_audio", content[0])

    # --- base64 audio data ---

    def test_input_audio_data_is_base64_encoded_audio(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        audio_part = content[0]["input_audio"]
        self.assertEqual(base64.b64decode(audio_part["data"]), self.fake_audio)

    def test_input_audio_format_matches_audio_format_wav(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["input_audio"]["format"], "wav")

    def test_input_audio_format_matches_audio_format_mp3(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "mp3", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["input_audio"]["format"], "mp3")

    def test_input_audio_format_matches_audio_format_flac(self):
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "flac", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(content[0]["input_audio"]["format"], "flac")

    # --- language param (accepted but ignored — MIMO gateway handles it) ---

    def test_language_param_accepted_without_error(self):
        """language is accepted for API compatibility but ignored by MIMO."""
        self._stub_response("test")
        transcribe(self.client, self.fake_audio, "wav", "mimo-v2.5-asr", language="zh")
        # No text part should be present regardless of language
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(len(content), 1)
        self.assertEqual(content[0]["type"], "input_audio")

    # --- empty / edge ---

    def test_empty_audio_produces_valid_base64_data(self):
        self._stub_response("")
        transcribe(self.client, b"", "wav", "mimo-v2.5-asr")
        content = self.client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        audio_part = content[0]["input_audio"]
        self.assertEqual(base64.b64decode(audio_part["data"]), b"")


if __name__ == "__main__":
    unittest.main()
