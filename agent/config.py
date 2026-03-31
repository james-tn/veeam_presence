"""Agent service configuration — Azure OpenAI settings."""

import os

AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_CHAT_DEPLOYMENT_NAME = os.environ.get(
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-5.3-chat"
)
AZURE_OPENAI_API_VERSION = os.environ.get(
    "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
)
