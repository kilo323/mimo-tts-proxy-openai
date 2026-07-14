# ASR — OpenAI `/v1/audio/transcriptions` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenAI-compatible `/v1/audio/transcriptions` endpoint to the proxy, translating requests to MIMO `mimo-v2.5-asr` via chat completions (base64 audio input).

**Architecture:** Mirror the TTS path — a new `transcribe.py` module encodes audio→base64 data URL, calls MIMO chat completions, extracts text. Server gains a `do_POST` route that parses `multipart/form-data` (stdlib `email` module, zero new deps) and a pure `handle_transcription()` function. Auth reuses existing `check_auth()`.

**Tech Stack:** Python 3.12 stdlib + `openai` SDK (existing), `pyyaml` (existing). Conda env `mimo-tts-proxy`.

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `config.yaml` | **Modify** | Add `mimo.asr_model: "mimo-v2.5-asr"` |
| `mimo_tts_proxy/transcribe.py` | **Create** | `transcribe(client, audio_bytes, audio_format, model, language)` → `str` |
| `mimo_tts_proxy/server.py` | **Modify** | `parse_multipart()` helper + `handle_transcription()` + `do_POST` routing + `make_handler` signature |
| `tests/test_transcribe.py` | **Create** | Unit tests for `transcribe()` (mock client) |
| `tests/test_server.py` | **Modify** | Tests for `parse_multipart()` + `handle_transcription()` |

## Global Constraints

- Zero new dependencies — stdlib only (project already uses `openai` + `pyyaml`)
- Reuse existing `openai.Client` instance and MIMO auth (`state.client`)
- Python 3.12+ (conda env `mimo-tts-proxy`)
- Existing 30 tests must stay green; new tests follow `unittest` + mock pattern
- Follow existing naming/idiom: snake_case modules, docstring on every public function, Chinese-capable
- MIMO ASR model: `mimo-v2.5-asr`; endpoint: `/v1/chat/completions`; audio sent as `data:audio/{fmt};base64,...` in a multi-part user-message `content` array

---

### Task 1: Add ASR model to config

**Files:**
- Modify: `config.yaml:9-15`

**Interfaces:**
- Produces: `state.config["mimo"]["asr_model"]` → `"mimo-v2.5-asr"`

- [ ] **Step 1: Add `asr_model` key to `config.yaml`**

Edit `config.yaml`. In the `mimo:` section, append one line after `audio_format: "wav"`:

```yaml
mimo:
  base_url: "https://api.xiaomimimo.com/v1"
  api_key_env: "MIMO_API_KEY"
  tts_model_preset: "mimo-v2.5-tts"
  tts_model_clone: "mimo-v2.5-tts-voiceclone"
  audio_format: "wav"
  asr_model: "mimo-v2.5-asr"
```

- [ ] **Step 2: Verify config loads**

```bash
cd /Volumes/Storage/Project/tools/mimo-tts-proxy-openai
python -c "from mimo_tts_proxy.config import load_config; c=load_config(); print(c['mimo']['asr_model'])"
```
Expected output: `mimo-v2.5-asr`

- [ ] **Step 3: Run existing tests — confirm no regressions**

```bash
python -m pytest tests/ -v
```
Expected: 30 passed

- [ ] **Step 4: Commit**

```bash
git add config.yaml
git commit -m "feat(config): add mimo.asr_model key for ASR support

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Implement `transcribe()` function

**Files:**
- Create: `mimo_tts_proxy/transcribe.py`
- Create: `tests/test_transcribe.py`

**Interfaces:**
- Produces: `transcribe(client, audio_bytes, audio_format, model, language=None) -> str`
  - `client` — `openai.OpenAI` instance
  - `audio_bytes` — raw audio as `bytes`
  - `audio_format` — format string without dot, e.g. `"wav"`, `"mp3"`, `"flac"`
  - `model` — ASR model name, e.g. `"mimo-v2.5-asr"`
  - `language` — optional ISO-639-1 code (`"zh"`, `"en"`, or `None` for auto-detect)
  - Returns: transcribed text string

- [ ] **Step 1: Create `tests/test_transcribe.py` with all tests**

```python
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
```

- [ ] **Step 2: Run tests — expect failure (module missing)**

```bash
python -m pytest tests/test_transcribe.py -v
```
Expected: `ModuleNotFoundError: No module named 'mimo_tts_proxy.transcribe'`

- [ ] **Step 3: Create `mimo_tts_proxy/transcribe.py`**

```python
"""ASR (speech-to-text) via MIMO chat completions.

MIMO's ``mimo-v2.5-asr`` model accepts audio as a base64 data URL in a
multi-part user-message content array, returning transcribed text in
``choices[0].message.content`` — the same chat-completions contract as TTS.
"""
import base64


