#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试JSON修复功能的脚本
"""

import json
from helpers import diagnose_json_error

def test_json_repair():
    # 模拟一些常见的JSON错误场景
    test_cases = [
        # 缺少逗号的情况
        '''
        {
            "name": "张伟",
            "email": "test@example.com"
            "phone": "138****8888",
            "skills": "Python, Java"
        }
        ''',
        
        # 多余逗号的情况
        '''
        {
            "name": "张伟",
            "email": "test@example.com",
            "phone": "138****8888",
            "skills": "Python, Java",
        }
        ''',
        
        # 带有前后文字的JSON
        '''
        这是脱敏后的简历：
        {
            "name": "张伟",
            "email": "test@example.com",
            "phone": "138****8888"
        }
        以上是脱敏结果。
        ''',
        
        # 正确的JSON（应该正常解析）
        '''
        {
            "name": "张伟",
            "email": "test@example.com",
            "phone": "138****8888"
        }
        '''
    ]
    
    print("=== JSON修复测试 ===\n")
    
    for i, test_json in enumerate(test_cases, 1):
        print(f"测试用例 {i}:")
        print(f"原始JSON: {test_json.strip()[:100]}...")
        
        try:
            # 尝试直接解析
            result = json.loads(test_json.strip())
            print("✅ JSON格式正确，无需修复")
        except json.JSONDecodeError as e:
            print(f"❌ JSON解析失败: {e}")
            
            # 应用修复逻辑
            try:
                cleaned_text = test_json.strip()
                
                # 移除可能的前后缀内容，只保留JSON部分
                start_idx = cleaned_text.find('{')
                end_idx = cleaned_text.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    fixed_text = cleaned_text[start_idx:end_idx+1]
                    
                    result = json.loads(fixed_text)
                    print("🔧 JSON修复成功！")
                    
            except json.JSONDecodeError as fix_error:
                print(f"🚫 JSON修复失败: {fix_error}")
                
                # 使用诊断工具
                diagnosis = diagnose_json_error(test_json.strip(), str(e))
                print(f"诊断报告:\n{diagnosis}")
        
        print("-" * 50)

if __name__ == "__main__":
    test_json_repair() 