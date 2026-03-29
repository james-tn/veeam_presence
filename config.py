"""Veeam Presence — configuration and constants."""

import os

# ---------------------------------------------------------------------------
# Credentials (set via environment variables — never hardcode in committed files)
# ---------------------------------------------------------------------------
DATABRICKS_HOST = os.environ.get("DATABRICKS_HOST", "adb-1715711735713564.4.azuredatabricks.net")
DATABRICKS_TOKEN = os.environ.get("DATABRICKS_TOKEN", "")
DATABRICKS_HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/be160f1edb836d88")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

# ---------------------------------------------------------------------------
# Databricks tables
# ---------------------------------------------------------------------------
OCCUPANCY_TABLE = "dev_catalog.jf_salesforce_bronze.office_occupancy_o_365_verkada"
WORKDAY_TABLE = "dev_catalog.revenue_intelligence.workday_enhanced"

# ---------------------------------------------------------------------------
# Pipeline parameters
# ---------------------------------------------------------------------------
BASELINE_WEEKS = 8          # Rolling window for baselines
PULL_WEEKS = 10             # Pull extra weeks for buffer
MIN_N_ROLE_SEGMENT = 10     # Minimum people for role-segmented baseline
HOLIDAY_THRESHOLD = 0.20    # Days below this % of baseline excluded from rolling window
COLLAB_WINDOW_THRESHOLD = 0.50  # % of daily peak for collaboration window

# ---------------------------------------------------------------------------
# Office metadata
# ---------------------------------------------------------------------------
OFFICES = {
    "Bucharest (AFI)":  {"region": "EMEA",     "offset_sec": 7200,   "sources": ["O365", "Verkada"], "size_class": "mega"},
    "Atlanta":          {"region": "Americas",  "offset_sec": -18000, "sources": ["O365", "Verkada"], "size_class": "large"},
    "Prague Rustonka":  {"region": "EMEA",      "offset_sec": 3600,   "sources": ["O365", "Verkada"], "size_class": "large"},
    "Seattle":          {"region": "Americas",  "offset_sec": -28800, "sources": ["O365", "Verkada"], "size_class": "large"},
    "Berlin":           {"region": "EMEA",      "offset_sec": 3600,   "sources": ["O365", "Verkada"], "size_class": "mid"},
    "Columbus":         {"region": "Americas",  "offset_sec": -18000, "sources": ["O365", "Verkada"], "size_class": "mid"},
    "Kuala Lumpur":     {"region": "APJ",       "offset_sec": 28800,  "sources": ["O365"],            "size_class": "mid"},
    "Lisbon":           {"region": "EMEA",      "offset_sec": 0,      "sources": ["O365"],            "size_class": "mid"},
    "Singapore":        {"region": "APJ",       "offset_sec": 28800,  "sources": ["O365"],            "size_class": "mid"},
    "Paris":            {"region": "EMEA",      "offset_sec": 3600,   "sources": ["O365"],            "size_class": "mid"},
    "Yerevan":          {"region": "EMEA",      "offset_sec": 14400,  "sources": ["O365"],            "size_class": "mid"},
    "Sydney":           {"region": "APJ",       "offset_sec": 36000,  "sources": ["O365"],            "size_class": "mid"},
    "Phoenix":          {"region": "Americas",  "offset_sec": -25200, "sources": ["O365", "Verkada"], "size_class": "mid"},
    "Mumbai":           {"region": "APJ",       "offset_sec": 19800,  "sources": ["O365"],            "size_class": "small"},
    "Baar":             {"region": "EMEA",      "offset_sec": 3600,   "sources": ["O365", "Verkada"], "size_class": "small"},
    "Buenos Aires":     {"region": "Americas",  "offset_sec": -10800, "sources": ["O365"],            "size_class": "small"},
    "Shanghai":         {"region": "APJ",       "offset_sec": 28800,  "sources": ["O365"],            "size_class": "small"},
    "Mexico":           {"region": "Americas",  "offset_sec": -21600, "sources": ["O365"],            "size_class": "small"},
}

# Anchor / leaderboard count by size class
ANCHOR_N = {"small": 5, "mid": 10, "large": 15, "mega": 20}

# ---------------------------------------------------------------------------
# Stream fallback mapping (for 625 people with blank stream)
# Maps job_family_group → stream when stream is blank
# ---------------------------------------------------------------------------
STREAM_FALLBACK = {
    "R&D":                          "R&D",
    "Engineering":                  "R&D",
    "Quota Carrying Sales":         "Sales",
    "Quota Carrying Overlay":       "Sales",
    "Sales":                        "Sales",
    "Professional Services (OLD JA)": "Cost of Revenue",
    "Customer Support (OLD JA)":    "Cost of Revenue",
    "HR":                           "G&A",
    "Facilities and Admin":         "G&A",
    "Corporate":                    "G&A",
    "Finance (OLD JA)":             "G&A",
    "Legal":                        "G&A",
    "Strategy and Ops":             "G&A",
    "Governance, Risk & Compliance":"G&A",
    "Corporate Marketing":          "Marketing",
    "Regional Marketing":           "Marketing",
    "General Marketing":            "Marketing",
}

# ---------------------------------------------------------------------------
# Seniority bands (derived from management_level)
# ---------------------------------------------------------------------------
SENIORITY_BANDS = {
    "11. Professional":             "IC",
    "12. Senior Para - professional": "IC",
    "13. Para - professional":      "IC",
    "Consultant":                   "IC",
    "8. Manager":                   "Manager",
    "9. Team Leader":               "Manager",
    "10. Supervisor":               "Manager",
    "7. Senior Manager":            "Senior Leader",
    "6. Director":                  "Senior Leader",
    "5. Senior Director":           "Senior Leader",
    "4. Vice President":            "Senior Leader",
    "3. Senior Vice President":     "Senior Leader",
    "2. Chief Officer":             "Senior Leader",
    "1. Board of Directors":        "Senior Leader",
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
