"""Step 6: Compute anchor lists and office leaderboards."""

import pandas as pd
import numpy as np
from datetime import timedelta
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


def compute_anchors(enriched_df):
    """
    Per office:
      - Identify top-N most consistent attenders (N scales by office size)
      - Compute current-week leaderboard with prior-week comparison
      - Track 4-week rolling streak (consecutive weeks in top N)

    Returns dict keyed by office name.
    """
    df = enriched_df.copy()
    today = df["date"].max()

    # Use most recent COMPLETE week (Mon-Fri with data on 3+ days)
    # to avoid partial-week artifacts
    today_ts = pd.Timestamp(today)
    candidate_start = today_ts - pd.Timedelta(days=today_ts.weekday())  # Monday of current week
    # Check if current week has enough data
    current_wk = df[(df["date"] >= candidate_start) & (df["dow"] <= 4)]
    current_wk_days = current_wk["date"].nunique()
    if current_wk_days < 3:
        # Fall back to prior complete week
        candidate_start = candidate_start - pd.Timedelta(weeks=1)
    current_week_start = candidate_start
    prior_week_start = current_week_start - pd.Timedelta(weeks=1)
    anchor_window_start = today - pd.Timedelta(weeks=config.BASELINE_WEEKS)
    streak_window_start = today - pd.Timedelta(weeks=4)

    # Weekdays only
    wdf = df[(df["date"] >= anchor_window_start) & (df["dow"] <= 4)].copy()

    results = {}

    for office_name, odf in wdf.groupby("office"):
        if office_name is None or str(office_name).strip() == "":
            continue

        meta = config.OFFICES.get(office_name, {})
        size_class = meta.get("size_class", "small")
        top_n = config.ANCHOR_N.get(size_class, 10)

        # --- Anchor identification (8-week window) ---
        # Count days present per person
        person_days = odf.groupby("email").agg(
            days_present=("date", "nunique"),
            avg_dwell=("dwell_hours", "mean"),
            name=("preferred_name", "first"),
            stream=("stream", "first"),
            job_family=("job_family", "first"),
            seniority=("seniority_band", "first"),
        ).reset_index()

        # Sort by days present (desc), then avg dwell (desc) for tiebreak
        person_days = person_days.sort_values(
            ["days_present", "avg_dwell"], ascending=[False, False]
        ).reset_index(drop=True)

        anchors_8wk = person_days.head(top_n).copy()
        anchor_emails_8wk = set(anchors_8wk["email"])

        # --- Current week leaderboard ---
        cw = odf[odf["date"] >= current_week_start]
        if len(cw) == 0:
            # Fall back to most recent week with data
            max_date = odf["date"].max()
            cw_start = max_date - pd.Timedelta(days=pd.Timestamp(max_date).weekday())
            cw = odf[odf["date"] >= cw_start]
            prior_week_start = cw_start - pd.Timedelta(weeks=1)

        cw_stats = cw.groupby("email").agg(
            days_this_week=("date", "nunique"),
            avg_dwell=("dwell_hours", "mean"),
            name=("preferred_name", "first"),
            stream=("stream", "first"),
            job_family=("job_family", "first"),
        ).reset_index()

        # Working days in current week (up to today)
        cw_working_days = cw["date"].dt.weekday.lt(5).sum()
        max_days = max(1, cw[cw["dow"] <= 4]["date"].nunique())

        cw_stats = cw_stats.sort_values(
            ["days_this_week", "avg_dwell"], ascending=[False, False]
        ).reset_index(drop=True)

        # --- Prior week stats (for trend comparison) ---
        pw = odf[(odf["date"] >= prior_week_start) & (odf["date"] < current_week_start)]
        pw_stats = pw.groupby("email").agg(
            days_prior_week=("date", "nunique"),
        ).reset_index() if len(pw) > 0 else pd.DataFrame(columns=["email", "days_prior_week"])

        # --- Build leaderboard ---
        leaderboard = []
        for rank, (_, row) in enumerate(cw_stats.head(top_n).iterrows(), 1):
            email = row["email"]
            days_now = int(row["days_this_week"])

            # Prior week comparison
            pw_match = pw_stats[pw_stats["email"] == email]
            days_prior = int(pw_match["days_prior_week"].iloc[0]) if len(pw_match) > 0 else 0

            if days_now > days_prior:
                trend = "up"
            elif days_now < days_prior:
                trend = "down"
            else:
                trend = "steady"

            # Is this person an 8-week anchor?
            is_anchor = email in anchor_emails_8wk

            leaderboard.append({
                "rank": rank,
                "email": email,
                "name": row["name"] if pd.notna(row["name"]) else email,
                "stream": row["stream"] if pd.notna(row["stream"]) else "Unknown",
                "job_family": row["job_family"] if pd.notna(row["job_family"]) else "",
                "days": f"{days_now}/{max_days}",
                "days_int": days_now,
                "trend": trend,
                "prior_days": f"{days_prior}/{max_days}" if days_prior > 0 else "new",
                "is_anchor": is_anchor,
            })

        # --- 4-week streak tracking ---
        # For each of the last 4 weeks, who was in the top N?
        weekly_tops = []
        for w in range(4):
            wk_end = today - pd.Timedelta(weeks=w)
            wk_start = wk_end - pd.Timedelta(days=pd.Timestamp(wk_end).weekday())
            wk_data = odf[(odf["date"] >= wk_start) & (odf["date"] < wk_start + pd.Timedelta(weeks=1))]
            if len(wk_data) == 0:
                weekly_tops.append(set())
                continue
            wk_rank = wk_data.groupby("email")["date"].nunique().nlargest(top_n)
            weekly_tops.append(set(wk_rank.index))

        # Compute streak for current leaderboard entries
        for entry in leaderboard:
            streak = 0
            for wk_set in weekly_tops:
                if entry["email"] in wk_set:
                    streak += 1
                else:
                    break
            entry["streak_weeks"] = streak
            if streak > 1:
                entry["streak_label"] = f"{streak} weeks in top {top_n}"
            elif streak == 1:
                entry["streak_label"] = "1 week"
            else:
                entry["streak_label"] = "new"

        # --- Anchor erosion check ---
        # Compare "established" anchors (weeks 5-8) to "recent" top (weeks 1-2)
        # Using separated windows avoids overlap that inflates retention
        established_start = today - pd.Timedelta(weeks=8)
        established_end = today - pd.Timedelta(weeks=4)
        recent_start = today - pd.Timedelta(weeks=2)

        established_data = odf[(odf["date"] >= established_start) & (odf["date"] < established_end)]
        recent_data = odf[odf["date"] >= recent_start]

        if len(established_data) > 0 and len(recent_data) > 0:
            est_rank = established_data.groupby("email")["date"].nunique().nlargest(top_n)
            rec_rank = recent_data.groupby("email")["date"].nunique().nlargest(top_n + 5)
            established_anchors = set(est_rank.index)
            recent_top = set(rec_rank.index)
            anchors_retained = len(established_anchors & recent_top)
            erosion_rate = 1.0 - (anchors_retained / max(len(established_anchors), 1))
        else:
            anchors_retained = top_n
            erosion_rate = 0.0

        results[office_name] = {
            "top_n": top_n,
            "size_class": size_class,
            "max_days_this_week": max_days,
            "leaderboard": leaderboard,
            "anchor_emails": list(anchor_emails_8wk),
            "anchors_retained": anchors_retained,
            "erosion_rate": round(erosion_rate, 2),
            "erosion_alert": erosion_rate > 0.25,  # >25% of anchors missing
            "total_appeared_this_week": len(cw_stats),
        }

    print(f"  [Anchors] Computed for {len(results)} offices")
    for name, r in sorted(results.items()):
        lb = r["leaderboard"]
        top = lb[0] if lb else {}
        erosion = "ALERT" if r["erosion_alert"] else "ok"
        print(f"    {name}: top-{r['top_n']}, #1={top.get('name','N/A')} "
              f"({top.get('days','?')}), erosion={erosion}")

    return results


if __name__ == "__main__":
    import pickle
    enriched = pd.read_pickle(os.path.join(config.DATA_DIR, "enriched.pkl"))
    anchors = compute_anchors(enriched)
    with open(os.path.join(config.DATA_DIR, "anchors.pkl"), "wb") as f:
        pickle.dump(anchors, f)
    print(f"  Saved to {config.DATA_DIR}/anchors.pkl")
