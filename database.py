import sqlite3

DB_PATH = "company_interviews.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS interviews (
                id TEXT PRIMARY KEY,
                candidate_name TEXT,
                target_role TEXT,
                resume_text TEXT,
                selected_questions TEXT,
                status TEXT DEFAULT 'IN_PROGRESS',
                overall_score INTEGER DEFAULT 0,
                hiring_decision TEXT DEFAULT 'Pending',
                recruiter_summary TEXT DEFAULT '{}',
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                interview_id TEXT,
                role TEXT,
                content TEXT,
                created_at TEXT
            )
        """)
init_db()