"""QA check on pipeline output — validate data quality and catch bugs."""

import os, sys, pickle
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

data_dir = config.DATA_DIR

print("=" * 60)
print("QA CHECK — Pipeline Output")
print("=" * 60)

# Load all data
enriched = pd.read_pickle(os.path.join(data_dir, "enriched.pkl"))
with open(os.path.join(data_dir, "baselines.pkl"), "rb") as f:
    baselines = pickle.load(f)
with open(os.path.join(data_dir, "personality.pkl"), "rb") as f:
    personality = pickle.load(f)
with open(os.path.join(data_dir, "anchors.pkl"), "rb") as f:
    anchors = pickle.load(f)

# --- Check 1: Missing offices ---
print("\n[1] MISSING OFFICES")
expected = set(config.OFFICES.keys())
got_baselines = set(baselines.keys())
got_personality = set(personality.keys())
got_anchors = set(anchors.keys())
missing_bl = expected - got_baselines
missing_pr = expected - got_personality
print(f"  Expected: {len(expected)} | Baselines: {len(got_baselines)} | Personality: {len(got_personality)} | Anchors: {len(got_anchors)}")
if missing_bl:
    print(f"  MISSING from baselines: {missing_bl}")
if missing_pr:
    print(f"  MISSING from personality: {missing_pr}")
# Check what offices are in the raw data
offices_in_data = enriched["office"].dropna().unique()
print(f"  Offices in enriched data: {sorted(offices_in_data)}")

# --- Check 2: Latest day — is it a partial day? ---
print("\n[2] LATEST DAY CHECK")
latest_date = enriched["date"].max()
latest_dow = pd.Timestamp(latest_date).day_name()
latest_data = enriched[enriched["date"] == latest_date]
print(f"  Latest date: {latest_date.date()} ({latest_dow})")
print(f"  Events on latest day: {len(latest_data)}")
print(f"  People on latest day: {latest_data['email'].nunique()}")
# Compare to prior same DOW
prior_same_dow = enriched[(enriched["dow"] == pd.Timestamp(latest_date).weekday()) & (enriched["date"] < latest_date)]
if len(prior_same_dow) > 0:
    avg_prior = prior_same_dow.groupby("date")["email"].nunique().mean()
    print(f"  Avg people on prior {latest_dow}s: {avg_prior:.0f}")
    ratio = latest_data['email'].nunique() / avg_prior if avg_prior > 0 else 0
    print(f"  Ratio (latest / avg prior): {ratio:.2f}")
    if ratio < 0.5:
        print(f"  WARNING: Latest day looks partial ({ratio:.0%} of normal). Should exclude from baselines.")

# --- Check 3: Dwell time sanity ---
print("\n[3] DWELL TIME BY OFFICE")
dwell = enriched[enriched["event_count"] >= 2].groupby("office")["dwell_hours"].median()
for office, d in dwell.sort_values(ascending=False).items():
    flag = " ← LOW" if d < 2 else ""
    print(f"  {office}: {d:.1f}h{flag}")

# --- Check 4: Arrival uses O365 only? ---
print("\n[4] ARRIVAL/DEPARTURE SOURCE CHECK")
# Check if Verkada-only person-days have inflated dwell
verkada_only = enriched[(enriched["has_verkada"]) & (~enriched["has_o365"])]
o365_present = enriched[enriched["has_o365"]]
print(f"  Verkada-only person-days: {len(verkada_only)} ({len(verkada_only)/len(enriched)*100:.1f}%)")
print(f"  O365 present person-days: {len(o365_present)} ({len(o365_present)/len(enriched)*100:.1f}%)")
if len(verkada_only) > 0:
    print(f"  Verkada-only median dwell: {verkada_only['dwell_hours'].median():.1f}h")
    print(f"  O365 present median dwell: {o365_present['dwell_hours'].median():.1f}h")

# --- Check 5: Baseline rates — do they make sense? ---
print("\n[5] BASELINE RATE SANITY")
for name, bl in sorted(baselines.items()):
    latest = bl.get("latest", {})
    rate = latest.get("rate", 0)
    dev = latest.get("deviation_pp", 0)
    pool = bl.get("active_pool", 0)
    hc = latest.get("headcount", 0)
    flag = ""
    if rate < 0.05:
        flag = " ← SUSPICIOUSLY LOW"
    elif rate > 0.95:
        flag = " ← SUSPICIOUSLY HIGH"
    print(f"  {name}: {rate:.0%} ({hc}/{pool}) dev={dev:+.0f}pp{flag}")

# --- Check 6: Anchor erosion — is it noisy? ---
print("\n[6] ANCHOR EROSION CHECK")
alert_count = sum(1 for a in anchors.values() if a.get("erosion_alert"))
print(f"  Offices with erosion alert: {alert_count}/{len(anchors)}")
if alert_count > len(anchors) * 0.6:
    print("  WARNING: Most offices alerting — likely a calibration issue, not real erosion")

# --- Check 7: Volatility distribution ---
print("\n[7] VOLATILITY LABELS")
vol_counts = {}
for p in personality.values():
    v = p.get("volatility_label", "unknown")
    vol_counts[v] = vol_counts.get(v, 0) + 1
for label, count in sorted(vol_counts.items()):
    print(f"  {label}: {count} offices")
if vol_counts.get("high", 0) > len(personality) * 0.7:
    print("  WARNING: Most offices labeled 'high volatility' — threshold may be too tight")

# --- Check 8: Stream and seniority coverage ---
print("\n[8] STREAM COVERAGE")
stream_counts = enriched.groupby("stream")["email"].nunique()
for stream, count in stream_counts.sort_values(ascending=False).items():
    print(f"  {stream}: {count} unique people")

print("\n[9] SENIORITY COVERAGE")
band_counts = enriched.groupby("seniority_band")["email"].nunique()
for band, count in band_counts.sort_values(ascending=False).items():
    print(f"  {band}: {count} unique people")

print("\n" + "=" * 60)
print("QA CHECK COMPLETE")
print("=" * 60)
