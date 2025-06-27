import os
import json
from flask import Blueprint, request, Response, stream_with_context
from openai import OpenAI
from helpers import get_prompt, log_model_request, log_model_response, log_processing_step, find_jd_by_id_or_title
import time

# Create a Blueprint
talent_sourcing_bp = Blueprint(
    'talent_sourcing',
    __name__,
    template_folder='templates',
    static_folder='static'
)

# Initialize OpenAI client
client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url = "http://47.93.181.123:4000",
)

# --- Multi-Agent System ---

def call_agent(agent_name, messages, temperature=1, json_output=True):
    """Generic function to call an agent with specific instructions."""
    log_processing_step(f"AGENT_CALL_{agent_name.upper()}", "START", f"Calling {agent_name} agent...")
    
    response_format = {"type": "json_object"} if json_output else {"type": "text"}
    
    try:
        response = client.chat.completions.create(
            model="o4-mini",
            messages=messages,
            temperature=temperature,
            response_format=response_format,
        )
        content = response.choices[0].message.content
        log_model_response("o4-mini", f"AGENT_{agent_name.upper()}", success=True, output_summary=content[:200])
        return content
    except Exception as e:
        log_model_response("o4-mini", f"AGENT_{agent_name.upper()}", success=False, error_msg=str(e))
        raise

def stream_event(event_type, data):
    """Helper to format and yield a server-sent event."""
    return f"data: {json.dumps({'type': event_type, 'data': data})}\n\n"

def execute_tool(tool_name: str, parameters: dict) -> str:
    """Executes a tool with given parameters."""
    if tool_name == "find_jd":
        jd_id = parameters.get("jd_id")
        title = parameters.get("title")
        return find_jd_by_id_or_title(jd_id=jd_id, title=title)
    else:
        return json.dumps({"status": "error", "message": f"未知工具: {tool_name}"})

@talent_sourcing_bp.route('/api/talent_sourcing/chat', methods=['POST'])
def talent_sourcing_chat_api():
    """API endpoint for the multi-agent talent sourcing chat."""
    data = request.get_json()
    user_message = data.get('message')
    history = data.get('history', [])

    if not user_message:
        return Response(json.dumps({'error': 'No message provided'}), status=400, mimetype='application/json')

    def multi_agent_stream():
        # State management
        task_history = []
        max_turns = 10
        current_turn = 0

        # Initial user request
        main_task = user_message

        try:
            # Load executor capabilities once at the beginning
            executor_capabilities = get_prompt('executor_capabilities.txt')
            if not executor_capabilities:
                yield stream_event("error", {"message": "Critical Error: Could not load executor capabilities."})
                return

            while current_turn < max_turns:
                current_turn += 1
                yield stream_event("status_update", {"message": f"--- Turn {current_turn}: Starting ---"})

                # 1. Planner Agent
                planner_prompt_template = get_prompt('sourcing_planner_system.txt')
                planner_prompt = planner_prompt_template.format(executor_capabilities=executor_capabilities)
                
                planner_messages = [
                    {"role": "system", "content": planner_prompt},
                    {"role": "user", "content": f"User's main task: {main_task}\n\nTask History (for context):\n{json.dumps(task_history, indent=2)}"}
                ]
                try:
                    plan_str = call_agent("planner", planner_messages)
                    plan = json.loads(plan_str)
                    yield stream_event("planner_output", plan)
                except Exception as e:
                    yield stream_event("error", {"message": f"Planner failed: {str(e)}"})
                    break

                # Execute the plan
                for step in plan.get("plan", []):
                    task = step.get("task")
                    yield stream_event("status_update", {"message": f"Executing Step {step.get('step')}: {task}"})

                    # 2. Executor Agent - Always expects JSON output now
                    executor_prompt = get_prompt('sourcing_executor_system.txt')
                    executor_messages = [
                        {"role": "system", "content": executor_prompt},
                        {"role": "user", "content": f"Main Task: {main_task}\n\nFull Plan:\n{json.dumps(plan, indent=2)}\n\nPrevious Steps History:\n{json.dumps(task_history, indent=2)}\n\nCurrent Task:\n{task}"}
                    ]
                    try:
                        executor_output_str = call_agent("executor", executor_messages, json_output=True)
                        executor_output = json.loads(executor_output_str)
                        
                        action = executor_output.get("action")
                        
                        if action == "tool_call":
                            tool_name = executor_output.get("tool_name")
                            parameters = executor_output.get("parameters", {})
                            yield stream_event("tool_call", {"tool": tool_name, "parameters": parameters})
                            execution_result = execute_tool(tool_name, parameters)
                        elif action == "generate_content":
                            execution_result = executor_output.get("content", "")
                        else:
                            # If the action is unknown, pass the raw JSON output for the observer to see.
                            execution_result = executor_output_str

                        yield stream_event("executor_output", {"step": step.get('step'), "result": execution_result})
                    except Exception as e:
                        yield stream_event("error", {"message": f"Executor failed on step {step.get('step')}: {str(e)}"})
                        break
                    
                    time.sleep(1) # Small delay for better UX

                    # 3. Observer Agent
                    observer_prompt_template = get_prompt('sourcing_observer_system.txt')
                    observer_prompt = observer_prompt_template.format(executor_capabilities=executor_capabilities)

                    observer_messages = [
                        {"role": "system", "content": observer_prompt},
                        {"role": "user", "content": f"Full Plan:\n{json.dumps(plan, indent=2)}\n\nCurrent Step:\n{json.dumps(step, indent=2)}\n\nExecution Result:\n{execution_result}"}
                    ]
                    try:
                        decision_str = call_agent("observer", observer_messages)
                        decision = json.loads(decision_str)
                        yield stream_event("observer_output", decision)
                    except Exception as e:
                        yield stream_event("error", {"message": f"Observer failed on step {step.get('step')}: {str(e)}"})
                        break
                    
                    time.sleep(1) # Small delay for better UX

                    # Handle decision
                    task_summary = {"step": step, "result": execution_result, "observer_decision": decision}
                    task_history.append(task_summary)

                    if decision.get("decision") == "retry":
                        yield stream_event("status_update", {"message": f"Observer requested retry for step {step.get('step')}. Retrying..."})
                        # This is a simplified retry. A more robust implementation would loop here.
                        continue
                    elif decision.get("decision") == "replan":
                        yield stream_event("status_update", {"message": "Observer requested a replan. Returning to planner."})
                        main_task = f"Original task: '{main_task}'. Feedback from observer: {decision.get('feedback_to_planner')}"
                        break # Break from plan execution loop to go back to the start of the while loop for replanning
                    
                    # If 'proceed', the loop continues to the next step
                
                # If the inner loop wasn't broken by a 'replan' request, we're done with the plan.
                else: 
                    yield stream_event("final_result", {"message": "Plan executed successfully.", "full_history": task_history})
                    break

            yield stream_event("status_update", {"message": "Process finished."})
        except GeneratorExit:
            # This is critical. It's raised when the client closes the connection.
            log_processing_step("MULTI_AGENT_STREAM", "TERMINATED", "Client disconnected, process stopped.")
        finally:
            # This block will run regardless of how the loop exits (completion, error, or termination).
            log_processing_step("MULTI_AGENT_STREAM", "FINISH", "Agent stream process has ended.")

    return Response(stream_with_context(multi_agent_stream()), mimetype='text/event-stream') 