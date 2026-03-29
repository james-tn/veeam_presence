"""Step 8: Compute team synchronization scores."""

import pandas as pd
import numpy as np
from itertools import combinations
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_team_sync(enriched_df):
    """
    Per supervisory_organization: pairwise co-presence rate.
    For each pair of team members, what fraction of their attendance days overlapped?

    Returns dict keyed by supervisory_org name.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=4)

    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)].copy()
    wdf = wdf[wdf["supervisory_organization"].notna() & (wdf["supervisory_organization"] != "")]

    results = {}

    for org_name, odf in wdf.groupby("supervisory_organization"):
        members = odf["email"].unique()
        if len(members) < 3:
            continue  # Too small for meaningful sync

        # Build attendance sets: for each person, which dates they were in
        person_dates = {}
        for email, pdf in odf.groupby("email"):
            person_dates[email] = set(pdf["date"].unique())

        # Pairwise co-presence
        pairs = list(combinations(person_dates.keys(), 2))
        if len(pairs) == 0:
            continue

        co_presence_rates = []
        for a, b in pairs:
            days_a = person_dates[a]
            days_b = person_dates[b]
            union = days_a | days_b
            intersection = days_a & days_b
            if len(union) > 0:
                co_presence_rates.append(len(intersection) / len(union))

        sync_score = np.mean(co_presence_rates) if co_presence_rates else 0

        # Get office and manager info
        office = odf["office"].mode().iloc[0] if len(odf["office"].mode()) > 0 else "Unknown"
        manager = odf["manager_name"].iloc[0] if pd.notna(odf["manager_name"].iloc[0]) else "Unknown"
        stream = odf["stream"].mode().iloc[0] if len(odf["stream"].mode()) > 0 else "Unknown"

        results[org_name] = {
            "team": org_name,
            "office": office,
            "manager": manager,
            "stream": stream,
            "members": len(members),
            "sync_score": round(sync_score, 2),
            "pairs_measured": len(pairs),
        }

    print(f"  [Team Sync] Computed for {len(results)} teams (3+ members)")

    # Summary stats
    if results:
        scores = [r["sync_score"] for r in results.values()]
        print(f"    Sync scores: min={min(scores):.2f}, median={np.median(scores):.2f}, max={max(scores):.2f}")
        low_sync = [r for r in results.values() if r["sync_score"] < 0.2]
        print(f"    Low sync (<0.2): {len(low_sync)} teams")

    return results


if __name__ == "__main__":
    import pickle
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    team_sync = compute_team_sync(enriched)
    with open(os.path.join(config.DATA_DIR, "team_sync.pkl"), "wb") as f:
        pickle.dump(team_sync, f)
    print(f"  Saved to {config.DATA_DIR}/team_sync.pkl")
