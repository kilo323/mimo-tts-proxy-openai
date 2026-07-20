# MIMO TTS Proxy — 新增 ASR（OpenAI `/v1/audio/transcriptions`）

日期: 2026-07-12
状态: approved

## 动机

当前 proxy 实现了 OpenAI `/v1/audio/speech` → MIMO TTS 的翻译层，让 Agent 可以"说话"。
需要补上"听懂"——实现 OpenAI `/v1/audio/transcriptions` → MIMO ASR 的翻译层，
让同一个 proxy 成为 Agent 的完整语音通道（耳朵 + 嘴巴）。

## 设计

### 新增文件: `mimo_tts_proxy/transcribe.py`

- `transcribe(client, audio_bytes, audio_format) -> str`
- 将 audio bytes 编码为 base64 data URL（`data:audio/{fmt};base64,...`）
- 构造 chat completions 请求，model=`mimo-v2.5-asr`，messages 包含一个 user message，
  content 为多 part 数组：text prompt + audio_url blob
- 从 `choices[0].message.content` 提取转写文本返回

### 修改文件: `mimo_tts_proxy/server.py`

- 在 `do_POST` 中新增路由 `/v1/audio/transcriptions`
- 解析 `multipart/form-data`（使用标准库 `cgi` 或 `email` 模块，零新依赖）
- 提取 `file` 字段（必填）、`language`（可选）、`response_format`（可选，默认 "json"）
- 调用 `transcribe()`，按 OpenAI 格式返回：`{"text": "..."}`
- 鉴权复用现有 `check_auth()` 逻辑

### 修改文件: `config.yaml`

- 新增 `mimo.asr_model: "mimo-v2.5-asr"`

### 修改文件: `mimo_tts_proxy/config.py`

- `load_config()` 确保 parsed config 包含 `mimo.asr_model` 默认值

### 新增文件: `tests/test_transcribe.py`

- Mock openai client，验证 `transcribe()` ：
  - 构造正确的 chat completion payload（model、多 part content）
  - base64 data URL 格式正确
  - 正确提取 `message.content` 返回

### 修改文件: `tests/test_server.py`

- 新增 test: `POST /v1/audio/transcriptions` multipart 请求
  - 200 + `{"text": "..."}`
  - 400 缺少 file
  - 401 鉴权失败
  - `response_format=text` 返回纯文本

## 不从这次做的东西

- 不实现 `/v1/audio/translations`（English-only translation 端点）—— 等有需求再说
- 本地 Whisper/开源 ASR 不在 scope 内
- Agent 端配置（Client 侧，与 proxy 实现无关）

## 架构约束

- 零新依赖，只用 stdlib + `openai` SDK（项目已有）
- 复用 `openai.Client` 实例和 MIMO 鉴权（`api-key` header）
- 和 TTS 路径对称：OpenAI 标准端点 → 翻译 → MIMO chat completions
- Python 3.12+，conda env `mimo-tts-proxy`
- 项目已有 30 个测试，保持全绿