LANGUAGE_PROMPTS = {
    None: "Transcribe this audio.",
    "zh": "Transcribe this audio in Chinese.",
    "en": "Transcribe this audio in English.",
}


def transcribe(client, audio_bytes, audio_format, model, language=None):
    """Transcribe audio using a MIMO ASR model.

    Args:
        client: ``openai.OpenAI`` instance (same as the TTS path).
        audio_bytes: Raw audio data.
        audio_format: Format string without dot prefix (``"wav"``, ``"mp3"``,
            ``"flac"``, etc.).
        model: ASR model name, e.g. ``"mimo-v2.5-asr"``.
        language: Optional ISO-639-1 code. ``"zh"`` / ``"en"`` add a language
            hint to the prompt; ``None`` (the default) uses auto-detection.

    Returns:
        The transcribed text string.
    """
    encoded = base64.b64encode(audio_bytes).decode("ascii")
    data_url = "data:audio/{fmt};base64,{data}".format(fmt=audio_format, data=encoded)

    prompt_text = LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS[None])

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "audio_url", "audio_url": {"url": data_url}},
                ],
            }
        ],
    )
    return completion.choices[0].message.content
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
python -m pytest tests/test_transcribe.py -v
```
Expected: 16 passed

- [ ] **Step 5: Run full test suite — confirm no regressions**

```bash
python -m pytest tests/ -v
```
Expected: 46 passed (30 existing + 16 new)

- [ ] **Step 6: Commit**

```bash
git add mimo_tts_proxy/transcribe.py tests/test_transcribe.py
git commit -m "feat: add transcribe() — MIMO ASR via chat completions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Add multipart parser and `/v1/audio/transcriptions` route

**Files:**
- Modify: `mimo_tts_proxy/server.py:1-163`

**Interfaces:**
- Consumes: `transcribe(client, audio_bytes, audio_format, model, language)` from Task 2
- Produces: `parse_multipart(body_bytes, content_type) -> dict[str, tuple[bytes|str, str|None, str]]`
  - Returns `{field_name: (payload, filename_or_None, content_type)}`
- Produces: `handle_transcription(raw_body, content_type, state) -> dict | str`
  - Returns `{"text": "..."}` (json) or `"..."` (text), depending on `response_format`
  - Reads `model`, `language`, `response_format` from multipart fields; `file` is required
- Modifies: `make_handler(state, proxy_key)` — adds `do_POST` routing for `/v1/audio/transcriptions`

