import requests
import sqlite3
import os
import time
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
RAPIDAPI_KEY     = os.environ["RAPIDAPI_KEY"]

KEYWORDS = [
    "performance test", "performance testing", "load test",
    "jmeter", "loadrunner", "k6", "performance engineer"
]

TARGET_COMPANIES = [
    # Banking / Financial GCCs
    "standard chartered", "hsbc", "bnp paribas", "citi", "citibank",
    "deutsche bank", "barclays", "bank of america", "bny mellon", "wells fargo",
    "goldman sachs", "jpmorgan", "morgan stanley",
    # Industrial / Automotive GCCs
    "hitachi energy", "caterpillar", "honeywell", "bosch",
    "renault nissan", "rntbci", "ford", "visteon", "hyundai", "john deere",
    # Telecom / Insurance GCCs
    "comcast", "verizon", "allstate",
    # Payments / Fintech
    "paypal", "visa", "mastercard", "phonepe", "razorpay", "cred",
    # E-commerce / Product
    "flipkart", "swiggy", "zomato",
    # SaaS / Enterprise
    "salesforce", "servicenow", "adobe", "sap", "oracle",
    # Others
    "optum", "unitedhealth", "pwc", "valgenesis", "trimble",
    "ups", "saviynt", "globallogic"
]

# Search queries — generic + one per target company
SEARCH_QUERIES = [
    # Generic
    "performance test engineer JMeter Chennai",
    "performance test engineer LoadRunner Chennai",
    "performance engineer k6 API Chennai",
    "load test engineer Dynatrace Chennai",
    "performance testing Grafana Prometheus Bangalore",
    # Company-specific
    "performance test engineer Standard Chartered India",
    "performance test engineer HSBC India",
    "performance test engineer BNP Paribas India",
    "performance test engineer Citi India",
    "performance test engineer Deutsche Bank India",
    "performance test engineer Barclays India",
    "performance test engineer Bank of America India",
    "performance test engineer BNY Mellon India",
    "performance test engineer Wells Fargo India",
    "performance test engineer Goldman Sachs India",
    "performance test engineer JPMorgan India",
    "performance test engineer Morgan Stanley India",
    "performance test engineer Hitachi Energy India",
    "performance test engineer Caterpillar India",
    "performance test engineer Honeywell India",
    "performance test engineer Bosch India",
    "performance test engineer Renault Nissan India",
    "performance test engineer Ford India",
    "performance test engineer Visteon India",
    "performance test engineer Hyundai India",
    "performance test engineer John Deere India",
    "performance test engineer Comcast India",
    "performance test engineer Verizon India",
    "performance test engineer Allstate India",
    "performance test engineer PayPal India",
    "performance test engineer Visa India",
    "performance test engineer Mastercard India",
    "performance test engineer PhonePe India",
    "performance test engineer Razorpay India",
    "performance test engineer CRED India",
    "performance test engineer Flipkart India",
    "performance test engineer Swiggy India",
    "performance test engineer Zomato India",
    "performance test engineer Salesforce India",
    "performance test engineer ServiceNow India",
    "performance test engineer Adobe India",
    "performance test engineer SAP Labs India",
    "performance test engineer Oracle India",
    "performance test engineer Optum India",
    "performance test engineer PwC India",
    "performance test engineer ValGenesis India",
    "performance test engineer Trimble India",
    "performance test engineer UPS India",
    "performance test engineer Saviynt India",
    "performance test engineer GlobalLogic India",
]

DB_PATH = "seen_jobs.db"

JSEARCH_URL = "https://jsearch.p.rapidapi.com/search"
JSEARCH_HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
}


