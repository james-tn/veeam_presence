"""Step 4: Compute rolling 8-week baselines per office × DOW × role segment."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_baselines(enriched_df):
    """
    Compute baselines at three levels:
      1. Office-wide attendance rate
      2. Role-segmented (by stream, min-N threshold)
      3. Seniority-segmented (IC / Manager / Senior Leader)

    Attendance rate = daily headcount / active office pool
    Active pool = distinct people seen at office in trailing 8 weeks.

    Returns dict keyed by office name.
    """
    df = enriched_df.copy()
    today = df["date"].max()
    baseline_start = today - timedelta(weeks=config.BASELINE_WEEKS)

    # Filter to baseline window
    bdf = df[df["date"] >= baseline_start].copy()
    # Weekdays only (Mon=0 to Fri=4)
    bdf = bdf[bdf["dow"] <= 4]

    # Exclude known holidays per office (loaded lazily)
    try:
        from pipeline.holidays_cal import is_holiday
        _has_holidays = True
    except ImportError:
        _has_holidays = False

    results = {}

    for office_name, odf in bdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        # Exclude holidays for this office's country
        if _has_holidays:
            holiday_mask = odf["date"].apply(lambda d: is_holiday(office_name, d))
            excluded = holiday_mask.sum()
            if excluded > 0:
                odf = odf[~holiday_mask]

        office_result = {
            "name": office_name,
            "metadata": config.OFFICES.get(office_name, {}),
        }

        # --- Active pool (distinct people in the 8-week window) ---
        active_pool = odf["email"].nunique()
        office_result["active_pool"] = active_pool

        if active_pool == 0:
            results[office_name] = office_result
            continue

        # --- Daily headcount ---
        daily = odf.groupby("date").agg(
            headcount=("email", "nunique"),
            dow=("dow", "first"),
        ).reset_index()

        # --- Office-wide baseline per DOW ---
        dow_baselines = {}
        for dow in range(5):  # Mon-Fri
            dow_days = daily[daily["dow"] == dow].copy()
            if len(dow_days) == 0:
                continue

            rates = dow_days["headcount"] / active_pool
            # Holidays already excluded upstream by holidays_cal.is_holiday()
            clean_mean = rates.mean()

            dow_baselines[dow] = {
                "rate": round(clean_mean, 4),
                "headcount_avg": round(dow_days["headcount"].mean(), 1),
                "n_weeks": len(dow_days),
                "std": round(rates.std(), 4) if len(rates) > 1 else 0,
            }

        office_result["dow_baselines"] = dow_baselines

        # --- Most recent day's data (skip partial days) ---
        # Use most recent weekday with reasonable headcount (> 20% of mean)
        daily_sorted = daily.sort_values("date", ascending=False)
        mean_hc = daily["headcount"].mean()
        most_recent = None
        for _, row in daily_sorted.iterrows():
            if row["headcount"] >= mean_hc * 0.2:
                most_recent = row
                break
        if most_recent is None:
            most_recent = daily_sorted.iloc[0]  # fallback
        office_result["latest"] = {
            "date": str(most_recent["date"].date()),
            "headcount": int(most_recent["headcount"]),
            "rate": round(most_recent["headcount"] / active_pool, 4),
            "dow": int(most_recent["dow"]),
        }

        # Deviation from baseline
        latest_dow = int(most_recent["dow"])
        if latest_dow in dow_baselines:
            bl = dow_baselines[latest_dow]["rate"]
            office_result["latest"]["baseline_rate"] = bl
            office_result["latest"]["deviation_pp"] = round(
                (office_result["latest"]["rate"] - bl) * 100, 1
            )

        # --- Role-segmented baselines (by stream) ---
        role_baselines = {}
        for stream, sdf in odf.groupby("stream"):
            if stream in (None, "", "Unknown"):
                continue
            stream_pool = sdf["email"].nunique()
            if stream_pool < config.MIN_N_ROLE_SEGMENT:
                continue  # Too small — roll into office-wide

            stream_daily = sdf.groupby(["date", "dow"]).agg(
                headcount=("email", "nunique"),
            ).reset_index()

            stream_dow = {}
            for dow in range(5):
                sd = stream_daily[stream_daily["dow"] == dow]
                if len(sd) == 0:
                    continue
                rates = sd["headcount"] / stream_pool
                mean_rate = rates.mean()
                non_holiday = rates[rates >= mean_rate * config.HOLIDAY_THRESHOLD]
                clean_mean = non_holiday.mean() if len(non_holiday) > 0 else mean_rate
                stream_dow[dow] = round(clean_mean, 4)

            # Latest rate for this stream
            latest_stream = sdf[sdf["date"] == most_recent["date"]]
            latest_hc = latest_stream["email"].nunique()

            role_baselines[stream] = {
                "pool": stream_pool,
                "dow_baselines": stream_dow,
                "latest_rate": round(latest_hc / stream_pool, 4) if stream_pool > 0 else 0,
                "latest_headcount": latest_hc,
            }

            # Add deviation for latest DOW
            if latest_dow in stream_dow:
                role_baselines[stream]["deviation_pp"] = round(
                    (role_baselines[stream]["latest_rate"] - stream_dow[latest_dow]) * 100, 1
                )

        office_result["role_baselines"] = role_baselines

        # --- Seniority-segmented baselines ---
        seniority_baselines = {}
        for band, bsdf in odf.groupby("seniority_band"):
            if band in (None, "", "Unknown"):
                continue
            band_pool = bsdf["email"].nunique()
            if band_pool < config.MIN_N_ROLE_SEGMENT:
                continue

            band_daily = bsdf.groupby(["date", "dow"]).agg(
                headcount=("email", "nunique"),
            ).reset_index()

            band_dow = {}
            for dow in range(5):
                bd = band_daily[band_daily["dow"] == dow]
                if len(bd) == 0:
                    continue
                rates = bd["headcount"] / band_pool
                mean_rate = rates.mean()
                non_holiday = rates[rates >= mean_rate * config.HOLIDAY_THRESHOLD]
                clean_mean = non_holiday.mean() if len(non_holiday) > 0 else mean_rate
                band_dow[dow] = round(clean_mean, 4)

            latest_band = bsdf[bsdf["date"] == most_recent["date"]]
            latest_hc = latest_band["email"].nunique()

            seniority_baselines[band] = {
                "pool": band_pool,
                "dow_baselines": band_dow,
                "latest_rate": round(latest_hc / band_pool, 4) if band_pool > 0 else 0,
            }

        office_result["seniority_baselines"] = seniority_baselines

        # --- Weekly headcount trend (8 weeks) ---
        weekly = odf.groupby(pd.Grouper(key="date", freq="W-MON")).agg(
            headcount=("email", "nunique"),
            days_with_data=("date", "nunique"),
        ).reset_index()
        weekly = weekly[weekly["days_with_data"] > 0].tail(config.BASELINE_WEEKS)
        office_result["weekly_trend"] = [
            {"week": str(r["date"].date()), "headcount": int(r["headcount"])}
            for _, r in weekly.iterrows()
        ]

        results[office_name] = office_result

    print(f"  [Baselines] Computed for {len(results)} offices")
    for name, r in sorted(results.items(), key=lambda x: x[1].get("active_pool", 0), reverse=True):
        pool = r.get("active_pool", 0)
        roles = len(r.get("role_baselines", {}))
        latest = r.get("latest", {})
        rate = latest.get("rate", 0)
        dev = latest.get("deviation_pp", 0)
        print(f"    {name}: pool={pool}, roles={roles}, latest={rate:.0%} ({dev:+.0f}pp)")

    return results


if __name__ == "__main__":
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    baselines = compute_baselines(enriched)
    import pickle
    with open(os.path.join(config.DATA_DIR, "baselines.pkl"), "wb") as f:
        pickle.dump(baselines, f)
    print(f"  Saved to {config.DATA_DIR}/baselines.pkl")
