#!/usr/bin/env python3
"""Interactive test client for the OpenAI-compatible /v1/audio/speech endpoint.

This script reads PROXY_API_KEY from the project's .env file, prompts for
voice and message, then sends a speech request and saves the returned audio.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_ENV_PATH = REPO_ROOT / ".env"
DEFAULT_VOICES_PATH = REPO_ROOT / "voices.yaml"
DEFAULT_ENDPOINT = "http://127.0.0.1:9880/v1/audio/speech"


def read_dotenv_value(env_path: Path, key_name: str) -> str | None:
    prefix = key_name + "="
    if not env_path.exists():
        return None
    with env_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(prefix):
                value = line.split("=", 1)[1].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                return value or None
    return None


def sanitize_filename_part(value: str) -> str:
    sanitized = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in value)
    sanitized = sanitized.strip("-")
    return sanitized or "voice"


def build_output_path(output: str | None, response_format: str, voice: str) -> Path:
    if output:
        return Path(output)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    voice_part = sanitize_filename_part(voice)
    return REPO_ROOT / f"speech-test-{voice_part}-{ts}.{response_format}"


def load_voice_names(voices_path: Path) -> list[str]:
    if not voices_path.exists():
        return []
    names: list[str] = []
    in_voices = False
    with voices_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if not in_voices:
                if stripped == "voices:":
                    in_voices = True
                continue

            if not line.startswith("  "):
                break
            if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
                names.append(stripped[:-1])

    return sorted(names)


def prompt_voice(voice_names: list[str]) -> str:
    if not voice_names:
        return prompt_non_empty("Voice: ")

    print("Available voices:")
    for idx, name in enumerate(voice_names, start=1):
        print(f"  {idx}. {name}")

    while True:
        raw = input("Select voice number (or type voice name): ").strip()
        if not raw:
            print("Value is required. Please try again.")
            continue
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(voice_names):
                return voice_names[choice - 1]
            print(f"Invalid choice: {choice}. Enter 1-{len(voice_names)}.")
            continue
        return raw


def prompt_non_empty(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("Value is required. Please try again.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactive test for OpenAI-compatible /v1/audio/speech"
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=f"Speech endpoint URL (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--format",
        default="mp3",
        choices=["mp3", "wav", "opus", "ogg", "flac", "aac", "pcm"],
        help="response_format to request (default: mp3)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output audio file path (default: speech-test-<timestamp>.<format>)",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help=f"Path to .env file (default: {DEFAULT_ENV_PATH})",
    )
    parser.add_argument(
        "--voices-file",
        default=str(DEFAULT_VOICES_PATH),
        help=f"Path to voices.yaml (default: {DEFAULT_VOICES_PATH})",
    )
    args = parser.parse_args()

    env_path = Path(args.env_file)
    proxy_api_key = read_dotenv_value(env_path, "PROXY_API_KEY")
    if not proxy_api_key:
        print(
            f"PROXY_API_KEY not found in {env_path}. "
            "Add PROXY_API_KEY=<your-key> to .env and retry.",
            file=sys.stderr,
        )
        return 1

    print(f"Endpoint: {args.endpoint}")
    print("Enter request data:")
    voice_names = load_voice_names(Path(args.voices_file))
    voice = prompt_voice(voice_names)
    message = prompt_non_empty("Message: ")

    payload = {
        "model": "tts-1",
        "input": message,
        "voice": voice,
        "response_format": args.format,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        args.endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {proxy_api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            audio = resp.read()
            content_type = resp.headers.get("Content-Type", "unknown")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        print(f"Request failed: HTTP {e.code}", file=sys.stderr)
        print(err_body, file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"Request failed: {e.reason}", file=sys.stderr)
        return 1

    output_path = build_output_path(args.output, args.format, voice)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(audio)

    print("\nRequest succeeded.")
    print(f"Content-Type: {content_type}")
    print(f"Bytes: {len(audio)}")
    print(f"Saved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
