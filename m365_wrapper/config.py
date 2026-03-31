"""Configuration for the M365 wrapper service."""

from __future__ import annotations

import os

from microsoft_agents.authentication.msal import MsalConnectionManager
from microsoft_agents.hosting.core import AgentAuthConfiguration, AuthHandler, AuthTypes


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required.")
    return value


def get_bot_app_id() -> str:
    return _required("BOT_APP_ID")


def get_bot_app_password() -> str:
    return _required("BOT_APP_PASSWORD")


def get_presence_service_base_url() -> str:
    return os.environ.get("PRESENCE_SERVICE_BASE_URL", "http://localhost:8000").rstrip("/")


def get_wrapper_ack_threshold_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("WRAPPER_LONG_RUNNING_ACK_THRESHOLD_SECONDS", "10")))
    except ValueError:
        return 10.0


def get_wrapper_timeout_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("WRAPPER_FORWARD_TIMEOUT_SECONDS", "300")))
    except ValueError:
        return 300.0


def get_port() -> int:
    try:
        return int(os.environ.get("PORT", "3978"))
    except ValueError:
        return 3978


def build_connection_manager() -> MsalConnectionManager:
    tenant_id = _required("AZURE_TENANT_ID")
    bot_app_id = get_bot_app_id()
    bot_app_password = get_bot_app_password()

    service_connection = AgentAuthConfiguration(
        auth_type=AuthTypes.client_secret,
        connection_name="SERVICE_CONNECTION",
        tenant_id=tenant_id,
        client_id=bot_app_id,
        client_secret=bot_app_password,
    )

    return MsalConnectionManager(
        connections_configurations={"SERVICE_CONNECTION": service_connection}
    )


def build_auth_handlers() -> dict[str, AuthHandler]:
    return {
        "presence_connector": AuthHandler(
            name="presence_connector",
            title="Sign in to Veeam Presence",
            text="Sign in",
            abs_oauth_connection_name="SERVICE_CONNECTION",
            obo_connection_name="",
            auth_type="UserAuthorization",
            scopes=[],
        ),
    }
