# mimo-tts-proxy-openai

An OpenAI-compatible audio HTTP proxy backed by **Xiaomi MIMO** (MiMo V2.5). It exposes two endpoints:

- **`POST /v1/audio/speech`** — text-to-speech (TTS) with cloned game-character voices or MIMO presets.
- **`POST /v1/audio/transcriptions`** — speech-to-text (ASR) using `mimo-v2.5-asr`.

Point any OpenAI audio client (OpenClaw / Hermes / OpenAI SDK) at this proxy to give an Agent both a voice and ears.

> 📖 [中文 README](README.md)

## Architecture

```
OpenAI audio client (OpenClaw / Hermes / OpenAI SDK / any)
        │
        │  POST /v1/audio/speech          ← text → audio
        │  POST /v1/audio/transcriptions  ← audio → text
        ▼
┌─────────────────────────────┐
│   mimo-tts-proxy            │
│   http://0.0.0.0:9880       │
│                             │
│  TTS:  resolve voice →      │
│        infer emotion →      │
│        chat-completions     │
│        + audio.voice →      │
│        base64 WAV → transcode│
│                             │
│  ASR:  multipart parse →    │
│        chat-completions     │
│        + input_audio → text │
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│   Xiaomi MIMO API           │
│   api.xiaomimimo.com/v1     │
│                             │
│  Both TTS and ASR run       │
│  through chat-completions,  │
│  NOT OpenAI's audio paths.  │
│  This proxy translates.     │
└─────────────────────────────┘
```

## How it works

MIMO exposes both TTS and ASR as **chat-completions** calls:

- **TTS**: the text to speak goes in an `assistant` message, optional style direction in a preceding `user` message, and the voice (preset name or `data:` URL of a clone sample) in an `audio.voice` field. The response carries base64-encoded WAV in `choices[0].message.audio.data`.
- **ASR**: audio is sent as a base64-encoded `input_audio` part in a `user` message's content array (**no text parts allowed** — the MIMO gateway injects its own prompt), model `mimo-v2.5-asr`. The transcribed text comes back in `choices[0].message.content`.

This proxy implements the standard **OpenAI `/v1/audio/speech`** and **`/v1/audio/transcriptions`** contracts on the front side and translates every request into the MIMO chat-completions shape on the back side. The TTS translation includes:

- **Voice resolution**: registered voices (`voices.yaml`) become either clone data-URLs or MIMO preset names; unknown names pass through as presets.
- **Emotion inference** (optional, per-voice): a small/fast LLM reads the reply text and produces a Chinese-language "director" instruction (e.g. `语调上扬，带着惊喜` / `低沉缓慢，略带悲伤` …), which is layered on top of the voice's base style to form the MIMO `user` message.
- **Format transcoding**: MIMO always returns WAV; if the client requests `mp3`, `opus`, `ogg`, `flac`, `aac`, or `pcm`, ffmpeg converts the WAV before returning it.

## Prerequisites

