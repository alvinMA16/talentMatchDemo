import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

import sqlite3
import json
import pathlib
import google.generativeai as genai
import pandas as pd
import io
from werkzeug.utils import secure_filename
from helpers import get_prompt, get_db_connection, check_and_migrate_db, log_model_request, log_model_response, log_processing_step, log_batch_item, log_desensitization, log_queue, diagnose_json_error, get_resume_and_jd_info
from resume_generator import resume_generator_bp
from candidate_agent import CandidateAgent
from recruiter_agent import RecruiterAgent
import time
import queue
import os
import datetime
from openai import OpenAI
from flask import Flask, render_template, request, jsonify, Response, stream_template

# 简单的消息队列数据结构
class MessageQueue:
    """
    简单的消息队列，用于存储撮合过程中的agent消息
    每条消息包含：消息来源、消息类型、reasoning、payload、时间戳
    """
    def __init__(self):
        self.messages = []  # 消息列表
        self.session_id = None  # 当前会话ID
    
    def init_session(self, session_id):
        """初始化新的撮合会话"""
        self.session_id = session_id
        self.messages = []
        print(f"[MessageQueue] 初始化会话: {session_id}")
    
    def add_message(self, source, msg_type, reasoning, payload, timestamp=None):
        """
        添加消息到队列
        
        Args:
            source (str): 消息来源 ('candidate' 或 'recruiter')
            msg_type (str): 消息类型 ('planning', 'chatting', 'decision')
            reasoning (str): 思考过程
            payload (str): 消息内容
            timestamp (str, optional): 时间戳，默认为当前时间
        
        Returns:
            dict: 添加的消息对象
        """
        if timestamp is None:
            timestamp = datetime.datetime.now().isoformat()
        
        message = {
            'id': len(self.messages) + 1,  # 简单的消息ID
            'source': source,
            'type': msg_type,
            'reasoning': reasoning,
            'payload': payload,
            'timestamp': timestamp,
            'session_id': self.session_id
        }
        
        self.messages.append(message)
        print(f"[MessageQueue] 添加消息 #{message['id']}: {source} - {msg_type}")
        return message
    
    def get_messages(self, source=None, msg_type=None):
        """
        获取消息列表，支持按来源和类型过滤
        
        Args:
            source (str, optional): 过滤消息来源
            msg_type (str, optional): 过滤消息类型
        
        Returns:
            list: 消息列表
        """
        filtered_messages = self.messages
        
        if source:
            filtered_messages = [msg for msg in filtered_messages if msg['source'] == source]
        
        if msg_type:
            filtered_messages = [msg for msg in filtered_messages if msg['type'] == msg_type]
        
        return filtered_messages
    
    def get_chat_history(self):
        """获取对话历史（只包含chatting类型的消息）"""
        return self.get_messages(msg_type='chatting')
    
    def get_latest_message(self):
        """获取最新消息"""
        messages = self.get_messages()
        return messages[-1] if messages else None
    
    def clear(self):
        """清空消息队列"""
        self.messages = []
        print(f"[MessageQueue] 清空会话 {self.session_id} 的消息队列")
    
    def get_message_count(self):
        """获取消息总数"""
        return len(self.messages)
    
    def get_session_summary(self):
        """获取会话摘要"""
        chat_count = len(self.get_messages(msg_type='chatting'))
        planning_count = len(self.get_messages(msg_type='planning'))
        decision_count = len(self.get_messages(msg_type='decision'))
        
        return {
            'session_id': self.session_id,
            'total_messages': len(self.messages),
            'chat_messages': chat_count,
            'planning_messages': planning_count,
            'decision_messages': decision_count,
            'start_time': self.messages[0]['timestamp'] if self.messages else None,
            'end_time': self.messages[-1]['timestamp'] if self.messages else None
        }

def get_history_for_agent(source_agent):
    """
    为指定的agent构建历史消息记录
    - 自己source的所有消息
    - 对方source的chatting类型消息
    - 如果对方没有chatting消息，提供一个kickoff消息
    """
    history = []
    opponent_agent = 'recruiter' if source_agent == 'candidate' else 'candidate'

    print(f"[HistoryBuilder] 为 {source_agent.upper()} 构建历史记录...")

    # 统计对方的chatting消息数量
    opponent_chat_count = 0
    
    for msg in message_queue.messages:
        role = 'assistant' if msg['source'] == source_agent else 'user'
        
        # 自己发的所有消息都要给到
        if msg['source'] == source_agent:
            # 对于自己的消息，将原始的 'planning', 'chatting', 'decision' 格式封装到 content 中
            history.append({
                "role": role,
                "content": json.dumps({
                    "type": msg['type'],
                    "reasoning": msg['reasoning'],
                    "payload": msg['payload']
                }, ensure_ascii=False)
            })
            print(f"  [+] 添加自己的消息 (ID: {msg['id']}, Type: {msg['type']})")
        # 对方发的 chatting 消息要给到
        elif msg['source'] == opponent_agent and msg['type'] == 'chatting':
            # 对于对方的聊天消息，只传递payload
            history.append({
                "role": role,
                "content": msg['payload']
            })
            opponent_chat_count += 1
            print(f"  [+] 添加对方的聊天消息 (ID: {msg['id']})")
    
    # 如果对方没有chatting消息，添加一个kickoff消息
    if opponent_chat_count == 0:
        kickoff_message = "您好，我想了解更多关于这个机会的信息。" if opponent_agent == 'candidate' else "您好，我想了解您的背景和经验。"
        history.append({
            "role": "user",
            "content": kickoff_message
        })
        print(f"  [+] 添加kickoff消息 (对方暂无chatting消息)")
    
    print(f"[HistoryBuilder] 为 {source_agent.upper()} 构建完成，共 {len(history)} 条历史记录。")
    return history

# 全局消息队列实例
message_queue = MessageQueue()

