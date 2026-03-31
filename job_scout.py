import os
import json
import hashlib
import time
import requests
from datetime import datetime
from google import genai
from jobspy import scrape_jobs

# ── Configuration ──────────────────────────────────────────────────────────────

import config  # Import your new modular settings

# Update your variables to reference the config file
GEMINI_API_KEY = config.GEMINI_API_KEY
NOTION_API_KEY = config.NOTION_API_KEY
NOTION_DATABASE_ID = config.NOTION_DATABASE_ID

# Update fetch_jobs to use config.LOCATION and config.SEARCH_TERMS
def fetch_jobs():
    for term in config.SEARCH_TERMS:
        jobs = scrape_jobs(
            location=config.LOCATION,
            # ... other params ...
        )

# Update hard_filter to use the config lists
def hard_filter(jobs):
    for job in jobs:
        if any(t in title for t in config.EXCLUDE_TITLE_KEYWORDS):
            continue
        # ... and so on ...

# ── System prompt ───────────────────────────────────────────────────────────────

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompt.txt")
with open(PROMPT_PATH, "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read()

# ── Helpers ─────────────────────────────────────────────────────────────────────

def make_fingerprint(company, title):
    """Create a normalized hash from company + title to catch duplicates across sites."""
    key = f"{str(company).lower().strip()}|{str(title).lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]

# ── Step 1: Fetch existing Notion entries to avoid duplicates ───────────────────

def get_existing_entries():
    """Fetch all posting URLs and company+title fingerprints from Notion."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    existing_urls = set()
    existing_fingerprints = set()
    has_more = True
    start_cursor = None

    while has_more:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        response = requests.post(url, headers=headers, json=body)
        data = response.json()
        for result in data.get("results", []):
            props = result.get("properties", {})
            posting_url = props.get("Posting URL", {}).get("url")
            if posting_url:
                existing_urls.add(posting_url)
            company_parts = props.get("Company", {}).get("title", [])
            company = company_parts[0]["text"]["content"] if company_parts else ""
            position_prop = props.get("Position", {})
            title = ""
            if "rich_text" in position_prop:
                title_parts = position_prop.get("rich_text", [])
                title = title_parts[0]["text"]["content"] if title_parts else ""
            elif "select" in position_prop:
                title = (position_prop.get("select") or {}).get("name", "")
            if company:
                existing_fingerprints.add(make_fingerprint(company, title))
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    print(f"Found {len(existing_urls)} existing URLs and {len(existing_fingerprints)} fingerprints in Notion")
    return existing_urls, existing_fingerprints

# ── Step 2: Scrape jobs ─────────────────────────────────────────────────────────

def fetch_jobs():
    """Fetch raw job results from Indeed, LinkedIn, and Google Jobs."""
    all_jobs = []
    seen_urls = set()
    seen_fingerprints = set()

    for term in SEARCH_TERMS:
        print(f"Searching: {term}")
        try:
            jobs = scrape_jobs(
                site_name=["indeed", "linkedin", "google"],
                search_term=term,
                location="London, UK",
                results_wanted=RESULTS_PER_SITE,
                hours_old=HOURS_OLD,
                country_indeed="UK"
            )
            jobs = jobs.fillna("")
            for _, row in jobs.iterrows():
                url = str(row.get("job_url", ""))
                fp = make_fingerprint(row.get("company", ""), row.get("title", ""))
                if url and url not in seen_urls and fp not in seen_fingerprints:
                    seen_urls.add(url)
                    seen_fingerprints.add(fp)
                    all_jobs.append(row.to_dict())
        except Exception as e:
            print(f"Search failed for '{term}': {e}")

    print(f"Total unique raw results: {len(all_jobs)}")
    return all_jobs

# ── Step 3: Hard filter ─────────────────────────────────────────────────────────

def hard_filter(jobs):
    """Remove obvious non-fits by title and description before spending API credits."""
    import re  # Added to allow pattern matching

    EXCLUDE_TITLE = ["senior", "lead", "principal", "staff", "head of",
                     "director", "manager", "vp ", "vice president", "cto", "ceo"]

    # This regex catches variations like: "5+ years", "3-5 yrs", "minimum 4 years"
    # It automatically ignores bullet points, extra spaces, and capitalization.
    exp_pattern = re.compile(
        r'(?:[3-9]|1[0-9])\s*\+\s*(?:years?|yrs?)|'                     # Matches "3+ years", "10 + yrs"
        r'(?:minimum|at least)\s+(?:of\s+)?(?:[3-9]|1[0-9])\s+(?:years?|yrs?)|' # Matches "minimum 5 years"
        r'(?:[3-9]|1[0-9])\s*(?:-|to)\s*\d+\s*(?:years?|yrs?)',         # Matches "3-5 years"
        re.IGNORECASE
    )

    ALLOW_SENIORITY = ["entry", "intern", "associate", ""]

    filtered = []
    for job in jobs:
        title = str(job.get("title", "")).lower()
        desc  = str(job.get("description", ""))
        seniority = str(job.get("job_level", "")).lower().strip()

        # 1. Kill by Title
        if any(t in title for t in EXCLUDE_TITLE):
            continue

        # 2. Kill by Regex Experience Match in Description
        if exp_pattern.search(desc):
            continue

        # 3. Kill by explicit Seniority level (if provided by scraper)
        if seniority and not any(s in seniority for s in ALLOW_SENIORITY):
            continue

        filtered.append(job)

    print(f"After hard filter: {len(filtered)} roles remaining")
    return filtered

# ── Step 4: Score with Gemini ───────────────────────────────────────────────────

def score_job(client, job):
    """Send a single JD to Gemini for scoring. Returns the job dict with score added."""
    description = str(job.get("description", ""))[:3000]  # Truncate very long JDs
    prompt = f"""Score this job posting.

Job title: {job.get('title', 'Unknown')}
Company: {job.get('company', 'Unknown')}
Location: {job.get('location', 'Unknown')}
Description: {description}"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=400,
                ),
            )
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            score_data = json.loads(text)
            time.sleep(1)  # Respect rate limits
            return {**job, **score_data}
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                print(f"Rate limited, waiting 10s before retry...")
                time.sleep(10)
                continue
            print(f"Scoring failed for {job.get('title')}: {e}")
            return {**job, "score": 0, "fit_reason": "Scoring error", 
                    "keyword_gaps": [], "mech_eng_asset": False, "exp_is_hard_block": False}

