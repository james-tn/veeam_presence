"""v1.5: Cross-functional mixing — are different teams overlapping in the same office?"""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_mixing(enriched_df):
    """
    Per office per day: how many different streams (Sales, R&D, G&A, etc.)
    have 2+ people present? Higher mixing = more cross-functional collision.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)]
    wdf = wdf[wdf["stream"].notna() & (wdf["stream"] != "Unknown")]

    results = {}

    for office_name, odf in wdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        # Count streams with 2+ people per day
        daily = odf.groupby(["date", "stream"])["email"].nunique().reset_index()
        daily = daily[daily["email"] >= 2]  # Only count streams with 2+ people
        daily_streams = daily.groupby("date")["stream"].nunique()

        max_streams = odf["stream"].nunique()
        avg_streams = round(daily_streams.mean(), 1) if len(daily_streams) > 0 else 0

        results[office_name] = {
            "streams_present": max_streams,
            "avg_streams_per_day": avg_streams,
            "mixing_score": round(avg_streams / max_streams, 2) if max_streams > 0 else 0,
        }

    print(f"  [Mixing] Computed for {len(results)} offices")
    for name, r in sorted(results.items(), key=lambda x: x[1]["mixing_score"], reverse=True)[:5]:
        print(f"    {name}: {r['avg_streams_per_day']}/{r['streams_present']} streams, score={r['mixing_score']}")

    return results
