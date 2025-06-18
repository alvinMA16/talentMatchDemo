import sqlite3

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('talent_match.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def check_and_migrate_db():
    """Checks for table existence and adds them if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # List of all tables that should exist
    required_tables = {'resumes', 'job_descriptions', 'facilitation_results'}
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    missing_tables = required_tables - existing_tables
    
    if missing_tables:
        print(f"Detected missing tables: {', '.join(missing_tables)}. Applying schema...")
        with open('schema.sql') as f:
            conn.executescript(f.read())
        print("Database schema applied.")
    else:
        print("Database schema is up-to-date.")
    
    conn.close()

def get_prompt(filename):
    """Loads a prompt from the prompts directory."""
    try:
        with open(f'prompts/{filename}', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None 