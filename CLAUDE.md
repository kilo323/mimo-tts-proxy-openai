# CLAUDE.md — mimo-tts-proxy-openai

OpenAI 音频协议（`/v1/audio/speech` + `/v1/audio/transcriptions`）→ 小米 MIMO chat-completions 的翻译代理。Python 3.10+，零 Web 框架（stdlib `http.server`），依赖只有 `openai` SDK + `pyyaml`。

## 环境与运行

- **Python 环境**：conda env `mimo-tts-proxy`（`~/miniforge3/envs/mimo-tts-proxy`）。激活：`source ~/miniforge3/etc/profile.d/conda.sh && conda activate mimo-tts-proxy`
- **运行**：`python -m mimo_tts_proxy.app`（监听 `0.0.0.0:9880`）
- **测试**：`python -m pytest tests/ -v`（66 个，不需要 API key）
- **冒烟测试**：`python smoke_test.py`（需要 `MIMO_API_KEY`，会真实调用 MIMO）
- **部署**：`./deploy.sh`（自动检测 Docker / macOS launchd / Linux systemd）

## 关键事实

- **MIMO TTS 和 ASR 都走 `/v1/chat/completions`**，不是 OpenAI 的 audio 端点。这个代理的全部职责就是协议翻译。
- **TTS**：文字 → `assistant` 消息，风格 → `user` 消息，音色 → `audio.voice`（预置名或 `data:` URL）。返回 base64 WAV 在 `choices[0].message.audio.data`。见 `mimo.py`。
- **ASR**：音频 → base64 `input_audio` part（**不能带 text part**，MIMO 网关自己注入 prompt）。返回文字在 `choices[0].message.content`。见 `transcribe.py`。
- **鉴权**：`.env` 里的 `PROXY_API_KEY` 可选。设了 → 客户端必须 `Authorization: Bearer <key>`；没设 → 开放访问。
- **Key 读取**：`MIMO_API_KEY` 从 `.env` 读（`config.py:resolve_api_key`），env-var 作为 Docker fallback。`PROXY_API_KEY` 同理（`resolve_proxy_api_key`）。
- **音色**：`voices.yaml` 注册名 → 克隆样本或预置名。未注册的名直接当预置名透传。

## 代码结构与边界

| 模块 | 职责 |
|------|------|
| `app.py` | 入口：加载 config、组装 OpenAI client、启动 server |
| `config.py` | `config.yaml` + `.env` 读取 + 音色注册表 |
| `server.py` | HTTP 路由（`/health`、`/v1/audio/speech`、`/v1/audio/transcriptions`）+ multipart 解析 + 鉴权 |
| `mimo.py` | TTS：构造 chat-completions 请求 + 调用 |
| `transcribe.py` | ASR：构造 chat-completions 请求 + 调用 |
| `voices.py` | 音色解析（注册 → 克隆/预置） |
| `emotion.py` | LLM 情绪推断 + 风格提示拼接（仅 TTS 用） |
| `transcode.py` | ffmpeg 音频格式转换（WAV → mp3/opus/flac/aac/ogg/pcm） |

**边界规则**：
- 新增依赖要克制——目前只有 `openai` + `pyyaml`，其他都用 stdlib（multipart 用 `email.parser`，不用 `cgi` 或第三方库）。
- MIMO 调用逻辑集中在 `mimo.py`（TTS）和 `transcribe.py`（ASR），不要散到 `server.py`。
- HTTP handler 只做路由 + 请求解析 + 调用 handler 函数；业务逻辑在独立函数里（`handle_speech`、`handle_transcription`），方便单元测试。

## 测试约定

- `unittest` + `unittest.mock.MagicMock`，不引入 `pytest` 专用 fixture（虽然用 pytest 跑）。
- Mock `openai.Client`，不真实调用 MIMO API（除 `smoke_test.py`）。
- 每个模块对应一个 `tests/test_<module>.py`。
- 测试覆盖：请求构造、响应解析、边界情况（空输入、未知格式等）。

## 红线

- **不要把 MIMO API key 硬编码**到任何文件。只从 `.env` / 环境变量读。
- **不要在 ASR 请求里加 text part**——MIMO 网关会报 `ASR request must not include text parts`。
- **不要用 `cgi.FieldStorage`**——Python 3.13 已移除。multipart 用 `email.parser.BytesParser`。
- **改动 MIMO 调用格式后**，务必跑 `smoke_test.py` 验证——MIMO 的 API 契约文档不全，很多细节只能靠真实调用发现。

## 深入文档

- 设计 specs：`docs/superpowers/specs/`
- 实现 plans：`docs/superpowers/plans/`
- MIMO API 参考：[xiaomimimo.com](https://xiaomimimo.com)
