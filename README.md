# 🎯 Automated EdTech & Development Opportunity Monitor

An automated data pipeline and alert system that aggregates, filters, and delivers targeted career, fellowship, and startup grant opportunities directly to an email inbox.

Built specifically to track opportunities at the intersection of **Instructional Design**, **Pedagogy (TSC Kenya)**, and **EdTech Innovation in Africa**.

---

## 🚀 Key Features

- **Multi-Source Ingestion:** Fetches real-time openings via the **ReliefWeb API** (UN/NGO humanitarian roles), the **Remotive API** (global remote EdTech/L&D positions), and **RSS Feeds** (scholarships and grants via Opportunity Desk).
- **Domain-Specific Filtering:** Implements structured boolean keyword matching tailored for education specialists, learning experience designers, and Kenyan educators.
- **Stateful Deduplication:** Uses an embedded **SQLite** database to store historical opportunity signatures, ensuring zero duplicate notifications.
- **Automated Cloud Dispatch:** Fully automated via **GitHub Actions** running on a daily cron schedule (`07:00 UTC`), eliminating the need for local server maintenance.
- **Rich HTML Digest:** Compiles daily findings into a structured, mobile-friendly email digest delivered via Gmail SMTP/TLS.

---

## 🛠️ Architecture & Tech Stack

- **Core Engine:** Python 3.10+
- **Data Ingestion:** `requests` (REST APIs), `feedparser` (RSS/XML)
- **Database / State Management:** SQLite (embedded)
- **CI/CD & Scheduling:** GitHub Actions (Linux Runner, Cron)
- **Email Delivery:** Python `smtplib` over TLS (Port 587)

---

## ⚙️ Local Setup & Configuration

1. **Clone the repository:**
   ```bash
   git clone https://github.com/upstreameduke-lab/opportunity-bot.git
   cd opportunity-bot
