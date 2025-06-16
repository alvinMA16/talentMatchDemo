from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import os
import json
import pathlib
import google.generativeai as genai
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

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

# 模拟数据存储
resumes = []
job_descriptions = []
matches = []

# 首页路由 - 默认显示Resume管理
@app.route('/')
def index():
    return redirect(url_for('resume_management'))

# Resume管理页面
@app.route('/resume')
def resume_management():
    return render_template('resume.html', resumes=resumes)

# JD管理页面
@app.route('/jd')
def jd_management():
    return render_template('jd.html', job_descriptions=job_descriptions)

# 人岗匹配页面
@app.route('/matching')
def talent_matching():
    return render_template('matching.html', resumes=resumes, job_descriptions=job_descriptions, matches=matches)

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
            
            prompt = """
            Please extract the following information from this resume and return it as a strict JSON object. Do not include any explanatory text or markdown code block markers.

            The JSON structure should be:
            {
                "name": "string (full name)",
                "email": "string (email address)",
                "phone": "string (phone number)",
                "skills": "string (comma-separated list of skills)",
                "experience": [
                    {
                        "role": "string",
                        "company": "string",
                        "dates": "string (e.g., 'Jan 2020 - Present')",
                        "description": "string (key responsibilities and achievements)"
                    }
                ],
                "education": [
                    {
                        "institution": "string",
                        "degree": "string",
                        "dates": "string (e.g., 'Sep 2016 - May 2020')"
                    }
                ],
                "summary": "string (a brief personal summary)"
            }
            """
            
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
        return jsonify({'status': 'error', 'message': '缺少必要字段'}), 400
    
    resume = {
        'id': len(resumes) + 1,
        'name': data['name'],
        'email': data.get('email', ''),
        'phone': data.get('phone', ''),
        'skills': data.get('skills', ''),
        'experience': data.get('experience', ''),
        'education': data.get('education', ''),
        'summary': data.get('summary', '')
    }
    resumes.append(resume)
    
    return jsonify({
        'status': 'success',
        'message': '简历添加成功',
        'resume': resume
    })

# API: 删除简历
@app.route('/api/resume/<int:resume_id>', methods=['DELETE'])
def delete_resume(resume_id):
    global resumes
    resumes = [r for r in resumes if r['id'] != resume_id]
    return jsonify({'status': 'success', 'message': '简历删除成功'})

# API: 添加职位描述
@app.route('/api/jd', methods=['POST'])
def add_jd():
    data = request.get_json()
    if not data or 'title' not in data:
        return jsonify({'status': 'error', 'message': '缺少必要字段'}), 400
    
    jd = {
        'id': len(job_descriptions) + 1,
        'title': data['title'],
        'company': data.get('company', ''),
        'location': data.get('location', ''),
        'salary': data.get('salary', ''),
        'requirements': data.get('requirements', ''),
        'description': data.get('description', ''),
        'benefits': data.get('benefits', '')
    }
    job_descriptions.append(jd)
    
    return jsonify({
        'status': 'success',
        'message': '职位描述添加成功',
        'jd': jd
    })

# API: 删除职位描述
@app.route('/api/jd/<int:jd_id>', methods=['DELETE'])
def delete_jd(jd_id):
    global job_descriptions
    job_descriptions = [jd for jd in job_descriptions if jd['id'] != jd_id]
    return jsonify({'status': 'success', 'message': '职位描述删除成功'})

# API: AI人岗匹配
@app.route('/api/match', methods=['POST'])
def ai_matching():
    data = request.get_json()
    resume_id = data.get('resume_id')
    jd_id = data.get('jd_id')
    
    if not resume_id or not jd_id:
        return jsonify({'status': 'error', 'message': '请选择简历和职位'}), 400
    
    # 模拟AI匹配逻辑
    resume = next((r for r in resumes if r['id'] == resume_id), None)
    jd = next((j for j in job_descriptions if j['id'] == jd_id), None)
    
    if not resume or not jd:
        return jsonify({'status': 'error', 'message': '找不到对应的简历或职位'}), 404
    
    # 简单的匹配分数计算（实际项目中会使用AI模型）
    import random
    match_score = random.randint(60, 95)
    
    match_result = {
        'id': len(matches) + 1,
        'resume_id': resume_id,
        'jd_id': jd_id,
        'resume_name': resume['name'],
        'jd_title': jd['title'],
        'company': jd['company'],
        'match_score': match_score,
        'strengths': ['技能匹配度高', '经验符合要求', '学历背景相符'],
        'improvements': ['某些技能需要加强', '相关项目经验可以更丰富'],
        'recommendation': '推荐' if match_score >= 80 else '一般推荐' if match_score >= 70 else '不推荐'
    }
    
    matches.append(match_result)
    
    return jsonify({
        'status': 'success',
        'message': 'AI匹配完成',
        'match': match_result
    })

# API: 获取匹配历史
@app.route('/api/matches')
def get_matches():
    return jsonify({
        'status': 'success',
        'matches': matches
    })

# 错误处理
@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

if __name__ == '__main__':
    # 开发环境运行配置
    app.run(debug=True, host='0.0.0.0', port=8000) 