# ── DATABASE ──────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id   TEXT PRIMARY KEY,
            title    TEXT,
            company  TEXT,
            location TEXT,
            url      TEXT,
            seen_at  TEXT
        )
    """)
    conn.commit()
    return conn


def is_new_job(conn, job_id):
    return conn.execute(
        "SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)
    ).fetchone() is None


def mark_seen(conn, job_id, title, company, location, url):
    conn.execute(
        "INSERT OR IGNORE INTO seen_jobs VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, title, company, location, url, datetime.now().isoformat())
    )
    conn.commit()


# ── JSEARCH API ───────────────────────────────────────────────────────────────
def fetch_jobs_for_query(query, seen_guids):
    """Call JSearch API for one query, return list of job dicts."""
    jobs = []
    params = {
        "query": query,
        "page": "1",
        "num_pages": "1",
        "date_posted": "week",         # jobs from last 7 days only
        "country": "in",               # India
    }
    try:
        resp = requests.get(
            JSEARCH_URL, headers=JSEARCH_HEADERS,
            params=params, timeout=20
        )
        if resp.status_code == 200:
            data = resp.json()
            for job in data.get("data", []):
                job_id = job.get("job_id", "")
                if not job_id or job_id in seen_guids:
                    continue
                seen_guids.add(job_id)

                title    = job.get("job_title", "").strip()
                company  = job.get("employer_name", "").strip()
                city     = job.get("job_city", "")
                state    = job.get("job_state", "")
                location = f"{city}, {state}".strip(", ")
                url      = job.get("job_apply_link") or job.get("job_google_link", "")
                desc     = job.get("job_description", "")
                posted   = job.get("job_posted_at_datetime_utc", "")[:10]

                jobs.append({
                    "id": job_id,
                    "title": title,
                    "company": company,
                    "location": location,
                    "url": url,
                    "description": desc,
                    "pub_date": posted
                })
        elif resp.status_code == 429:
            print(f"Rate limited — sleeping 10s")
            time.sleep(10)
        else:
            print(f"HTTP {resp.status_code} for query: {query}")
    except Exception as e:
        print(f"Error fetching '{query}': {e}")
    return jobs


def fetch_all_jobs():
    """Run all search queries with a small delay between each."""
    all_jobs = []
    seen_guids = set()
    total = len(SEARCH_QUERIES)

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"[{i}/{total}] {query}")
        jobs = fetch_jobs_for_query(query, seen_guids)
        all_jobs.extend(jobs)
        # 1.5s delay to stay within free tier rate limits (200 req/month)
        time.sleep(1.5)

    return all_jobs


# ── FILTERS ───────────────────────────────────────────────────────────────────
def is_relevant(job):
    text = f"{job['title']} {job['description']}".lower()
    return any(kw in text for kw in KEYWORDS)


def is_target_company(job):
    text = f"{job['company']} {job['description']}".lower()
    return any(tc in text for tc in TARGET_COMPANIES)


def is_india_location(job):
    """Filter out non-India results (JSearch is global)."""
    loc = job.get("location", "").lower()
    desc = job.get("description", "").lower()
    india_signals = ["india", "chennai", "bangalore", "bengaluru", "hyderabad",
                     "mumbai", "pune", "noida", "gurgaon", "gurugram"]
    return any(s in loc or s in desc for s in india_signals)


# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }, timeout=15)
    if resp.status_code != 200:
        print(f"Telegram error: {resp.text}")


def format_message(jobs, batch_num=1, total_batches=1):
    if not jobs:
        return None
    header = f"🔔 <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>"
    if total_batches > 1:
        header += f" ({batch_num}/{total_batches})"

    lines = [header, f"Found <b>{len(jobs)}</b> new role(s):\n"]
    for i, job in enumerate(jobs, 1):
        star = "⭐ " if job.get("is_target") else ""
        lines.append(f"{i}. {star}<b>{job['title']}</b>")
        lines.append(f"   🏢 {job['company']}")
        lines.append(f"   📍 {job['location']}")
        if job.get("pub_date"):
            lines.append(f"   📅 {job['pub_date']}")
        lines.append(f"   🔗 <a href='{job['url']}'>View &amp; Apply</a>")
        lines.append("")
    lines += ["─────────────────", "⭐ = One of your 40 target companies"]
    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Starting job alert run...")
    print(f"Queries: {len(SEARCH_QUERIES)} | Target companies: {len(TARGET_COMPANIES)}")
    conn = init_db()

    all_jobs = fetch_all_jobs()
    print(f"\nTotal unique jobs fetched: {len(all_jobs)}")

    new_jobs = []
    for job in all_jobs:
        if not is_india_location(job):
            continue
        if not is_relevant(job):
            continue
        if not is_new_job(conn, job["id"]):
            continue
        job["is_target"] = is_target_company(job)
        new_jobs.append(job)
        mark_seen(conn, job["id"], job["title"],
                  job["company"], job["location"], job["url"])

    new_jobs.sort(key=lambda j: (0 if j["is_target"] else 1, j["title"]))
    print(f"New relevant India jobs: {len(new_jobs)}")

    if new_jobs:
        batches = [new_jobs[i:i+10] for i in range(0, len(new_jobs), 10)]
        for i, batch in enumerate(batches, 1):
            msg = format_message(batch, i, len(batches))
            if msg:
                send_telegram(msg)
                print(f"Sent batch {i}/{len(batches)}")
                time.sleep(2)
    else:
        send_telegram(
            f"✅ <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>\n"
            f"Searched <b>{len(SEARCH_QUERIES)} queries</b> across 40 target companies "
            f"via JSearch (Indeed + LinkedIn + Glassdoor).\n"
            f"No new performance testing roles found today. Will check again tomorrow!"
        )
        print("No new jobs — sent check-in message")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