def create_message_from_agent_response(agent_response, source):
    """
    从agent响应创建消息对象并添加到队列
    
    Args:
        agent_response (dict): agent的响应
        source (str): 消息来源 ('candidate' 或 'recruiter')
    
    Returns:
        dict: 创建的消息对象
    """
    if not agent_response or not isinstance(agent_response, dict):
        return None
    
    msg_type = agent_response.get('type', 'unknown')
    reasoning = agent_response.get('reasoning', '')
    payload = agent_response.get('payload', '')
    
    return message_queue.add_message(
        source=source,
        msg_type=msg_type,
        reasoning=reasoning,
        payload=payload
    )

def get_chat_messages_for_agent(source):
    """
    获取指定agent可见的对话消息
    
    Args:
        source (str): agent来源 ('candidate' 或 'recruiter')
    
    Returns:
        list: 对话消息列表，格式化为agent可理解的格式
    """
    chat_messages = message_queue.get_chat_history()
    formatted_messages = []
    
    for msg in chat_messages:
        # 将消息格式化为agent可理解的格式
        formatted_msg = {
            'sender': msg['source'],
            'content': msg['payload'],
            'round': msg['id'],  # 使用消息ID作为轮次
            'timestamp': msg['timestamp']
        }
        formatted_messages.append(formatted_msg)
    
    return formatted_messages

# --- Database Setup ---
DATABASE = 'talent_match.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# --- OpenAI Setup ---
# Initialize OpenAI client for profile generation
openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url = "http://47.93.181.123:4000",
)

def get_desensitized_version(resume_data):
    """Calls GenAI to create a desensitized version of the resume."""
    candidate_name = resume_data.get('name', 'Unknown')
    
    if os.environ.get("GOOGLE_API_KEY") is None:
        log_desensitization("RESUME", candidate_name, success=False, error_msg="GOOGLE_API_KEY not found")
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
        
        # Log model request
        log_model_request("gemini-1.5-flash", "RESUME_DESENSITIZATION", f"Resume: {candidate_name}")

        response = model.generate_content([prompt, resume_json_string])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        
        # 尝试解析JSON，如果失败则尝试修复
        try:
            desensitized_data = json.loads(cleaned_text)
        except json.JSONDecodeError as json_error:
            # 诊断JSON错误
            diagnosis = diagnose_json_error(cleaned_text, str(json_error))
            log_model_response("gemini-1.5-flash", "RESUME_DESENSITIZATION", success=False, 
                              error_msg=f"JSON parse error: {str(json_error)}")
            print(f"JSON诊断报告:\n{diagnosis}")
            
            # 尝试基本的JSON修复
            try:
                # 移除可能的多余内容和修复常见问题
                fixed_text = cleaned_text
                
                # 移除可能的前后缀内容，只保留JSON部分
                start_idx = fixed_text.find('{')
                end_idx = fixed_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    fixed_text = fixed_text[start_idx:end_idx+1]
                
                # 尝试解析修复后的JSON
                desensitized_data = json.loads(fixed_text)
                log_model_response("gemini-1.5-flash", "RESUME_DESENSITIZATION", success=True, 
                                  output_summary=f"JSON repaired and parsed successfully")
                
            except json.JSONDecodeError:
                # 如果修复仍然失败，创建基本的脱敏版本
                log_model_response("gemini-1.5-flash", "RESUME_DESENSITIZATION", success=False, 
                                  error_msg=f"JSON repair failed, using fallback desensitization")
                
                desensitized_data = resume_data.copy()
                desensitized_data['name'] = "Candidate"
                desensitized_data['email'] = "hidden@example.com"
                desensitized_data['phone'] = "***-****-****"
                
                # 移除或脱敏其他敏感信息
                if 'education' in desensitized_data:
                    for edu in desensitized_data.get('education', []):
                        if isinstance(edu, dict) and 'institution' in edu:
                            edu['institution'] = "某大学"
                
                if 'experience' in desensitized_data:
                    for exp in desensitized_data.get('experience', []):
                        if isinstance(exp, dict) and 'company' in exp:
                            exp['company'] = "某公司"
        
        # Log successful response
        desensitized_name = desensitized_data.get('name', 'Candidate')
        log_model_response("gemini-1.5-flash", "RESUME_DESENSITIZATION", success=True, 
                          output_summary=f"Desensitized name: {desensitized_name}")
        log_desensitization("RESUME", candidate_name, success=True)
        
        return desensitized_data
    except Exception as e:
        log_model_response("gemini-1.5-flash", "RESUME_DESENSITIZATION", success=False, error_msg=str(e))
        log_desensitization("RESUME", candidate_name, success=False, error_msg=str(e))
        # In case of failure, return the original data to avoid breaking the flow
        return resume_data

