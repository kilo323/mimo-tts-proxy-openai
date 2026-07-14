import json
import unittest
from unittest.mock import patch, MagicMock

from mimo_tts_proxy.server import check_auth, ProxyError, parse_multipart, handle_transcription


class CheckAuthTest(unittest.TestCase):
    def test_passes_when_no_proxy_key_configured(self):
        """If no PROXY_API_KEY is set, all requests pass."""
        check_auth("anything", None)

    def test_passes_when_bearer_matches(self):
        check_auth("Bearer my-secret", "my-secret")
        check_auth("bearer my-secret", "my-secret")

    def test_raises_when_no_authorization_header(self):
        with self.assertRaises(ProxyError) as ctx:
            check_auth(None, "required-key")
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("missing", str(ctx.exception).lower())

    def test_raises_when_empty_authorization_header(self):
        with self.assertRaises(ProxyError) as ctx:
            check_auth("", "required-key")
        self.assertEqual(ctx.exception.status, 401)

    def test_raises_when_not_bearer_format(self):
        with self.assertRaises(ProxyError) as ctx:
            check_auth("Basic dXNlcjpwYXNz", "required-key")
        self.assertEqual(ctx.exception.status, 401)

    def test_raises_when_bearer_key_mismatch(self):
        with self.assertRaises(ProxyError) as ctx:
            check_auth("Bearer wrong-key", "correct-key")
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("invalid", str(ctx.exception).lower())


def _make_multipart(fields):
    """Build a multipart/form-data body and its Content-Type header value.

    *fields* is a list of ``(name, payload, filename, content_type)`` tuples.
    *payload* can be ``bytes`` (for file fields) or ``str`` (for text fields).
    *filename* is ``None`` for text fields.

    Returns ``(body_bytes, content_type_value)``.
    """
    boundary = "----TestBoundary12345"
    parts = []
    for name, payload, filename, ct in fields:
        hdr = '--{b}\r\nContent-Disposition: form-data; name="{n}"'.format(
            b=boundary, n=name
        )
        if filename:
            hdr += '; filename="{f}"'.format(f=filename)
        hdr += "\r\nContent-Type: {c}\r\n\r\n".format(c=ct)
        parts.append(hdr.encode("utf-8"))
        if isinstance(payload, str):
            parts.append(payload.encode("utf-8"))
        else:
            parts.append(payload)
        parts.append(b"\r\n")
    parts.append("--{b}--\r\n".format(b=boundary).encode("utf-8"))
    body = b"".join(parts)
    ct = 'multipart/form-data; boundary="{b}"'.format(b=boundary)
    return body, ct


class ParseMultipartTest(unittest.TestCase):
    def test_extracts_file_field_with_filename(self):
        body, ct = _make_multipart([
            ("file", b"fake-audio-data", "recording.wav", "audio/wav"),
        ])
        fields = parse_multipart(body, ct)
        self.assertIn("file", fields)
        payload, filename, content_type = fields["file"]
        self.assertEqual(payload, b"fake-audio-data")
        self.assertEqual(filename, "recording.wav")
        self.assertEqual(content_type, "audio/wav")

    def test_extracts_text_fields(self):
        body, ct = _make_multipart([
            ("model", "whisper-1", None, "text/plain"),
            ("language", "zh", None, "text/plain"),
        ])
        fields = parse_multipart(body, ct)
        self.assertEqual(fields["model"][0], "whisper-1")
        self.assertIsNone(fields["model"][1])
        self.assertEqual(fields["language"][0], "zh")

    def test_mixed_file_and_text_fields(self):
        body, ct = _make_multipart([
            ("file", b"audio-data", "input.mp3", "audio/mpeg"),
            ("model", "whisper-1", None, "text/plain"),
            ("language", "en", None, "text/plain"),
            ("response_format", "text", None, "text/plain"),
        ])
        fields = parse_multipart(body, ct)
        self.assertEqual(fields["file"][0], b"audio-data")
        self.assertEqual(fields["file"][1], "input.mp3")
        self.assertEqual(fields["model"][0], "whisper-1")
        self.assertEqual(fields["language"][0], "en")
        self.assertEqual(fields["response_format"][0], "text")

    def test_handles_empty_body(self):
        """Edge case: body with no parts returns empty dict."""
        boundary = "----EmptyBoundary"
        body = "--{b}--\r\n".format(b=boundary).encode("utf-8")
        ct = 'multipart/form-data; boundary="{b}"'.format(b=boundary)
        fields = parse_multipart(body, ct)
        self.assertEqual(fields, {})


class HandleTranscriptionTest(unittest.TestCase):
    def setUp(self):
        self.state = MagicMock()
        self.state.config = {
            "mimo": {
                "asr_model": "mimo-v2.5-asr",
                "audio_format": "wav",
            },
            "audio": {"default_format": "mp3"},
        }

    def test_returns_json_text_by_default(self):
        body, ct = _make_multipart([
            ("file", b"audio-data", "input.wav", "audio/wav"),
            ("model", "whisper-1", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="识别结果"):
            result = handle_transcription(body, ct, self.state)
        self.assertEqual(result, {"text": "识别结果"})

    def test_response_format_text_returns_plain_string(self):
        body, ct = _make_multipart([
            ("file", b"audio-data", "input.wav", "audio/wav"),
            ("model", "whisper-1", None, "text/plain"),
            ("response_format", "text", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="纯文本结果"):
            result = handle_transcription(body, ct, self.state)
        self.assertEqual(result, "纯文本结果")

    def test_raises_400_when_file_field_missing(self):
        body, ct = _make_multipart([
            ("model", "whisper-1", None, "text/plain"),
        ])
        with self.assertRaises(ProxyError) as ctx:
            handle_transcription(body, ct, self.state)
        self.assertEqual(ctx.exception.status, 400)
        self.assertIn("file", str(ctx.exception).lower())

    def test_passes_language_to_transcribe(self):
        body, ct = _make_multipart([
            ("file", b"audio-data", "input.wav", "audio/wav"),
            ("model", "whisper-1", None, "text/plain"),
            ("language", "zh", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="你好") as mock_tr:
            handle_transcription(body, ct, self.state)
        call_kwargs = mock_tr.call_args.kwargs
        self.assertEqual(call_kwargs["language"], "zh")

    def test_infers_audio_format_from_filename_extension(self):
        body, ct = _make_multipart([
            ("file", b"mp3-data", "recording.mp3", "audio/mpeg"),
            ("model", "whisper-1", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="test") as mock_tr:
            handle_transcription(body, ct, self.state)
        call_kwargs = mock_tr.call_args.kwargs
        self.assertEqual(call_kwargs["audio_format"], "mp3")

    def test_infers_audio_format_from_content_type_when_no_filename(self):
        body, ct = _make_multipart([
            ("file", b"ogg-data", None, "audio/ogg"),
            ("model", "whisper-1", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="test") as mock_tr:
            handle_transcription(body, ct, self.state)
        call_kwargs = mock_tr.call_args.kwargs
        self.assertEqual(call_kwargs["audio_format"], "ogg")

    def test_defaults_audio_format_to_wav_when_unknown(self):
        body, ct = _make_multipart([
            ("file", b"data", "unknown.bin", "application/octet-stream"),
            ("model", "whisper-1", None, "text/plain"),
        ])
        with patch("mimo_tts_proxy.server.transcribe", return_value="test") as mock_tr:
            handle_transcription(body, ct, self.state)
        call_kwargs = mock_tr.call_args.kwargs
        self.assertEqual(call_kwargs["audio_format"], "wav")


if __name__ == "__main__":
    unittest.main()
