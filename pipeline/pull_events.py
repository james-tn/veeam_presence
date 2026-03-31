"""Step 1: Pull raw occupancy events and Workday data from Databricks.

Uses the Databricks SQL Statement Execution API with Entra ID (MSI) authentication.
On Azure Container Apps, DefaultAzureCredential uses the system-assigned managed identity.
Locally, it falls back to Azure CLI credentials.
"""

import pandas as pd
import requests
import json
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def _get_databricks_token():
    """Get an Entra ID access token for Databricks using DefaultAzureCredential."""
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    # The resource ID for Databricks is "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
    # (the well-known Databricks Azure AD application ID)
    token = credential.get_token("2ff814a6-3304-4ab8-85cb-cd0e6f879c1d/.default")
    return token.token


def _run_query(sql, label=""):
    """Execute SQL via the Databricks SQL Statement Execution API and return a DataFrame."""
    if label:
        print(f"  [{label}]", end=" ", flush=True)

    host = config.DATABRICKS_HOST.rstrip("/")
    if not host.startswith("https://"):
        host = f"https://{host}"

    warehouse_id = config.DATABRICKS_WAREHOUSE_ID
    token = _get_databricks_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Submit query
    resp = requests.post(
        f"{host}/api/2.0/sql/statements",
        headers=headers,
        json={"statement": sql, "warehouse_id": warehouse_id, "wait_timeout": "0s"},
        timeout=120,
    )
    resp.raise_for_status()
    result = resp.json()
    statement_id = result["statement_id"]

    # Poll until complete
    for _ in range(120):
        state = result.get("status", {}).get("state", "")
        if state == "SUCCEEDED":
            break
        if state == "FAILED":
            error_msg = result.get("status", {}).get("error", {}).get("message", "Unknown error")
            raise RuntimeError(f"Query failed: {error_msg}")
        time.sleep(2)
        resp = requests.get(
            f"{host}/api/2.0/sql/statements/{statement_id}",
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

    if result.get("status", {}).get("state") != "SUCCEEDED":
        raise RuntimeError("Query timed out")

    columns = [col["name"] for col in result["manifest"]["schema"]["columns"]]
    rows = result.get("result", {}).get("data_array", [])

    # Handle pagination
    next_link = result.get("result", {}).get("next_chunk_internal_link")
    while next_link:
        resp = requests.get(f"{host}{next_link}", headers=headers, timeout=30)
        resp.raise_for_status()
        chunk = resp.json()
        rows.extend(chunk.get("data_array", []))
        next_link = chunk.get("next_chunk_internal_link")

    df = pd.DataFrame(rows, columns=columns)

    if label:
        print(f"{len(df):,} rows")

    return df


def pull_occupancy(weeks=None):
    """Pull raw occupancy events for the trailing N weeks."""
    weeks = weeks or config.PULL_WEEKS
    days = weeks * 7
    query = f"""SELECT userPrincipalName, source, timestamp, Office, offset, local_timestamp
FROM {config.OCCUPANCY_TABLE}
WHERE timestamp >= DATE_ADD(CURRENT_DATE(), -{days})"""

    df = _run_query(query, f"Occupancy events (last {weeks} weeks)")

    # Type conversions (REST API returns strings)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["local_timestamp"] = pd.to_datetime(df["local_timestamp"])
    df["offset"] = pd.to_numeric(df["offset"], errors="coerce").fillna(0).astype(int)

    return df


def pull_workday():
    """Pull Workday employee data."""
    query = f"""SELECT email, preferred_name, stream, job_family, job_family_group,
    management_level, ismanager, manager_name, manager_id,
    supervisory_organization, hire_date, original_hire_date,
    worker_status, VX_Hierarchy, location_hierarchy_region,
    businesstitle, country, Employee_ID
FROM {config.WORKDAY_TABLE}"""

    return _run_query(query, "Workday employees")


if __name__ == "__main__":
    print("Pulling data from Databricks...")
    occ = pull_occupancy()
    wd = pull_workday()
    print(f"\nOccupancy: {len(occ):,} events, {occ['userPrincipalName'].nunique():,} people")
    print(f"Workday:   {len(wd):,} employees")
    os.makedirs(config.DATA_DIR, exist_ok=True)
    occ.to_pickle(os.path.join(config.DATA_DIR, "raw_events.pkl"))
    wd.to_pickle(os.path.join(config.DATA_DIR, "workday.pkl"))
    print(f"Saved to {config.DATA_DIR}/")
