"""Step 2: Aggregate raw events to person-day level."""

import pandas as pd
import numpy as np


def aggregate_person_day(events_df):
    """
    From raw events, compute one row per person per day:
      - arrival (first O365 event, local time)
      - departure (last O365 event, local time)
      - dwell_hours (departure - arrival)
      - office (most frequent office that day)
      - has_o365, has_verkada (source flags)
      - event_count (raw count, for reference only)
    """
    df = events_df.copy()

    # Ensure timestamps are datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["local_timestamp"] = pd.to_datetime(df["local_timestamp"])

    # Extract date from local_timestamp (the person's local date)
    df["date"] = df["local_timestamp"].dt.date

    # Lowercase email for consistent joining
    df["email"] = df["userPrincipalName"].str.lower()

    # --- Per person-day aggregation ---
    # Use ALL sources for arrival/departure. Some offices (Prague, etc.)
    # are primarily Verkada — O365-only dwell would return 0 for them.
    # The full-source dwell was validated at 5-6h median across offices.
    agg = df.groupby(["email", "date"]).agg(
        office=("Office", lambda x: x.mode().iloc[0] if len(x.mode()) > 0 else x.iloc[0]),
        arrival=("local_timestamp", "min"),
        departure=("local_timestamp", "max"),
        has_o365=("source", lambda x: (x == "O365").any()),
        has_verkada=("source", lambda x: (x == "Verkada").any()),
        event_count=("source", "count"),
    ).reset_index()

    # Compute dwell hours (meaningful when 2+ events from any source)
    agg["dwell_hours"] = (
        (agg["departure"] - agg["arrival"]).dt.total_seconds() / 3600.0
    ).round(2)
    # Single-event days get dwell = 0
    agg.loc[agg["event_count"] <= 1, "dwell_hours"] = 0.0

    # Arrival / departure as time-of-day (hours, decimal)
    agg["arrival_hour"] = agg["arrival"].dt.hour + agg["arrival"].dt.minute / 60.0
    agg["departure_hour"] = agg["departure"].dt.hour + agg["departure"].dt.minute / 60.0

    # Day of week (0=Mon, 6=Sun)
    agg["dow"] = pd.to_datetime(agg["date"]).dt.dayofweek
    agg["dow_name"] = pd.to_datetime(agg["date"]).dt.day_name()

    # Convert date to proper date type
    agg["date"] = pd.to_datetime(agg["date"])

    # --- Exclude partial-ingestion WEEKDAYS ---
    # A partial weekday has < 20% of the median weekday headcount.
    # These are pipeline artifacts (data hasn't fully landed yet).
    # Weekends are kept as-is (low headcount is expected).
    weekday_data = agg[agg["dow"] <= 4]
    weekday_totals = weekday_data.groupby("date")["email"].nunique()
    median_weekday = weekday_totals.median()
    partial_threshold = median_weekday * 0.20
    partial_days = weekday_totals[weekday_totals < partial_threshold].index
    if len(partial_days) > 0:
        agg = agg[~agg["date"].isin(partial_days)]
        print(f"  [Aggregate] Excluded {len(partial_days)} partial-ingestion weekdays "
              f"(headcount < {partial_threshold:.0f}): {[str(d.date()) for d in partial_days]}")

    print(f"  [Aggregate] {len(agg):,} person-days from {len(events_df):,} events")
    print(f"    People: {agg['email'].nunique():,} | Offices: {agg['office'].nunique()}")
    print(f"    Date range: {agg['date'].min().date()} to {agg['date'].max().date()}")
    dwell_valid = agg.loc[agg["event_count"] >= 2, "dwell_hours"]
    median_dwell = dwell_valid.median() if len(dwell_valid) > 0 else 0
    print(f"    Median dwell (2+ O365 events): {median_dwell:.1f}h")

    return agg


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    import config

    events = pd.read_pickle(os.path.join(config.DATA_DIR, "raw_events.pkl"))
    person_day = aggregate_person_day(events)
    person_day.to_pickle(os.path.join(config.DATA_DIR, "person_day.pkl"))
    print(f"  Saved to {config.DATA_DIR}/person_day.pkl")
