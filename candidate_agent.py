import json
import os
from openai import OpenAI
from helpers import log_model_request, log_model_response, log_processing_step, get_prompt
import re
from datetime import datetime

# Initialize OpenAI client
openai_client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    base_url="http://47.93.181.123:4000",
)

class CandidateAgent:
    def __init__(self, resume_info, jd_info, candidate_profile):
        """
        初始化候选人agent
        
        Args:
            resume_info: 完整的简历信息
            jd_info: 脱敏的职位信息
            candidate_profile: 候选人求职画像
        """
        self.resume_info = resume_info
        self.jd_info = jd_info  # 这是脱敏版本
        self.candidate_profile = candidate_profile
        self.conversation_history = []  # 存储完整对话历史（包括planning）
        self.chat_history = []  # 存储给对方看的chatting历史
        self.decision_made = False
        self.final_decision = "UNCERTAIN"
        self.chat_rounds = 0  # 记录对话轮数
        
    def get_system_prompt(self):
        """获取候选人agent的系统提示"""
        prompt = get_prompt('candidate_agent_system.txt')
        if not prompt:
            # 如果文件读取失败，使用默认提示
            return """你是一位专业的求职者代理，代表候选人的利益进行求职撮合。请用JSON格式回复，包含type、reasoning、payload字段。"""
        
        # 替换候选人画像占位符
        if self.candidate_profile:
            profile_text = json.dumps(self.candidate_profile, ensure_ascii=False, indent=2)
            prompt = prompt.replace('{CANDIDATE_PROFILE_PLACEHOLDER}', profile_text)
        else:
            prompt = prompt.replace('{CANDIDATE_PROFILE_PLACEHOLDER}', '暂无画像信息')
        
        return prompt

    def respond(self, history=None):
        """
        核心方法，根据用户消息和历史记录生成回应
        """
        system_prompt = get_prompt('candidate_agent_system.txt')
        messages = [{"role": "system", "content": system_prompt}]

        # 如果没有历史记录，构建初始上下文
        if not history:
            initial_user_prompt = f"""以下是相关信息：

候选人简历信息：
{json.dumps(self.resume_info, ensure_ascii=False, indent=2)}

职位描述信息（脱敏版）：
{json.dumps(self.jd_info, ensure_ascii=False, indent=2)}

候选人求职画像：
{json.dumps(self.candidate_profile, ensure_ascii=False, indent=2)}
"""
            messages.append({"role": "user", "content": initial_user_prompt})
            
            # 初始启动指令
            messages.append({"role": "user", "content": "请开始评估这个职位机会，并与招聘方进行沟通。请先planning，然后发送chatting消息。"})
        else:
            # 如果有历史记录，直接使用
            messages.extend(history)
        
        # 增加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 遵循 LOGGING_GUIDE.md 格式记录模型请求
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                model_name = "bedrock-claude-4-sonnet"
                task_type = "CANDIDATE_AGENT_CHAT"
                
                print(f"[{timestamp}] 🤖 MODEL REQUEST | {model_name} | {task_type} | Input: {json.dumps(messages, ensure_ascii=False, indent=2)}")

                log_model_request("bedrock-claude-4-sonnet", "CANDIDATE_AGENT_RESPONSE", 
                                 f"Responding to recruiter message")
                
                response = openai_client.chat.completions.create(
                    model="bedrock-claude-4-sonnet",
                    messages=messages,
                    temperature=1,
                    max_tokens=2000
                )
                
                response_content = response.choices[0].message.content

                # 增加对空响应的检查和重试逻辑
                if not response_content:
                    if attempt < max_retries - 1:
                        log_processing_step("CANDIDATE_AGENT", "RETRY", f"Empty response on attempt {attempt + 1}, retrying...")
                        continue
                    else:
                        log_model_response("bedrock-claude-4-sonnet", "CANDIDATE_AGENT_RESPONSE", success=False, error_msg="Empty response from model after all retries")
                        return {
                            "type": "chatting",
                            "reasoning": f"模型在{max_retries}次尝试后仍返回空响应，使用默认回复",
                            "payload": "抱歉，我暂时遇到了技术问题，请稍后再试。如果问题持续，请联系管理员。"
                        }

                try:
                    # 解析模型返回的JSON字符串
                    parsed_response = json.loads(response_content)
                    response_type = parsed_response['type']
                    reasoning = parsed_response['reasoning']
                    payload = parsed_response['payload']
                    
                    if not response_type or not payload:
                        raise ValueError("JSON响应缺少'type'或'payload'字段")

                    # 记录完整的对话历史
                    conversation_entry = {
                        "sender": "candidate",
                        "type": response_type,
                        "reasoning": reasoning,
                        "content": payload,
                        "timestamp": __import__('datetime').datetime.now().isoformat()
                    }
                    self.conversation_history.append(conversation_entry)
                    
                    # 处理不同类型的回复
                    if response_type == "planning":
                        # planning不需要额外处理，已记录到历史中
                        pass
                    elif response_type == "chatting":
                        # chatting消息需要记录到对方可见的历史中
                        self.chat_rounds += 1
                        self.chat_history.append({
                            "sender": "candidate",
                            "content": payload,
                            "round": self.chat_rounds,
                            "timestamp": conversation_entry["timestamp"]
                        })
                    elif response_type == "decision":
                        # 处理决策
                        self.decision_made = True
                        if payload == "同意":
                            self.final_decision = "SUITABLE"
                        elif payload == "拒绝":
                            self.final_decision = "UNSUITABLE"
                        else:
                            self.final_decision = "UNKNOWN"
                    
                    log_model_response("bedrock-claude-4-sonnet", "CANDIDATE_AGENT_RESPONSE", success=True,
                                      output_summary=f"Generated {response_type} message, decision_made: {self.decision_made}")
                    log_processing_step("CANDIDATE_AGENT", "COMPLETE", 
                                       f"Candidate agent generated {response_type} message")
                    
                    return parsed_response
                    
                except json.JSONDecodeError as e:
                    # 如果JSON解析失败，记录错误并使用一个通用的、安全的回复
                    error_message = f"JSON解析失败: {e}"
                    log_processing_step("CANDIDATE_AGENT", "DEBUG", f"JSON decode error: {e}")
                    log_model_response("bedrock-claude-4-sonnet", "CANDIDATE_AGENT_RESPONSE", success=False, error_msg=error_message)
                    
                    # 返回一个安全的、通用的聊天消息，而不是返回None或崩溃
                    return {
                        "type": "chatting",
                        "reasoning": f"JSON解析失败: {e}，使用默认回复",
                        "payload": "抱歉，我在处理信息时遇到了一些问题，请稍后再试。"
                    }
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    log_processing_step("CANDIDATE_AGENT", "RETRY", f"Error on attempt {attempt + 1}: {str(e)}, retrying...")
                    continue
                else:
                    # 最后一次尝试也失败了
                    log_model_response("bedrock-claude-4-sonnet", "CANDIDATE_AGENT_RESPONSE", success=False, error_msg=f"All {max_retries} attempts failed: {str(e)}")
                    log_processing_step("CANDIDATE_AGENT", "ERROR", f"Error in candidate agent after all retries: {str(e)}")
                    return {
                        "type": "chatting",
                        "reasoning": f"多次重试后仍然失败: {str(e)}，使用默认回复",
                        "payload": f"抱歉，候选人代理遇到了技术问题：{str(e)}，请稍后重试或联系管理员。",
                        "error": True
                    }
    
    def get_conversation_history(self):
        """获取完整对话历史（包括planning）"""
        return self.conversation_history
    
    def get_chat_history(self):
        """获取对方可见的chatting历史"""
        return self.chat_history
    
    def get_final_decision(self):
        """获取最终决策"""
        return self.final_decision
    
    def has_reached_decision(self):
        """检查是否已做出最终决策"""
        return self.decision_made
    
    def get_chat_rounds(self):
        """获取对话轮数"""
        return self.chat_rounds 