# config.py

# --- API & Database IDs ---
# These should ideally stay in environment variables for security
import os
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# --- Search Settings ---
LOCATION = "London, UK"
HOURS_OLD = 48
RESULTS_PER_SITE = 30
DAILY_APPLY_LIMIT = 4
REVIEW_THRESHOLD = 8

SEARCH_TERMS = [
    "AI solutions engineer",
    "implementation engineer AI",
    "forward deployed engineer",
    "applied AI engineer",
    "AI agent developer",
    "AI engineer graduate"
]

# --- Hard Filters (Script Level) ---
# Add or remove keywords that trigger an immediate skip
EXCLUDE_TITLE_KEYWORDS = [
    "senior", "lead", "principal", "staff", "head of",
    "director", "manager", "vp ", "vice president", "cto", "ceo"
]

EXCLUDE_DESC_KEYWORDS = [
    "minimum 5 years", "5+ years", "8+ years", "10+ years"
]

ALLOW_SENIORITY_LEVELS = ["entry", "associate", ""]

# --- File Paths ---
PROMPT_FILE = "prompt.txt"