def get_desensitized_jd_version(jd_data):
    """Calls GenAI to create a desensitized version of the job description."""
    jd_title = jd_data.get('title', 'Unknown Job')
    company = jd_data.get('company', 'Unknown Company')
    
    if os.environ.get("GOOGLE_API_KEY") is None:
        log_desensitization("JD", f"{jd_title} @ {company}", success=False, error_msg="GOOGLE_API_KEY not found")
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

        # Log model request
        log_model_request("gemini-1.5-flash", "JD_DESENSITIZATION", f"JD: {jd_title} @ {company}")

        response = model.generate_content([prompt, jd_json_string])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        
        # 尝试解析JSON，如果失败则尝试修复
        try:
            desensitized_data = json.loads(cleaned_text)
        except json.JSONDecodeError as json_error:
            # 诊断JSON错误
            diagnosis = diagnose_json_error(cleaned_text, str(json_error))
            log_model_response("gemini-1.5-flash", "JD_DESENSITIZATION", success=False, 
                              error_msg=f"JSON parse error: {str(json_error)}")
            print(f"JSON诊断报告:\n{diagnosis}")
            
            # 尝试基本的JSON修复
            try:
                # 移除可能的多余内容和修复常见问题
                fixed_text = cleaned_text
                
                # 移除可能的前后缀内容，只保留JSON部分
                start_idx = fixed_text.find('{')
                end_idx = fixed_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    fixed_text = fixed_text[start_idx:end_idx+1]
                
                # 尝试解析修复后的JSON
                desensitized_data = json.loads(fixed_text)
                log_model_response("gemini-1.5-flash", "JD_DESENSITIZATION", success=True, 
                                  output_summary=f"JSON repaired and parsed successfully")
                
            except json.JSONDecodeError:
                # 如果修复仍然失败，创建基本的脱敏版本
                log_model_response("gemini-1.5-flash", "JD_DESENSITIZATION", success=False, 
                                  error_msg=f"JSON repair failed, using fallback desensitization")
                
                desensitized_data = jd_data.copy()
                desensitized_data['company'] = "某公司"
                if 'location' in desensitized_data:
                    desensitized_data['location'] = "某城市"
                if 'salary' in desensitized_data:
                    # 保留薪资范围但移除具体数字
                    salary_text = str(desensitized_data.get('salary', ''))
                    if any(x in salary_text.lower() for x in ['万', 'k', '千']):
                        desensitized_data['salary'] = "面议"
        
        # Log successful response
        desensitized_company = desensitized_data.get('company', '某公司')
        log_model_response("gemini-1.5-flash", "JD_DESENSITIZATION", success=True, 
                          output_summary=f"Desensitized company: {desensitized_company}")
        log_desensitization("JD", f"{jd_title} @ {company}", success=True)
        
        return desensitized_data
    except Exception as e:
        log_model_response("gemini-1.5-flash", "JD_DESENSITIZATION", success=False, error_msg=str(e))
        log_desensitization("JD", f"{jd_title} @ {company}", success=False, error_msg=str(e))
        # In case of failure, return the original data to avoid breaking the flow
        return jd_data

def get_prompt(filename):
    """Loads a prompt from the prompts directory."""
    try:
        with open(f'prompts/{filename}', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None

def generate_candidate_profile(resume_info, jd_info):
    """
    使用OpenAI o4-mini模型生成候选人求职画像
    
    Args:
        resume_info (dict): 候选人简历信息
        jd_info (dict): 职位描述信息
    
    Returns:
        dict: 生成的候选人画像，如果失败返回None
    """
    log_processing_step("CANDIDATE_PROFILE_GENERATION", "START", 
                       f"Generating profile for {resume_info['name']} -> {jd_info['title']}")
    
    try:
        prompt = get_prompt('generate_candidate_profile.txt')
        if not prompt:
            log_processing_step("CANDIDATE_PROFILE_GENERATION", "ERROR", "Could not load candidate profile prompt")
            return None
        
        # 构建输入数据 - 使用脱敏版本的简历和JD信息
        desensitized_resume = resume_info.get('desensitized_data')
        if not desensitized_resume:
            log_processing_step("CANDIDATE_PROFILE_GENERATION", "ERROR", "No desensitized data available for resume")
            return None
            
        desensitized_jd = jd_info.get('desensitized_data')
        if not desensitized_jd:
            log_processing_step("CANDIDATE_PROFILE_GENERATION", "ERROR", "No desensitized data available for JD")
            return None
            
        input_data = {
            "候选人简历": desensitized_resume,
            "目标职位": desensitized_jd
        }
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请基于以下信息生成候选人求职画像：\n\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"}
        ]
        
        log_model_request("gpt-4o-mini", "CANDIDATE_PROFILE_GENERATION", 
                         f"Candidate: {resume_info['name']}, Position: {jd_info['title']}")
        
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        response_content = response.choices[0].message.content
        candidate_profile = json.loads(response_content)
        
        log_model_response("o4-mini", "CANDIDATE_PROFILE_GENERATION", success=True, 
                          output_summary=f"Generated profile with {len(candidate_profile.get('job_preferences', []))} preferences")
        log_processing_step("CANDIDATE_PROFILE_GENERATION", "COMPLETE", 
                           f"Profile generated for {resume_info['name']}")
        
        return candidate_profile
        
    except Exception as e:
        log_model_response("o4-mini", "CANDIDATE_PROFILE_GENERATION", success=False, error_msg=str(e))
        log_processing_step("CANDIDATE_PROFILE_GENERATION", "ERROR", f"Error generating profile: {str(e)}")
        return None

def generate_company_profile(jd_info):
    """
    使用OpenAI o4-mini模型生成企业招聘画像
    
    Args:
        jd_info (dict): 职位描述信息
    
    Returns:
        dict: 生成的企业招聘画像，如果失败返回None
    """
    log_processing_step("COMPANY_PROFILE_GENERATION", "START", 
                       f"Generating company profile for {jd_info['title']} @ {jd_info['company']}")
    
    try:
        prompt = get_prompt('generate_company_profile.txt')
        if not prompt:
            log_processing_step("COMPANY_PROFILE_GENERATION", "ERROR", "Could not load company profile prompt")
            return None
        
        # 构建输入数据
        input_data = {
            "职位信息": {
                "职位名称": jd_info['title'],
                "公司": jd_info['company'],
                "地点": jd_info['location'],
                "薪资": jd_info['salary'],
                "职位要求": jd_info['requirements'],
                "职位描述": jd_info['description'],
                "福利待遇": jd_info['benefits']
            }
        }
        
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"请基于以下职位信息生成企业招聘画像：\n\n{json.dumps(input_data, ensure_ascii=False, indent=2)}"}
        ]
        
        log_model_request("o4-mini", "COMPANY_PROFILE_GENERATION", 
                         f"Position: {jd_info['title']} @ {jd_info['company']}")
        
        response = openai_client.chat.completions.create(
            model="o4-mini",
            messages=messages,
            response_format={"type": "json_object"}
        )
        
        response_content = response.choices[0].message.content
        company_profile = json.loads(response_content)
        
        log_model_response("o4-mini", "COMPANY_PROFILE_GENERATION", success=True, 
                          output_summary=f"Generated company profile with {len(company_profile.get('valued_traits', []))} valued traits")
        log_processing_step("COMPANY_PROFILE_GENERATION", "COMPLETE", 
                           f"Company profile generated for {jd_info['company']}")
        
        return company_profile
        
    except Exception as e:
        log_model_response("o4-mini", "COMPANY_PROFILE_GENERATION", success=False, error_msg=str(e))
        log_processing_step("COMPANY_PROFILE_GENERATION", "ERROR", f"Error generating company profile: {str(e)}")
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
    log_processing_step("SYSTEM_INIT", "COMPLETE", "Google API Key configured successfully")
