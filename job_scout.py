import os
import json
import hashlib
import requests
from datetime import datetime
from google import genai
from jobspy import scrape_jobs

# ── Configuration ──────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
NOTION_API_KEY = os.environ["NOTION_API_KEY"]
NOTION_DATABASE_ID = os.environ["NOTION_DATABASE_ID"]

# Minimum score to write a role into your Applications database as Priority
PRIORITY_THRESHOLD = 7

# Minimum score to write a role into Applications at all
# Roles scoring between REVIEW_THRESHOLD and PRIORITY_THRESHOLD go in as non-priority
# for you to manually review once a week
REVIEW_THRESHOLD = 5

# How many hours back to look for new postings
HOURS_OLD = 48

# How many raw results to pull from job sites before filtering
RESULTS_PER_SITE = 30

# Job title search terms — broad enough to catch niche roles
SEARCH_TERMS = [
    "AI solutions engineer",
    "implementation engineer AI",
    "forward deployed engineer",
    "applied AI engineer",
    "AI agent developer",
    "AI engineer graduate",
    "solutions engineer machine learning",
    "digital twin engineer",
    "industrial AI engineer"
]

# ── System prompt ───────────────────────────────────────────────────────────────
# Paste the full text from your Candidate Profile page here
# This is read once at startup, not fetched from Notion every run

SYSTEM_PROMPT = """
You are a specialist job scout. Your task is to assess whether a job posting is a strong fit for the following candidate. Read this profile carefully before evaluating any role.

Who the candidate is:
Recent mechanical engineering graduate with a 14-month placement year at Knorr-Bremse in test and validation. Has independently built working AI-powered applications. Passionate about AI as a field, not just as a tool. Not a CS graduate but practically capable — comfortable with Python, APIs, and building with LLMs. Currently seeking a first full-time role after graduation.

Target roles:
The candidate is open to a variety of early-career roles at the intersection of AI and engineering. Any of the following are a strong fit:
- AI solutions engineering or implementation engineering
- Forward deployed engineering — embedded technical work directly with clients or end users
- AI agent development or applied AI engineering
- Roles intersecting physical engineering and AI — predictive maintenance, digital twins, simulation, industrial AI, robotics, autonomous systems
- Any niche early-career role where an engineering background is explicitly valued over a pure CS background

Why the background is an asset:
Mechanical engineers bring systems thinking, comfort with physical constraints, cross-disciplinary problem solving, and experience with test, validation, and real-world deployment that pure CS graduates typically lack. The placement year at Knorr-Bremse demonstrates applied engineering rigour in a regulated industrial environment. The independent AI projects demonstrate self-driven capability and genuine passion for the field beyond formal education.

Hard filters — do not recommend these:
- Roles with a hard stated minimum of 3 or more years of experience
- Senior, lead, principal, staff, head of, director, or management roles
- Pure software engineering roles with no AI, implementation, or physical engineering angle
- Roles at non-AI companies where AI is clearly peripheral to the core business

Soft negative bias — lower score but do not automatically exclude:
- Roles that explicitly require a CS degree as a stated requirement
- Roles that are purely research-oriented with no applied or implementation component
- Large enterprise or consulting firms with generic rotational graduate programmes

Preferences — these increase the score:
- Early-stage AI-native companies, typically 20–200 employees
- Product-led companies building AI products
- London-based or remote UK
- Roles where the JD explicitly mentions engineering background, physical systems, or domain expertise as valuable
- Any mention of mechanical, electrical, or physical engineering knowledge in the JD
- Roles involving direct customer or end-user contact on technical work

Scoring guide — score each role from 1 to 10:
- 9–10: Strong fit. Role explicitly values engineering background, involves AI implementation or applied work, early-career friendly, company is AI-native
- 7–8: Good fit. Role is clearly in the right space, experience requirement is flexible, background is plausible advantage
- 5–6: Possible. Role is adjacent but not perfectly shaped, or has one soft negative factor
- Below 5: Poor fit

Return ONLY valid JSON. No preamble, no markdown fences. Exactly this structure:
{
  "score": <integer 1-10>,
  "fit_reason": "<max 2 sentences explaining the score>",
  "keyword_gaps": ["<up to 5 skills in the JD you may need to surface>"],
  "mech_eng_asset": <true or false>,
  "exp_is_hard_block": <true or false>
}
"""

# ── Step 1: Fetch existing Notion URLs to avoid duplicates ──────────────────────

def get_existing_urls():
    """Fetch all posting URLs already in the Notion database to prevent duplicates."""
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    existing_urls = set()
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
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    print(f"Found {len(existing_urls)} existing URLs in Notion")
    return existing_urls

