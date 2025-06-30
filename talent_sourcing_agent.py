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
        log_model_response("o4-mini", f"AGENT_{agent_name.upper()}", success=True, output_summary=content[:300])
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
    elif tool_name == "show_preview":
        # This tool doesn't return data to the agent, it streams an event to the frontend.
        # The content is passed directly. The return value signals success to the agent.
        html_content = parameters.get("html_content", "<p>内容为空。</p>")
        # We need a way to send this to the frontend stream *from here*.
        # For now, we'll return a success message that the observer can see.
        # The actual streaming will be handled in the main loop.
        return json.dumps({"status": "success", "message": f"内容已发送到预览区。内容长度: {len(html_content)}"})
    elif tool_name == "ask_user":
        question = parameters.get("question", "")
        # This tool also doesn't return data to the agent loop. It pauses the process.
        # We just return a success message for the agent's internal state.
        return json.dumps({"status": "success", "message": f"已向用户提问: {question}"})
    else:
        return json.dumps({"status": "error", "message": f"未知工具: {tool_name}"})

@talent_sourcing_bp.route('/api/talent_sourcing/chat', methods=['POST'])
def talent_sourcing_chat_api():
    """API endpoint for the multi-agent talent sourcing chat."""
    data = request.get_json()
    user_message = data.get('message')
    history = data.get('history', [])
    agent_state = data.get('agent_state', None) # New: Get agent state from request

    if not user_message:
        return Response(json.dumps({'error': 'No message provided'}), status=400, mimetype='application/json')

    def multi_agent_stream(user_message, history, agent_state):
        # 1. Initialize State
        plan = agent_state.get("plan", None) if agent_state else None
        current_step_index = agent_state.get("current_step_index", 0) if agent_state else 0
        task_history = agent_state.get("task_history", []) if agent_state else []
        main_task = agent_state.get("main_task", user_message) if agent_state else user_message
        max_turns = 10
        current_turn = agent_state.get("turn_count", 0) if agent_state else 0

        try:
            executor_capabilities = get_prompt('executor_capabilities.txt')
            if not executor_capabilities:
                yield stream_event("error", {"message": "Critical Error: Could not load executor capabilities."})
                return
            
            # New: Handle resumption from user feedback by invoking the Observer first
            if agent_state and agent_state.get('last_action') == 'ask_user':
                previous_step_info = plan[current_step_index - 1]
                execution_result = json.dumps({"status": "success", "user_response": user_message})

                yield stream_event("status_update", {"message": f"Observer is evaluating your feedback..."})
                
                # Run Observer
                observer_prompt_template = get_prompt('sourcing_observer_system.txt')
                observer_prompt = observer_prompt_template.format(executor_capabilities=executor_capabilities)
                observer_messages = [
                    {"role": "system", "content": observer_prompt},
                    {"role": "user", "content": f"Full Plan:\n{json.dumps(plan, indent=2)}\n\nCurrent Step:\n{json.dumps(previous_step_info, indent=2)}\n\nExecution Result:\n{execution_result}"}
                ]
                decision_str = call_agent("observer", observer_messages)
                decision = json.loads(decision_str)
                yield stream_event("observer_output", decision)

                # Update task history with this synthetic step
                task_summary = {"step": previous_step_info, "result": execution_result, "observer_decision": decision}
                task_history.append(task_summary)

                # Handle decision
                if decision.get("decision") == "finish":
                    yield stream_event("final_result", {"message": decision.get("summary", "Task completed based on your feedback.")})
                    return
                elif decision.get("decision") == "replan":
                    yield stream_event("status_update", {"message": "Observer requested a replan based on your feedback."})
                    main_task = f"Original task: '{main_task}'. Your latest feedback: '{user_message}'. Observer feedback: {decision.get('feedback_to_planner')}"
                    plan = None # Reset plan to trigger replanning
                # If 'proceed', do nothing, the main loop will continue executing the next step.

            while current_turn < max_turns:
                current_turn += 1
                
                # 2. Planner Agent - Only runs if there is no existing plan
                if not plan:
                    yield stream_event("status_update", {"message": "--- Planning Phase ---"})
                    planner_prompt_template = get_prompt('sourcing_planner_system.txt')
                    planner_prompt = planner_prompt_template.format(executor_capabilities=executor_capabilities)
                    
                    # Construct full conversation history for the planner
                    conversation_context = []
                    for msg in history:
                        conversation_context.append(f"{msg['role']}: {msg['content']}")
                    conversation_context.append(f"user: {user_message}")
                    
                    planner_user_prompt = (
                        f"Conversation History:\n{'---'.join(conversation_context)}\n\n"
                        f"Agent's Structured Task History:\n{json.dumps(task_history, indent=2)}"
                    )

                    planner_messages = [
                        {"role": "system", "content": planner_prompt},
                        {"role": "user", "content": planner_user_prompt}
                    ]
                    try:
                        plan_str = call_agent("planner", planner_messages)
                        plan_data = json.loads(plan_str)
                        plan = plan_data.get("plan", []) # The plan is the list of steps
                        yield stream_event("planner_output", {"plan": plan}) # Stream the whole plan
                    except Exception as e:
                        yield stream_event("error", {"message": f"Planner failed: {str(e)}"})
                        break # Exit the loop on planner failure
                
                # 3. Execution Phase
                yield stream_event("status_update", {"message": "--- Execution Phase ---"})
                
                # Loop through the plan starting from the current step
                for step_index in range(current_step_index, len(plan)):
                    step_info = plan[step_index]
                    current_step_index = step_index
                    task = step_info.get("task")

                    yield stream_event("status_update", {"message": f"Executing Step {step_info.get('step')}: {task}"})
                    time.sleep(1)

                    # 4. Executor Agent
                    executor_prompt = get_prompt('sourcing_executor_system.txt')
                    executor_messages = [
                        {"role": "system", "content": executor_prompt},
                        {"role": "user", "content": f"Main Task: {main_task}\n\nFull Plan:\n{json.dumps(plan, indent=2)}\n\nPrevious Steps History:\n{json.dumps(task_history, indent=2)}\n\nCurrent Task:\n{task}"}
                    ]
                    
                    try:
                        executor_output_str = call_agent("executor", executor_messages, json_output=True)
                        executor_output = json.loads(executor_output_str)
                    except Exception as e:
                        yield stream_event("error", {"message": f"Executor failed on step {step_info.get('step')}: {str(e)}"})
                        # Decide how to handle failure. For now, we stop.
                        return

                    execution_result = ""
                    action = executor_output.get("action")
                    if action == "tool_call":
                        tool_calls = executor_output.get("tool_calls", [])
                        if tool_calls:
                            call = tool_calls[0]
                            tool_name = call.get("name")
                            arguments = call.get("arguments", {})
                            yield stream_event("tool_call", {"tool": tool_name, "parameters": arguments})

                            # Handle special tools that affect the stream
                            if tool_name == "show_preview":
                                html_content = arguments.get("html_content", "<p>内容为空。</p>")
                                yield stream_event("show_preview", {"html_content": html_content})
                            
                            elif tool_name == "ask_user":
                                question = arguments.get("question", "需要您的反馈，但问题描述丢失。")
                                # Create agent state to be sent to frontend
                                agent_state_to_persist = {
                                    "plan": plan,
                                    "current_step_index": current_step_index + 1, # Start from next step
                                    "task_history": task_history,
                                    "main_task": main_task,
                                    "turn_count": current_turn,
                                    "last_action": "ask_user" # Flag that we are waiting for user input
                                }
                                yield stream_event("user_feedback_request", {
                                    "question": question,
                                    "agent_state": agent_state_to_persist # Send state to frontend
                                })
                                return # IMPORTANT: Stop the stream and wait for user's next message

                            execution_result = execute_tool(tool_name, arguments)
                        else:
                            execution_result = json.dumps({"status": "error", "message": "Executor wanted to call a tool but sent an empty tool_calls list."})
                    elif action == "generate_content":
                        execution_result = executor_output.get("content", "")
                    else:
                        execution_result = executor_output_str

                    yield stream_event("executor_output", {"step": step_info.get('step'), "result": execution_result})
                    time.sleep(1)

                    # 5. Observer Agent
                    observer_prompt_template = get_prompt('sourcing_observer_system.txt')
                    observer_prompt = observer_prompt_template.format(executor_capabilities=executor_capabilities)
                    observer_messages = [
                        {"role": "system", "content": observer_prompt},
                        {"role": "user", "content": f"Full Plan:\n{json.dumps(plan, indent=2)}\n\nCurrent Step:\n{json.dumps(step_info, indent=2)}\n\nExecution Result:\n{execution_result}"}
                    ]
                    try:
                        decision_str = call_agent("observer", observer_messages)
                        decision = json.loads(decision_str)
                        yield stream_event("observer_output", decision)
                    except Exception as e:
                        yield stream_event("error", {"message": f"Observer failed on step {step_info.get('step')}: {str(e)}"})
                        break

                    time.sleep(1)
                    
                    # 6. Update State and Handle Decision
                    task_summary = {"step": step_info, "result": execution_result, "observer_decision": decision}
                    task_history.append(task_summary)

                    if decision.get("decision") == "replan":
                        yield stream_event("status_update", {"message": "Observer requested a replan. Returning to planner."})
                        main_task = f"Original task: '{main_task}'. Feedback from observer: {decision.get('feedback_to_planner')}"
                        plan = None # Reset plan to trigger replanning
                        task_history.append({"REPLAN_TRIGGERED": decision.get("feedback_to_planner")})
                        break # Break from step execution loop, outer while loop will replan
                
                # If the inner loop finished all steps without a 'replan'
                else: 
                    yield stream_event("final_result", {"message": "Plan executed successfully.", "full_history": task_history})
                    break # Exit the main while loop

            yield stream_event("status_update", {"message": "Process finished."})
        except GeneratorExit:
            log_processing_step("MULTI_AGENT_STREAM", "TERMINATED", "Client disconnected, process stopped.")
        finally:
            log_processing_step("MULTI_AGENT_STREAM", "FINISH", "Agent stream process has ended.")

    return Response(stream_with_context(multi_agent_stream(user_message, history, agent_state)), mimetype='text/event-stream') 