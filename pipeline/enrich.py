"""Step 3: Enrich person-day data with Workday (role, team, seniority, name)."""

import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def enrich_with_workday(person_day_df, workday_df):
    """
    LEFT JOIN person-day to Workday on email.
    Applies stream fallback mapping and seniority band assignment.
    """
    wd = workday_df.copy()
    wd["email"] = wd["email"].str.lower()

    # Select the columns we need from Workday
    wd_cols = wd[[
        "email", "preferred_name", "stream", "job_family", "job_family_group",
        "management_level", "ismanager", "manager_name", "manager_id",
        "supervisory_organization", "hire_date", "original_hire_date",
        "worker_status", "VX_Hierarchy", "businesstitle", "Employee_ID",
    ]].copy()

    # Deduplicate Workday (should be ~1:1 but just in case)
    wd_cols = wd_cols.drop_duplicates(subset=["email"], keep="first")

    # --- Stream fallback for blank/null stream ---
    mask_blank = wd_cols["stream"].isna() | (wd_cols["stream"] == "")
    wd_cols.loc[mask_blank, "stream"] = wd_cols.loc[mask_blank, "job_family_group"].map(
        config.STREAM_FALLBACK
    )
    # Any remaining blanks after fallback → "Unknown"
    wd_cols.loc[wd_cols["stream"].isna() | (wd_cols["stream"] == ""), "stream"] = "Unknown"

    # --- Seniority band from management_level ---
    wd_cols["seniority_band"] = wd_cols["management_level"].map(config.SENIORITY_BANDS)
    wd_cols.loc[wd_cols["seniority_band"].isna(), "seniority_band"] = "Unknown"

    # --- Join ---
    enriched = person_day_df.merge(wd_cols, on="email", how="left")

    # Flag matched vs unmatched
    enriched["workday_matched"] = enriched["preferred_name"].notna()

    # Fill display name for unmatched
    enriched.loc[~enriched["workday_matched"], "preferred_name"] = enriched.loc[
        ~enriched["workday_matched"], "email"
    ]

    # Parse hire_date for tenure calculations
    enriched["hire_date"] = pd.to_datetime(enriched["hire_date"], errors="coerce")

    matched = enriched["workday_matched"].sum()
    total = len(enriched)
    people_matched = enriched.loc[enriched["workday_matched"], "email"].nunique()
    people_total = enriched["email"].nunique()

    match_pct = matched / total * 100 if total > 0 else 0
    people_pct = people_matched / people_total * 100 if people_total > 0 else 0
    print(f"  [Enrich] {matched:,}/{total:,} person-days matched ({match_pct:.0f}%)")
    print(f"    People: {people_matched:,}/{people_total:,} matched ({people_pct:.0f}%)")
    print(f"    Stream distribution: {enriched['stream'].value_counts().to_dict()}")
    print(f"    Seniority: {enriched['seniority_band'].value_counts().to_dict()}")

    return enriched


if __name__ == "__main__":
    person_day = pd.read_pickle(os.path.join(config.DATA_DIR, "person_day.pkl"))
    workday = pd.read_pickle(os.path.join(config.DATA_DIR, "workday.pkl"))
    enriched = enrich_with_workday(person_day, workday)
    enriched.to_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    print(f"  Saved to {config.DATA_DIR}/enriched.pkl")
