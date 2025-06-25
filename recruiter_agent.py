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

class RecruiterAgent:
    def __init__(self, resume_info, jd_info, company_profile):
        """
        初始化招聘方agent
        
        Args:
            resume_info: 脱敏的简历信息
            jd_info: 完整的职位信息
            company_profile: 企业招聘画像
        """
        self.resume_info = resume_info  # 这是脱敏版本
        self.jd_info = jd_info
        self.company_profile = company_profile
        self.conversation_history = []  # 存储完整对话历史（包括planning）
        self.chat_history = []  # 存储给对方看的chatting历史
        self.decision_made = False
        self.final_decision = "UNCERTAIN"
        self.chat_rounds = 0  # 记录对话轮数
        
    def get_system_prompt(self):
        """获取招聘方agent的系统提示"""
        prompt = get_prompt('recruiter_agent_system.txt')
        if not prompt:
            # 如果文件读取失败，使用默认提示
            return """你是一位专业的招聘代理，代表企业的利益进行人才招聘撮合。请用JSON格式回复，包含type、reasoning、payload字段。"""
        
        # 替换企业画像占位符
        if self.company_profile:
            profile_text = json.dumps(self.company_profile, ensure_ascii=False, indent=2)
            prompt = prompt.replace('{COMPANY_PROFILE_PLACEHOLDER}', profile_text)
        else:
            prompt = prompt.replace('{COMPANY_PROFILE_PLACEHOLDER}', '暂无画像信息')
        
        return prompt

    def respond(self, history=None):
        """
        核心方法，根据用户消息和历史记录生成回应
        """
        system_prompt = get_prompt('recruiter_agent_system.txt')
        messages = [{"role": "system", "content": system_prompt}]

        # 如果没有历史记录，构建初始上下文
        if not history:
            initial_user_prompt = f"""以下是相关信息：

职位信息：
{json.dumps(self.jd_info, ensure_ascii=False, indent=2)}

候选人简历信息（脱敏版）：
{json.dumps(self.resume_info, ensure_ascii=False, indent=2)}

企业招聘画像：
{json.dumps(self.company_profile, ensure_ascii=False, indent=2)}
"""
            messages.append({"role": "user", "content": initial_user_prompt})
            
            # 初始启动指令
            messages.append({"role": "user", "content": "请开始评估这个候选人，并与候选人代理进行沟通。请先planning，然后发送chatting消息。"})
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
                task_type = "RECRUITER_AGENT_CHAT"
                
                print(f"[{timestamp}] 🤖 MODEL REQUEST | {model_name} | {task_type} | Input: {json.dumps(messages, ensure_ascii=False, indent=2)}")
                
                response = openai_client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=1,
                    max_tokens=2000
                )
                
                response_content = response.choices[0].message.content

                # 增加对空响应的检查和重试逻辑
                if not response_content:
                    if attempt < max_retries - 1:
                        log_processing_step("RECRUITER_AGENT", "RETRY", f"Empty response on attempt {attempt + 1}, retrying...")
                        continue
                    else:
                        log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=False, error_msg="Empty response from model after all retries")
                        return {
                            "type": "chatting",
                            "reasoning": f"模型在{max_retries}次尝试后仍返回空响应，使用默认回复",
                            "payload": "抱歉，我暂时遇到了技术问题，请稍后再试。如果问题持续，请联系管理员。"
                        }

                try:
                    # 解析模型返回的JSON字符串
                    parsed_response = json.loads(response_content)
                    response_type = parsed_response.get("type")
                    reasoning = parsed_response.get("reasoning")
                    payload = parsed_response.get("payload")

                    if not response_type or not payload:
                        raise ValueError("JSON响应缺少'type'或'payload'字段")

                except json.JSONDecodeError as e:
                    # 如果JSON解析失败，记录错误并使用一个通用的、安全的回复
                    error_message = f"JSON解析失败: {e}"
                    log_processing_step("RECRUITER_AGENT", "DEBUG", f"JSON decode error: {e}")
                    log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=False, error_msg=error_message)

                    # 返回一个安全的、通用的聊天消息
                    return {
                        "type": "chatting",
                        "reasoning": f"JSON解析失败: {e}，使用默认回复",
                        "payload": "抱歉，我在处理信息时遇到了一些问题，请稍后再试。"
                    }

                # 根据响应类型更新内部状态
                self.conversation_history.append({
                    "sender": "recruiter",
                    "type": response_type,
                    "reasoning": reasoning,
                    "content": payload,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
                
                # 处理不同类型的回复
                if response_type == "planning":
                    # planning不需要额外处理，已记录到历史中
                    pass
                elif response_type == "chatting":
                    # chatting消息需要记录到对方可见的历史中
                    self.chat_rounds += 1
                    self.chat_history.append({
                        "sender": "recruiter",
                        "content": payload,
                        "round": self.chat_rounds,
                        "timestamp": __import__('datetime').datetime.now().isoformat()
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
                
                log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=True,
                                  output_summary=f"Generated {response_type} message, decision_made: {self.decision_made}")
                log_processing_step("RECRUITER_AGENT", "COMPLETE", 
                                   f"Recruiter agent generated {response_type} message")
                
                return {
                    "type": response_type,
                    "reasoning": reasoning,
                    "payload": payload
                }
                
            except Exception as e:
                if attempt < max_retries - 1:
                    log_processing_step("RECRUITER_AGENT", "RETRY", f"Error on attempt {attempt + 1}: {str(e)}, retrying...")
                    continue
                else:
                    # 最后一次尝试也失败了
                    log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=False, 
                                      error_msg=f"All {max_retries} attempts failed: {str(e)}")
                    
                    # 返回错误格式
                    return {
                        "type": "chatting",
                        "reasoning": f"多次重试后仍然失败: {str(e)}，使用默认回复",
                        "payload": f"抱歉，我遇到了技术问题（{str(e)}），请稍后重试或联系管理员。",
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