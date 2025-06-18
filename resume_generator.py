import os
import json
from flask import Blueprint, render_template, request, jsonify
from openai import OpenAI
from helpers import get_prompt, get_db_connection

# Create a Blueprint
resume_generator_bp = Blueprint(
    'resume_generator',
    __name__,
    template_folder='templates',
    static_folder='static'
)

# Initialize OpenAI client
# Make sure you have OPENAI_API_KEY set in your environment variables
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url = "https://admin-mbymnex2-eastus2.cognitiveservices.azure.com/openai/deployments/o4-mini",
    default_query={"api-version":"2025-01-01-preview"}
    )

# --- Tool Definition ---
def find_candidate_by_id_or_name(candidate_id=None, name=None):
    """根据候选人ID或姓名从数据库获取候选人信息。优先使用ID查询。"""
    if not candidate_id and not name:
        return json.dumps({"error": "Either candidate_id or name must be provided."})

    query = ""
    params = ()
    
    if candidate_id:
        print(f"--- [Tool Executing] Finding candidate by ID: {candidate_id} ---")
        query = 'SELECT * FROM resumes WHERE id = ?'
        params = (candidate_id,)
    elif name:
        print(f"--- [Tool Executing] Finding candidate by Name: {name} ---")
        query = 'SELECT * FROM resumes WHERE name = ?'
        params = (name,)

    try:
        conn = get_db_connection()
        candidate = conn.execute(query, params).fetchone()
        conn.close()
        if candidate:
            return json.dumps(dict(candidate))
        else:
            return json.dumps({"error": f"Candidate not found."})
    except Exception as e:
        print(f"--- [Tool Error] {e} ---")
        return json.dumps({"error": str(e)})

tools = [
    {
        "type": "function",
        "function": {
            "name": "find_candidate_by_id_or_name",
            "description": "根据候选人的ID或姓名，从数据库获取该候选人的详细背景信息。优先使用ID查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_id": {
                        "type": "integer",
                        "description": "要查询的候选人的唯一ID, e.g., 1"
                    },
                    "name": {
                        "type": "string",
                        "description": "要查询的候选人的姓名, e.g., '张三'"
                    }
                },
                "required": [] # No single field is strictly required, but the logic handles one or the other
            }
        }
    }
]

@resume_generator_bp.route('/resume/generate')
def resume_generation_page():
    """Renders the resume generation page."""
    return render_template('resume_generator.html')

@resume_generator_bp.route('/api/resume/generate_chat', methods=['POST'])
def resume_generate_chat_api():
    """API endpoint for the resume generation chat with tool-calling capability."""
    data = request.get_json()
    user_message = data.get('message')
    history = data.get('history', [])

    if not user_message:
        return jsonify({'status': 'error', 'message': 'No message provided'}), 400

    messages = []
    if not history:
        system_prompt = get_prompt('generate_resume_chat.txt')
        if not system_prompt:
            return jsonify({'status': 'error', 'message': 'Could not load prompt.'}), 500
        messages.append({'role': 'system', 'content': system_prompt})
    else:
        for item in history:
            messages.append({'role': item['role'], 'content': item['parts'][0]})

    messages.append({'role': 'user', 'content': user_message})
    
    try:
        print("--- OpenAI API Request (1st call) ---")
        print(json.dumps(messages, indent=2, ensure_ascii=False))

        response = client.chat.completions.create(
            model="o4-mini",
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        print("--- OpenAI API Response (1st call) ---")
        print(response_message)
        
        tool_calls = response_message.tool_calls

        if tool_calls:
            messages.append(response_message.model_dump())
            available_functions = {"find_candidate_by_id_or_name": find_candidate_by_id_or_name}
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call.function.arguments)
                function_response = function_to_call(**function_args)
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
            
            print("--- OpenAI API Request (2nd call with tool response) ---")
            print(json.dumps(messages, indent=2, ensure_ascii=False))

            second_response = client.chat.completions.create(
                model="o4-mini",
                messages=messages,
                response_format={"type": "json_object"}
            )
            final_response_message = second_response.choices[0].message
            print("--- OpenAI API Response (2nd call) ---")
            print(final_response_message)
            ai_response_text = final_response_message.content
        else:
            ai_response_text = response_message.content

        ai_response_data = json.loads(ai_response_text)

        updated_history = list(history)
        updated_history.append({'role': 'user', 'parts': [user_message]})
        updated_history.append({'role': 'assistant', 'parts': [ai_response_text]})
        
        return jsonify({
            'status': 'success',
            'response': ai_response_data,
            'history': updated_history
        })

    except Exception as e:
        print(f"Error during resume generation chat with OpenAI: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500 