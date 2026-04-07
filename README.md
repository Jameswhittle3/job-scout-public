# Job Scout

An automated job scouting pipeline that scrapes job postings, scores them with AI, and writes the best matches to a Notion database — running daily via GitHub Actions.

## How It Works

```
Scrape (Indeed, LinkedIn, Google Jobs)
  → Hard Filter (title, experience, seniority level)
    → AI Score (Gemini rates each role 1-10 against your profile)
      → Write to Notion (qualifying jobs enter the Pool)
        → Promote (top 4 from Pool move to Apply each day)
```

1. **Scrape** — Searches multiple job boards using your configured search terms and location.
2. **Hard Filter** — Removes obvious non-fits by title keywords (e.g. "senior", "director"), experience phrases in descriptions (e.g. "5+ years"), and LinkedIn seniority tags (e.g. "mid-senior level").
3. **Deduplicate** — Uses URL matching and company+title fingerprinting to prevent the same role appearing twice, even across different job boards.
4. **AI Score** — Sends each surviving job to Gemini with a customisable system prompt describing your background, target roles, and preferences. Returns a 1-10 score with reasoning.
5. **Write to Notion** — Jobs scoring above the threshold (default: 8/10) are written to your Notion database with Stage set to "Pool".
6. **Promote** — After writing, the script queries all Pool entries and promotes the top N (default: 4) by score to "Apply". Lower-scoring jobs carry over and compete with tomorrow's results.

## Setup

### Prerequisites

- Python 3.12+
- A [Notion integration](https://www.notion.so/my-integrations) with access to your database
- A [Gemini API key](https://aistudio.google.com/apikey)
- A GitHub account (for automated scheduling)

### 1. Notion Database

Create a Notion database with these properties:

| Property | Type | Purpose |
|---|---|---|
| Company | Title | Company name |
| Position | Select | Job title |
| Posting URL | URL | Link to the job listing |
| Job Description | Rich text | Truncated JD (first 2000 chars) |
| ai-notes | Rich text | AI scoring details and reasoning |
| Score | Number | AI-assigned score (1-10) |
| Stage | Select | Options: `Pool`, `Apply`, `Applied`, `Rejected` (script only uses Pool and Apply) |

Share the database with your Notion integration.

### 2. Clone and Configure

```bash
git clone https://github.com/your-username/job-scout.git
cd job-scout
pip install -r requirements.txt
```

### 3. Environment Variables

Set these as environment variables locally (or as GitHub Secrets for CI):

```
GEMINI_API_KEY=your-gemini-api-key
NOTION_API_KEY=your-notion-integration-token
NOTION_DATABASE_ID=your-notion-database-id
```

### 4. Customise

#### `config.py` — Search and filter settings

```python
LOCATION = "London, UK"          # Your target location
REVIEW_THRESHOLD = 8             # Minimum score to enter Pool (1-10)
DAILY_APPLY_LIMIT = 4            # How many Pool jobs get promoted to Apply each run

SEARCH_TERMS = [                 # Job title search queries
    "AI solutions engineer",
    "applied AI engineer",
    # Add your own...
]

EXCLUDE_TITLE_KEYWORDS = [       # Titles containing these are skipped
    "senior", "lead", "director",
    # Add your own...
]
```

#### `prompt.txt` — AI scoring prompt

This is the system prompt sent to Gemini for every job. It contains:

- **Who the candidate is** — Your background, degree, experience
- **Target roles** — What types of roles you're looking for
- **Why the background is an asset** — What makes you a differentiator
- **Hard filters** — What the AI should reject outright (e.g. 2+ years experience required)
- **Soft negatives** — What should lower the score but not auto-reject
- **Preferences** — What should increase the score
- **Scoring guide** — How to assign 1-10

Each section has `<!-- CUSTOMISE -->` comments with examples. Replace the examples with your own details.

### 5. Run

#### Locally
```bash
python job_scout.py
```

#### Automated (GitHub Actions)
The included workflow (`.github/workflows/job_scout.yml`) runs weekdays at 8am GMT. Add your three environment variables as [GitHub Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets) and push to trigger.

## Architecture

```
job_scout.py      — Main pipeline (scrape → filter → score → write → promote)
config.py         — All tuneable settings (search terms, thresholds, filters)
prompt.txt        — AI system prompt (your profile, scoring criteria)
requirements.txt  — Python dependencies
.github/workflows/job_scout.yml — GitHub Actions cron schedule
```

## How the Pool/Apply System Works

- Every new qualifying job enters as **Pool**.
- After writing, the script queries **all** Pool entries (new + carryover from previous days) and promotes the **top 4 by score** to **Apply**.
- If today's jobs are weaker than yesterday's leftovers, the older higher-scoring jobs get promoted instead.
- The script never touches entries in Applied, Rejected, or any other stage — those are for you to manage manually.

## Dependencies

- [python-jobspy](https://github.com/Bunsly/JobSpy) — Multi-site job scraping
- [google-genai](https://github.com/googleapis/python-genai) — Gemini API client
- [requests](https://docs.python-requests.org/) — Notion API calls
- [pandas](https://pandas.pydata.org/) — Data handling

## License

MIT