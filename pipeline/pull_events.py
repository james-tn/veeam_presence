"""Step 1: Pull raw occupancy events and Workday data from Databricks.

Uses PowerShell subprocess for Databricks queries (the Windows HTTP stack
is required due to corporate network agent routing). Python handles all
analytics from step 2 onwards.
"""

import pandas as pd
import subprocess
import json
import tempfile
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def _run_ps_query(sql, label=""):
    """Execute SQL via PowerShell Invoke-RestMethod and return a DataFrame."""
    if label:
        print(f"  [{label}]", end=" ", flush=True)

    wh_id = config.DATABRICKS_HTTP_PATH.split("/")[-1]
    out_file = os.path.join(tempfile.gettempdir(), "dbx_query_result.json")

    ps_script = f'''
$token = "{config.DATABRICKS_TOKEN}"
$workspace = "https://{config.DATABRICKS_HOST}"
$wh = "{wh_id}"
$headers = @{{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }}
$out = "{out_file.replace(os.sep, '/')}"

$body = @{{ statement = @"
{sql}
"@; warehouse_id = $wh; wait_timeout = "0s" }} | ConvertTo-Json

$r = Invoke-RestMethod -Uri "$workspace/api/2.0/sql/statements" -Method POST -Headers $headers -Body $body -TimeoutSec 120
$sid = $r.statement_id

# Poll until complete
for ($i = 0; $i -lt 120; $i++) {{
    if ($r.status.state -eq "SUCCEEDED") {{ break }}
    if ($r.status.state -eq "FAILED") {{ throw "Query failed: $($r.status.error.message)" }}
    Start-Sleep -Seconds 2
    $r = Invoke-RestMethod -Uri "$workspace/api/2.0/sql/statements/$sid" -Method GET -Headers $headers
}}

if ($r.status.state -ne "SUCCEEDED") {{ throw "Query timed out" }}

$columns = $r.manifest.schema.columns | ForEach-Object {{ $_.name }}
$result = @{{ columns = $columns; rows = $r.result.data_array; row_count = $r.result.row_count }}

# Handle pagination
$next = $r.result.next_chunk_internal_link
while ($next) {{
    $chunk = Invoke-RestMethod -Uri "$workspace$next" -Method GET -Headers $headers
    $result.rows += $chunk.data_array
    $next = $chunk.next_chunk_internal_link
}}

$result | ConvertTo-Json -Depth 10 -Compress | Out-File $out -Encoding utf8
'''

    ps_file = os.path.join(tempfile.gettempdir(), "dbx_query.ps1")
    with open(ps_file, "w", encoding="utf-8") as f:
        f.write(ps_script)

    proc = subprocess.run(
        ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", ps_file],
        capture_output=True, text=True, timeout=600,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"PowerShell query failed: {proc.stderr[:500]}")

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    columns = data.get("columns", [])
    rows = data.get("rows", [])

    df = pd.DataFrame(rows, columns=columns)

    if label:
        print(f"{len(df):,} rows")

    # Cleanup
    for tmp in [ps_file, out_file]:
        try:
            os.remove(tmp)
        except OSError:
            pass

    return df


def pull_occupancy(weeks=None):
    """Pull raw occupancy events for the trailing N weeks."""
    weeks = weeks or config.PULL_WEEKS
    days = weeks * 7
    query = f"""SELECT userPrincipalName, source, timestamp, Office, offset, local_timestamp
FROM {config.OCCUPANCY_TABLE}
WHERE timestamp >= DATE_ADD(CURRENT_DATE(), -{days})"""

    df = _run_ps_query(query, f"Occupancy events (last {weeks} weeks)")

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

    return _run_ps_query(query, "Workday employees")


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
