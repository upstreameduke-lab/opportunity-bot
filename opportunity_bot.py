import os
import sqlite3
import smtplib
import feedparser
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
# ==========================================
# CONFIGURATION
# ==========================================
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "YOUR_GMAIL@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "YOUR_16_CHAR_APP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "YOUR_GMAIL@gmail.com")

DB_FILE = "opportunities.db"

# ==========================================
# KEYWORD FILTERS
# ==========================================
JOB_KEYWORDS = [
    "instructional designer", "learning experience designer", "learning designer",
    "curriculum designer", "instructional technologist", "l&d specialist",
    "learning and development", "education program manager", "education officer",
    "e-learning specialist", "digital learning", "mel officer", "monitoring evaluation"
]

FUNDING_KEYWORDS = [
    "edtech accelerator", "grant", "seed funding", "innovation challenge",
    "startup competition", "fellowship", "proof of concept", "entrepreneurship fund",
    "tony elumelu", "villgro", "mit solve", "unicef innovation"
]

SCHOLARSHIP_KEYWORDS = [
    "fully funded", "master's scholarship", "phd scholarship", "graduate fellowship",
    "emerging leaders", "young leaders", "global scholars", "learning sciences"
]

# ==========================================
# DATABASE (DEDUPLICATION)
# ==========================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS seen_opportunities (
            id TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            found_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def is_new(item_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM seen_opportunities WHERE id = ?", (item_id,))
    result = c.fetchone()
    conn.close()
    return result is None

def mark_as_seen(item_id, title, source):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO seen_opportunities VALUES (?, ?, ?, ?)",
              (item_id, title, source, datetime.utcnow()))
    conn.commit()
    conn.close()

# ==========================================
# COLLECTORS
# ==========================================

def fetch_reliefweb_jobs():
    """Fetches NGO/UN jobs (UNICEF, Save the Children, World Bank, etc.)"""
    results = []
    url = "https://api.reliefweb.int/v1/jobs?appname=opportunity_bot&limit=30"
    
    payload = {
        "filter": {
            "operator": "OR",
            "conditions": [
                {"field": "theme", "value": "Education"},
                {"field": "theme", "value": "Monitoring and Evaluation"}
            ]
        },
        "fields": {"include": ["title", "url", "source", "body"]}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=15).json()
        for item in res.get("data", []):
            item_id = str(item.get("id"))
            fields = item.get("fields", {})
            title = fields.get("title", "")
            apply_url = fields.get("url", "")
            org = fields.get("source", [{}])[0].get("name", "NGO")
            
            # Match keywords
            full_text = f"{title}".lower()
            if any(k in full_text for k in JOB_KEYWORDS):
                if is_new(item_id):
                    results.append({
                        "category": "International Dev & NGO Jobs",
                        "title": title,
                        "org": org,
                        "url": apply_url,
                        "id": item_id
                    })
    except Exception as e:
        print(f"Error fetching ReliefWeb: {e}")
        
    return results

def fetch_remotive_jobs():
    """Fetches remote Tech, L&D, and Design roles"""
    results = []
    url = "https://remotive.com/api/remote-jobs?limit=50"
    
    try:
        res = requests.get(url, timeout=15).json()
        for job in res.get("jobs", []):
            job_id = str(job.get("id"))
            title = job.get("title", "")
            company = job.get("company_name", "")
            apply_url = job.get("url", "")
            
            full_text = f"{title}".lower()
            if any(k in full_text for k in JOB_KEYWORDS):
                if is_new(job_id):
                    results.append({
                        "category": "Remote L&D / EdTech Roles",
                        "title": title,
                        "org": company,
                        "url": apply_url,
                        "id": job_id
                    })
    except Exception as e:
        print(f"Error fetching Remotive: {e}")
        
    return results

