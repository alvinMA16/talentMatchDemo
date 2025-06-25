#!/usr/bin/env python3
"""
测试消息队列功能的简单脚本
"""

import sys
import os
import datetime
import json

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入消息队列类
from app import MessageQueue, create_message_from_agent_response

def test_message_queue():
    """测试消息队列基本功能"""
    print("🧪 开始测试消息队列功能...")
    
    # 1. 创建消息队列实例
    queue = MessageQueue()
    print(f"✅ 创建消息队列实例: {queue}")
    
    # 2. 初始化会话
    session_id = "test_session_001"
    queue.init_session(session_id)
    print(f"✅ 初始化会话: {session_id}")
    
    # 3. 添加不同类型的消息
    messages = [
        {
            'source': 'candidate',
            'type': 'planning',
            'reasoning': '我需要了解这个职位的具体要求和发展前景',
            'payload': '正在分析职位匹配度...'
        },
        {
            'source': 'candidate',
            'type': 'chatting',
            'reasoning': '基于分析结果，我想了解更多细节',
            'payload': '您好，我对这个AI产品经理职位很感兴趣，能详细介绍一下工作内容吗？'
        },
        {
            'source': 'recruiter',
            'type': 'planning',
            'reasoning': '候选人看起来有相关背景，我需要了解他的具体经验',
            'payload': '准备询问候选人的AI产品经验...'
        },
        {
            'source': 'recruiter',
            'type': 'chatting',
            'reasoning': '通过提问了解候选人的实际能力',
            'payload': '您好！这个职位主要负责AI产品的需求分析和产品设计，请问您有相关的AI产品经验吗？'
        },
        {
            'source': 'candidate',
            'type': 'decision',
            'reasoning': '经过沟通，我认为这个职位很适合我的发展方向',
            'payload': '同意'
        }
    ]
    
    # 添加消息到队列
    for msg in messages:
        added_msg = queue.add_message(
            source=msg['source'],
            msg_type=msg['type'],
            reasoning=msg['reasoning'],
            payload=msg['payload']
        )
        print(f"✅ 添加消息 #{added_msg['id']}: {msg['source']} - {msg['type']}")
    
    # 4. 测试消息检索功能
    print(f"\n📊 消息统计:")
    print(f"   总消息数: {queue.get_message_count()}")
    print(f"   候选人消息数: {len(queue.get_messages(source='candidate'))}")
    print(f"   企业方消息数: {len(queue.get_messages(source='recruiter'))}")
    print(f"   对话消息数: {len(queue.get_chat_history())}")
    print(f"   Planning消息数: {len(queue.get_messages(msg_type='planning'))}")
    print(f"   Decision消息数: {len(queue.get_messages(msg_type='decision'))}")
    
    # 5. 获取会话摘要
    summary = queue.get_session_summary()
    print(f"\n📋 会话摘要:")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    
    # 6. 测试最新消息获取
    latest_msg = queue.get_latest_message()
    print(f"\n📬 最新消息:")
    print(f"   来源: {latest_msg['source']}")
    print(f"   类型: {latest_msg['type']}")
    print(f"   内容: {latest_msg['payload']}")
    
    # 7. 测试agent响应转换
    print(f"\n🤖 测试Agent响应转换:")
    agent_response = {
        'type': 'chatting',
        'reasoning': '根据候选人的回答，我需要进一步了解技术细节',
        'payload': '您提到的AI产品经验很有趣，能具体说说您负责的项目吗？'
    }
    
    converted_msg = create_message_from_agent_response(agent_response, 'recruiter')
    if converted_msg:
        print(f"✅ 成功转换Agent响应为消息: #{converted_msg['id']}")
    
    # 8. 清理测试
    queue.clear()
    print(f"\n🧹 清理完成，剩余消息数: {queue.get_message_count()}")
    
    print(f"\n🎉 消息队列测试完成！")

def test_concurrent_sessions():
    """测试多会话场景"""
    print("\n🔄 测试多会话场景...")
    
    # 创建两个不同的队列实例模拟并发
    queue1 = MessageQueue()
    queue2 = MessageQueue()
    
    # 初始化不同会话
    queue1.init_session("session_001")
    queue2.init_session("session_002")
    
    # 在不同会话中添加消息
    queue1.add_message('candidate', 'chatting', '第一个会话的消息', '你好，我是第一个会话')
    queue2.add_message('recruiter', 'chatting', '第二个会话的消息', '你好，我是第二个会话')
    
    print(f"✅ 会话1消息数: {queue1.get_message_count()}")
    print(f"✅ 会话2消息数: {queue2.get_message_count()}")
    
    # 获取各自的摘要
    summary1 = queue1.get_session_summary()
    summary2 = queue2.get_session_summary()
    
    print(f"✅ 会话1 ID: {summary1['session_id']}")
    print(f"✅ 会话2 ID: {summary2['session_id']}")
    
    print("🎉 多会话测试完成！")

if __name__ == "__main__":
    test_message_queue()
    test_concurrent_sessions() 