# config.py

# --- API & Database IDs ---
# These should stay in environment variables (set via GitHub Secrets for CI)
import os
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# --- Search Settings ---
LOCATION = "London, UK"  # CUSTOMISE: Your target job location
HOURS_OLD = 48
RESULTS_PER_SITE = 30
DAILY_APPLY_LIMIT = 4
REVIEW_THRESHOLD = 8

# CUSTOMISE: Add your own search terms targeting your desired roles
SEARCH_TERMS = [
    "AI solutions engineer",
    "forward deployed engineer",
    "applied AI engineer",
    "AI engineer graduate",
]

# --- Hard Filters (Script Level) ---
# CUSTOMISE: Add or remove keywords that trigger an immediate skip
EXCLUDE_TITLE_KEYWORDS = [
    "senior", "lead", "principal", "staff", "head of",
    "director", "manager", "vp ", "vice president", "cto", "ceo"
]

EXCLUDE_DESC_KEYWORDS = [
    "minimum 5 years", "5+ years", "8+ years", "10+ years"
]

ALLOW_SENIORITY_LEVELS = ["entry", "associate"]

# --- File Paths ---
PROMPT_FILE = "prompt.txt"