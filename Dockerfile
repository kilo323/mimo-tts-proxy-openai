FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY mimo_tts_proxy /app/mimo_tts_proxy
COPY config.yaml voices.yaml /app/
COPY samples /app/samples

RUN pip install --no-cache-dir openai pyyaml

EXPOSE 9880

CMD ["python", "-m", "mimo_tts_proxy.app"]
