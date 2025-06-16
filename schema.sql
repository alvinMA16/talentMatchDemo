DROP TABLE IF EXISTS resumes;

CREATE TABLE resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    skills TEXT,
    summary TEXT,
    experience_json TEXT,
    education_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(email),
    UNIQUE(phone)
); 