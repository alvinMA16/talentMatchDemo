import json
import os
from openai import OpenAI
from helpers import log_model_request, log_model_response, log_processing_step, get_prompt

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
        self.final_decision = None
        self.has_made_decision = False
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

    def respond(self, candidate_message=None):
        """
        招聘方agent响应候选人或开始对话
        
        Args:
            candidate_message: 候选人的消息，如果为None表示开始对话
            
        Returns:
            dict: 解析后的回复，包含type、reasoning、payload等信息
        """
        if self.has_made_decision:
            return None
            
        log_processing_step("RECRUITER_AGENT", "START", f"Processing message from candidate")
        
        try:
            # 构建消息历史
            messages = [{"role": "system", "content": self.get_system_prompt()}]
            
            # 添加企业信息上下文
            context = f"""
职位信息：
{json.dumps(self.jd_info, ensure_ascii=False, indent=2)}

企业招聘画像：
{json.dumps(self.company_profile, ensure_ascii=False, indent=2)}

候选人简历信息（脱敏版本）：
{json.dumps(self.resume_info, ensure_ascii=False, indent=2)}
"""
            
            messages.append({"role": "user", "content": f"以下是相关信息：\n{context}"})
            
            # 添加对话历史（只有chatting部分对对方可见）
            for entry in self.chat_history:
                if entry["sender"] == "recruiter":
                    messages.append({"role": "assistant", "content": entry["content"]})
                else:
                    messages.append({"role": "user", "content": entry["content"]})
            
            # 添加当前候选人消息
            if candidate_message:
                messages.append({"role": "user", "content": candidate_message})
                # 先将候选人消息添加到chat历史中
                self.chat_history.append({
                    "sender": "candidate",
                    "content": candidate_message,
                    "timestamp": __import__('datetime').datetime.now().isoformat()
                })
            else:
                # 开始对话
                messages.append({"role": "user", "content": "请开始评估这个候选人，并与候选人代理进行沟通。请先planning，然后发送chatting消息。"})
            
            log_model_request("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", 
                             f"Responding to candidate message")
            
            response = openai_client.chat.completions.create(
                model="bedrock-claude-4-sonnet",
                messages=messages,
                temperature=1,
                max_tokens=1000
            )
            
            recruiter_response = response.choices[0].message.content.strip()
            
            # 检查响应是否为空
            if not recruiter_response:
                log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=False, 
                                  error_msg="Empty response from model")
                return {
                    "type": "chatting",
                    "reasoning": "模型返回空响应，使用默认回复",
                    "payload": "抱歉，我暂时无法给出回复，请稍后再试。",
                    "error": True
                }
            
            # 记录原始响应以便调试
            log_processing_step("RECRUITER_AGENT", "DEBUG", f"Raw model response: {recruiter_response}")
            
            # 清理可能的markdown格式
            cleaned_response = recruiter_response.strip()
            if cleaned_response.startswith('```json'):
                cleaned_response = cleaned_response[7:]
            if cleaned_response.endswith('```'):
                cleaned_response = cleaned_response[:-3]
            cleaned_response = cleaned_response.strip()
            
            # 解析JSON回复
            try:
                # 尝试解析JSON
                response_data = json.loads(cleaned_response)
            except json.JSONDecodeError as json_error:
                # 如果JSON解析失败，尝试找到有效的JSON部分
                log_processing_step("RECRUITER_AGENT", "DEBUG", f"JSON decode error: {str(json_error)}")
                
                # 尝试找到第一个完整的JSON对象
                try:
                    # 查找第一个 { 和对应的 }
                    start_idx = cleaned_response.find('{')
                    if start_idx != -1:
                        brace_count = 0
                        end_idx = start_idx
                        for i, char in enumerate(cleaned_response[start_idx:], start_idx):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    end_idx = i
                                    break
                        
                        if brace_count == 0:
                            json_part = cleaned_response[start_idx:end_idx + 1]
                            log_processing_step("RECRUITER_AGENT", "DEBUG", f"Extracted JSON part: {json_part}")
                            response_data = json.loads(json_part)
                        else:
                            raise json_error
                    else:
                        raise json_error
                except:
                    raise json_error
            
            # 验证响应格式
            if not isinstance(response_data, dict) or 'type' not in response_data or 'reasoning' not in response_data or 'payload' not in response_data:
                raise ValueError("Response missing required fields: type, reasoning, payload")
            
            response_type = response_data['type']
            reasoning = response_data['reasoning']
            payload = response_data['payload']
            
            # 验证消息类型
            if response_type not in ['planning', 'chatting', 'decision']:
                raise ValueError(f"Invalid message type: {response_type}")
            
            # 记录完整的对话历史
            conversation_entry = {
                "sender": "recruiter",
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
                    "sender": "recruiter",
                    "content": payload,
                    "round": self.chat_rounds,
                    "timestamp": conversation_entry["timestamp"]
                })
            elif response_type == "decision":
                # 处理决策
                self.has_made_decision = True
                if payload == "同意":
                    self.final_decision = "SUITABLE"
                elif payload == "拒绝":
                    self.final_decision = "UNSUITABLE"
                else:
                    self.final_decision = "UNKNOWN"
            
            log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=True,
                              output_summary=f"Generated {response_type} message, decision_made: {self.has_made_decision}")
            log_processing_step("RECRUITER_AGENT", "COMPLETE", 
                               f"Recruiter agent generated {response_type} message")
            
            return response_data
                
        except (json.JSONDecodeError, ValueError) as e:
            # JSON解析失败，尝试提取有用信息
            log_model_response("bedrock-claude-4-sonnet", "RECRUITER_AGENT_RESPONSE", success=False, 
                              error_msg=f"JSON parse error: {str(e)}")
            
            # 返回错误格式
            return {
                "type": "chatting",
                "reasoning": f"JSON解析失败: {str(e)}，使用默认回复",
                "payload": "抱歉，我在处理信息时遇到了一些问题，请稍后再试。",
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
        return self.has_made_decision
    
    def get_chat_rounds(self):
        """获取对话轮数"""
        return self.chat_rounds 