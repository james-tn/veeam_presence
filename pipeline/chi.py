"""Step 10: Culture Health Index — 7-component composite score per office."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os, pickle
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_chi(enriched_df, baselines, anchors, team_sync, signals):
    """
    Compute CHI (0-100) per office from 7 components:
      1. Consistency (20%) — week-to-week headcount volatility
      2. Depth (15%) — dwell time vs baseline
      3. Synchronization (20%) — team co-presence
      4. Anchor Stability (15%) — top-N retention
      5. Integration (10%) — new hire attendance slope
      6. Leadership Presence (10%) — IC vs leader gap trajectory
      7. Breadth (10%) — cross-functional stream mix
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    wdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)]

    results = {}

    for office_name, bl in baselines.items():
        pool = bl.get("active_pool", 0)
        if pool < 10:
            continue

        odf = wdf[wdf["office"] == office_name].sort_values("date")
        if len(odf) == 0:
            continue

        # --- 1. Consistency (20%) ---
        daily = odf.groupby("date")["email"].nunique()
        if len(daily) > 3 and daily.mean() > 0:
            cv = daily.std() / daily.mean()
            consistency = max(0, min(100, 100 - cv * 200))
        else:
            consistency = 50

        # --- 2. Depth (15%) ---
        valid_dwell = odf[odf["dwell_hours"] > 0]["dwell_hours"]
        if len(valid_dwell) > 10:
            recent_dwell = valid_dwell.tail(len(valid_dwell) // 2).median()
            baseline_dwell = valid_dwell.head(len(valid_dwell) // 2).median()
            if baseline_dwell > 0:
                depth = min(100, (recent_dwell / baseline_dwell) * 100)
            else:
                depth = 70
        else:
            depth = 70

        # --- 3. Synchronization (20%) ---
        office_teams = {k: v for k, v in team_sync.items() if v.get("office") == office_name}
        if office_teams:
            sync_scores = [t["sync_score"] for t in office_teams.values()]
            sync = np.mean(sync_scores) * 100
        else:
            sync = 50  # No team data

        # --- 4. Anchor Stability (15%) ---
        an = anchors.get(office_name, {})
        erosion = an.get("erosion_rate", 0)
        anchor_stability = max(0, (1 - erosion) * 100)

        # --- 5. Integration (10%) ---
        # New hires in last 6 months — check if attendance is ramping up
        new_hires = odf[odf["hire_date"].notna() & (odf["hire_date"] >= today - pd.Timedelta(days=180))]
        if new_hires["email"].nunique() >= 3:
            nh_weekly = new_hires.groupby([pd.Grouper(key="date", freq="W-MON")])["email"].nunique()
            if len(nh_weekly) > 2:
                slope = np.polyfit(range(len(nh_weekly)), nh_weekly.values, 1)[0]
                # Dampen: scale by 100 not 500, cap contribution to ±30 from midpoint
                integration = min(100, max(0, 50 + max(-30, min(30, slope * 100))))
            else:
                integration = 70
        else:
            integration = 70  # Default — not enough new hires to measure

        # --- 6. Leadership Presence (10%) ---
        ic = odf[odf["seniority_band"] == "IC"]
        leaders = odf[odf["seniority_band"] == "Senior Leader"]
        if len(ic) > 0 and len(leaders) > 0:
            recent_start = today - pd.Timedelta(weeks=4)
            prior_start = today - pd.Timedelta(weeks=8)

            ic_recent = ic[ic["date"] >= recent_start].groupby("date")["email"].nunique().mean() if len(ic[ic["date"] >= recent_start]) > 0 else 0
            ic_prior = ic[(ic["date"] >= prior_start) & (ic["date"] < recent_start)].groupby("date")["email"].nunique().mean() if len(ic[(ic["date"] >= prior_start) & (ic["date"] < recent_start)]) > 0 else 0
            leader_recent = leaders[leaders["date"] >= recent_start].groupby("date")["email"].nunique().mean() if len(leaders[leaders["date"] >= recent_start]) > 0 else 0
            leader_prior = leaders[(leaders["date"] >= prior_start) & (leaders["date"] < recent_start)].groupby("date")["email"].nunique().mean() if len(leaders[(leaders["date"] >= prior_start) & (leaders["date"] < recent_start)]) > 0 else 0

            current_gap = (ic_recent - leader_recent) if ic_recent > 0 else 0
            prior_gap = (ic_prior - leader_prior) if ic_prior > 0 else 0
            gap_change = current_gap - prior_gap
            # Normalize gap_change by office size to prevent small-office volatility
            norm = max(ic_recent, leader_recent, 5)  # Floor of 5 to dampen small numbers
            gap_pct = gap_change / norm
            leadership = max(0, min(100, 80 - gap_pct * 200))
        else:
            leadership = 70

        # --- 7. Breadth (10%) ---
        daily_streams = odf[odf["stream"].notna() & (odf["stream"] != "Unknown")].groupby("date")["stream"].nunique()
        max_streams = odf[odf["stream"].notna() & (odf["stream"] != "Unknown")]["stream"].nunique()
        if max_streams > 0 and len(daily_streams) > 0:
            breadth = (daily_streams.mean() / max_streams) * 100
        else:
            breadth = 50

        # --- Composite ---
        chi = (
            consistency * 0.20 +
            depth * 0.15 +
            sync * 0.20 +
            anchor_stability * 0.15 +
            integration * 0.10 +
            leadership * 0.10 +
            breadth * 0.10
        )

        results[office_name] = {
            "chi": round(chi),
            "components": {
                "consistency": round(consistency),
                "depth": round(depth),
                "sync": round(sync),
                "anchor_stability": round(anchor_stability),
                "integration": round(integration),
                "leadership": round(leadership),
                "breadth": round(breadth),
            },
        }

    print(f"  [CHI] Computed for {len(results)} offices")
    for name, r in sorted(results.items(), key=lambda x: x[1]["chi"], reverse=True):
        print(f"    {name}: CHI={r['chi']}")

    return results


if __name__ == "__main__":
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    with open(os.path.join(config.DATA_DIR, "baselines.pkl"), "rb") as f:
        baselines_data = pickle.load(f)
    with open(os.path.join(config.DATA_DIR, "anchors.pkl"), "rb") as f:
        anchors_data = pickle.load(f)
    with open(os.path.join(config.DATA_DIR, "team_sync.pkl"), "rb") as f:
        team_sync_data = pickle.load(f)
    with open(os.path.join(config.DATA_DIR, "signals.pkl"), "rb") as f:
        signals_data = pickle.load(f)
    chi = compute_chi(enriched, baselines_data, anchors_data, team_sync_data, signals_data)
    with open(os.path.join(config.DATA_DIR, "chi.pkl"), "wb") as f:
        pickle.dump(chi, f)
    print(f"  Saved to {config.DATA_DIR}/chi.pkl")