| Requirement | How to check | How to install |
|---|---|---|
| **Python ≥ 3.10** | `python3 --version` | [python.org](https://www.python.org/) or `brew install python` / `apt install python3` |
| **ffmpeg** | `ffmpeg -version` | `brew install ffmpeg` / `apt install ffmpeg` |
| **MIMO API key** | `echo $MIMO_API_KEY` | Register at [xiaomimimo.com](https://xiaomimimo.com), then put it in `.env` or `export MIMO_API_KEY="sk-..."` |

No other services or databases are required.

## Setup

### Option 1: One-click script (recommended)

```bash
./deploy.sh
```

The script auto-detects the environment (Docker / macOS / Linux), generates `.env` interactively, and picks the best deployment method (Docker Compose / launchd / systemd).

### Option 2: Manual setup

#### 1. Clone

```bash
git clone https://github.com/Jedi-Pz/mimo-tts-proxy-openai.git
cd mimo-tts-proxy-openai
```

#### 2. Create a virtual environment and install dependencies

The proxy has two Python dependencies: `openai` (OpenAI Python SDK, used as the MIMO HTTP client) and `pyyaml` (config parsing).

```bash
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install openai pyyaml
```

#### 3. Configure environment variables

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

```dotenv
MIMO_API_KEY=sk-your-mimo-api-key
PROXY_API_KEY=your-proxy-auth-key   # optional; leave empty to disable auth
```

The proxy reads keys from `.env` at startup (with an env-var fallback for Docker). Keys are **never** hardcoded.

- `MIMO_API_KEY` (required): API key for the MIMO platform.
- `PROXY_API_KEY` (optional): proxy auth key. When set, clients must send `Authorization: Bearer <key>`; when unset, the proxy is open (suitable for isolated LANs).

#### 4. Review the configuration

The file `config.yaml` ships with defaults that work out of the box:

```yaml
server:
  host: "0.0.0.0"    # Bind address (use 127.0.0.1 for localhost-only)
  port: 9880          # Port

mimo:
  base_url: "https://api.xiaomimimo.com/v1"
  api_key_env: "MIMO_API_KEY"
  tts_model_preset: "mimo-v2.5-tts"              # Model for preset voices
  tts_model_clone: "mimo-v2.5-tts-voiceclone"    # Model for cloned voices
  audio_format: "wav"                             # Format MIMO returns
  asr_model: "mimo-v2.5-asr"                      # Speech recognition model

emotion:
  enabled: true                    # Set false to skip LLM inference
  model: "mimo-v2-flash"           # Small/fast model for emotion hints
  base_url: "https://api.xiaomimimo.com/v1"
  api_key_env: "MIMO_API_KEY"      # Falls back to mimo key if unset
  max_input_chars: 1000            # Truncate long text before sending to LLM

audio:
  default_format: "mp3"   # Used when the client omits response_format
  ffmpeg_path: "ffmpeg"   # Path to ffmpeg binary
```

You can override `server.host` to `127.0.0.1` if you only need local access.

#### 5. Register voices

Edit `voices.yaml`. Each voice entry has four fields:

| Field | Required | Description |
|---|---|---|
| `sample_file` | For clone | Absolute path to a WAV or MP3 file (≤ 10 MB). The proxy base64-encodes it and passes it as a `data:` URL to MIMO for voice cloning. |
| `preset` | For preset | MIMO preset voice name (e.g. `冰糖`, `alloy`). Omit `sample_file` and set this instead. |
| `base_style` | No | A fixed Chinese-language style hint always prepended to the emotion prompt (e.g. `温柔、知性的女声`). |
| `emotion_inference` | No | Boolean. When `true`, an LLM reads each input text and appends a dynamic emotion direction. |

**Clone voice example:**
```yaml
voices:
  zhuangfangyi:
    sample_file: "/home/you/voices/my-character.wav"
    base_style: "温柔、知性的女声"
    emotion_inference: true
```

**Preset voice example:**
```yaml
voices:
  bingtang:
    preset: "冰糖"
    base_style: "活泼少女"
    emotion_inference: false
```

**Fallback behavior:** Any voice name NOT in `voices.yaml` is treated as a MIMO preset — so `"voice": "alloy"` just works without registration.

### Option 3: Docker

```bash
docker compose up -d
```

`docker-compose.yml` injects env vars from `.env` and maps port `9880:9880`. See `Dockerfile` and `docker-compose.yml` for details.

## Run

```bash
# Activate the venv if not already in it
source venv/bin/activate

# Start the proxy
python -m mimo_tts_proxy.app
```

You should see:
```
mimo-tts-proxy listening on http://0.0.0.0:9880/v1/audio/speech
```

**Daemonizing (Linux):** use `systemd` (template in `deploy/mimo-tts-proxy.service`), or a simple `nohup python -m mimo_tts_proxy.app &`.

**Daemonizing (macOS):** use `launchd` (template in `deploy/mimo-tts-proxy.plist`), or run inside a `tmux`/`screen` session.

## Test

### Unit tests (no API key needed)

```bash
python -m pytest tests/ -v
```

Expected: **66 tests, all passing.**

### Smoke test (needs MIMO_API_KEY)

This starts the proxy, sends two real TTS requests (one clone, one preset), then feeds the TTS audio into ASR to verify transcription:

```bash
MIMO_API_KEY="sk-..." python smoke_test.py
```

Expected output:
```
server is up at http://127.0.0.1:9880
[clone ] 17709 bytes  audio/mpeg  -> /tmp/mimo_proxy_smoke_clone.mp3
[preset] 122924 bytes  audio/wav  -> /tmp/mimo_proxy_smoke_preset.wav
[asr   ] 12 chars  -> 你好，这是预置音色测试。

SMOKE TEST PASSED
```

## API reference

### `GET /health`
Returns `{"status": "ok"}` with HTTP 200. No auth required.

### `POST /v1/audio/speech` (TTS)

OpenAI-compatible. **Headers, request body, and response semantics match the OpenAI TTS API.**

#### Request

```json
{
  "model": "tts-1",
  "input": "今天天气真好，我们一起出去玩吧！",
  "voice": "zhuangfangyi",
  "response_format": "mp3",
  "context": null
}
```

| Field | Required | Default | Notes |
|---|---|---|---|
| `model` | No | — | Ignored by the proxy; accepted for client compatibility. |
| `input` | **Yes** | — | Text to synthesize. Up to ~4000 chars (MIMO limit). |
| `voice` | **Yes** | — | Resolved against `voices.yaml`; falls back to MIMO preset name. |
| `response_format` | No | `mp3` | One of: `mp3`, `wav`, `opus`, `ogg`, `flac`, `aac`, `pcm`. |
| `context` | No | `null` | **Extension.** If provided, it is used verbatim as the MIMO style prompt, bypassing base-style + emotion inference entirely. |

#### Response

**HTTP 200** — audio bytes with the appropriate `Content-Type` header:
- `audio/mpeg` for mp3
- `audio/wav` for wav
- `audio/ogg` for opus/ogg
- `audio/flac` for flac
- `audio/aac` for aac
- `audio/pcm` for pcm

### `POST /v1/audio/transcriptions` (ASR)

OpenAI-compatible. Accepts `multipart/form-data` and returns transcribed text.

#### Request

`multipart/form-data` fields:

| Field | Required | Notes |
|---|---|---|
| `file` | **Yes** | Audio file (wav/mp3/flac/m4a/ogg, etc.). |
| `model` | No | Ignored — the proxy always uses `mimo.asr_model` from `config.yaml`. |
| `language` | No | Accepted but unused — the MIMO gateway handles language detection. |
| `response_format` | No | `json` (default, returns `{"text": "..."}`) or `text` (returns plain text). |

#### Response

**HTTP 200** — `response_format=json`:
```json
{"text": "你好，这是预置音色测试。"}
```

**HTTP 200** — `response_format=text`:
```
你好，这是预置音色测试。
```

**HTTP 4xx / 5xx** — JSON error body:
```json
{
  "error": {
    "message": "file is required",
    "type": "invalid_request_error"
  }
}
```

### Authentication

If `PROXY_API_KEY` is set in `.env`, all requests must include:
```
Authorization: Bearer <PROXY_API_KEY>
```
When unset, the proxy is open (suitable for isolated LANs).

## Client configuration

### OpenAI Python SDK — TTS

```python
from openai import OpenAI

client = OpenAI(
    api_key="your-proxy-key",        # PROXY_API_KEY if set; any non-empty string otherwise
    base_url="http://127.0.0.1:9880/v1",  # ← points at the proxy
)

with client.audio.speech.with_streaming_response.create(
    model="tts-1",
    input="你好世界",
    voice="zhuangfangyi",
    response_format="mp3",
) as response:
    response.stream_to_file("output.mp3")
```

### OpenAI Python SDK — ASR

```python
with open("recording.wav", "rb") as f:
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=f,
    )
print(transcript.text)
```

### curl — TTS

```bash
curl -s -X POST http://127.0.0.1:9880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-proxy-key" \
  -d '{"model":"tts-1","input":"你好世界","voice":"zhuangfangyi","response_format":"mp3"}' \
  -o output.mp3
```

### curl — ASR

```bash
curl -s -X POST http://127.0.0.1:9880/v1/audio/transcriptions \
  -H "Authorization: Bearer your-proxy-key" \
  -F "file=@recording.wav" \
  -F "model=whisper-1"
```

### OpenClaw / Hermes

Both clients support OpenAI audio natively. Set both TTS and STT `base_url` to `http://127.0.0.1:9880/v1` and `api_key` to `PROXY_API_KEY` (or any non-empty string if unset). The Agent can then understand voice messages and reply with voice.

## Emotion inference

When a voice has `emotion_inference: true` and `config.yaml` has `emotion.enabled: true`, the proxy sends the input text to an LLM (default: `mimo-v2-flash`) with the prompt:

```
你是语音合成情绪导演。阅读下面这段将要被朗读的文字，用一句简短的中文描述
该用什么语气和情绪来朗读（语调、语速、情绪色彩等）。只输出这一句描述，
不要朗读原文，不要解释。

文字：
<the input text>
```

The LLM's reply (e.g. `语调上扬，带着惊喜和期待`) is combined with the voice's `base_style` via newline-separated concatenation and sent as the MIMO `user` message — giving the TTS model direction on *how* to speak the line.

If emotion inference fails (network error, LLM returns empty), the proxy logs a warning to stderr and continues with just the `base_style`. It never blocks a TTS request on inference failure.

To skip emotion inference entirely, either set `emotion.enabled: false` in `config.yaml` or set `emotion_inference: false` on the voice entry.

## Audio formats and transcoding

MIMO always returns WAV (`audio/wav`). When the client requests any other format, the proxy pipes the WAV through ffmpeg:

| Target format | ffmpeg args (beyond `-i in.wav`) |
|---|---|
| `mp3` | `-acodec libmp3lame` |
| `opus` / `ogg` | `-acodec libopus -ac 1 -b:a 64k` |
| `flac` | `-acodec flac` |
| `aac` | `-acodec aac` |
| `pcm` | `-acodec pcm_s16le` |

If the requested format equals `audio_format` in config (default `wav`), the proxy returns the WAV directly — no ffmpeg call.

## Project structure

```
mimo-tts-proxy-openai/
├── mimo_tts_proxy/         # Python package
│   ├── __init__.py
│   ├── app.py              # Entry point: wire everything, start server
│   ├── config.py           # YAML config + .env loading + voice registry
│   ├── emotion.py          # LLM emotion inference + style prompt assembly
│   ├── mimo.py             # MIMO TTS request builder + synthesis caller
│   ├── transcribe.py       # MIMO ASR request builder + transcription caller
│   ├── server.py           # HTTP server (/speech + /transcriptions)
│   ├── transcode.py        # ffmpeg-based audio format conversion
│   └── voices.py           # Voice resolution (registered → clone/preset)
├── tests/                  # 66 unit tests
├── deploy/                 # Daemon templates
│   ├── mimo-tts-proxy.plist    # macOS launchd
│   └── mimo-tts-proxy.service  # Linux systemd
├── samples/                # Voice clone sample files
├── config.yaml             # Server, MIMO, emotion, audio settings
├── voices.yaml             # Your voice character registry
├── .env.example            # Environment variable template
├── smoke_test.py           # End-to-end test (needs MIMO_API_KEY)
├── deploy.sh               # One-click deploy script
├── Dockerfile
├── docker-compose.yml
├── .gitignore
├── README.md               # Chinese README
└── README.en.md            # This file (English)
```

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `MIMO_API_KEY not found` at startup | `.env` missing or key not filled | Create `.env` (see `.env.example`), or use `env_file: .env` in Docker |
| HTTP 401 `Authorization header missing` | `PROXY_API_KEY` is set but client didn't send it | Add `Authorization: Bearer <PROXY_API_KEY>` to requests |
| HTTP 401 `Invalid proxy API key` | Client key doesn't match `PROXY_API_KEY` in `.env` | Check the value in `.env` |
| `voice sample >10MB` | Clone sample file too large | Compress/resample the WAV to mono 16-24 kHz |
| `unsupported sample format` | Clone sample is not `.wav` or `.mp3` | Convert: `ffmpeg -i file.m4a file.wav` |
| `ffmpeg failed` | ffmpeg not installed or not on PATH | `brew install ffmpeg` / `apt install ffmpeg`, or set `audio.ffmpeg_path` in `config.yaml` |
| `emotion inference failed (continuing without)` in stderr | Transient LLM error | Harmless — TTS still works with `base_style` only |
| `MIMO returned no audio data` | Invalid voice name, or MIMO API error | Check the voice exists (preset) or the sample is valid (clone); test MIMO directly with curl |
| ASR returns 500 `ASR requires exactly one input_audio part` | Malformed request body (internal proxy error) | Ensure you're using multipart/form-data with a `file` field; the proxy builds the correct MIMO request |
| Connection refused | Proxy not running, or wrong host/port | Verify `server.host` and `server.port` in `config.yaml`; check no other process is on that port |

For more detail, consult the MIMO API docs at [xiaomimimo.com](https://xiaomimimo.com).

## License

MIT
