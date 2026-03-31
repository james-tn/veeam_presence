"""Step 5: Compute office personality profiles (7 dimensions)."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_personality(enriched_df, baselines):
    """
    Compute 7 personality dimensions per office:
      1. Rhythm type — steady, spiky, or distributed
      2. Peak shape — sharp arrivals vs. gradual
      3. Active window — median dwell time
      4. Arrival center — median arrival hour
      5. Weekend boundary — Friday/Thursday ratio
      6. Volatility — week-to-week CV of headcount
      7. Size class — from config
    """
    df = enriched_df.copy()
    today = df["date"].max()
    window_start = today - timedelta(weeks=config.BASELINE_WEEKS)
    bdf = df[(df["date"] >= window_start) & (df["dow"] <= 4)]

    profiles = {}

    for office_name, odf in bdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        bl = baselines.get(office_name, {})
        meta = config.OFFICES.get(office_name, {})
        size_class = meta.get("size_class", "small")

        # Daily headcount series
        daily = odf.groupby(["date", "dow"]).agg(
            headcount=("email", "nunique"),
        ).reset_index()

        # --- 1. Rhythm type ---
        dow_means = daily.groupby("dow")["headcount"].mean()
        rhythm_cv = 0.0
        if len(dow_means) >= 3 and dow_means.mean() > 0:
            rhythm_cv = dow_means.std() / dow_means.mean()
            if rhythm_cv < 0.15:
                rhythm = "steady"
            elif rhythm_cv < 0.35:
                rhythm = "distributed"
            else:
                rhythm = "spiky"
        else:
            rhythm = "unknown"

        # Peak days
        peak_dow = dow_means.idxmax() if len(dow_means) > 0 else None
        trough_dow = dow_means.idxmin() if len(dow_means) > 0 else None
        dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}

        # --- 2. Peak shape (std dev of arrival times on peak day) ---
        if peak_dow is not None:
            peak_arrivals = odf[odf["dow"] == peak_dow]["arrival_hour"].dropna()
            peak_shape_std = peak_arrivals.std() if len(peak_arrivals) > 5 else None
            if peak_shape_std is not None:
                peak_shape = "sharp" if peak_shape_std < 1.5 else "gradual"
            else:
                peak_shape = "unknown"
        else:
            peak_shape = "unknown"
            peak_shape_std = None

        # --- 3. Active window (median dwell for people with 2+ events) ---
        dwell_data = odf[odf["event_count"] >= 2]["dwell_hours"]
        active_window = round(dwell_data.median(), 1) if len(dwell_data) > 0 else 0

        # --- 4. Arrival center (median arrival hour, O365 events only) ---
        valid_arrivals = odf["arrival_hour"].dropna()
        arrival_center = round(valid_arrivals.median(), 1) if len(valid_arrivals) > 0 else 0

        # --- 5. Weekend boundary (Friday / Thursday headcount ratio) ---
        fri_mean = dow_means.get(4, 0)
        thu_mean = dow_means.get(3, 0)
        weekend_boundary = round(fri_mean / thu_mean, 2) if thu_mean > 0 else 0
        boundary_type = "hard cliff" if weekend_boundary < 0.5 else (
            "gradual fade" if weekend_boundary < 0.8 else "minimal drop"
        )

        # --- 6. Volatility (CV of daily headcount across all weekdays in window) ---
        if len(daily) > 3:
            volatility_cv = round(daily["headcount"].std() / daily["headcount"].mean(), 3) \
                if daily["headcount"].mean() > 0 else 0
        else:
            volatility_cv = 0
        volatility_label = "low" if volatility_cv < 0.25 else (
            "moderate" if volatility_cv < 0.45 else "high"
        )

        profiles[office_name] = {
            "rhythm_type": rhythm,
            "rhythm_cv": round(rhythm_cv, 3),
            "peak_day": dow_names.get(peak_dow, "unknown"),
            "trough_day": dow_names.get(trough_dow, "unknown"),
            "peak_shape": peak_shape,
            "peak_shape_std": round(peak_shape_std, 2) if peak_shape_std else None,
            "active_window_hours": active_window,
            "arrival_center_hour": arrival_center,
            "arrival_center_time": _hour_to_time(arrival_center),
            "weekend_boundary_ratio": weekend_boundary,
            "weekend_boundary_type": boundary_type,
            "volatility_cv": volatility_cv,
            "volatility_label": volatility_label,
            "size_class": size_class,
            "dow_headcounts": {
                dow_names.get(int(k), str(k)): round(v, 0)
                for k, v in dow_means.items()
            },
        }

    print(f"  [Personality] Profiled {len(profiles)} offices")
    for name, p in sorted(profiles.items()):
        print(f"    {name}: {p['rhythm_type']}, peak={p['peak_day']}, "
              f"window={p['active_window_hours']}h, arrival={p['arrival_center_time']}, "
              f"vol={p['volatility_label']}")

    return profiles


def _hour_to_time(h):
    """Convert decimal hour to HH:MM string."""
    if not h or h == 0:
        return "N/A"
    hours = int(h)
    minutes = int((h - hours) * 60)
    return f"{hours}:{minutes:02d}"


if __name__ == "__main__":
    import pickle
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    with open(os.path.join(config.DATA_DIR, "baselines.pkl"), "rb") as f:
        baselines = pickle.load(f)
    profiles = compute_personality(enriched, baselines)
    with open(os.path.join(config.DATA_DIR, "personality.pkl"), "wb") as f:
        pickle.dump(profiles, f)
    print(f"  Saved to {config.DATA_DIR}/personality.pkl")
