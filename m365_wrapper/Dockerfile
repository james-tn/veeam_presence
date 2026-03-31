FROM python:3.12-slim

WORKDIR /app

# Install wrapper dependencies
COPY m365_wrapper/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY m365_wrapper/ ./m365_wrapper/
COPY shared/ ./shared/

EXPOSE 3978

CMD ["python", "-m", "m365_wrapper.server"]
