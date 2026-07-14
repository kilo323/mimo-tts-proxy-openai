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
