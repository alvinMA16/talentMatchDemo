import sqlite3
import datetime
import json
import queue
import threading

# 全局日志队列，用于向前端广播日志
log_queue = queue.Queue(maxsize=1000)

def broadcast_log_to_frontend(log_message):
    """向前端广播日志消息"""
    try:
        log_data = {
            'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'message': log_message
        }
        # 如果队列满了，移除最老的消息
        if log_queue.full():
            try:
                log_queue.get_nowait()
            except queue.Empty:
                pass
        log_queue.put_nowait(log_data)
    except queue.Full:
        pass  # 如果队列满了就忽略

def log_model_request(model_name, prompt_type, input_summary=""):
    """记录模型请求日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] 🤖 MODEL REQUEST | {model_name} | {prompt_type} | Input: {input_summary}"
    print(log_message)
    broadcast_log_to_frontend(log_message)

def log_model_response(model_name, prompt_type, success=True, output_summary="", error_msg=""):
    """记录模型响应日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ SUCCESS" if success else "❌ ERROR"
    if success:
        log_message = f"[{timestamp}] 🤖 MODEL RESPONSE | {model_name} | {prompt_type} | {status} | Output: {output_summary}"
    else:
        log_message = f"[{timestamp}] 🤖 MODEL RESPONSE | {model_name} | {prompt_type} | {status} | Error: {error_msg}"
    print(log_message)
    broadcast_log_to_frontend(log_message)

def log_processing_step(step_name, status="START", details="", item_count=None):
    """记录处理步骤日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if status == "START":
        count_info = f"({item_count} items)" if item_count else ""
        log_message = f"[{timestamp}] ⚙️  PROCESSING | {step_name} | 🚀 {status} {count_info} | {details}"
    elif status == "COMPLETE":
        count_info = f"({item_count} completed)" if item_count else ""
        log_message = f"[{timestamp}] ⚙️  PROCESSING | {step_name} | ✅ {status} {count_info} | {details}"
    elif status == "ERROR":
        log_message = f"[{timestamp}] ⚙️  PROCESSING | {step_name} | ❌ {status} | {details}"
    else:
        log_message = f"[{timestamp}] ⚙️  PROCESSING | {step_name} | ℹ️  {status} | {details}"
    print(log_message)
    broadcast_log_to_frontend(log_message)

def log_batch_item(batch_name, item_index, total_items, item_name, success=True, details=""):
    """记录批量处理中单个项目的日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅" if success else "❌"
    progress = f"({item_index + 1}/{total_items})"
    log_message = f"[{timestamp}] 📦 BATCH | {batch_name} | {status} {progress} | {item_name} | {details}"
    print(log_message)
    broadcast_log_to_frontend(log_message)

def log_desensitization(data_type, name_or_title, success=True, error_msg=""):
    """记录脱敏处理日志"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "✅ SUCCESS" if success else "❌ ERROR"
    if success:
        log_message = f"[{timestamp}] 🔒 DESENSITIZATION | {data_type} | {status} | {name_or_title}"
    else:
        log_message = f"[{timestamp}] 🔒 DESENSITIZATION | {data_type} | {status} | {name_or_title} | Error: {error_msg}"
    print(log_message)
    broadcast_log_to_frontend(log_message)

def diagnose_json_error(json_text, error_msg):
    """诊断JSON错误并提供详细信息"""
    lines = json_text.split('\n')
    total_lines = len(lines)
    
    # 提取错误位置信息
    import re
    line_match = re.search(r'line (\d+)', error_msg)
    char_match = re.search(r'char (\d+)', error_msg)
    
    if line_match:
        error_line = int(line_match.group(1))
        context = []
        
        # 显示错误行前后的上下文
        start_line = max(1, error_line - 2)
        end_line = min(total_lines, error_line + 2)
        
        for i in range(start_line - 1, end_line):
            prefix = ">>> " if i == error_line - 1 else "    "
            context.append(f"{prefix}Line {i+1}: {lines[i]}")
        
        context_str = "\n".join(context)
        return f"JSON Error Context:\n{context_str}\nTotal lines: {total_lines}"
    
    return f"JSON Error: {error_msg}\nJSON preview: {json_text[:200]}..."

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect('talent_match.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def check_and_migrate_db():
    """Checks for table existence and adds them if they don't exist."""
    log_processing_step("DATABASE_MIGRATION", "START", "Checking database schema")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # List of all tables that should exist
    required_tables = {'resumes', 'job_descriptions', 'facilitation_results'}
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = {row[0] for row in cursor.fetchall()}
    
    missing_tables = required_tables - existing_tables
    
    if missing_tables:
        log_processing_step("DATABASE_MIGRATION", "PROGRESS", f"Missing tables detected: {', '.join(missing_tables)}")
        with open('schema.sql') as f:
            conn.executescript(f.read())
        log_processing_step("DATABASE_MIGRATION", "COMPLETE", "Database schema applied successfully")
    else:
        log_processing_step("DATABASE_MIGRATION", "COMPLETE", "Database schema is up-to-date")
    
    conn.close()

