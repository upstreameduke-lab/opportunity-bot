import os
import json
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
GMAIL_SENDER = os.getenv("GMAIL_SENDER", "YOUR_GMAIL@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "YOUR_16_CHAR_APP_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "YOUR_GMAIL@gmail.com")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

DB_FILE = "opportunities.db"

# Candidate Profile Matrix for the AI
CANDIDATE_PROFILE = """
- Professional: TSC-Registered Educator (Kenya) & Instructional / Learning Experience Designer (LXD).
- Core Skills: Curriculum Design, Pedagogy, E-Learning Development, MEL (Monitoring & Evaluation), EdTech.
- Geographic Location: Kenya (Eligible for remote globally, or local in Kenya/East Africa).
- Entrepreneurial/Academic Targets: African EdTech startup grants, fully-funded master's/PhD/fellowships, innovation challenges.
"""

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
# AI EVALUATION ENGINE (GEMINI 1.5 FLASH)
# ==========================================
def evaluate_with_ai(title, org, snippet):
    """Evaluates fit, extracts deadline, and generates a pitch using Google Gemini."""
    if not GEMINI_API_KEY or "YOUR_GEMINI" in GEMINI_API_KEY:
        # Fallback if no AI key is provided
        return {"match_score": 80, "deadline": "Check link", "winning_pitch": "Review listing for alignment.", "eligible": True}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    You are an executive career advisor evaluating opportunities for this specific candidate:
    {CANDIDATE_PROFILE}

    Evaluate this opportunity:
    - Title: {title}
    - Organization/Provider: {org}
    - Details: {snippet}

    Return a strict JSON object with these exact keys:
    {{
      "match_score": (Integer from 0 to 100 based on alignment with candidate's profile),
      "is_eligible": (Boolean, false ONLY if explicitly restricted away from Kenya/Africa or non-citizens),
      "deadline": (String, e.g. "October 25, 2024" or "Rolling / Not Stated"),
      "funding_or_comp": (String, estimated grant size or salary if mentioned, else "Not Disclosed"),
      "winning_pitch": (1-2 sharp, strategic sentences advising the candidate on how to pitch their TSC teaching + Instructional Design background for this specific role/grant)
    }}
    Return ONLY raw JSON. No markdown backticks.
    """

    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=15
        )
        if response.status_code == 200:
            res_text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean possible markdown ticks
            if res_text.startswith("```"):
                res_text = res_text.split("```")[1]
                if res_text.startswith("json"):
                    res_text = res_text[4:]
            return json.loads(res_text.strip())
    except Exception as e:
        print(f"AI evaluation fallback: {e}")

    return {"match_score": 75, "deadline": "Check post", "winning_pitch": "Leverage your teaching and LXD expertise.", "is_eligible": True}

# ==========================================
# COLLECTORS
# ==========================================
def fetch_reliefweb():
    """UN, NGOs, and Kenya/Remote Education Roles"""
    results = []
    url = "https://api.reliefweb.int/v1/jobs?appname=opportunity_bot&limit=25"
    payload = {
        "filter": {
            "operator": "AND",
            "conditions": [
                {
                    "operator": "OR",
                    "conditions": [
                        {"field": "theme", "value": "Education"},
                        {"field": "theme", "value": "Monitoring and Evaluation"}
                    ]
                },
                {
                    "operator": "OR",
                    "conditions": [
                        {"field": "country.name", "value": "Kenya"},
                        {"field": "type", "value": "Job"}
                    ]
                }
            ]
        },
        "fields": {"include": ["title", "url", "source", "body-html"]}
    }
    
    try:
        res = requests.post(url, json=payload, timeout=15).json()
        for item in res.get("data", []):
            item_id = str(item.get("id"))
            if is_new(item_id):
                fields = item.get("fields", {})
                results.append({
                    "id": item_id,
                    "title": fields.get("title", ""),
                    "org": fields.get("source", [{}])[0].get("name", "International NGO"),
                    "url": fields.get("url", ""),
                    "category": "Education, NGO & Pedagogy Roles",
                    "snippet": fields.get("title", "")
                })
    except Exception as e:
        print(f"Error ReliefWeb: {e}")
    return results

def fetch_remotive():
    """Global Remote Instructional Design & EdTech"""
    results = []
    url = "https://remotive.com/api/remote-jobs?category=all&limit=35"
    keywords = ["instructional", "learning", "curriculum", "education", "training", "pedagogy"]
    
    try:
        res = requests.get(url, timeout=15).json()
        for job in res.get("jobs", []):
            job_id = str(job.get("id"))
            title = job.get("title", "")
            if any(k in title.lower() for k in keywords) and is_new(job_id):
                results.append({
                    "id": job_id,
                    "title": title,
                    "org": job.get("company_name", "Remote Firm"),
                    "url": job.get("url", ""),
                    "category": "Global Remote LXD & EdTech",
                    "snippet": job.get("description", "")[:400]
                })
    except Exception as e:
        print(f"Error Remotive: {e}")
    return results

def fetch_opportunity_desk():
    """Grants, Fellowships, and Accelerators"""
    results = []
    feed = feedparser.parse("https://opportunitydesk.org/feed/")
    keywords = ["grant", "fellowship", "scholarship", "accelerator", "funding", "seed", "award", "africa"]
    
    for entry in feed.entries:
        entry_id = entry.link
        title = entry.title
        summary = entry.get("summary", "")
        if any(k in f"{title} {summary}".lower() for k in keywords) and is_new(entry_id):
            cat = "Startup Grants & Innovation Funds" if any(w in title.lower() for w in ["grant", "fund", "accelerator", "startup"]) else "Scholarships & Fellowships"
            results.append({
                "id": entry_id,
                "title": title,
                "org": "Opportunity Desk",
                "url": entry.link,
                "category": cat,
                "snippet": summary[:400]
            })
    return results

# ==========================================
# EXECUTIVE BRIEFING BUILDER
# ==========================================
def build_executive_digest(evaluated_items):
    grouped = {}
    for item in evaluated_items:
        grouped.setdefault(item["category"], []).append(item)

    cards_html = ""
    for category, opps in grouped.items():
        cards_html += f"""
        <div style="margin-top: 30px;">
            <h2 style="font-size: 16px; text-transform: uppercase; letter-spacing: 1px; color: #475569; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                {category} ({len(opps)})
            </h2>
        """
        for opp in opps:
            ai = opp["ai"]
            score = ai.get("match_score", 75)
            badge_color = "#16a34a" if score >= 85 else "#2563eb"

            cards_html += f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 18px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
                    <span style="background: {badge_color}; color: #ffffff; font-size: 11px; font-weight: 700; padding: 4px 8px; border-radius: 20px;">
                        {score}% MATCH
                    </span>
                    <span style="font-size: 12px; color: #dc2626; font-weight: 600;">
                        ⏳ {ai.get('deadline', 'Check site')}
                    </span>
                </div>
                <h3 style="font-size: 17px; margin: 4px 0 2px 0; color: #0f172a;">{opp['title']}</h3>
                <div style="font-size: 13px; color: #64748b; margin-bottom: 10px;">Organization: <b>{opp['org']}</b></div>
                
                <div style="background: #f8fafc; border-left: 3px solid #0284c7; padding: 10px; border-radius: 4px; font-size: 13px; color: #334155; margin-bottom: 12px;">
                    <b>💡 Your Winning Angle:</b> {ai.get('winning_pitch', 'Pitch your unique pedagogy + LXD experience.')}
                </div>
                
                <a href="{opp['url']}" target="_blank" style="display: inline-block; background: #0f172a; color: #ffffff; padding: 7px 14px; border-radius: 5px; font-size: 13px; font-weight: 500; text-decoration: none;">
                    View & Apply &rarr;
                </a>
            </div>
            """
        cards_html += "</div>"

    return f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f1f5f9; padding: 25px;">
        <div style="max-width: 680px; margin: 0 auto; background: #fafafa; padding: 30px; border-radius: 12px;">
            <div style="border-bottom: 1px solid #cbd5e1; padding-bottom: 15px;">
                <h1 style="font-size: 22px; color: #0f172a; margin: 0;">🎯 Executive Intelligence Briefing</h1>
                <p style="color: #64748b; font-size: 13px; margin: 5px 0 0 0;">
                    Tailored for: <b>TSC Educator & Instructional Designer (Kenya)</b> &bull; {datetime.now().strftime('%B %d, %Y')}
                </p>
            </div>
            {cards_html}
            <div style="text-align: center; margin-top: 35px; font-size: 11px; color: #94a3b8;">
                AI Opportunity Agent &bull; Evaluated by Gemini 1.5 Flash
            </div>
        </div>
    </body>
    </html>
    """

def send_digest(items):
    if not items:
        print("No high-relevance opportunities found today.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 AI Career Briefing: {len(items)} High-Fit Opportunities"
    msg["From"] = GMAIL_SENDER
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(build_executive_digest(items), "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD.replace(" ", ""))
        server.sendmail(GMAIL_SENDER, RECIPIENT_EMAIL, msg.as_string())
        server.quit()
        print(f"Executive Briefing sent! ({len(items)} qualified items)")

        for item in items:
            mark_as_seen(item["id"], item["title"], item["category"])
    except Exception as e:
        print(f"Failed to send email: {e}")

# ==========================================
# MAIN PIPELINE
# ==========================================
def run_pipeline():
    init_db()
    print("1. Harvesting raw opportunities across global feeds...")
    raw = []
    raw.extend(fetch_reliefweb())
    raw.extend(fetch_remotive())
    raw.extend(fetch_opportunity_desk())
    print(f"-> Harvested {len(raw)} potential new items.")

    print("2. Running AI Semantic Evaluation on candidates...")
    qualified = []
    for opp in raw:
        evaluation = evaluate_with_ai(opp["title"], opp["org"], opp["snippet"])
        score = evaluation.get("match_score", 0)
        eligible = evaluation.get("is_eligible", True)

        # Quality Threshold: Only keep matches that score 70%+ and are open to Kenya
        if score >= 70 and eligible:
            opp["ai"] = evaluation
            qualified.append(opp)
            print(f"   [PASSED - {score}%] {opp['title']}")
        else:
            print(f"   [FILTERED - {score}%] {opp['title']}")

    # Sort descending by match score (highest quality first)
    qualified.sort(key=lambda x: x["ai"].get("match_score", 0), reverse=True)

    print(f"3. Dispatching briefing with {len(qualified)} vetted opportunities...")
    send_digest(qualified)

if __name__ == "__main__":
    run_pipeline()
