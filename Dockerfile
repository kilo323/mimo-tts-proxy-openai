FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

# Tarball URL (not git+) keeps the image free of a git install.
RUN pip install --no-cache-dir openai pyyaml \
    "mcp-auth @ https://github.com/Jedi-Pz/mcp-auth/archive/refs/heads/main.tar.gz"

EXPOSE 9880

CMD ["python", "-m", "mimo_tts_proxy.app"]
