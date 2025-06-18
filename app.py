import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
import json
import sqlite3
import pathlib
import google.generativeai as genai
import pandas as pd
import io
from werkzeug.utils import secure_filename
from helpers import get_prompt, get_db_connection, check_and_migrate_db
from resume_generator import resume_generator_bp

# --- Database Setup ---
DATABASE = 'talent_match.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_desensitized_version(resume_data):
    """Calls GenAI to create a desensitized version of the resume."""
    if os.environ.get("GOOGLE_API_KEY") is None:
        print("Warning: GOOGLE_API_KEY not found. Skipping desensitization.")
        # Return the original data with PII cleared as a fallback
        fallback_data = resume_data.copy()
        fallback_data['name'] = "Candidate"
        fallback_data['email'] = "hidden"
        fallback_data['phone'] = "hidden"
        return fallback_data

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = get_prompt('desensitize_resume.txt')
        if not prompt:
            raise Exception("Could not load desensitization prompt.")

        # Convert python dict to a JSON string to send to the model
        resume_json_string = json.dumps(resume_data)

        response = model.generate_content([prompt, resume_json_string])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        desensitized_data = json.loads(cleaned_text)
        return desensitized_data
    except Exception as e:
        print(f"Error during desensitization: {e}")
        # In case of failure, return the original data to avoid breaking the flow
        return resume_data

def get_desensitized_jd_version(jd_data):
    """Calls GenAI to create a desensitized version of the job description."""
    if os.environ.get("GOOGLE_API_KEY") is None:
        print("Warning: GOOGLE_API_KEY not found. Skipping JD desensitization.")
        # Return the original data with sensitive info cleared as a fallback
        fallback_data = jd_data.copy()
        fallback_data['company'] = "某公司"
        return fallback_data

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = get_prompt('desensitize_jd.txt')
        if not prompt:
            raise Exception("Could not load JD desensitization prompt.")

        # Convert python dict to a JSON string to send to the model
        jd_json_string = json.dumps(jd_data)

        response = model.generate_content([prompt, jd_json_string])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        desensitized_data = json.loads(cleaned_text)
        return desensitized_data
    except Exception as e:
        print(f"Error during JD desensitization: {e}")
        # In case of failure, return the original data to avoid breaking the flow
        return jd_data