# ── Step 5: Write to Notion ─────────────────────────────────────────────────────

def write_to_notion(job, existing_urls, existing_fingerprints):
    """Write a single job to the Notion Applications database as a Pool entry."""
    job_url = str(job.get("job_url", ""))
    fp = make_fingerprint(job.get("company", ""), job.get("title", ""))

    # Skip if URL or company+title already in Notion
    if job_url and job_url in existing_urls:
        print(f"Skipping duplicate (URL match): {job.get('title')} at {job.get('company')}")
        return False
    if fp in existing_fingerprints:
        print(f"Skipping duplicate (company+title match): {job.get('title')} at {job.get('company')}")
        return False

    raw_title = str(job.get("title", "Unknown")).strip()
    formatted_title = " ".join(
        [word.upper() if word.lower() == "ai" else word.capitalize() 
         for word in raw_title.split()]
    )

    score = job.get("score", 0)
    gaps = job.get("keyword_gaps", [])
    gaps_str = ", ".join(gaps) if gaps else "None identified"
    mech_asset = "Yes" if job.get("mech_eng_asset") else "No"

    notes = (
        f"Score: {score}/10 | {job.get('fit_reason', '')} | "
        f"Keyword gaps: {gaps_str} | Mech eng asset: {mech_asset} | "
        f"Found: {datetime.today().strftime('%Y-%m-%d')}"
    )

    properties = {
        "Company": {
            "title": [{"text": {"content": str(job.get("company", "Unknown"))}}]
        },
        "Position": {
            "select": {"name": formatted_title}
        },
        "Job Description": {
            "rich_text": [{"text": {"content": str(job.get("description", ""))[:2000]}}]
        },
        "ai-notes": {
            "rich_text": [{"text": {"content": notes}}]
        },
        "Score": {
            "number": score
        },
        "Stage": {
            "select": {"name": "Pool"}
        }
    }

    if job_url:
        properties["Posting URL"] = {"url": job_url}

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties
    }

    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload
    )

    if response.status_code == 200:
        print(f"✓ Written to Pool: {formatted_title} at {job.get('company')} — Score {score}/10")
        return True
    else:
        print(f"✗ Notion write failed for {job.get('title')}: {response.status_code} {response.text}")
        return False
    
