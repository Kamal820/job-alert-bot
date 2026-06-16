import requests
import sqlite3
import os
import json
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KEYWORDS = [
    "performance test", "performance testing", "load test",
    "jmeter", "loadrunner", "k6", "performance engineer"
]

TARGET_COMPANIES = [
    "standard chartered", "hsbc", "bnp paribas", "citi", "deutsche bank",
    "barclays", "bank of america", "bny mellon", "wells fargo",
    "hitachi energy", "caterpillar", "honeywell", "bosch", "renault nissan",
    "ford", "visteon", "paypal", "visa", "mastercard",
    "optum", "unitedhealth", "pwc", "valgenesis", "trimble",
    "comcast", "verizon", "allstate", "ups", "saviynt"
]

# Indeed job search URLs (India - no auth needed, public API)
SEARCH_QUERIES = [
    "performance+test+engineer+jmeter",
    "performance+test+engineer+loadrunner",
    "performance+engineer+k6+api",
    "load+test+engineer+dynatrace",
]

LOCATIONS = ["Chennai%2C+Tamil+Nadu", "Bengaluru%2C+Karnataka"]

DB_PATH = "seen_jobs.db"


# ── DATABASE ─────────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            job_id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            url TEXT,
            seen_at TEXT
        )
    """)
    conn.commit()
    return conn


def is_new_job(conn, job_id):
    row = conn.execute("SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return row is None


def mark_seen(conn, job_id, title, company, location, url):
    conn.execute(
        "INSERT OR IGNORE INTO seen_jobs VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, title, company, location, url, datetime.now().isoformat())
    )
    conn.commit()


# ── SCRAPER ──────────────────────────────────────────────────────────────────
def fetch_indeed_jobs():
    """Fetch jobs from Indeed India using their public RSS/JSON feed."""
    jobs = []
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    for query in SEARCH_QUERIES:
        for location in LOCATIONS:
            url = (
                f"https://in.indeed.com/jobs?q={query}"
                f"&l={location}&fromage=7&sort=date&format=json"
            )
            # Use Indeed's public RSS feed (no auth needed)
            rss_url = (
                f"https://in.indeed.com/rss?q={query}"
                f"&l={location}&fromage=7&sort=date"
            )
            try:
                resp = requests.get(rss_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    jobs.extend(parse_rss(resp.text, location))
            except Exception as e:
                print(f"Error fetching {rss_url}: {e}")

    return jobs


def parse_rss(xml_text, location):
    """Parse Indeed RSS feed XML into job dicts."""
    import xml.etree.ElementTree as ET
    jobs = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return jobs
        for item in channel.findall("item"):
            title = item.findtext("title", "").strip()
            company = ""
            # Indeed RSS puts company in title like "Job Title - Company"
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""

            link = item.findtext("link", "").strip()
            guid = item.findtext("guid", link).strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()
            loc_text = location.replace("%2C+", ", ").replace("+", " ")

            jobs.append({
                "id": guid,
                "title": title,
                "company": company,
                "location": loc_text,
                "url": link,
                "description": description,
                "pub_date": pub_date
            })
    except ET.ParseError as e:
        print(f"RSS parse error: {e}")
    return jobs


# ── FILTERS ──────────────────────────────────────────────────────────────────
def is_relevant(job):
    """Check if job matches our keywords."""
    text = f"{job['title']} {job['description']}".lower()
    return any(kw in text for kw in KEYWORDS)


def is_target_company(job):
    """Check if job is from one of our target companies (bonus flag)."""
    company = job["company"].lower()
    return any(tc in company for tc in TARGET_COMPANIES)


# ── TELEGRAM ─────────────────────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"Telegram error: {resp.text}")


def format_job_message(jobs):
    """Format new jobs into a clean Telegram message."""
    if not jobs:
        return None

    lines = [f"🔔 <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>"]
    lines.append(f"Found <b>{len(jobs)}</b> new performance testing role(s):\n")

    for i, job in enumerate(jobs, 1):
        star = "⭐ " if job.get("is_target") else ""
        lines.append(f"{i}. {star}<b>{job['title']}</b>")
        lines.append(f"   🏢 {job['company']}")
        lines.append(f"   📍 {job['location']}")
        if job.get("pub_date"):
            lines.append(f"   📅 {job['pub_date'][:16]}")
        lines.append(f"   🔗 <a href='{job['url']}'>View & Apply</a>")
        lines.append("")

    lines.append("─────────────────")
    lines.append("⭐ = Target GCC/Product company")
    return "\n".join(lines)


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Starting job alert run...")
    conn = init_db()

    all_jobs = fetch_indeed_jobs()
    print(f"Fetched {len(all_jobs)} total jobs from Indeed RSS")

    new_jobs = []
    for job in all_jobs:
        if not is_relevant(job):
            continue
        if not is_new_job(conn, job["id"]):
            continue
        job["is_target"] = is_target_company(job)
        new_jobs.append(job)
        mark_seen(conn, job["id"], job["title"], job["company"],
                  job["location"], job["url"])

    # Sort: target companies first
    new_jobs.sort(key=lambda j: (0 if j["is_target"] else 1, j["title"]))

    print(f"New relevant jobs: {len(new_jobs)}")

    if new_jobs:
        # Send in batches of 10 to avoid Telegram message length limits
        for i in range(0, len(new_jobs), 10):
            batch = new_jobs[i:i+10]
            msg = format_job_message(batch)
            if msg:
                send_telegram(msg)
                print(f"Sent batch {i//10 + 1} to Telegram")
    else:
        # Send a brief daily check-in even if no new jobs
        send_telegram(
            f"✅ <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>\n"
            f"No new performance testing roles found today. Will check again tomorrow!"
        )
        print("No new jobs — sent check-in message")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