def get_prompt(filename):
    """Loads a prompt from the prompts directory."""
    try:
        with open(f'prompts/{filename}', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None

def init_db():
    conn = get_db_connection()
    with open('schema.sql', 'r') as f:
        conn.executescript(f.read())
    conn.close()
    print("Database initialized.")

# 配置GenAI
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    print("Google API Key configured successfully.")
except KeyError:
    print("Warning: GOOGLE_API_KEY not found in environment variables. Upload feature will not work.")
    genai.configure(api_key="mock-api-key") # Avoid crashing if key is not set

# 创建Flask应用实例
app = Flask(__name__)
app.config['SECRET_KEY'] = 'talent-match-secret-key'

# Define constants
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'json', 'xlsx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Register Blueprints
app.register_blueprint(resume_generator_bp)

# Initialize and migrate database
with app.app_context():
    check_and_migrate_db()

# 模拟数据存储
resumes = []
# job_descriptions = [] # Will be fetched from DB

# 首页路由 - 默认显示Resume管理
@app.route('/')
def index():
    return redirect(url_for('resume_management'))

# Resume管理页面
@app.route('/resume')
def resume_management():
    conn = get_db_connection()
    resumes_from_db = conn.execute('SELECT * FROM resumes ORDER BY created_at DESC').fetchall()
    conn.close()
    
    resumes = []
    for r in resumes_from_db:
        resume = dict(r)
        # Safely parse JSON fields
        try:
            resume['experience'] = json.loads(r['experience_json']) if r['experience_json'] else []
        except json.JSONDecodeError:
            resume['experience'] = r['experience_json'] # Store as plain text if not valid JSON
        try:
            resume['education'] = json.loads(r['education_json']) if 'education_json' in r.keys() and r['education_json'] else []
        except json.JSONDecodeError:
            resume['education'] = r['education_json']
        try:
            resume['publications'] = json.loads(r['publications_json']) if 'publications_json' in r.keys() and r['publications_json'] else []
        except json.JSONDecodeError:
            resume['publications'] = r['publications_json'] if 'publications_json' in r.keys() else ''
        try:
            resume['projects'] = json.loads(r['projects_json']) if 'projects_json' in r.keys() and r['projects_json'] else []
        except json.JSONDecodeError:
            resume['projects'] = r['projects_json'] if 'projects_json' in r.keys() else ''
        
        # Safely parse desensitized data
        try:
            resume['desensitized'] = json.loads(r['desensitized_json']) if 'desensitized_json' in r.keys() and r['desensitized_json'] else None
        except (json.JSONDecodeError, TypeError):
            resume['desensitized'] = None

        resumes.append(resume)

    return render_template('resume.html', resumes=resumes)

# JD管理页面
@app.route('/jd')
def jd_management():
    conn = get_db_connection()
    jds_from_db = conn.execute('SELECT * FROM job_descriptions ORDER BY created_at DESC').fetchall()
    conn.close()
    job_descriptions = [dict(jd) for jd in jds_from_db]
    
    # Parse desensitized data for each JD
    for jd in job_descriptions:
        try:
            jd['desensitized'] = json.loads(jd['desensitized_json']) if jd.get('desensitized_json') else None
        except (json.JSONDecodeError, TypeError):
            jd['desensitized'] = None
    
    return render_template('jd.html', job_descriptions=job_descriptions)

# 人岗撮合页面
@app.route('/facilitate')
def talent_facilitate():
    conn = get_db_connection()
    
    # Fetch resumes sorted by ID
    resumes = conn.execute('SELECT id, name FROM resumes ORDER BY id ASC').fetchall()
    
    # Fetch job descriptions sorted by ID
    jds = conn.execute('SELECT id, title, company FROM job_descriptions ORDER BY id ASC').fetchall()
    
    # Fetch facilitation history
    history_query = """
        SELECT
            fr.id,
            fr.created_at,
            r.name as resume_name,
            j.title as jd_title
        FROM facilitation_results fr
        JOIN resumes r ON fr.resume_id = r.id
        JOIN job_descriptions j ON fr.jd_id = j.id
        ORDER BY fr.created_at DESC;
    """
    facilitation_history = conn.execute(history_query).fetchall()
    
    conn.close()

    return render_template('facilitate.html', resumes=resumes, job_descriptions=jds, facilitation_history=facilitation_history)

# API: 批量上传简历 (处理单个文件)
@app.route('/api/resume/batch_upload', methods=['POST'])
def batch_upload_resume():
    if 'resume_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part in the request'}), 400

    file = request.files['resume_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400

    if not file or not file.filename.endswith('.pdf'):
        return jsonify({'status': 'error', 'message': 'Invalid file type, only PDF is supported'}), 400

    try:
        # 1. AI Parsing
        if os.environ.get("GOOGLE_API_KEY") is None:
            return jsonify({'status': 'error', 'message': 'Google API Key not configured'}), 500

        pdf_bytes = file.read()
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = get_prompt('extract_resume_info.txt')
        if not prompt:
            return jsonify({'status': 'error', 'message': 'Could not load resume extraction prompt.'}), 500

        response = model.generate_content([
            {"mime_type": "application/pdf", "data": pdf_bytes},
            prompt
        ])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        data = json.loads(cleaned_text)

        # 2. Desensitize the extracted data
        desensitized_data = get_desensitized_version(data)

        # 3. Duplicate Check
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        
        if not name:
             return jsonify({'status': 'error', 'message': 'Failed to extract candidate name.'})

        conn = get_db_connection()
        query = "SELECT id FROM resumes WHERE name = ? OR (email != '' AND email = ?) OR (phone != '' AND phone = ?)"
        existing = conn.execute(query, (name, email, phone)).fetchone()

        if existing:
            conn.close()
            return jsonify({'status': 'duplicate', 'message': f"Candidate already exists (ID: {existing['id']})"})

        # 4. Insert into DB
        conn.execute(
            """
            INSERT INTO resumes (name, email, phone, skills, summary, experience_json, education_json, publications_json, projects_json, desensitized_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, email, phone,
                data.get('skills', ''),
                data.get('summary', ''),
                json.dumps(data.get('experience', [])),
                json.dumps(data.get('education', [])),
                json.dumps(data.get('publications', [])),
                json.dumps(data.get('projects', [])),
                json.dumps(desensitized_data)
            )
        )
        conn.commit()
        conn.close()
        
        return jsonify({'status': 'success', 'message': 'Resume added successfully'})

    except Exception as e:
        print(f"Batch upload error for {file.filename}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API: 上传并解析简历
@app.route('/api/resume/upload', methods=['POST'])
def upload_resume():
    if 'resume_file' not in request.files:
        return jsonify({'status': 'error', 'message': '没有找到文件部分'}), 400

    file = request.files['resume_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '没有选择文件'}), 400

    if file and file.filename.endswith('.pdf'):
        try:
            # Check if API key is mocked
            if os.environ.get("GOOGLE_API_KEY") is None:
                return jsonify({'status': 'error', 'message': 'Google API Key未设置，无法解析简历。'}), 500

            pdf_bytes = file.read()
            
            prompt = get_prompt('extract_resume_info.txt')
            if not prompt:
                 return jsonify({'status': 'error', 'message': 'Could not load resume extraction prompt.'}), 500
            
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content([
                {
                    "mime_type": "application/pdf",
                    "data": pdf_bytes
                },
                prompt
            ])

            # 清理和解析响应
            cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
            extracted_data = json.loads(cleaned_text)
            
            # 打印log
            print(f"=================Extracted data===============:\n {extracted_data}")

            return jsonify({
                'status': 'success',
                'message': '简历解析成功',
                'data': extracted_data
            })           

        except Exception as e:
            print(f"Error parsing resume: {e}")
            return jsonify({'status': 'error', 'message': f'简历解析失败: {e}'}), 500

    return jsonify({'status': 'error', 'message': '只支持PDF文件格式'}), 400

# API: 添加简历
@app.route('/api/resume', methods=['POST'])
def add_resume():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

    name = data.get('name')
    email = data.get('email')
    phone = data.get('phone')

    conn = get_db_connection()

    # Check for duplicates
    query = "SELECT * FROM resumes WHERE name = ? OR (email != '' AND email = ?) OR (phone != '' AND phone = ?)"
    existing = conn.execute(query, (name, email, phone)).fetchone()
    
    if existing:
        conn.close()
        return jsonify({
            'status': 'duplicate',
            'message': f"A candidate with similar info already exists (ID: {existing['id']}, Name: {existing['name']}). Please review before adding another."
        })

    # Get desensitized version
    desensitized_data = get_desensitized_version(data)

    # Insert new resume
    conn.execute(
        """
        INSERT INTO resumes (name, email, phone, skills, summary, experience_json, education_json, publications_json, projects_json, desensitized_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            email,
            phone,
            data.get('skills', ''),
            data.get('summary', ''),
            json.dumps(data.get('experience', [])),
            json.dumps(data.get('education', [])),
            json.dumps(data.get('publications', [])),
            json.dumps(data.get('projects', [])),
            json.dumps(desensitized_data)
        )
    )
    conn.commit()
    new_resume_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    new_resume = conn.execute('SELECT * FROM resumes WHERE id = ?', (new_resume_id,)).fetchone()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': '简历添加成功',
        'resume': dict(new_resume)
    })

