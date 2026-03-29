FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir botbuilder-core botbuilder-integration-aiohttp aiohttp

COPY app.py .

EXPOSE 3978

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3978/health')" || exit 1

CMD ["python", "app.py"]
