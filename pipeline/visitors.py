"""Step 7: Compute cross-office visitor flows."""

import pandas as pd
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_visitors(enriched_df):
    """
    Detect cross-office travel by finding people who appear at
    multiple offices. Returns visitor flows and individual trips.

    Home office = most frequent office in trailing 8 weeks (>60% of days).
    Visit = appearance at non-home office.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)

    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)].copy()

    # --- Determine home office per person ---
    office_counts = wdf.groupby(["email", "office"]).agg(
        days=("date", "nunique"),
        name=("preferred_name", "first"),
        role=("stream", "first"),
    ).reset_index()

    total_days = wdf.groupby("email")["date"].nunique().reset_index()
    total_days.columns = ["email", "total_days"]

    office_counts = office_counts.merge(total_days, on="email")
    office_counts["share"] = office_counts["days"] / office_counts["total_days"]

    # Home office = office with highest share, must be >60%
    home_df = office_counts.sort_values(["email", "share"], ascending=[True, False])
    home_df = home_df.groupby("email").first().reset_index()
    home_df["is_home"] = home_df["share"] > 0.6
    home_map = home_df[home_df["is_home"]].set_index("email")["office"].to_dict()

    # --- Find visits (days at non-home office) ---
    wdf["home_office"] = wdf["email"].map(home_map)
    visits = wdf[wdf["home_office"].notna() & (wdf["office"] != wdf["home_office"])].copy()

    if len(visits) == 0:
        print("  [Visitors] No cross-office visits detected")
        return {"flows": [], "recent_trips": [], "multi_office_people": 0}

    # --- Aggregate flows ---
    flows = visits.groupby(["home_office", "office"]).agg(
        visitors=("email", "nunique"),
        visit_days=("date", "count"),  # person-visit-days, not calendar days
    ).reset_index()
    flows.columns = ["from_office", "to_office", "visitors", "visit_days"]
    flows = flows.sort_values("visitors", ascending=False)

    # --- Recent individual trips (last 4 weeks) ---
    recent_start = today - pd.Timedelta(weeks=4)
    recent_visits = visits[visits["date"] >= recent_start]

    recent_trips = []
    for email, vdf in recent_visits.groupby("email"):
        name = vdf["preferred_name"].iloc[0] if pd.notna(vdf["preferred_name"].iloc[0]) else email
        home = home_map.get(email, "Unknown")
        visited = vdf.groupby("office")["date"].nunique().to_dict()
        for dest, days in visited.items():
            recent_trips.append({
                "name": name,
                "home_office": home,
                "visited": dest,
                "days": days,
            })

    recent_trips.sort(key=lambda x: x["days"], reverse=True)

    # Multi-office people (no >60% home)
    multi_office = len(home_df[~home_df["is_home"]])

    print(f"  [Visitors] {len(flows)} office-to-office flows, "
          f"{len(recent_trips)} recent trips, {multi_office} multi-office people")

    return {
        "flows": [
            {"from": r["from_office"], "to": r["to_office"],
             "people": int(r["visitors"]), "days": int(r["visit_days"])}
            for _, r in flows.head(20).iterrows()
        ],
        "recent_trips": recent_trips[:20],
        "multi_office_people": multi_office,
    }


if __name__ == "__main__":
    import pickle
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    visitors = compute_visitors(enriched)
    with open(os.path.join(config.DATA_DIR, "visitors.pkl"), "wb") as f:
        pickle.dump(visitors, f)
    print(f"  Saved to {config.DATA_DIR}/visitors.pkl")