except KeyError:
    log_processing_step("SYSTEM_INIT", "WARNING", "GOOGLE_API_KEY not found - some features will be limited")
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

    log_processing_step("RESUME_BATCH_UPLOAD", "START", f"Processing file: {file.filename}")
    
    try:
        # 1. AI Parsing
        if os.environ.get("GOOGLE_API_KEY") is None:
            log_processing_step("RESUME_BATCH_UPLOAD", "ERROR", "Google API Key not configured")
            return jsonify({'status': 'error', 'message': 'Google API Key not configured'}), 500

        pdf_bytes = file.read()
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = get_prompt('extract_resume_info.txt')
        if not prompt:
            log_processing_step("RESUME_BATCH_UPLOAD", "ERROR", "Could not load resume extraction prompt")
            return jsonify({'status': 'error', 'message': 'Could not load resume extraction prompt.'}), 500

        # Log model request
        log_model_request("gemini-1.5-flash", "RESUME_EXTRACTION", f"PDF file: {file.filename}")

        response = model.generate_content([
            {"mime_type": "application/pdf", "data": pdf_bytes},
            prompt
        ])
        
        cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
        data = json.loads(cleaned_text)
        
        # Log successful extraction
        candidate_name = data.get('name', 'Unknown')
        log_model_response("gemini-1.5-flash", "RESUME_EXTRACTION", success=True, 
                          output_summary=f"Extracted: {candidate_name}")

        # 2. Desensitize the extracted data
        log_processing_step("RESUME_DESENSITIZATION", "START", f"Desensitizing data for: {candidate_name}")
        desensitized_data = get_desensitized_version(data)

        # 3. Duplicate Check
        name = data.get('name')
        email = data.get('email')
        phone = data.get('phone')
        
        if not name:
            log_processing_step("RESUME_BATCH_UPLOAD", "ERROR", "Failed to extract candidate name")
            return jsonify({'status': 'error', 'message': 'Failed to extract candidate name.'})

        log_processing_step("DUPLICATE_CHECK", "START", f"Checking duplicates for: {name}")
        conn = get_db_connection()
        query = "SELECT id FROM resumes WHERE name = ? OR (email != '' AND email = ?) OR (phone != '' AND phone = ?)"
        existing = conn.execute(query, (name, email, phone)).fetchone()

        if existing:
            conn.close()
            log_processing_step("DUPLICATE_CHECK", "COMPLETE", f"Duplicate found (ID: {existing['id']})")
            return jsonify({'status': 'duplicate', 'message': f"Candidate already exists (ID: {existing['id']})"})

        # 4. Insert into DB
        log_processing_step("DATABASE_INSERT", "START", f"Inserting resume for: {name}")
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
        
        log_processing_step("DATABASE_INSERT", "COMPLETE", f"Successfully inserted: {name}")
        log_processing_step("RESUME_BATCH_UPLOAD", "COMPLETE", f"Successfully processed: {file.filename}")
        
        return jsonify({'status': 'success', 'message': 'Resume added successfully'})

    except Exception as e:
        log_processing_step("RESUME_BATCH_UPLOAD", "ERROR", f"Error processing {file.filename}: {str(e)}")
        log_model_response("gemini-1.5-flash", "RESUME_EXTRACTION", success=False, error_msg=str(e))
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
        log_processing_step("RESUME_UPLOAD", "START", f"Processing file: {file.filename}")
        
        try:
            # Check if API key is mocked
            if os.environ.get("GOOGLE_API_KEY") is None:
                log_processing_step("RESUME_UPLOAD", "ERROR", "Google API Key未设置")
                return jsonify({'status': 'error', 'message': 'Google API Key未设置，无法解析简历。'}), 500

            pdf_bytes = file.read()
            
            prompt = get_prompt('extract_resume_info.txt')
            if not prompt:
                log_processing_step("RESUME_UPLOAD", "ERROR", "Could not load resume extraction prompt")
                return jsonify({'status': 'error', 'message': 'Could not load resume extraction prompt.'}), 500
            
            # Log model request
            log_model_request("gemini-1.5-flash", "RESUME_EXTRACTION", f"PDF file: {file.filename}")
            
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
            
            # Log successful extraction
            candidate_name = extracted_data.get('name', 'Unknown')
            log_model_response("gemini-1.5-flash", "RESUME_EXTRACTION", success=True, 
                              output_summary=f"Extracted: {candidate_name}")
            log_processing_step("RESUME_UPLOAD", "COMPLETE", f"Successfully parsed: {file.filename}")

            return jsonify({
                'status': 'success',
                'message': '简历解析成功',
                'data': extracted_data
            })           

        except Exception as e:
            log_model_response("gemini-1.5-flash", "RESUME_EXTRACTION", success=False, error_msg=str(e))
            log_processing_step("RESUME_UPLOAD", "ERROR", f"Error parsing {file.filename}: {str(e)}")
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

    log_processing_step("ADD_RESUME", "START", f"Adding resume for: {name}")

    conn = get_db_connection()

    # Check for duplicates
    log_processing_step("DUPLICATE_CHECK", "START", f"Checking duplicates for: {name}")
    query = "SELECT * FROM resumes WHERE name = ? OR (email != '' AND email = ?) OR (phone != '' AND phone = ?)"
    existing = conn.execute(query, (name, email, phone)).fetchone()
    
    if existing:
        conn.close()
        log_processing_step("DUPLICATE_CHECK", "COMPLETE", f"Duplicate found (ID: {existing['id']})")
        return jsonify({
            'status': 'duplicate',
            'message': f"A candidate with similar info already exists (ID: {existing['id']}, Name: {existing['name']}). Please review before adding another."
        })

    log_processing_step("DUPLICATE_CHECK", "COMPLETE", "No duplicates found")

    # Get desensitized version
    log_processing_step("RESUME_DESENSITIZATION", "START", f"Desensitizing data for: {name}")
    desensitized_data = get_desensitized_version(data)

    # Insert new resume
    log_processing_step("DATABASE_INSERT", "START", f"Inserting resume for: {name}")
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

    log_processing_step("DATABASE_INSERT", "COMPLETE", f"Successfully inserted: {name} (ID: {new_resume_id})")
    log_processing_step("ADD_RESUME", "COMPLETE", f"Successfully added resume for: {name}")

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
        log_processing_step("JD_BATCH_UPLOAD", "START", f"Processing file: {filename}")
        jobs_to_process = []
        try:
            if filename.endswith(('.xlsx', '.xls')):
                # Use io.BytesIO to let pandas read from the in-memory bytes
                df = pd.read_excel(io.BytesIO(file_content))
                df['combined_text'] = df.apply(lambda row: ' '.join(row.astype(str)), axis=1)
                jobs_to_process = [{'source': f"Row {i+2}", 'content': row['combined_text']} for i, row in df.iterrows()]
                log_processing_step("FILE_PARSING", "COMPLETE", f"Parsed Excel file with {len(jobs_to_process)} jobs")
            elif filename.endswith('.json'):
                # Decode bytes to string for json.loads
                raw_data = json.loads(file_content.decode('utf-8'))
                if isinstance(raw_data, list):
                    jobs_to_process = [{'source': f"Object {i+1}", 'content': json.dumps(obj)} for i, obj in enumerate(raw_data)]
                    log_processing_step("FILE_PARSING", "COMPLETE", f"Parsed JSON file with {len(jobs_to_process)} jobs")
                else:
                    log_processing_step("FILE_PARSING", "ERROR", "JSON file must contain a list of job objects")
                    yield f"data: {json.dumps({'status': 'error', 'message': 'JSON file must contain a list of job objects.'})}\n\n"
                    return
            else:
                log_processing_step("FILE_PARSING", "ERROR", f"Unsupported file type: {filename}")
                yield f"data: {json.dumps({'status': 'error', 'message': 'Unsupported file type. Please use JSON, XLSX, or XLS.'})}\n\n"
                return
        except Exception as e:
            log_processing_step("FILE_PARSING", "ERROR", f"Failed to read or parse file: {str(e)}")
            yield f"data: {json.dumps({'status': 'error', 'message': f'Failed to read or parse file: {e}'})}\n\n"
            return

        # 2. Process each job with GenAI
        if os.environ.get("GOOGLE_API_KEY") is None:
            log_processing_step("JD_BATCH_UPLOAD", "ERROR", "Google API Key not configured")
            yield f"data: {json.dumps({'status': 'error', 'message': 'Google API Key not configured'})}\n\n"
            return
        
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = get_prompt('extract_jd_info.txt')
        if not prompt:
            log_processing_step("JD_BATCH_UPLOAD", "ERROR", "Could not load JD extraction prompt")
            yield f"data: {json.dumps({'status': 'error', 'message': 'Could not load JD extraction prompt.'})}\n\n"
            return

        total_jobs = len(jobs_to_process)
        success_count = 0
        failures = []
        conn = get_db_connection()
        
        log_processing_step("JD_BATCH_PROCESSING", "START", f"Processing {total_jobs} jobs")

        for i, job in enumerate(jobs_to_process):
            try:
                # Log model request for each job
                log_model_request("gemini-1.5-flash", "JD_EXTRACTION", f"Batch item {i+1}/{total_jobs}: {job['source']}")
                
                response = model.generate_content([job['content'], prompt])
                cleaned_text = response.text.strip().replace('```json', '').replace('```', '').strip()
                data = json.loads(cleaned_text)

                title = data.get('title')
                if not title:
                    raise ValueError('Failed to extract job title.')
                
                # Log successful extraction
                company = data.get('company', 'Unknown')
                log_model_response("gemini-1.5-flash", "JD_EXTRACTION", success=True, 
                                  output_summary=f"Extracted: {title} @ {company}")
                
                # Get desensitized version
                desensitized_data = get_desensitized_jd_version(data)
                
                # Check for duplicates
                existing = conn.execute('SELECT id FROM job_descriptions WHERE title = ? AND company = ?', (title, company)).fetchone()
                if existing:
                    raise ValueError(f'Duplicate job already exists (ID: {existing["id"]})')

                # Insert into database
                conn.execute(
                    """
                    INSERT INTO job_descriptions (title, company, location, salary, requirements, description, benefits, desensitized_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (title, company, data.get('location', ''), data.get('salary', ''), data.get('requirements', ''), data.get('description', ''), data.get('benefits', ''), json.dumps(desensitized_data))
                )
                conn.commit()
                success_count += 1
                
                # Log successful batch item
                log_batch_item("JD_BATCH_UPLOAD", i, total_jobs, f"{title} @ {company}", success=True, 
                              details="Successfully inserted into database")
                
                yield f"data: {json.dumps({'type': 'progress', 'processed': i + 1, 'total': total_jobs, 'source': job['source']})}\n\n"

            except Exception as e:
                # Log failed extraction
                log_model_response("gemini-1.5-flash", "JD_EXTRACTION", success=False, error_msg=str(e))
                log_batch_item("JD_BATCH_UPLOAD", i, total_jobs, job['source'], success=False, 
                              details=str(e))
                
                failures.append({'source': job['source'], 'reason': str(e)})
                yield f"data: {json.dumps({'type': 'progress', 'processed': i + 1, 'total': total_jobs, 'source': job['source'], 'error': str(e)})}\n\n"
        
        conn.close()
        
        log_processing_step("JD_BATCH_PROCESSING", "COMPLETE", f"Processed {total_jobs} jobs: {success_count} successful, {len(failures)} failed")

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

    log_processing_step("ADD_JD", "START", f"Adding JD: {title} @ {company}")

    conn = get_db_connection()

    # Check for duplicates
    log_processing_step("DUPLICATE_CHECK", "START", f"Checking duplicates for: {title} @ {company}")
    existing = conn.execute('SELECT id FROM job_descriptions WHERE title = ? AND company = ?', (title, company)).fetchone()
    if existing:
        conn.close()
        log_processing_step("DUPLICATE_CHECK", "COMPLETE", f"Duplicate found (ID: {existing['id']})")
        return jsonify({'status': 'duplicate', 'message': f'该职位的记录已存在 (ID: {existing["id"]})'})

    log_processing_step("DUPLICATE_CHECK", "COMPLETE", "No duplicates found")

    # Get desensitized version
    log_processing_step("JD_DESENSITIZATION", "START", f"Desensitizing data for: {title} @ {company}")
    desensitized_data = get_desensitized_jd_version(data)

    # Insert new JD
    log_processing_step("DATABASE_INSERT", "START", f"Inserting JD: {title} @ {company}")
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

    log_processing_step("DATABASE_INSERT", "COMPLETE", f"Successfully inserted: {title} @ {company} (ID: {new_jd_id})")
    log_processing_step("ADD_JD", "COMPLETE", f"Successfully added JD: {title} @ {company}")

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

# API: AI画像生成
@app.route('/api/generate_profiles', methods=['POST'])
def generate_profiles():
    data = request.get_json()
    resume_id = data.get('resume_id')
    jd_id = data.get('jd_id')
    
    if not resume_id or not jd_id:
        return jsonify({'status': 'error', 'message': '请选择简历和职位'}), 400
    
    log_processing_step("PROFILE_GENERATION", "START", f"Starting profile generation for Resume ID: {resume_id}, JD ID: {jd_id}")
    
    # 1. 获取简历和JD的完整信息
    resume_info, jd_info = get_resume_and_jd_info(resume_id, jd_id)
    
    if not resume_info or not jd_info:
        log_processing_step("PROFILE_GENERATION", "ERROR", "Resume or JD not found in database")
        return jsonify({'status': 'error', 'message': '找不到对应的简历或职位'}), 404
    
    candidate_name = resume_info['name']
    jd_title = jd_info['title']
    company = jd_info['company']
    
    log_processing_step("PROFILE_GENERATION", "PROGRESS", f"Generating profiles for {candidate_name} with {jd_title} @ {company}")
    
    # 2. 生成候选人求职画像
    log_processing_step("PROFILE_GENERATION", "PROGRESS", "Generating candidate profile...")
    candidate_profile = generate_candidate_profile(resume_info, jd_info)
    
    if not candidate_profile:
        log_processing_step("PROFILE_GENERATION", "ERROR", "Failed to generate candidate profile")
        return jsonify({'status': 'error', 'message': '生成候选人画像失败'}), 500
    
    # 3. 生成企业招聘画像
    log_processing_step("PROFILE_GENERATION", "PROGRESS", "Generating company profile...")
    company_profile = generate_company_profile(jd_info)
    
    if not company_profile:
        log_processing_step("PROFILE_GENERATION", "ERROR", "Failed to generate company profile")
        return jsonify({'status': 'error', 'message': '生成企业画像失败'}), 500
    
    log_processing_step("PROFILE_GENERATION", "COMPLETE", f"Profile generation completed for {candidate_name} <-> {jd_title}")
    
    # 4. Prepare data for JSON response (只包含画像信息，不保存到数据库)
    result_to_return = {
        'resume_name': resume_info['name'],
        'jd_title': jd_info['title'],
        'company': jd_info['company'],
        'candidate_profile': candidate_profile,
        'company_profile': company_profile,
        'generated_at': datetime.datetime.now().isoformat()
    }
    
    return jsonify({
        'status': 'success',
        'message': '画像生成完成',
        'profiles': result_to_return
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

# API: 日志流 (Server-Sent Events)
@app.route('/api/logs/stream')
def log_stream():
    """通过SSE向前端推送实时日志"""
    def generate_logs():
        # 发送初始化消息
        yield f"data: {json.dumps({'type': 'init', 'message': 'Log stream connected'})}\n\n"
        
        # 持续监听日志队列
        while True:
            try:
                # 等待新的日志消息，超时时间30秒
                log_data = log_queue.get(timeout=30)
                yield f"data: {json.dumps({'type': 'log', **log_data})}\n\n"
            except:
                # 超时或其他异常，发送心跳消息
                yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
    
    return Response(generate_logs(), mimetype='text/event-stream', 
                   headers={'Cache-Control': 'no-cache'})

# API: AI撮合流式接口（实时对话展示）
@app.route('/api/ai_matching_stream', methods=['GET'])
def ai_matching_stream():
    resume_id = request.args.get('resume_id', type=int)
    jd_id = request.args.get('jd_id', type=int)
    profiles_param = request.args.get('profiles')
    
    if not resume_id or not jd_id:
        return jsonify({'status': 'error', 'message': '请选择简历和职位'}), 400
    
    log_processing_step("AI_MATCHING_STREAM", "START", f"Starting streaming AI matching for Resume ID: {resume_id}, JD ID: {jd_id}")
    
    def generate_matching_stream():
        try:
            # 初始化消息队列会话
            session_id = f"{resume_id}_{jd_id}_{int(time.time())}"
            message_queue.init_session(session_id)
            
            # 发送开始信号
            yield f"data: {json.dumps({'type': 'start', 'message': '开始AI撮合...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
            # 1. 获取简历和JD的完整信息
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在获取简历和职位信息...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            resume_info, jd_info = get_resume_and_jd_info(resume_id, jd_id)
            
            if not resume_info or not jd_info:
                yield f"data: {json.dumps({'type': 'error', 'message': '找不到对应的简历或职位', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                return
            
            candidate_name = resume_info['name']
            jd_title = jd_info['title']
            company = jd_info['company']
            
            # 2. 获取或生成画像
            if profiles_param:
                # 使用传递的画像数据
                try:
                    profiles_data = json.loads(profiles_param)
                    candidate_profile = profiles_data.get('candidate_profile')
                    company_profile = profiles_data.get('company_profile')
                    yield f"data: {json.dumps({'type': 'progress', 'message': '使用已生成的画像数据...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                    
                    if not candidate_profile or not company_profile:
                        yield f"data: {json.dumps({'type': 'error', 'message': '画像数据不完整，请重新生成画像', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                        return
                except (json.JSONDecodeError, KeyError) as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': '画像数据解析失败，请重新生成画像', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                    return
            else:
                # 重新生成画像（兼容旧流程）
                yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成候选人和企业画像...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                candidate_profile = generate_candidate_profile(resume_info, jd_info)
                company_profile = generate_company_profile(jd_info)
                
                if not candidate_profile or not company_profile:
                    yield f"data: {json.dumps({'type': 'error', 'message': '生成画像失败，无法进行撮合', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
                    return
            
            # 3. 准备Agent数据
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在准备代理数据...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
            # 候选人agent看到：完整简历 + 脱敏JD + 候选人画像
            full_resume = {
                'name': resume_info['name'],
                'email': resume_info['email'],
                'phone': resume_info['phone'],
                'skills': resume_info['skills'],
                'summary': resume_info['summary'],
                'experience': resume_info['experience'],
                'education': resume_info['education'],
                'publications': resume_info['publications'],
                'projects': resume_info['projects']
            }
            
            desensitized_jd = jd_info.get('desensitized_data') if jd_info.get('desensitized_data') else {
                'title': jd_info['title'],
                'company': '某公司',
                'location': jd_info.get('location', '某城市'),
                'salary': '面议',
                'requirements': jd_info['requirements'],
                'description': jd_info['description'],
                'benefits': jd_info['benefits']
            }
            
            # 招聘方agent看到：脱敏简历 + 完整JD + 企业画像
            desensitized_resume = resume_info.get('desensitized_data') if resume_info.get('desensitized_data') else {
                'name': '候选人',
                'email': 'hidden@example.com',
                'phone': '***-****-****',
                'skills': resume_info['skills'],
                'summary': resume_info['summary'],
                'experience': resume_info['experience'],
                'education': resume_info['education'],
                'publications': resume_info['publications'],
                'projects': resume_info['projects']
            }
            
            full_jd = {
                'title': jd_info['title'],
                'company': jd_info['company'],
                'location': jd_info['location'],
                'salary': jd_info['salary'],
                'requirements': jd_info['requirements'],
                'description': jd_info['description'],
                'benefits': jd_info['benefits']
            }
            
            # 4. 创建双方agent
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在初始化候选人和企业代理...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            candidate_agent = CandidateAgent(full_resume, desensitized_jd, candidate_profile)
            recruiter_agent = RecruiterAgent(desensitized_resume, full_jd, company_profile)
            
            # 发送撮合信息
            yield f"data: {json.dumps({'type': 'matching_info', 'data': {'resume_name': candidate_name, 'jd_title': jd_title, 'company': company}, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
            # 5. 开始agent对话撮合（使用消息队列）
            yield f"data: {json.dumps({'type': 'progress', 'message': '开始代理对话撮合...', 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
            max_rounds = 10  # 最大对话轮数
            current_round = 1
            
            # 候选人agent先开始
            candidate_response = candidate_agent.respond(history=get_history_for_agent('candidate'))
            if candidate_response:
                # 将响应添加到消息队列
                message = create_message_from_agent_response(candidate_response, 'candidate')
                if message:
                    # 构造一个更简洁的数据结构
                    data_payload = {
                        'sender': 'candidate',
                        'reasoning': message.get('reasoning'),
                        'timestamp': message.get('timestamp')
                    }
                    message_type = message.get('type')

                    if message_type == 'planning':
                        data_payload['content'] = message.get('payload')
                        yield f"data: {json.dumps({'type': 'planning', 'data': data_payload})}\n\n"
                        time.sleep(0.5)
                    elif message_type == 'chatting':
                        data_payload['content'] = message.get('payload')
                        data_payload['round'] = current_round
                        yield f"data: {json.dumps({'type': 'chatting', 'data': data_payload})}\n\n"
                        time.sleep(1)
                    elif message_type == 'decision':
                        data_payload['decision'] = message.get('payload')
                        yield f"data: {json.dumps({'type': 'decision', 'data': data_payload})}\n\n"
            
            # 开始对话循环
            while current_round < max_rounds and not candidate_agent.has_reached_decision() and not recruiter_agent.has_reached_decision():
                # 招聘方回应
                recruiter_response = recruiter_agent.respond(
                    history=get_history_for_agent('recruiter')
                )
                if recruiter_response:
                    # 将响应添加到消息队列
                    message = create_message_from_agent_response(recruiter_response, 'recruiter')
                    if message:
                        # 构造一个更简洁的数据结构
                        data_payload = {
                            'sender': 'recruiter',
                            'reasoning': message.get('reasoning'),
                            'timestamp': message.get('timestamp')
                        }
                        message_type = message.get('type')

                        if message_type == 'planning':
                            data_payload['content'] = message.get('payload')
                            yield f"data: {json.dumps({'type': 'planning', 'data': data_payload})}\n\n"
                            time.sleep(0.5)
                        elif message_type == 'chatting':
                            data_payload['content'] = message.get('payload')
                            data_payload['round'] = current_round
                            yield f"data: {json.dumps({'type': 'chatting', 'data': data_payload})}\n\n"
                            time.sleep(1)
                        elif message_type == 'decision':
                            data_payload['decision'] = message.get('payload')
                            yield f"data: {json.dumps({'type': 'decision', 'data': data_payload})}\n\n"
                            break
                
                # 如果招聘方已做决定，跳出循环
                if recruiter_agent.has_reached_decision():
                    break
                
                # 候选人回应
                candidate_response = candidate_agent.respond(
                    history=get_history_for_agent('candidate')
                )
                if candidate_response:
                    # 将响应添加到消息队列
                    message = create_message_from_agent_response(candidate_response, 'candidate')
                    if message:
                        # 构造一个更简洁的数据结构
                        data_payload = {
                            'sender': 'candidate',
                            'reasoning': message.get('reasoning'),
                            'timestamp': message.get('timestamp')
                        }
                        message_type = message.get('type')

                        if message_type == 'planning':
                            data_payload['content'] = message.get('payload')
                            yield f"data: {json.dumps({'type': 'planning', 'data': data_payload})}\n\n"
                            time.sleep(0.5)
                        elif message_type == 'chatting':
                            current_round += 1
                            data_payload['content'] = message.get('payload')
                            data_payload['round'] = current_round
                            yield f"data: {json.dumps({'type': 'chatting', 'data': data_payload})}\n\n"
                            time.sleep(1)
                        elif message_type == 'decision':
                            data_payload['decision'] = message.get('payload')
                            yield f"data: {json.dumps({'type': 'decision', 'data': data_payload})}\n\n"
                            break
                
                # 如果候选人已做决定，跳出循环
                if candidate_agent.has_reached_decision():
                    break
            
            # 6. 发送最终决策结果
            final_decisions = {
                'candidate_decision': candidate_agent.get_final_decision(),
                'recruiter_decision': recruiter_agent.get_final_decision()
            }
            
            yield f"data: {json.dumps({'type': 'decisions', 'data': final_decisions, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
            # 7. 计算最终结果
            if final_decisions['candidate_decision'] == 'SUITABLE' and final_decisions['recruiter_decision'] == 'SUITABLE':
                final_result = {
                    'status': 'MATCH',
                    'message': '双方撮合成功！',
                    'icon': '🎉',
                    'summary': f'{candidate_name} 和 {company} 的 {jd_title} 职位达成匹配'
                }
            elif final_decisions['candidate_decision'] == 'UNSUITABLE' or final_decisions['recruiter_decision'] == 'UNSUITABLE':
                final_result = {
                    'status': 'NO_MATCH',
                    'message': '撮合未成功',
                    'icon': '😔',
                    'summary': '双方未能达成一致，撮合失败'
                }
            else:
                final_result = {
                    'status': 'UNCERTAIN',
                    'message': '撮合结果不明确',
                    'icon': '🤔',
                    'summary': '需要进一步沟通确认'
                }
            
            # 8. 保存撮合结果到数据库
            try:
                conn = get_db_connection()
                
                # 获取消息队列摘要
                session_summary = message_queue.get_session_summary()
                
                conn.execute(
                    """
                    INSERT INTO facilitation_results 
                    (resume_id, jd_id, candidate_decision, recruiter_decision, final_result, conversation_log, session_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        resume_id,
                        jd_id,
                        final_decisions['candidate_decision'],
                        final_decisions['recruiter_decision'],
                        final_result['status'],
                        json.dumps(message_queue.messages),  # 保存完整的消息队列
                        json.dumps(session_summary)  # 保存会话摘要
                    )
                )
                conn.commit()
                conn.close()
                
                log_processing_step("AI_MATCHING_STREAM", "COMPLETE", f"Saved facilitation result: {final_result['status']}")
                
            except Exception as e:
                log_processing_step("AI_MATCHING_STREAM", "ERROR", f"Failed to save result: {str(e)}")
            
            # 发送完成信号
            yield f"data: {json.dumps({'type': 'complete', 'data': final_result, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
            
        except GeneratorExit:
            log_processing_step("AI_MATCHING_STREAM", "INFO", "Client disconnected, closing stream.")
        except Exception as e:
            error_message = f"撮合过程中发生错误: {str(e)}"
            log_processing_step("AI_MATCHING_STREAM", "ERROR", error_message)
            yield f"data: {json.dumps({'type': 'error', 'message': error_message, 'timestamp': datetime.datetime.now().isoformat()})}\n\n"
        finally:
            # 清理消息队列
            message_queue.clear()
    
    return Response(generate_matching_stream(), mimetype='text/event-stream')

# API: 获取当前消息队列状态（调试用）
@app.route('/api/message_queue/status', methods=['GET'])
def get_message_queue_status():
    """获取当前消息队列状态，用于调试"""
    try:
        status = {
            'session_id': message_queue.session_id,
            'message_count': message_queue.get_message_count(),
            'messages': message_queue.messages,
            'summary': message_queue.get_session_summary() if message_queue.messages else None,
            'latest_message': message_queue.get_latest_message(),
            'chat_history': message_queue.get_chat_history()
        }
        return jsonify({'status': 'success', 'data': status})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# API: 清空消息队列（调试用）
@app.route('/api/message_queue/clear', methods=['POST'])
def clear_message_queue():
    """清空当前消息队列，用于调试"""
    try:
        old_count = message_queue.get_message_count()
        message_queue.clear()
        return jsonify({
            'status': 'success', 
            'message': f'已清空消息队列，删除了 {old_count} 条消息'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # 开发环境运行配置
    log_processing_step("SYSTEM_START", "START", "Starting TalentMatch application on port 8000")
    app.run(debug=True, host='0.0.0.0', port=8000) 