"""v1.5: New hire integration curves — are recent hires establishing office rhythm?"""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_new_hire_integration(enriched_df):
    """
    For people hired in the last 6 months: track their weekly attendance
    by tenure week. Are they ramping up (healthy) or fading out (concerning)?
    """
    df = enriched_df.copy()
    today = df["date"].max()
    six_months_ago = today - pd.Timedelta(days=180)

    # Filter to matched employees with recent hire dates
    recent_hires = df[
        (df["hire_date"].notna()) &
        (df["hire_date"] >= six_months_ago) &
        (df["dow"] <= 4) &
        (df["workday_matched"] == True)
    ].copy()

    if len(recent_hires) == 0:
        print("  [New Hires] No recent hires with attendance data")
        return {"per_office": {}, "people": []}

    # Compute tenure week for each person-day
    recent_hires["tenure_days"] = (recent_hires["date"] - recent_hires["hire_date"]).dt.days
    recent_hires["tenure_week"] = recent_hires["tenure_days"] // 7

    # Per-person summary
    people = []
    for email, pdf in recent_hires.groupby("email"):
        name = pdf["preferred_name"].iloc[0] if pd.notna(pdf["preferred_name"].iloc[0]) else email
        office = pdf["office"].mode().iloc[0] if len(pdf["office"].mode()) > 0 else "Unknown"
        role = pdf["stream"].iloc[0] if pd.notna(pdf.get("stream", pd.Series()).iloc[0] if len(pdf) > 0 else None) else "Unknown"
        hire_date = pdf["hire_date"].iloc[0]

        # Weekly attendance by tenure week
        weekly = pdf.groupby("tenure_week")["date"].nunique()
        if len(weekly) < 2:
            continue

        # Trend: first half vs second half
        mid = len(weekly) // 2
        first_half = weekly.head(mid).mean() if mid > 0 else 0
        second_half = weekly.tail(mid).mean() if mid > 0 else 0

        if second_half > first_half + 0.3:
            trend = "ramping up"
        elif second_half < first_half - 0.3:
            trend = "fading"
        else:
            trend = "steady"

        people.append({
            "name": name,
            "office": office,
            "role": role,
            "hire_date": str(hire_date.date()) if pd.notna(hire_date) else "unknown",
            "weeks_tracked": len(weekly),
            "avg_days_per_week": round(weekly.mean(), 1),
            "trend": trend,
        })

    # Per-office summary
    per_office = {}
    for p in people:
        office = p["office"]
        if office not in per_office:
            per_office[office] = {"total": 0, "ramping_up": 0, "steady": 0, "fading": 0}
        per_office[office]["total"] += 1
        trend_key = p["trend"].replace(" ", "_")
        if trend_key in per_office[office]:
            per_office[office][trend_key] += 1

    print(f"  [New Hires] {len(people)} recent hires tracked across {len(per_office)} offices")
    for office, counts in sorted(per_office.items()):
        print(f"    {office}: {counts['total']} hires — {counts.get('ramping_up', 0)} ramping, {counts.get('steady', 0)} steady, {counts.get('fading', 0)} fading")

    return {"per_office": per_office, "people": people}