# API: 删除简历
@app.route('/api/resume/<int:resume_id>', methods=['DELETE'])
def delete_resume(resume_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM resumes WHERE id = ?', (resume_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': '简历删除成功'})

# API: 批量上传职位描述
@app.route('/api/jd/batch_upload', methods=['POST'])
def batch_upload_jd():
    if 'jd_file' not in request.files:
        return jsonify({'status': 'error', 'message': 'No file part in the request'}), 400

    file = request.files['jd_file']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'No file selected'}), 400

    # Read the file into memory immediately to prevent "I/O operation on closed file"
    # in the generator that is executed after this function returns.
    file_content = file.read()
    filename = file.filename.lower()

    def generate_progress():
        # 1. Read file content based on type
        jobs_to_process = []
        try:
            if filename.endswith(('.xlsx', '.xls')):
                # Use io.BytesIO to let pandas read from the in-memory bytes
                df = pd.read_excel(io.BytesIO(file_content))
                df['combined_text'] = df.apply(lambda row: ' '.join(row.astype(str)), axis=1)
                jobs_to_process = [{'source': f"Row {i+2}", 'content': row['combined_text']} for i, row in df.iterrows()]
            elif filename.endswith('.json'):
                # Decode bytes to string for json.loads
                raw_data = json.loads(file_content.decode('utf-8'))
                if isinstance(raw_data, list):
                    jobs_to_process = [{'source': f"Object {i+1}", 'content': json.dumps(obj)} for i, obj in enumerate(raw_data)]
                else:
                    yield f"data: {json.dumps({'status': 'error', 'message': 'JSON file must contain a list of job objects.'})}\n\n"
                    return
            else:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Unsupported file type. Please use JSON, XLSX, or XLS.'})}\n\n"
                return
        except Exception as e:
            yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to read or parse file: {e}'})}\n\n"
            return

        # 2. Process each job with GenAI
        if os.environ.get("GOOGLE_API_KEY") is None:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Google API Key not configured'})}\n\n"
            return
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = get_prompt('extract_jd_info.txt')
        if not prompt:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Could not load JD extraction prompt.'})}\n\n"
            return

        total_jobs = len(jobs_to_process)
        success_count = 0
        failures = []
        conn = get_db_connection()

        for i, job in enumerate(jobs_to_process):
            try:
                response = model.generate_content([job['content'], prompt])
                cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
                data = json.loads(cleaned_text)

                title = data.get('title')
                if not title:
                    raise ValueError('Failed to extract job title.')
                
                # Get desensitized version
                desensitized_data = get_desensitized_jd_version(data)
                
                company = data.get('company', '')
                existing = conn.execute('SELECT id FROM job_descriptions WHERE title = ? AND company = ?', (title, company)).fetchone()
                if existing:
                    raise ValueError(f'Duplicate job already exists (ID: {existing["id"]})')

                conn.execute(
                    """
                    INSERT INTO job_descriptions (title, company, location, salary, requirements, description, benefits, desensitized_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (title, company, data.get('location', ''), data.get('salary', ''), data.get('requirements', ''), data.get('description', ''), data.get('benefits', ''), json.dumps(desensitized_data))
                )
                conn.commit()
                success_count += 1
                yield f"data: {json.dumps({'type': 'progress', 'processed': i + 1, 'total': total_jobs, 'source': job['source']})}\n\n"

            except Exception as e:
                failures.append({'source': job['source'], 'reason': str(e)})
                yield f"data: {json.dumps({'type': 'progress', 'processed': i + 1, 'total': total_jobs, 'source': job['source'], 'error': str(e)})}\n\n"
        
        conn.close()

        yield f"data: {json.dumps({'type': 'complete', 'success_count': success_count, 'failures': failures})}\n\n"

    return Response(generate_progress(), mimetype='text/event-stream')

# API: 添加职位描述
@app.route('/api/jd', methods=['POST'])
def add_jd():
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'status': 'error', 'message': '缺少职位名称'}), 400

    title = data['title']
    company = data.get('company', '')

    conn = get_db_connection()

    # Check for duplicates
    existing = conn.execute('SELECT id FROM job_descriptions WHERE title = ? AND company = ?', (title, company)).fetchone()
    if existing:
        conn.close()
        return jsonify({'status': 'duplicate', 'message': f'该职位的记录已存在 (ID: {existing["id"]})'})

    # Get desensitized version
    desensitized_data = get_desensitized_jd_version(data)

    # Insert new JD
    cursor = conn.execute(
        """
        INSERT INTO job_descriptions (title, company, location, salary, requirements, description, benefits, desensitized_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            company,
            data.get('location', ''),
            data.get('salary', ''),
            data.get('requirements', ''),
            data.get('description', ''),
            data.get('benefits', ''),
            json.dumps(desensitized_data)
        )
    )
    conn.commit()
    new_jd_id = cursor.lastrowid
    new_jd = conn.execute('SELECT * FROM job_descriptions WHERE id = ?', (new_jd_id,)).fetchone()
    conn.close()

    return jsonify({
        'status': 'success',
        'message': '职位描述添加成功',
        'jd': dict(new_jd)
    })

