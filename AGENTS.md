# AGENTS.md — mimo-tts-proxy-openai

OpenAI audio-protocol proxy for Xiaomi MIMO (MiMo V2.5). Front side exposes the
standard OpenAI endpoints `POST /v1/audio/speech` (TTS) and
`POST /v1/audio/transcriptions` (ASR); back side translates each request into a
MIMO **chat-completions** call.

- **Language / framework**: Python **3.10+** (env target conda env
  `mimo-tts-proxy`). **Zero web framework** — plain stdlib `http.server`.
- **Runtime deps (only these two)**: `openai` (OpenAI SDK, used as MIMO's HTTP
  client) + `pyyaml`. Everything else is stdlib (e.g. multipart parsing uses
  `email.parser`, never `cgi`). The Docker image additionally installs
  `mcp-auth` (see the auth note below).

## Commands

- **Run** (proxy on `0.0.0.0:9880`): `python -m mimo_tts_proxy.app`
- **Test**: `python -m pytest tests/ -v` → 66 passed, 5 skipped (skips need a MIMO key).
- **Smoke test** (real MIMO call, needs `MIMO_API_KEY`): `python smoke_test.py`
- **Deploy** (auto-detects Docker / macOS launchd / Linux systemd): `./deploy.sh`

Install deps manually if needed: `pip install openai pyyaml`.

## Layout

```
mimo_tts_proxy/          # Python package
  app.py                 # entry: load config, build clients, start server
  server.py              # HTTP routes + multipart parse + auth
  config.py              # config.yaml/.env loading, voice registry, key lookup
  mimo.py                # TTS: build chat-completions request + synthesize
  transcribe.py          # ASR: build chat-completions request + transcribe
  voices.py              # voice name -> clone/preset resolution
  emotion.py             # LLM emotion inference + style prompt assembly
  transcode.py           # ffmpeg WAV -> mp3/opus/ogg/flac/aac/pcm
tests/                   # one test_*.py per module
config.yaml              # server + MIMO + emotion + audio settings
config-custom.yaml       # alternate config (token-plan baseUrl)
voices.yaml              # registered voice character library
samples/                 # voice-clone sample files (gitignored, stay local)
deploy/                  # launchd (.plist) / systemd (.service) templates
smoke_test.py            # end-to-end test (needs MIMO_API_KEY)
test_openai_speech_endpoint.py
```

## Key facts / gotchas

- **TTS and ASR both go through MIMO `chat-completions`**, not OpenAI's audio
  endpoints — this proxy is purely a protocol translation layer.
- **TTS**: text → `assistant` message, style → preceding `user` message, voice
  → `audio.voice` (preset name or `data:` URL). Returns base64 WAV in
  `choices[0].message.audio.data`; transcoded by ffmpeg.
- **ASR**: audio → base64 `input_audio` part in a `user` message's content array.
  **Do NOT add a text part** — the MIMO gateway injects its own prompt and will
  reject the request otherwise (`ASR request must not include text parts`).
- **Auth**: `.env` `PROXY_API_KEY` is optional. Set → clients must send
  `Authorization: Bearer <key>`; unset → open access.
- **Keys**: `MIMO_API_KEY` read from `.env` (`config.py:resolve_api_key`, with an
  env-var fallback for Docker). `PROXY_API_KEY` likewise (`resolve_proxy_api_key`).
- **Voices**: `voices.yaml` registered name → clone sample or preset; an
  **unregistered name passes straight through** as a MIMO preset.
- **MIMO base_url** is `https://api.xiaomimimo.com/v1` (check the spelling).
  `config-custom.yaml` points at the token-plan endpoint instead.
- **mcp_auth**: server.py lazily imports `mcp_auth.store` only when
  `MCP_AUTH_DB` is set (see `check_auth` / `open_token_store`).

## Testing conventions

- `unittest` + `unittest.mock.MagicMock`; the suite runs under `pytest`.
- Mock `openai.Client` — do **not** call the real MIMO API in unit tests
  (except `smoke_test.py`).
- Keep one `tests/test_<module>.py` per module.

## Red lines

- **Never hardcode the MIMO API key** — only read from `.env` / env vars.
- **Never add a text part to an ASR request** (see above).
- **Never use `cgi.FieldStorage`** — removed in Python 3.13; use
  `email.parser.BytesParser`.
- After **changing the MIMO request/response format**, run `smoke_test.py` to
  verify — MIMO's API docs are incomplete and the real contract is discovered by
  calling it.

## Docs

- Design specs: `docs/superpowers/specs/`; implementation plans:
  `docs/superpowers/plans/`
- Full usage/API details: `README.md` (Chinese), `README.en.md` (English).
