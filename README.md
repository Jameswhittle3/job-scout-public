# AI Job Scout Automation

An automated pipeline that scrapes job postings from major platforms, evaluates their fit against a specific candidate profile using Google Gemini, and pushes the best matches into a Notion database for review.

## Overview

1. **Scraping:** Fetches recent job postings from Indeed, LinkedIn, and Google Jobs based on custom search terms using `python-jobspy`.
2. **Hard Filtering:** Discards roles matching exclusion keywords (e.g., "Senior", "10+ years") to save on API processing time.
3. **AI Scoring:** Sends the surviving job descriptions to Google Gemini. The model scores the role out of 10 based on how well it aligns with the candidate's background as defined in the prompt.
4. **Notion Integration:** Roles that meet a minimum score threshold are formatted and injected directly into a Notion database.
5. **Promotion:** The system automatically tags a daily quota of the highest-scoring jobs to an "Apply" stage.

## Prerequisites

To run this project, you will need:
* **Python 3.12+**
* A **Google Gemini API Key**
* A **Notion Integration Secret** (API Key)
* A **Notion Database ID** *Note: The Notion database must have the following properties configured: `Company` (Title), `Position` (Select), `Job Description` (Rich Text), `ai-notes` (Rich Text), `Score` (Number), `Stage` (Select), and `Posting URL` (URL).*

## Configuration

The scout is modular and can be adapted by editing the following files:

### 1. prompt.txt
This file dictates how Gemini evaluates the jobs. Update this text file to reflect the candidate's actual background, goals, and hard filters. The prompt requires the output to be strictly valid JSON without preamble; leave the JSON formatting instructions intact at the bottom of the file.

### 2. job_scout.py
At the top of the script, you can adjust the search limits and logic thresholds:
* `DAILY_APPLY_LIMIT`: Number of top jobs promoted from the "Pool" to "Apply" each day (default: 4).
* `REVIEW_THRESHOLD`: The minimum score out of 10 a job needs to be saved to Notion (default: 8).
* `SEARCH_TERMS`: The job titles to scrape.
* `EXCLUDE_TITLE` & `EXCLUDE_DESC`: Lists inside the `hard_filter` function to instantly filter out bad matches before API scoring.

## Local Setup

To test the script on your local machine:

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt