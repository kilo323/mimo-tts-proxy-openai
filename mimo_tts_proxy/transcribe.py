"""ASR (speech-to-text) via MIMO chat completions.

MIMO's ``mimo-v2.5-asr`` model accepts a single base64-encoded ``input_audio``
part in a user-message content array, returning transcribed text in
``choices[0].message.content``. The gateway injects its own text prompt, so
the request must contain *only* the audio part — no text parts.
"""
import base64


def transcribe(client, audio_bytes, audio_format, model, language=None):
    """Transcribe audio using a MIMO ASR model.

    Args:
        client: ``openai.OpenAI`` instance (same as the TTS path).
        audio_bytes: Raw audio data.
        audio_format: Format string without dot prefix (``"wav"``, ``"mp3"``,
            ``"flac"``, etc.).
        model: ASR model name, e.g. ``"mimo-v2.5-asr"``.
        language: Optional ISO-639-1 code. Currently ignored — the MIMO gateway
            injects its own prompt and handles language detection. Accepted
            for API compatibility with the OpenAI transcriptions interface.

    Returns:
        The transcribed text string.
    """
    encoded = base64.b64encode(audio_bytes).decode("ascii")

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": encoded, "format": audio_format},
                    },
                ],
            }
        ],
    )
    return completion.choices[0].message.content