def fetch_opportunity_desk():
    """Fetches Scholarships, Fellowships, and Startup Grants via RSS"""
    results = []
    feed_url = "https://opportunitydesk.org/feed/"
    feed = feedparser.parse(feed_url)
    
    for entry in feed.entries:
        entry_id = entry.link
        title = entry.title
        summary = entry.get("summary", "").lower()
        full_text = f"{title} {summary}".lower()
        
        # Categorize
        cat = None
        if any(k in full_text for k in FUNDING_KEYWORDS):
            cat = "Startup Funding & Grants"
        elif any(k in full_text for k in SCHOLARSHIP_KEYWORDS):
            cat = "Scholarships & Fellowships"
            
        if cat and is_new(entry_id):
            results.append({
                "category": cat,
                "title": title,
                "org": "Opportunity Desk",
                "url": entry.link,
                "id": entry_id
            })
            
    return results

# ==========================================
# EMAIL BUILDER & DISPATCHER
# ==========================================

def build_html_email(items):
    """Formats findings into a clean, modern email digest."""
    # Group items by category
    grouped = {}
    for item in items:
        grouped.setdefault(item["category"], []).append(item)
        
    body_content = ""
    for category, opps in grouped.items():
        body_content += f"""
        <h2 style="color: #1a365d; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 25px;">
            {category} ({len(opps)})
        </h2>
        <ul style="list-style-type: none; padding-left: 0;">
        """
        for opp in opps:
            body_content += f"""
            <li style="margin-bottom: 14px; padding: 12px; background: #f8fafc; border-radius: 6px; border-left: 4px solid #2563eb;">
                <div style="font-size: 16px; font-weight: bold; color: #0f172a;">{opp['title']}</div>
                <div style="font-size: 13px; color: #64748b; margin-top: 2px;">Provider / Organization: {opp['org']}</div>
                <div style="margin-top: 6px;">
                    <a href="{opp['url']}" style="color: #2563eb; text-decoration: none; font-weight: 500;" target="_blank">
                        View Opportunity & Apply &rarr;
                    </a>
                </div>
            </li>
            """
        body_content += "</ul>"

    html = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; padding: 20px;">
        <div style="max-width: 650px; margin: 0 auto; background: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
            <h1 style="color: #0f172a; margin-top: 0; font-size: 22px;">🎯 Daily Opportunities Digest</h1>
            <p style="color: #64748b; font-size: 14px;">Here are the new openings matching your criteria for today ({datetime.now().strftime('%B %d, %Y')}):</p>
            {body_content}
            <div style="margin-top: 35px; padding-top: 15px; border-top: 1px solid #e2e8f0; text-align: center; color: #94a3b8; font-size: 12px;">
                Automated Opportunities Bot &bull; Filtered for Learning Design, Funding & Fellowships
            </div>
        </div>
    </body>
    </html>
    """
    return html

def send_digest(items):
    if not items:
        print("No new opportunities matching your criteria today.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Daily Digest: {len(items)} New Opportunities Found"
    msg["From"] = GMAIL_SENDER
    msg["To"] = RECIPIENT_EMAIL
    
    html_content = build_html_email(items)
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        # Use Port 587 with STARTTLS instead of 465
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD.replace(" ", ""))  # removes any spaces
        server.sendmail(GMAIL_SENDER, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print(f"Digest successfully sent! ({len(items)} items included)")
        
        # Mark all sent items as seen
        for item in items:
            mark_as_seen(item["id"], item["title"], item["category"])
            
    except Exception as e:
        print(f"Failed to send email: {e}")

# ==========================================
# MAIN EXECUTION
# ==========================================
def run_pipeline():
    init_db()
    print("Fetching opportunities across sources...")
    
    all_new_opportunities = []
    all_new_opportunities.extend(fetch_reliefweb_jobs())
    all_new_opportunities.extend(fetch_remotive_jobs())
    all_new_opportunities.extend(fetch_opportunity_desk())
    
    print(f"Found {len(all_new_opportunities)} new matched opportunities.")
    send_digest(all_new_opportunities)

if __name__ == "__main__":
    run_pipeline()