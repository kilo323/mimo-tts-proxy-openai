#!/usr/bin/env python3
"""End-to-end smoke test for the MIMO TTS proxy.

Starts the proxy server, sends two /v1/audio/speech requests (a cloned voice
with emotion inference, and a preset voice), verifies the responses are valid
audio, and prints the result. Requires MIMO_API_KEY in the environment.

Run with the project env python:
    /Users/pz/miniforge3/envs/mimo-tts-proxy/bin/python smoke_test.py
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

from mimo_tts_proxy.config import BASE_DIR, _read_dotenv_key, _read_dotenv_value

BASE_URL = "http://127.0.0.1:9880"


def load_smoke_test_env():
    dotenv_path = os.environ.get("MIMO_TTS_PROXY_DOTENV", str(BASE_DIR / ".env"))
    mimo_api_key = _read_dotenv_key(dotenv_path) or os.environ.get("MIMO_API_KEY")
    proxy_api_key = _read_dotenv_value(dotenv_path, "PROXY_API_KEY") or os.environ.get(
        "PROXY_API_KEY"
    )
    return mimo_api_key, proxy_api_key


def wait_for_server(proc, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False, "server process exited"
        try:
            with urllib.request.urlopen(BASE_URL + "/health", timeout=2) as r:
                if r.status == 200:
                    return True, None
        except Exception:
            time.sleep(0.5)
    return False, "timed out waiting for /health"


def speech(body, proxy_api_key=None):
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if proxy_api_key:
        headers["Authorization"] = f"Bearer {proxy_api_key}"
    else:
        headers["Authorization"] = "Bearer smoke"
    req = urllib.request.Request(
        BASE_URL + "/v1/audio/speech",
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def verify_audio(path, fmt):
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", path],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0
    head = open(path, "rb").read(12)
    if fmt == "wav":
        return head[:4] == b"RIFF"
    if fmt == "mp3":
        return head[:3] == b"ID3" or (head[0] & 0xFF) == 0xFF
    return len(head) > 0


def transcribe(filepath, language=None, proxy_api_key=None):
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

    headers = {
        "Content-Type": 'multipart/form-data; boundary="{b}"'.format(b=boundary),
    }
    if proxy_api_key:
        headers["Authorization"] = f"Bearer {proxy_api_key}"
    else:
        headers["Authorization"] = "Bearer smoke"

    req = urllib.request.Request(
        BASE_URL + "/v1/audio/transcriptions",
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def main():
    mimo_api_key, proxy_api_key = load_smoke_test_env()
    if not mimo_api_key:
        print("MIMO_API_KEY not set; cannot run smoke test", file=sys.stderr)
        return 1

    proc = subprocess.Popen(
        [sys.executable, "-m", "mimo_tts_proxy.app"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        ok, reason = wait_for_server(proc)
        if not ok:
            out = proc.stdout.read().decode("utf-8", "ignore") if proc.stdout else ""
            print(f"server did not come up ({reason}):\n{out}", file=sys.stderr)
            return 1
        print("server is up at", BASE_URL)

        # 1) cloned voice + emotion inference -> mp3
        status, ctype, audio = speech(
            {
                "model": "tts-1",
                "input": "哇，今天天气真好，我们一起出去玩吧！",
                "voice": "zhuangfangyi",
                "response_format": "mp3",
            },
            proxy_api_key=proxy_api_key,
        )
        assert status == 200, f"clone: status {status}"
        assert ctype == "audio/mpeg", f"clone: content-type {ctype}"
        assert len(audio) > 2000, f"clone: audio too small ({len(audio)} bytes)"
        path1 = "/tmp/mimo_proxy_smoke_clone.mp3"
        open(path1, "wb").write(audio)
        assert verify_audio(path1, "mp3"), "clone: invalid audio"
        print(f"[clone ] {len(audio)} bytes  {ctype}  -> {path1}")

        # 2) preset voice -> wav
        status, ctype, audio = speech(
            {
                "model": "tts-1",
                "input": "你好，这是预置音色测试。",
                "voice": "bingtang",
                "response_format": "wav",
            },
            proxy_api_key=proxy_api_key,
        )
        assert status == 200, f"preset: status {status}"
        assert ctype == "audio/wav", f"preset: content-type {ctype}"
        path2 = "/tmp/mimo_proxy_smoke_preset.wav"
        open(path2, "wb").write(audio)
        assert verify_audio(path2, "wav"), "preset: invalid audio"
        print(f"[preset] {len(audio)} bytes  {ctype}  -> {path2}")

        # 3) ASR transcription — send a WAV file and verify text comes back
        # Use one of the TTS output files as test audio (it contains speech)
        asr_file = path2  # the preset WAV from step 2
        status, ctype, text_bytes = transcribe(
            asr_file,
            proxy_api_key=proxy_api_key,
        )
        assert status == 200, f"asr: status {status}"
        text = json.loads(text_bytes.decode("utf-8"))["text"]
        assert len(text) > 0, "asr: empty transcription"
        print(f"[asr   ] {len(text)} chars  -> {text[:80]}")

        print("\nSMOKE TEST PASSED")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
