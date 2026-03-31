"""v1.5: Weekend and after-hours attendance tracking."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_weekend(enriched_df):
    """
    Track weekend (Sat/Sun) attendance per office.
    Who's coming in on weekends, how many, is it growing?
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    wdf = df[(df["date"] >= window_start) & (df["dow"] >= 5)]  # Sat=5, Sun=6

    if len(wdf) == 0:
        print("  [Weekend] No weekend attendance data")
        return {"offices": {}, "total_weekend_people": 0}

    results = {}

    for office_name, odf in wdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        people = odf["email"].nunique()
        total_days = odf.groupby("date")["email"].nunique()
        avg_per_day = round(total_days.mean(), 1) if len(total_days) > 0 else 0

        # Who comes in most on weekends
        top_weekend = odf.groupby("email").agg(
            days=("date", "nunique"),
            name=("preferred_name", "first"),
            role=("stream", "first"),
        ).reset_index().sort_values("days", ascending=False).head(5)

        # Trend: recent 4 weeks vs prior 4 weeks
        mid = today - pd.Timedelta(weeks=4)
        recent = odf[odf["date"] >= mid]["email"].nunique()
        prior = odf[odf["date"] < mid]["email"].nunique()

        if recent > prior + 2:
            trend = "increasing"
        elif recent < prior - 2:
            trend = "decreasing"
        else:
            trend = "stable"

        results[office_name] = {
            "weekend_people": people,
            "avg_per_weekend_day": avg_per_day,
            "trend": trend,
            "top_weekend_people": [
                {"name": r["name"] if pd.notna(r["name"]) else r["email"],
                 "role": r["role"] if pd.notna(r["role"]) else "",
                 "days": int(r["days"])}
                for _, r in top_weekend.iterrows()
            ],
        }

    total = sum(r["weekend_people"] for r in results.values())
    print(f"  [Weekend] {total} people across {len(results)} offices on weekends")

    return {"offices": results, "total_weekend_people": total}