# ── Step 6: Promote top Pool entries to Apply ───────────────────────────────────

def promote_top_apply():
    """Query all Pool entries, promote the top DAILY_APPLY_LIMIT by score to Apply."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

    # Only fetch Pool entries, sorted by Score descending
    body = {
        "filter": {
            "property": "Stage",
            "select": {"equals": "Pool"}
        },
        "sorts": [
            {"property": "Score", "direction": "descending"}
        ],
        "page_size": DAILY_APPLY_LIMIT
    }

    response = requests.post(url, headers=headers, json=body)
    data = response.json()
    pages = data.get("results", [])

    if not pages:
        print("No Pool entries to promote.")
        return

    promoted = 0
    for page in pages:
        page_id = page["id"]
        props = page.get("properties", {})
        company_parts = props.get("Company", {}).get("title", [])
        company = company_parts[0]["text"]["content"] if company_parts else "Unknown"
        score_val = props.get("Score", {}).get("number", 0)

        patch_resp = requests.patch(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={
                "properties": {
                    "Stage": {"select": {"name": "Apply"}}
                }
            }
        )

        if patch_resp.status_code == 200:
            print(f"↑ Promoted to Apply: {company} — Score {score_val}/10")
            promoted += 1
        else:
            print(f"✗ Failed to promote {company}: {patch_resp.status_code} {patch_resp.text}")

    print(f"Promoted {promoted} roles from Pool to Apply")

# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n=== Job Scout starting {datetime.today().strftime('%Y-%m-%d %H:%M')} ===\n")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Get existing Notion entries to avoid duplicates
    existing_urls, existing_fingerprints = get_existing_entries()

    # Fetch and filter jobs
    raw_jobs = fetch_jobs()
    filtered_jobs = hard_filter(raw_jobs)

    if not filtered_jobs:
        print("No jobs passed the hard filter today.")
    else:
        # Score each job and collect results
        scored = []
        for i, job in enumerate(filtered_jobs):
            print(f"Scoring {i+1}/{len(filtered_jobs)}: {job.get('title')} at {job.get('company')}")
            scored.append(score_job(client, job))

        # Sort by score descending
        scored.sort(key=lambda x: x.get("score", 0), reverse=True)

        # Write qualifying roles to Notion as Pool entries
        written = 0
        for job in scored:
            # FIX: Check if the score is high enough AND ensure it's not a hard block
            is_good_score = job.get("score", 0) >= REVIEW_THRESHOLD
            is_not_blocked = not job.get("exp_is_hard_block", False)

            if is_good_score and is_not_blocked:
                success = write_to_notion(job, existing_urls, existing_fingerprints)
                if success:
                    written += 1
                    existing_urls.add(str(job.get("job_url", "")))
                    existing_fingerprints.add(make_fingerprint(job.get("company", ""), job.get("title", "")))
            elif is_good_score and not is_not_blocked:
                # Optional: Print why it was rejected despite a good score
                print(f"Blocked by AI Experience Filter: {job.get('title')} at {job.get('company')}")

        print(f"\n{written} new roles added to Pool.\n")

    # Promote the top 4 from the entire Pool (new + carryover)
    print("── Promoting top roles to Apply ──")
    promote_top_apply()

    print(f"\n=== Run complete. ===\n")

if __name__ == "__main__":
    main()