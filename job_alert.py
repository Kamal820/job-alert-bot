import requests
import sqlite3
import os
import time
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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

# ── SEARCH QUERIES ────────────────────────────────────────────────────────────
# Generic performance testing searches
GENERIC_QUERIES = [
    "performance+test+engineer+jmeter",
    "performance+test+engineer+loadrunner",
    "performance+engineer+k6+api",
    "load+test+engineer+dynatrace",
    "performance+testing+grafana+prometheus",
]

# Company-specific searches — all 40 companies from tracker
COMPANY_QUERIES = [
    # Banking / Financial GCCs
    "performance+test+%22standard+chartered%22",
    "performance+test+%22hsbc%22",
    "performance+test+%22bnp+paribas%22",
    "performance+test+%22citi%22",
    "performance+test+%22deutsche+bank%22",
    "performance+test+%22barclays%22",
    "performance+test+%22bank+of+america%22",
    "performance+test+%22bny+mellon%22",
    "performance+test+%22wells+fargo%22",
    "performance+test+%22goldman+sachs%22",
    "performance+test+%22jpmorgan%22",
    "performance+test+%22morgan+stanley%22",
    # Industrial / Automotive GCCs
    "performance+test+%22hitachi+energy%22",
    "performance+test+%22caterpillar%22",
    "performance+test+%22honeywell%22",
    "performance+test+%22bosch%22",
    "performance+test+%22renault+nissan%22",
    "performance+test+%22ford%22",
    "performance+test+%22visteon%22",
    "performance+test+%22hyundai%22",
    "performance+test+%22john+deere%22",
    # Telecom / Insurance GCCs
    "performance+test+%22comcast%22",
    "performance+test+%22verizon%22",
    "performance+test+%22allstate%22",
    # Payments / Fintech
    "performance+test+%22paypal%22",
    "performance+test+%22visa%22",
    "performance+test+%22mastercard%22",
    "performance+test+%22phonepe%22",
    "performance+test+%22razorpay%22",
    "performance+test+%22cred%22",
    # E-commerce / Product
    "performance+test+%22flipkart%22",
    "performance+test+%22swiggy%22",
    "performance+test+%22zomato%22",
    # SaaS / Enterprise
    "performance+test+%22salesforce%22",
    "performance+test+%22servicenow%22",
    "performance+test+%22adobe%22",
    "performance+test+%22sap+labs%22",
    "performance+test+%22oracle%22",
    # Others
    "performance+test+%22optum%22",
    "performance+test+%22pwc%22",
    "performance+test+%22valgenesis%22",
    "performance+test+%22trimble%22",
    "performance+test+%22ups%22",
    "performance+test+%22saviynt%22",
    "performance+test+%22globallogic%22",
]

SEARCH_QUERIES = GENERIC_QUERIES + COMPANY_QUERIES
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
    """Fetch jobs from Indeed India using their public RSS feed."""
    jobs = []
    seen_guids = set()
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    }

    total = len(SEARCH_QUERIES) * len(LOCATIONS)
    count = 0

    for query in SEARCH_QUERIES:
        for location in LOCATIONS:
            count += 1
            rss_url = (
                f"https://in.indeed.com/rss?q={query}"
                f"&l={location}&fromage=7&sort=date"
            )
            try:
                resp = requests.get(rss_url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    new = parse_rss(resp.text, location, seen_guids)
                    jobs.extend(new)
                    print(f"[{count}/{total}] {query[:40]}... → {len(new)} jobs")
                else:
                    print(f"[{count}/{total}] HTTP {resp.status_code} for {query[:40]}")
            except Exception as e:
                print(f"[{count}/{total}] Error: {e}")

            # Small delay to avoid rate limiting
            time.sleep(1)

    return jobs


def parse_rss(xml_text, location, seen_guids):
    """Parse Indeed RSS feed XML into job dicts. Deduplicates by GUID."""
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
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else ""

            link = item.findtext("link", "").strip()
            guid = item.findtext("guid", link).strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()
            loc_text = location.replace("%2C+", ", ").replace("+", " ")

            # Skip duplicates across queries
            if guid in seen_guids:
                continue
            seen_guids.add(guid)

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
    """Check if job is from one of our 40 target companies."""
    text = f"{job['company']} {job['description']}".lower()
    return any(tc in text for tc in TARGET_COMPANIES)


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


def format_job_message(jobs, batch_num=1, total_batches=1):
    """Format new jobs into a clean Telegram message."""
    if not jobs:
        return None

    header = f"🔔 <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>"
    if total_batches > 1:
        header += f" (Part {batch_num}/{total_batches})"

    lines = [header]
    lines.append(f"Found <b>{len(jobs)}</b> new role(s):\n")

    for i, job in enumerate(jobs, 1):
        star = "⭐ " if job.get("is_target") else ""
        lines.append(f"{i}. {star}<b>{job['title']}</b>")
        lines.append(f"   🏢 {job['company']}")
        lines.append(f"   📍 {job['location']}")
        if job.get("pub_date"):
            lines.append(f"   📅 {job['pub_date'][:16]}")
        lines.append(f"   🔗 <a href='{job['url']}'>View &amp; Apply</a>")
        lines.append("")

    lines.append("─────────────────")
    lines.append("⭐ = One of your 40 target companies")
    return "\n".join(lines)


# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"[{datetime.now()}] Starting job alert run...")
    print(f"Total search queries: {len(SEARCH_QUERIES)} × {len(LOCATIONS)} locations")
    conn = init_db()

    all_jobs = fetch_indeed_jobs()
    print(f"\nTotal unique jobs fetched: {len(all_jobs)}")

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

    # Sort: target companies first, then by title
    new_jobs.sort(key=lambda j: (0 if j["is_target"] else 1, j["title"]))

    print(f"New relevant jobs after filtering: {len(new_jobs)}")

    if new_jobs:
        # Send in batches of 10 to stay within Telegram message limits
        batches = [new_jobs[i:i+10] for i in range(0, len(new_jobs), 10)]
        total_batches = len(batches)
        for i, batch in enumerate(batches, 1):
            msg = format_job_message(batch, batch_num=i, total_batches=total_batches)
            if msg:
                send_telegram(msg)
                print(f"Sent batch {i}/{total_batches} to Telegram")
                time.sleep(2)  # avoid Telegram rate limit
    else:
        send_telegram(
            f"✅ <b>Job Alert — {datetime.now().strftime('%d %b %Y')}</b>\n"
            f"Checked <b>{len(SEARCH_QUERIES)}</b> queries across 40 target companies.\n"
            f"No new performance testing roles found today. Will check again tomorrow!"
        )
        print("No new jobs — sent check-in message")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