# API: 删除职位描述
@app.route('/api/jd/<int:jd_id>', methods=['DELETE'])
def delete_jd(jd_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM job_descriptions WHERE id = ?', (jd_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'message': '职位描述删除成功'})

# API: AI人岗撮合
@app.route('/api/facilitate', methods=['POST'])
def ai_facilitate():
    data = request.get_json()
    resume_id = data.get('resume_id')
    jd_id = data.get('jd_id')
    
    if not resume_id or not jd_id:
        return jsonify({'status': 'error', 'message': '请选择简历和职位'}), 400
    
    conn = get_db_connection()
    resume = conn.execute('SELECT * FROM resumes WHERE id = ?', (resume_id,)).fetchone()
    jd = conn.execute('SELECT * FROM job_descriptions WHERE id = ?', (jd_id,)).fetchone()
    
    if not resume or not jd:
        conn.close()
        return jsonify({'status': 'error', 'message': '找不到对应的简历或职位'}), 404
    
    # 简单的撮合分数计算（实际项目中会使用AI模型）
    import random
    facilitation_score = random.randint(60, 95)
    
    strengths = ['技能匹配度高', '经验符合要求', '学历背景相符']
    improvements = ['某些技能需要加强', '相关项目经验可以更丰富']
    recommendation = '推荐' if facilitation_score >= 80 else '一般推荐' if facilitation_score >= 70 else '不推荐'

    # Store result in DB
    cursor = conn.execute(
        """
        INSERT INTO facilitation_results (resume_id, jd_id, facilitation_score, strengths, improvements, recommendation)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (resume_id, jd_id, facilitation_score, json.dumps(strengths), json.dumps(improvements), recommendation)
    )
    conn.commit()
    new_id = cursor.lastrowid
    
    # Fetch the newly created record to return
    new_facilitation_result = conn.execute('SELECT * FROM facilitation_results WHERE id = ?', (new_id,)).fetchone()

    conn.close()
    
    # Prepare data for JSON response
    result_to_return = {
        'id': new_facilitation_result['id'],
        'resume_id': resume_id,
        'jd_id': jd_id,
        'resume_name': resume['name'],
        'jd_title': jd['title'],
        'company': jd['company'],
        'facilitation_score': facilitation_score,
        'strengths': strengths,
        'improvements': improvements,
        'recommendation': recommendation,
        'created_at': new_facilitation_result['created_at']
    }
    
    return jsonify({
        'status': 'success',
        'message': 'AI撮合完成',
        'facilitation': result_to_return
    })

# API: 获取单个撮合历史
@app.route('/api/facilitate/<int:facilitation_id>')
def get_facilitation_result(facilitation_id):
    conn = get_db_connection()
    
    query = """
        SELECT
            fr.*,
            r.name as resume_name,
            j.title as jd_title,
            j.company as company
        FROM facilitation_results fr
        JOIN resumes r ON fr.resume_id = r.id
        JOIN job_descriptions j ON fr.jd_id = j.id
        WHERE fr.id = ?;
    """
    result = conn.execute(query, (facilitation_id,)).fetchone()
    conn.close()

    if not result:
        return jsonify({'status': 'error', 'message': '找不到该撮合记录'}), 404

    return jsonify({
        'status': 'success',
        'facilitation': {
            'id': result['id'],
            'resume_id': result['resume_id'],
            'jd_id': result['jd_id'],
            'resume_name': result['resume_name'],
            'jd_title': result['jd_title'],
            'company': result['company'],
            'facilitation_score': result['facilitation_score'],
            'strengths': json.loads(result['strengths']),
            'improvements': json.loads(result['improvements']),
            'recommendation': result['recommendation'],
            'created_at': result['created_at']
        }
    })

# API: Clear table
@app.route('/api/database/clear', methods=['POST'])
def clear_database():
    data = request.get_json()
    table_to_clear = data.get('table')

    if table_to_clear not in ['resumes', 'job_descriptions']:
        return jsonify({'status': 'error', 'message': 'Invalid table name specified.'}), 400

    try:
        conn = get_db_connection()
        conn.execute(f'DELETE FROM {table_to_clear}')
        # Reset autoincrement counter for sqlite
        conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_to_clear}'")
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': f"Table '{table_to_clear}' has been cleared."})
    except sqlite3.Error as e:
        # Handle case where table might not be in sqlite_sequence (if it never had data)
        if "no such table: sqlite_sequence" in str(e):
             conn.commit()
             conn.close()
             return jsonify({'status': 'success', 'message': f"Table '{table_to_clear}' has been cleared."})
        print(f"Database clear error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # 开发环境运行配置
    app.run(debug=True, host='0.0.0.0', port=8000) 