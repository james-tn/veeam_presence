"""v1.5: Seniority band breakdowns per office + org leader rollups."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_seniority(enriched_df):
    """
    Per office: IC / Manager / Senior Leader attendance breakdowns.
    Plus: org leader rollups using CF_EE_Org_Leader hierarchy.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)]

    # --- Seniority breakdowns per office ---
    office_seniority = {}
    for office_name, odf in wdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        bands = {}
        for band, bdf in odf.groupby("seniority_band"):
            if band in (None, "", "Unknown"):
                continue
            people = bdf["email"].nunique()
            days = bdf.groupby("email")["date"].nunique()
            avg_days = round(days.mean(), 1) if len(days) > 0 else 0
            bands[band] = {
                "people": people,
                "avg_days_per_week": round(avg_days / max(1, config.BASELINE_WEEKS), 1),
                "total_person_days": int(days.sum()),
            }

        office_seniority[office_name] = bands

    # --- Org leader rollups ---
    # Use CF_EE_Org_Leader_1 (top-level) and _2 (second level)
    org_leaders = {}

    # Find the org leader columns available
    leader_cols = [c for c in df.columns if c.startswith("CF_EE_Org_Leader_")]
    if not leader_cols:
        print("  [Seniority] No org leader columns found — skipping rollups")
        return {"office_seniority": office_seniority, "org_leaders": {}}

    # We need the Workday data for org leader fields
    # They're already in enriched via the join, but only for matched records
    matched = wdf[wdf["workday_matched"] == True] if "workday_matched" in wdf.columns else wdf

    for level_col in ["CF_EE_Org_Leader_1", "CF_EE_Org_Leader_2"]:
        if level_col not in matched.columns:
            continue

        level_name = "L1" if "1" in level_col else "L2"

        for leader, ldf in matched.groupby(level_col):
            if pd.isna(leader) or str(leader).strip() == "":
                continue

            # Extract leader name from format: "Name (EID)" or "Division (Name) (EID)"
            leader_str = str(leader)
            people = ldf["email"].nunique()
            offices = ldf["office"].nunique()
            top_offices = ldf.groupby("office")["email"].nunique().nlargest(3)

            # Average attendance
            person_weeks = ldf.groupby("email").apply(
                lambda x: x["date"].nunique() / max(1, config.BASELINE_WEEKS)
            )
            avg_days_per_week = round(person_weeks.mean(), 1) if len(person_weeks) > 0 else 0

            org_leaders[f"{level_name}:{leader_str}"] = {
                "level": level_name,
                "leader": leader_str,
                "people": people,
                "offices": offices,
                "avg_days_per_week": avg_days_per_week,
                "top_offices": {str(k): int(v) for k, v in top_offices.items()},
            }

    print(f"  [Seniority] {len(office_seniority)} offices with band breakdowns")
    print(f"  [Org Leaders] {len(org_leaders)} leader rollups")

    return {"office_seniority": office_seniority, "org_leaders": org_leaders}
