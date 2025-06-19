import os
import json
from flask import Blueprint, render_template, request, jsonify, Response
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

@resume_generator_bp.route('/resume/generate')
def resume_generation_page():
    """Renders the resume generation page."""
    return render_template('resume_generator.html')

@resume_generator_bp.route('/api/resume/generate_chat', methods=['POST'])
def resume_generate_chat_api():
    """API endpoint for the resume generation chat with a structured output agent.
    This endpoint uses streaming to send back each step of the agent's process.
    """
    data = request.get_json()
    user_message = data.get('message')
    history = data.get('history', [])
    
    if not user_message:
        # This case should ideally not be hit with the current frontend, but as a safeguard:
        return Response(json.dumps({'status': 'error', 'message': 'No message provided'}), status=400, mimetype='application/json')

    def stream_response():
        max_turns = 5 # Prevent infinite loops
        
        # --- Message History Setup ---
        system_prompt = get_prompt('generate_resume_chat.txt')
        if not system_prompt:
            error_message = {'status': 'error', 'message': 'Could not load system prompt.'}
            yield json.dumps(error_message) + '\n\n'
            return

        messages = [{'role': 'system', 'content': system_prompt}]
        if history:
            for item in history:
                if 'role' in item and 'parts' in item and item['parts']:
                    content = item['parts'][0]
                    messages.append({'role': item['role'], 'content': content})
        
        # Add the current user message to the history for the agent
        messages.append({'role': 'user', 'content': user_message})
        
        try:
            for turn in range(max_turns):
                print(f"--- Agent Turn {turn + 1} ---")

                response = client.chat.completions.create(
                    model="o4-mini",
                    messages=messages,
                    response_format={"type": "json_object"}
                )
                
                response_content = response.choices[0].message.content
                
                # Stream the raw OpenAI response to the client
                yield response_content + '\n\n'

                # Add the AI's full action JSON to the history for the next turn
                messages.append({'role': 'assistant', 'content': response_content})
                
                try:
                    response_json = json.loads(response_content)
                    ai_action = response_json.get("action", {})
                    action_type = ai_action.get("type")
                    payload = ai_action.get("payload")
                except (json.JSONDecodeError, AttributeError):
                    # If parsing fails, we can't continue the loop logically.
                    break

                if action_type in ["thought", "tool_call", "generate_resume"]:
                    print(f"--- Action: Intermediate Step ({action_type}) ---")

                    # Handle tool call specifically as it adds a new message to the history
                    if action_type == "tool_call":
                        if payload:
                            function_name = payload.get("function_name")
                            if function_name == "find_candidate_by_id_or_name":
                                tool_result = find_candidate_by_id_or_name(**payload.get("parameters", {}))
                                
                                # Add tool result and stream it.
                                # The role MUST be 'assistant' for the model to understand the response.
                                tool_message = {"role": "assistant", "content": tool_result}
                                messages.append(tool_message)
                                yield json.dumps(tool_message) + '\n\n'
                    
                    # For 'thought' and 'generate_resume', the assistant message is already in history.
                    # We just continue to the next turn.
                    continue
                else:
                    # This covers chat_message, final_message, and any unknown types
                    print(f"--- Action: Breaking action ({action_type}) ---")
                    break

        except Exception as e:
            print(f"Error during resume generation stream: {e}")
            error_message = {
                "reasoning": "发生了一个内部错误。",
                "action": {
                    "type": "chat_message",
                    "payload": {"text": f"抱歉，处理您的请求时出现错误: {e}"}
                }
            }
            yield json.dumps(error_message) + '\n\n'

    return Response(stream_response(), mimetype='application/x-ndjson') 