def get_prompt(filename):
    """Loads a prompt from the prompts directory."""
    try:
        with open(f'prompts/{filename}', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None 

def get_resume_and_jd_info(resume_id, jd_id):
    """
    从数据库中获取简历和JD的完整信息
    
    Args:
        resume_id (int): 简历ID
        jd_id (int): 职位描述ID
    
    Returns:
        tuple: (resume_info, jd_info) 包含完整信息的字典，如果找不到返回 (None, None)
    """
    log_processing_step("GET_RESUME_JD_INFO", "START", f"Fetching Resume ID: {resume_id}, JD ID: {jd_id}")
    
    conn = get_db_connection()
    
    try:
        # 获取简历信息
        resume = conn.execute('SELECT * FROM resumes WHERE id = ?', (resume_id,)).fetchone()
        if not resume:
            log_processing_step("GET_RESUME_JD_INFO", "ERROR", f"Resume ID {resume_id} not found")
            return None, None
        
        # 获取JD信息
        jd = conn.execute('SELECT * FROM job_descriptions WHERE id = ?', (jd_id,)).fetchone()
        if not jd:
            log_processing_step("GET_RESUME_JD_INFO", "ERROR", f"JD ID {jd_id} not found")
            return None, None
        
        # 构建简历信息字典
        resume_info = {
            'id': resume['id'],
            'name': resume['name'],
            'email': resume['email'],
            'phone': resume['phone'],
            'skills': resume['skills'],
            'summary': resume['summary'],
            'experience': json.loads(resume['experience_json']) if resume['experience_json'] else [],
            'education': json.loads(resume['education_json']) if resume['education_json'] else [],
            'publications': json.loads(resume['publications_json']) if resume['publications_json'] else [],
            'projects': json.loads(resume['projects_json']) if resume['projects_json'] else [],
            'desensitized_data': json.loads(resume['desensitized_json']) if resume['desensitized_json'] else None,
            'created_at': resume['created_at']
        }
        
        # 构建JD信息字典
        jd_info = {
            'id': jd['id'],
            'title': jd['title'],
            'company': jd['company'],
            'location': jd['location'],
            'salary': jd['salary'],
            'requirements': jd['requirements'],
            'description': jd['description'],
            'benefits': jd['benefits'],
            'desensitized_data': json.loads(jd['desensitized_json']) if jd['desensitized_json'] else None,
            'created_at': jd['created_at']
        }
        
        log_processing_step("GET_RESUME_JD_INFO", "COMPLETE", 
                          f"Retrieved {resume_info['name']} -> {jd_info['title']} @ {jd_info['company']}")
        
        return resume_info, jd_info
        
    except Exception as e:
        log_processing_step("GET_RESUME_JD_INFO", "ERROR", f"Database error: {str(e)}")
        return None, None
    finally:
        conn.close() 

def find_jd_by_id_or_title(jd_id: int = None, title: str = None) -> str:
    """
    根据职位ID或职位名称从数据库中查询职位描述(JD)。
    优先使用 ID 查询。如果两者都未提供，则返回错误。
    
    Args:
        jd_id (int, optional): 职位的数据库ID。
        title (str, optional): 职位的标题。
        
    Returns:
        str: 一个JSON字符串，包含查询到的JD信息或错误信息。
    """
    if not jd_id and not title:
        return json.dumps({"status": "error", "message": "必须提供职位ID或职位名称。"})

    conn = get_db_connection()
    try:
        if jd_id:
            log_processing_step("JD_TOOL_SEARCH", "START", f"通过ID查询JD: {jd_id}")
            query = 'SELECT * FROM job_descriptions WHERE id = ?'
            params = (jd_id,)
        else:
            log_processing_step("JD_TOOL_SEARCH", "START", f"通过标题查询JD: {title}")
            # 使用LIKE进行模糊匹配，并优先选择最新的一个
            query = 'SELECT * FROM job_descriptions WHERE title LIKE ? ORDER BY created_at DESC LIMIT 1'
            params = (f'%{title}%',)

        jd = conn.execute(query, params).fetchone()

        if jd:
            jd_dict = dict(jd)
            log_processing_step("JD_TOOL_SEARCH", "COMPLETE", f"成功找到JD: {jd_dict['title']} (ID: {jd_dict['id']})")
            return json.dumps({"status": "success", "data": jd_dict}, ensure_ascii=False, indent=2)
        else:
            log_processing_step("JD_TOOL_SEARCH", "COMPLETE", "未找到对应的JD。")
            return json.dumps({"status": "not_found", "message": "未找到对应的职位描述。"})
    except Exception as e:
        log_processing_step("JD_TOOL_SEARCH", "ERROR", f"数据库查询JD时出错: {str(e)}")
        return json.dumps({"status": "error", "message": f"数据库查询时发生错误: {str(e)}"})
    finally:
        conn.close() 