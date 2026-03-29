"""Veeam Presence — Analytics Pipeline (Steps 2-6).

Reads raw JSON from PowerShell data pull, runs all analytics.
Designed to run after run_pipeline.ps1 has pulled data from Databricks.
"""

import os, sys, time, json, pickle
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

from aggregate import aggregate_person_day
from enrich import enrich_with_workday
from baselines import compute_baselines
from personality import compute_personality
from anchors import compute_anchors


def load_json_data(filepath, label=""):
    """Load data from JSON file written by PowerShell."""
    if label:
        print(f"  [Loading {label}]", end=" ", flush=True)
    with open(filepath, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    columns = data["columns"]
    rows = data["rows"]
    df = pd.DataFrame(rows, columns=columns)
    if label:
        print(f"{len(df):,} rows")
    return df


def run_analytics():
    start = time.time()
    data_dir = config.DATA_DIR

    print("=" * 60)
    print("VEEAM PRESENCE — Analytics Pipeline")
    print("=" * 60)

    # Load raw data from JSON
    print("\n[Loading] Raw data from PowerShell pull...")
    events_file = os.path.join(data_dir, "raw_events.json")
    workday_file = os.path.join(data_dir, "workday.json")

    if not os.path.exists(events_file):
        print(f"ERROR: {events_file} not found. Run run_pipeline.ps1 first.")
        sys.exit(1)

    events = load_json_data(events_file, "Occupancy events")
    workday = load_json_data(workday_file, "Workday")

    # Type conversions for events
    events["timestamp"] = pd.to_datetime(events["timestamp"])
    events["local_timestamp"] = pd.to_datetime(events["local_timestamp"])
    events["offset"] = pd.to_numeric(events["offset"], errors="coerce").fillna(0).astype(int)

    print(f"    Events: {len(events):,}, People: {events['userPrincipalName'].nunique():,}")
    print(f"    Workday: {len(workday):,} employees")

    # Step 2: Aggregate
    print("\n[Step 2] Aggregating to person-day...")
    person_day = aggregate_person_day(events)

    # Step 3: Enrich
    print("\n[Step 3] Enriching with Workday...")
    enriched = enrich_with_workday(person_day, workday)

    # Save enriched for tool queries
    enriched.to_pickle(os.path.join(data_dir, "enriched.pkl"))

    # Step 4: Baselines
    print("\n[Step 4] Computing baselines...")
    baselines = compute_baselines(enriched)
    with open(os.path.join(data_dir, "baselines.pkl"), "wb") as f:
        pickle.dump(baselines, f)

    # Step 5: Personality profiles
    print("\n[Step 5] Computing office personality profiles...")
    profiles = compute_personality(enriched, baselines)
    with open(os.path.join(data_dir, "personality.pkl"), "wb") as f:
        pickle.dump(profiles, f)

    # Step 6: Anchors and leaderboards
    print("\n[Step 6] Computing anchors and leaderboards...")
    anchors_data = compute_anchors(enriched)
    with open(os.path.join(data_dir, "anchors.pkl"), "wb") as f:
        pickle.dump(anchors_data, f)

    # Summary
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print(f"Analytics complete in {elapsed:.0f}s")
    print(f"  Person-days: {len(person_day):,}")
    print(f"  Offices: {len(baselines)}")
    print(f"  Data dir: {data_dir}")
    print("=" * 60)


if __name__ == "__main__":
    run_analytics()
