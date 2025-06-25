DROP TABLE IF EXISTS resumes;
DROP TABLE IF EXISTS job_descriptions;
DROP TABLE IF EXISTS facilitation_results;

CREATE TABLE resumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    skills TEXT,
    summary TEXT,
    experience_json TEXT,
    education_json TEXT,
    publications_json TEXT,
    projects_json TEXT,
    desensitized_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(email),
    UNIQUE(phone)
);

CREATE TABLE job_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    salary TEXT,
    requirements TEXT,
    description TEXT,
    benefits TEXT,
    desensitized_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE facilitation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resume_id INTEGER,
    jd_id INTEGER,
    candidate_decision TEXT,
    recruiter_decision TEXT,
    final_result TEXT,
    conversation_log TEXT,
    session_summary TEXT,
    facilitation_score INTEGER,
    strengths TEXT,
    improvements TEXT,
    recommendation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resume_id) REFERENCES resumes (id) ON DELETE CASCADE,
    FOREIGN KEY (jd_id) REFERENCES job_descriptions (id) ON DELETE CASCADE
); 