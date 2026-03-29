FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY config.py .
COPY app.py .
COPY agent.py .
COPY system_prompt.py .
COPY pipeline/ pipeline/
COPY tools/ tools/
COPY cards/ cards/

# Create data directory (populated by pipeline job or mounted volume)
RUN mkdir -p data output

# Expose agent service port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