**Design decisions:**
- Multipart parsing uses stdlib `email.parser.BytesParser` (not the deprecated `cgi.FieldStorage`)
- Audio format inferred from the file part's filename extension, falling back to Content-Type
- `response_format` supported: `"json"` (default) and `"text"`; `"verbose_json"`, `"srt"`, `"vtt"` return 400 for now (explicitly unsupported rather than silently degraded)
- `model`, `prompt`, `temperature` fields accepted but ignored (MIMO ASR doesn't need them)

- [ ] **Step 1: Update `tests/test_server.py` with new test classes**

Append these imports to the top of `tests/test_server.py` (after the existing `from mimo_tts_proxy.server import check_auth, ProxyError`):

```python
from unittest.mock import patch, MagicMock
from mimo_tts_proxy.server import parse_multipart, handle_transcription
```

Remove the old `from unittest.mock import patch, MagicMock` line if it exists; replace with the above.

Then append these test classes at the end of the file (before `if __name__ == "__main__":`):

```python
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
```

Note: the existing `unittest.mock` import line at the top of `test_server.py` must also import `patch` and `MagicMock`:

```python
from unittest.mock import patch, MagicMock
```

If the existing import says `from unittest.mock import patch, MagicMock` already, keep it as-is. If it only says `from unittest.mock import patch, MagicMock`, that's fine — but currently it has neither. Check the file — `test_server.py` line 2 currently reads:

```python
from unittest.mock import patch, MagicMock
```

If this line is already present, keep it. If not, update it.

- [ ] **Step 2: Run tests — expect failure**

```bash
python -m pytest tests/test_server.py -v
```
Expected: tests like `test_extracts_file_field_with_filename` fail with `AttributeError` or `ImportError` because `parse_multipart` and `handle_transcription` don't exist yet. The existing `CheckAuthTest` tests should still pass.

- [ ] **Step 3: Add `parse_multipart()` and `handle_transcription()` to `server.py`**

In `mimo_tts_proxy/server.py`, add these new imports at the top:

```python
from email.parser import BytesParser
from email.policy import default as email_default_policy
```

Then add these two functions between `check_auth()` and `handle_speech()` (i.e., after line 36, before line 39):

```python
def parse_multipart(body_bytes, content_type):
    """Parse a ``multipart/form-data`` body into a dict of fields.

    Each value is a ``(payload, filename, content_type)`` tuple.
    For text fields *payload* is a ``str`` and *filename* is ``None``.
    For file fields *payload* is ``bytes`` and *filename* is the
    original filename (or ``None`` if not provided).

    Uses stdlib ``email.parser.BytesParser`` — zero new dependencies.
    """
    parser = BytesParser(policy=email_default_policy)
    msg = parser.parsebytes(
        "Content-Type: {ct}\r\n\r\n".format(ct=content_type).encode()
        + body_bytes
    )
    fields = {}
    for part in msg.walk():
        cd = part.get_content_disposition()
        if cd != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_param("filename", header="content-disposition")
        payload = part.get_payload(decode=True)
        if filename is None and payload is not None:
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = payload.decode(charset)
            except UnicodeDecodeError:
                pass  # keep as bytes
        fields[name] = (payload, filename, part.get_content_type())
    return fields


def _infer_audio_format(filename, content_type):
    """Guess audio format from filename extension or MIME type.

    Returns a short format string without dot (``"wav"``, ``"mp3"``, …).
    Defaults to ``"wav"`` when neither source provides a known format.
    """
    known = {"wav", "mp3", "mpeg", "flac", "m4a", "ogg", "opus", "aac", "webm"}
    if filename and "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in known:
            return ext
    if content_type:
        fmt = content_type.split("/")[-1].lower()
        if fmt == "mpeg":
            return "mp3"
        if fmt in known:
            return fmt
    return "wav"


def handle_transcription(raw_body, content_type, state):
    """Handle an OpenAI ``/v1/audio/transcriptions`` request.

    Parses the multipart body, extracts the ``file`` field, calls MIMO ASR
    via :func:`transcribe`, and returns the result in the requested format.

    All parameters (``model``, ``language``, ``response_format``, ``file``)
    are read from the multipart form fields — there is no JSON wrapper.

    Returns:
        ``{"text": "..."}`` for ``response_format=json`` (default), or a
        plain ``str`` for ``response_format=text``.

    Raises:
        ProxyError: 400 when the ``file`` field is missing or empty.
    """
    fields = parse_multipart(raw_body, content_type)

    if "file" not in fields:
        raise ProxyError("file is required", 400)
    audio_bytes, filename, file_ct = fields["file"]
    if not audio_bytes:
        raise ProxyError("file is empty", 400)

    # Read scalar params from multipart fields (with defaults)
    response_format = fields.get("response_format", ("json", None, "text/plain"))[0]
    language = (fields.get("language") or (None,))[0] or None

    audio_format = _infer_audio_format(filename, file_ct)
    model = state.config["mimo"]["asr_model"]

    text = transcribe(state.client, audio_bytes, audio_format, model, language)

    if response_format == "text":
        return text
    return {"text": text}
```

- [ ] **Step 4: Update `do_POST` in `make_handler()` to route transcriptions**

In `mimo_tts_proxy/server.py`, inside the `Handler` class within `make_handler()`, modify the `do_POST` method (lines 119-150). The current method only handles `/v1/audio/speech`. Add a branch for `/v1/audio/transcriptions` **before** the existing speech-handling logic.

Replace the `do_POST` method body with:

```python
        def do_POST(self):
            try:
                check_auth(self.headers.get("Authorization"), proxy_key)
            except ProxyError as e:
                self._send_json(e.status, {"error": {"message": str(e), "type": e.type_}})
                return

            # --- /v1/audio/transcriptions ---
            if self.path == "/v1/audio/transcriptions":
                try:
                    content_type = self.headers.get("Content-Type", "")
                    length = int(self.headers.get("Content-Length", 0) or 0)
                    raw = self.rfile.read(length) if length else b""

                    result = handle_transcription(raw, content_type, state)
                except ProxyError as e:
                    self._send_json(e.status, {"error": {"message": str(e), "type": e.type_}})
                    return
                except Exception as e:
                    self._send_json(500, {"error": {"message": str(e), "type": "internal_error"}})
                    return

                if isinstance(result, str):
                    # response_format=text — plain text response
                    data = result.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._send_json(200, result)
                return

            # --- /v1/audio/speech (existing) ---
            if self.path != "/v1/audio/speech":
                self._send_json(404, {"error": {"message": "not found", "type": "not_found"}})
                return
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw or "{}")
            except Exception as e:
                self._send_json(
                    400,
                    {"error": {"message": "invalid JSON: %s" % e, "type": "invalid_request_error"}},
                )
                return
            try:
                audio_bytes, content_type = handle_speech(body, state)
            except ProxyError as e:
                self._send_json(e.status, {"error": {"message": str(e), "type": e.type_}})
                return
            except Exception as e:
                self._send_json(500, {"error": {"message": str(e), "type": "internal_error"}})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(audio_bytes)))
            self.end_headers()
            self.wfile.write(audio_bytes)
```

Also add the import for `transcribe` and `handle_transcription` at the top of the file. Update line 6:

```python
from .emotion import assemble_style_prompt, infer_emotion
from .mimo import build_mimo_request, select_model, synthesize
from .transcode import content_type_for, needs_transcode, transcode_audio
from .transcribe import transcribe
from .voices import build_voice_param, resolve_voice
```

- [ ] **Step 5: Run all tests**

```bash
python -m pytest tests/ -v
```
Expected: 57 passed (30 existing + 16 Task 2 + 11 Task 3)

- [ ] **Step 6: Commit**

```bash
git add mimo_tts_proxy/server.py tests/test_server.py
git commit -m "feat: add /v1/audio/transcriptions endpoint with multipart parsing

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Smoke test — end-to-end validation

**Files:**
- Modify: `smoke_test.py:65-119`

**Interfaces:**
- Consumes: `POST /v1/audio/transcriptions` (Task 3)

- [ ] **Step 1: Add ASR smoke test to `smoke_test.py`**

Add a `transcribe()` helper function and extend `main()`:

After the `speech()` function (line 44), add:

```python
def transcribe(filepath, language=None):
    """Send an audio file to /v1/audio/transcriptions and return the text."""
    boundary = "----SmokeTestBoundary"
    filename = os.path.basename(filepath)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"
    mime_type = "audio/" + ("mpeg" if ext == "mp3" else ext)

    with open(filepath, "rb") as f:
        audio_data = f.read()

    parts = []
    # file part
    parts.append(
            '--{b}\r\nContent-Disposition: form-data; name="file"; filename="{fn}"\r\n'
            "Content-Type: {ct}\r\n\r\n".format(b=boundary, fn=filename, ct=mime_type).encode()
    )
    parts.append(audio_data)
    parts.append(b"\r\n")
    # model part
    parts.append(
        '--{b}\r\nContent-Disposition: form-data; name="model"\r\n\r\nwhisper-1\r\n'.format(
            b=boundary
        ).encode()
    )
    if language:
        parts.append(
            '--{b}\r\nContent-Disposition: form-data; name="language"\r\n\r\n{l}\r\n'.format(
                b=boundary, l=language
            ).encode()
        )
    parts.append("--{b}--\r\n".format(b=boundary).encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        BASE_URL + "/v1/audio/transcriptions",
        data=body,
        headers={
            "Content-Type": 'multipart/form-data; boundary="{b}"'.format(b=boundary),
            "Authorization": "Bearer smoke",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.headers.get("Content-Type"), r.read()
```

Then in `main()`, after the preset voice test (after line 108: `print(f"[preset] {len(audio)} bytes  {ctype}  -> {path2}")`), add:

```python
        # 3) ASR transcription — send a WAV file and verify text comes back
        # Use one of the TTS output files as test audio (it contains speech)
        asr_file = path2  # the preset WAV from step 2
        status, ctype, text_bytes = transcribe(asr_file)
        assert status == 200, f"asr: status {status}"
        text = json.loads(text_bytes.decode("utf-8"))["text"]
        assert len(text) > 0, "asr: empty transcription"
        print(f"[asr   ] {len(text)} chars  -> {text[:80]}")
```

- [ ] **Step 2: Run smoke test (requires MIMO_API_KEY)**

```bash
python smoke_test.py
```
Expected: All three steps pass (clone TTS, preset TTS, ASR transcription). The transcription should return recognizable Chinese text.

- [ ] **Step 3: Run full test suite one final time**

```bash
python -m pytest tests/ -v
```
Expected: 56 passed

- [ ] **Step 4: Commit**

```bash
git add smoke_test.py
git commit -m "test: add ASR end-to-end smoke test

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Verification Checklist

After all tasks are complete:

1. `python -m pytest tests/ -v` — 56 tests pass
2. `python smoke_test.py` — TTS + ASR both work against real MIMO API
3. `git log --oneline -5` — four commits (config → transcribe → server → smoke)
