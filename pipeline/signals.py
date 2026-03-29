"""Step 9: Ghost detection and rhythm shift signals."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_signals(enriched_df, baselines):
    """
    Per office, compute:
      1. Ghost score (3-of-4 decay signals)
      2. Rhythm shift detection
      3. Dwell compression

    Returns dict keyed by office name.
    """
    df = enriched_df.copy()
    today = df["date"].max()

    results = {}

    for office_name, bl in baselines.items():
        pool = bl.get("active_pool", 0)
        if pool < 10:
            continue

        odf = df[(df["office"] == office_name) & (df["dow"] <= 4)].copy()
        if len(odf) == 0:
            continue

        # --- Weekly aggregation for trend detection ---
        weekly = odf.groupby(pd.Grouper(key="date", freq="W-MON")).agg(
            headcount=("email", "nunique"),
            fri_hc=("email", lambda x: x[odf.loc[x.index, "dow"] == 4].nunique()),
            peak_hc=("email", lambda x: max(
                odf.loc[x.index].groupby("dow")["email"].nunique().values
            ) if len(x) > 0 else 0),
            dwell_median=("dwell_hours", lambda x: x[x > 0].median() if len(x[x > 0]) > 0 else 0),
        ).reset_index()
        weekly = weekly[weekly["headcount"] > 0].tail(8)

        if len(weekly) < 4:
            results[office_name] = {"ghost_score": 0, "signals": []}
            continue

        # Split into recent (last 4 weeks) vs prior (weeks 5-8)
        mid = len(weekly) // 2
        recent = weekly.tail(mid)
        prior = weekly.head(mid)

        # --- Signal 1: Friday erosion ---
        fri_recent = recent["fri_hc"].mean()
        fri_prior = prior["fri_hc"].mean()
        friday_declining = fri_recent < fri_prior * 0.85 if fri_prior > 0 else False

        # --- Signal 2: Peak ceiling drop ---
        peak_recent = recent["peak_hc"].mean()
        peak_prior = prior["peak_hc"].mean()
        peak_declining = peak_recent < peak_prior * 0.85 if peak_prior > 0 else False

        # --- Signal 3: Shape flattening ---
        # CV of DOW headcounts — lower CV = flatter shape
        recent_dow = odf[odf["date"] >= today - pd.Timedelta(weeks=4)].groupby("dow")["email"].nunique()
        prior_dow = odf[(odf["date"] >= today - pd.Timedelta(weeks=8)) &
                        (odf["date"] < today - pd.Timedelta(weeks=4))].groupby("dow")["email"].nunique()
        recent_cv = recent_dow.std() / recent_dow.mean() if len(recent_dow) > 2 and recent_dow.mean() > 0 else 0
        prior_cv = prior_dow.std() / prior_dow.mean() if len(prior_dow) > 2 and prior_dow.mean() > 0 else 0
        shape_flattening = recent_cv < prior_cv * 0.7 if prior_cv > 0 else False

        # --- Signal 4: Dwell compression ---
        dwell_recent = recent["dwell_median"].mean()
        dwell_prior = prior["dwell_median"].mean()
        dwell_declining = dwell_recent < dwell_prior * 0.85 if dwell_prior > 0 else False

        # --- Ghost score ---
        signals_active = sum([friday_declining, peak_declining, shape_flattening, dwell_declining])
        # 3-of-4 for 4+ weeks, or 2-of-4 for 6+ weeks
        ghost_score = signals_active / 4.0

        signal_list = []
        if friday_declining:
            signal_list.append(f"Friday attendance down: {fri_recent:.0f} vs {fri_prior:.0f} prior avg")
        if peak_declining:
            signal_list.append(f"Peak day attendance down: {peak_recent:.0f} vs {peak_prior:.0f} prior avg")
        if shape_flattening:
            signal_list.append("Weekly pattern flattening — less difference between busy and quiet days")
        if dwell_declining:
            signal_list.append(f"People staying shorter: {dwell_recent:.1f}h vs {dwell_prior:.1f}h prior avg")

        results[office_name] = {
            "ghost_score": round(ghost_score, 2),
            "signals_active": signals_active,
            "ghost_flag": signals_active >= 3,
            "signals": signal_list,
            "friday_trend": {"recent": round(fri_recent, 0), "prior": round(fri_prior, 0)},
            "peak_trend": {"recent": round(peak_recent, 0), "prior": round(peak_prior, 0)},
            "dwell_trend": {"recent": round(dwell_recent, 1), "prior": round(dwell_prior, 1)},
        }

    # Summary
    flagged = [name for name, r in results.items() if r.get("ghost_flag")]
    print(f"  [Signals] Computed for {len(results)} offices")
    print(f"    Ghost flags (3+ signals): {len(flagged)} — {flagged if flagged else 'none'}")
    for name, r in sorted(results.items()):
        if r.get("signals"):
            print(f"    {name}: {r['signals_active']}/4 signals — {'; '.join(r['signals'][:2])}")

    return results


if __name__ == "__main__":
    import pickle
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    with open(os.path.join(config.DATA_DIR, "baselines.pkl"), "rb") as f:
        baselines = pickle.load(f)
    signals = compute_signals(enriched, baselines)
    with open(os.path.join(config.DATA_DIR, "signals.pkl"), "wb") as f:
        pickle.dump(signals, f)
    print(f"  Saved to {config.DATA_DIR}/signals.pkl")