# ── Step 2: Scrape jobs ─────────────────────────────────────────────────────────

def fetch_jobs():
    """Fetch raw job results from Indeed, LinkedIn, and Google Jobs."""
    all_jobs = []
    seen_urls = set()

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
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_jobs.append(row.to_dict())
        except Exception as e:
            print(f"Search failed for '{term}': {e}")

    print(f"Total unique raw results: {len(all_jobs)}")
    return all_jobs

# ── Step 3: Hard filter ─────────────────────────────────────────────────────────

def hard_filter(jobs):
    """Remove obvious non-fits by title before spending any API credits."""
    EXCLUDE_TITLE = ["senior", "lead", "principal", "staff", "head of",
                     "director", "manager", "vp ", "vice president", "cto", "ceo"]
    EXCLUDE_DESC  = ["minimum 5 years", "minimum 4 years", "at least 5 years",
                     "at least 4 years", "10+ years", "8+ years", "7+ years"]

    filtered = []
    for job in jobs:
        title = str(job.get("title", "")).lower()
        desc  = str(job.get("description", "")).lower()
        if any(t in title for t in EXCLUDE_TITLE):
            continue
        if any(d in desc for d in EXCLUDE_DESC):
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

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=400,
            ),
        )
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        score_data = json.loads(text)
        return {**job, **score_data}
    except Exception as e:
        print(f"Scoring failed for {job.get('title')}: {e}")
        return {**job, "score": 0, "fit_reason": "Scoring error", 
                "keyword_gaps": [], "mech_eng_asset": False, "exp_is_hard_block": False}

# ── Step 5: Write to Notion ─────────────────────────────────────────────────────

def write_to_notion(job, existing_urls):
    """Write a single job to the Notion Applications database."""
    job_url = str(job.get("job_url", ""))

    # Skip if already in Notion
    if job_url and job_url in existing_urls:
        print(f"Skipping duplicate: {job.get('title')} at {job.get('company')}")
        return False

    score = job.get("score", 0)
    is_priority = score >= PRIORITY_THRESHOLD

    gaps = job.get("keyword_gaps", [])
    gaps_str = ", ".join(gaps) if gaps else "None identified"
    mech_asset = "Yes" if job.get("mech_eng_asset") else "No"

    notes = (
        f"Score: {score}/10 | {job.get('fit_reason', '')} | "
        f"Keyword gaps: {gaps_str} | Mech eng asset: {mech_asset} | "
        f"Found: {datetime.today().strftime('%Y-%m-%d')}"
    )

    # Only write to safe fields — Company (title), Job Description (text),
    # Posting URL (url), notes (text), Priority (checkbox)
    # Stage and Position are left for you to fill in manually
    # to avoid format errors with fixed option lists
    properties = {
        "Company": {
            "title": [{"text": {"content": str(job.get("company", "Unknown"))}}]
        },
        "Job Description": {
            "rich_text": [{"text": {"content": str(job.get("description", ""))[:2000]}}]
        },
        "notes": {
            "rich_text": [{"text": {"content": notes}}]
        },
        "Priority": {
            "checkbox": is_priority
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
        print(f"✓ Written to Notion: {job.get('title')} at {job.get('company')} — Score {score}/10")
        return True
    else:
        print(f"✗ Notion write failed for {job.get('title')}: {response.status_code} {response.text}")
        return False

# ── Main ────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n=== Job Scout starting {datetime.today().strftime('%Y-%m-%d %H:%M')} ===\n")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Get existing Notion URLs to avoid duplicates
    existing_urls = get_existing_urls()

    # Fetch and filter jobs
    raw_jobs = fetch_jobs()
    filtered_jobs = hard_filter(raw_jobs)

    if not filtered_jobs:
        print("No jobs passed the hard filter today. Exiting.")
        return

    # Score each job and collect results
    scored = []
    for i, job in enumerate(filtered_jobs):
        print(f"Scoring {i+1}/{len(filtered_jobs)}: {job.get('title')} at {job.get('company')}")
        scored.append(score_job(client, job))

    # Sort by score descending
    scored.sort(key=lambda x: x.get("score", 0), reverse=True)

    # Write qualifying roles to Notion
    written = 0
    for job in scored:
        score = job.get("score", 0)
        if score >= REVIEW_THRESHOLD:
            success = write_to_notion(job, existing_urls)
            if success:
                written += 1
                existing_urls.add(str(job.get("job_url", "")))

    print(f"\n=== Run complete. {written} new roles added to Notion. ===\n")

if __name__ == "__main__":
    main()