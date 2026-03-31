FROM python:3.12-slim

WORKDIR /app

# Install agent service dependencies
COPY agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/ ./agent/
COPY tools/ ./tools/
COPY cards/ ./cards/
COPY config.py ./config.py
COPY system_prompt.py ./system_prompt.py
COPY response_cache.py ./response_cache.py
COPY pipeline/holidays_cal.py ./pipeline/holidays_cal.py
COPY pipeline/__init__.py ./pipeline/__init__.py

# Copy data (baked into image for R1)
COPY data/ ./data/

EXPOSE 8000

CMD ["python", "-m", "agent.server"]
