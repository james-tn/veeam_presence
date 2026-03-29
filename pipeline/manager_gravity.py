"""v1.5: Manager gravity — does the manager's presence pull the team in?"""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_manager_gravity(enriched_df):
    """
    For each manager: compare team attendance on days the manager is in
    vs days the manager is not in. The difference is the "gravity" score.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)]

    # Need managers who are in the occupancy data AND have reports
    wdf = wdf[wdf["workday_matched"] == True] if "workday_matched" in wdf.columns else wdf

    results = {}

    # Group by manager
    manager_groups = wdf[wdf["manager_name"].notna() & (wdf["manager_name"] != "")].groupby("manager_name")

    for manager_name, team_df in manager_groups:
        team_emails = team_df["email"].unique()
        if len(team_emails) < 3:
            continue  # Need enough team members

        # Find the manager's own email (if they appear in the data)
        manager_email = None
        for email in team_emails:
            person_data = wdf[wdf["email"] == email]
            if len(person_data) > 0 and person_data.iloc[0].get("ismanager") == "1":
                manager_email = email
                break

        if not manager_email:
            # Manager not found in attendance data — can't compute gravity
            continue

        # Days the manager was in
        manager_days = set(wdf[wdf["email"] == manager_email]["date"].unique())
        if len(manager_days) < 3:
            continue  # Not enough data

        # Team members (excluding the manager)
        reports = [e for e in team_emails if e != manager_email]
        if len(reports) < 2:
            continue

        # Team attendance on manager-in days vs manager-out days
        all_workdays = set(team_df["date"].unique())
        manager_out_days = all_workdays - manager_days

        if len(manager_out_days) == 0:
            continue

        team_on_mgr_in = 0
        team_on_mgr_out = 0

        for report_email in reports:
            report_days = set(wdf[wdf["email"] == report_email]["date"].unique())
            team_on_mgr_in += len(report_days & manager_days)
            team_on_mgr_out += len(report_days & manager_out_days)

        avg_in = team_on_mgr_in / (len(manager_days) * len(reports)) if len(manager_days) > 0 else 0
        avg_out = team_on_mgr_out / (len(manager_out_days) * len(reports)) if len(manager_out_days) > 0 else 0

        gravity = round(avg_in - avg_out, 2)

        office = team_df["office"].mode().iloc[0] if len(team_df["office"].mode()) > 0 else "Unknown"

        results[manager_name] = {
            "manager": manager_name,
            "office": office,
            "team_size": len(reports),
            "manager_days_in": len(manager_days),
            "gravity_score": gravity,
            "team_attendance_when_mgr_in": round(avg_in * 100),
            "team_attendance_when_mgr_out": round(avg_out * 100),
        }

    # Sort by gravity
    sorted_results = dict(sorted(results.items(), key=lambda x: abs(x[1]["gravity_score"]), reverse=True))

    print(f"  [Manager Gravity] Computed for {len(sorted_results)} managers")
    if sorted_results:
        top = list(sorted_results.values())[:3]
        for t in top:
            print(f"    {t['manager']} ({t['office']}): gravity={t['gravity_score']}, "
                  f"team in when mgr in={t['team_attendance_when_mgr_in']}%, "
                  f"when mgr out={t['team_attendance_when_mgr_out']}%")

    return sorted_results
