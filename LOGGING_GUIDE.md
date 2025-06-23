# TalentMatch 系统日志指南

## 概述

本系统已增强了全面的日志记录功能，支持**后端控制台**和**前端浏览器控制台**双重输出，帮助开发者和运维人员更好地了解系统运行状况。日志按照不同类型进行分类，包含时间戳和状态标识符，便于快速识别和调试。

### 🆕 前端日志功能

- **实时同步**: 后端日志通过Server-Sent Events (SSE)实时推送到前端
- **浏览器控制台**: 在开发环境中自动显示后端日志，带有颜色编码
- **可视化面板**: 按 `Ctrl+Shift+L` 切换页面内日志显示面板
- **智能过滤**: 根据日志类型自动应用不同的颜色和样式

## 日志类型

### 1. 🤖 模型调用日志 (MODEL REQUEST/RESPONSE)

记录所有AI模型的请求和响应信息：

**请求日志格式：**
```
[YYYY-MM-DD HH:MM:SS] 🤖 MODEL REQUEST | {模型名称} | {任务类型} | Input: {输入摘要}
```

**响应日志格式：**
```
[YYYY-MM-DD HH:MM:SS] 🤖 MODEL RESPONSE | {模型名称} | {任务类型} | ✅ SUCCESS | Output: {输出摘要}
[YYYY-MM-DD HH:MM:SS] 🤖 MODEL RESPONSE | {模型名称} | {任务类型} | ❌ ERROR | Error: {错误信息}
```

**覆盖的模型调用：**
- Gemini 1.5 Flash (简历信息提取、JD信息提取、数据脱敏)
- OpenAI o4-mini (简历生成聊天)

### 2. ⚙️ 处理步骤日志 (PROCESSING)

记录系统主要处理步骤的状态：

**日志格式：**
```
[YYYY-MM-DD HH:MM:SS] ⚙️ PROCESSING | {步骤名称} | 🚀 START | {详细信息}
[YYYY-MM-DD HH:MM:SS] ⚙️ PROCESSING | {步骤名称} | ✅ COMPLETE | {详细信息}
[YYYY-MM-DD HH:MM:SS] ⚙️ PROCESSING | {步骤名称} | ❌ ERROR | {错误信息}
[YYYY-MM-DD HH:MM:SS] ⚙️ PROCESSING | {步骤名称} | ℹ️ {状态} | {详细信息}
```

**主要处理步骤：**
- SYSTEM_INIT: 系统初始化
- DATABASE_MIGRATION: 数据库迁移
- RESUME_UPLOAD: 简历上传处理
- RESUME_BATCH_UPLOAD: 简历批量上传
- JD_BATCH_UPLOAD: JD批量上传
- RESUME_DESENSITIZATION: 简历脱敏
- JD_DESENSITIZATION: JD脱敏
- AI_FACILITATE: AI人岗撮合
- DUPLICATE_CHECK: 重复检查
- DATABASE_INSERT: 数据库插入

### 3. 📦 批量处理日志 (BATCH)

记录批量操作中每个项目的处理状态：

**日志格式：**
```
[YYYY-MM-DD HH:MM:SS] 📦 BATCH | {批量任务名称} | ✅ ({当前项目}/{总项目数}) | {项目名称} | {详细信息}
[YYYY-MM-DD HH:MM:SS] 📦 BATCH | {批量任务名称} | ❌ ({当前项目}/{总项目数}) | {项目名称} | {错误信息}
```

**批量任务类型：**
- JD_BATCH_UPLOAD: JD文件批量上传处理

### 4. 🔒 脱敏处理日志 (DESENSITIZATION)

记录数据脱敏操作的结果：

**日志格式：**
```
[YYYY-MM-DD HH:MM:SS] 🔒 DESENSITIZATION | {数据类型} | ✅ SUCCESS | {数据标识}
[YYYY-MM-DD HH:MM:SS] 🔒 DESENSITIZATION | {数据类型} | ❌ ERROR | {数据标识} | Error: {错误信息}
```

**数据类型：**
- RESUME: 简历数据脱敏
- JD: 职位描述数据脱敏

## 前端日志使用方法

### 浏览器控制台

1. 打开浏览器开发者工具 (F12)
2. 切换到 Console 标签
3. 在开发环境中(localhost)，日志会自动开始显示
4. 日志会根据类型显示不同的颜色：
   - 🤖 模型请求: 蓝色粗体
   - ✅ 成功响应: 绿色粗体
   - ❌ 错误: 红色粗体
   - ⚙️ 处理步骤: 青色/绿色/红色
   - 📦 批量处理: 紫色
   - 🔒 脱敏: 橙色

### 页面日志面板

1. 按 `Ctrl+Shift+L` 切换日志面板显示
2. 日志面板支持：
   - 实时滚动显示
   - 颜色编码
   - 清空日志按钮
   - 时间戳显示

## 示例日志输出

### 后端控制台 & 前端浏览器控制台
```
[2024-01-15 10:30:15] ⚙️ PROCESSING | SYSTEM_INIT | ✅ COMPLETE | Google API Key configured successfully
[2024-01-15 10:30:15] ⚙️ PROCESSING | DATABASE_MIGRATION | 🚀 START | Checking database schema
[2024-01-15 10:30:15] ⚙️ PROCESSING | DATABASE_MIGRATION | ✅ COMPLETE | Database schema is up-to-date
[2024-01-15 10:30:15] ⚙️ PROCESSING | SYSTEM_START | 🚀 START | Starting TalentMatch application on port 8000

[2024-01-15 10:35:22] ⚙️ PROCESSING | RESUME_UPLOAD | 🚀 START | Processing file: resume_john_doe.pdf
[2024-01-15 10:35:22] 🤖 MODEL REQUEST | gemini-1.5-flash | RESUME_EXTRACTION | PDF file: resume_john_doe.pdf
[2024-01-15 10:35:25] 🤖 MODEL RESPONSE | gemini-1.5-flash | RESUME_EXTRACTION | ✅ SUCCESS | Output: Extracted: John Doe
[2024-01-15 10:35:25] ⚙️ PROCESSING | RESUME_DESENSITIZATION | 🚀 START | Desensitizing data for: John Doe
[2024-01-15 10:35:25] 🤖 MODEL REQUEST | gemini-1.5-flash | RESUME_DESENSITIZATION | Resume: John Doe
[2024-01-15 10:35:27] 🤖 MODEL RESPONSE | gemini-1.5-flash | RESUME_DESENSITIZATION | ✅ SUCCESS | Output: Desensitized name: Candidate
[2024-01-15 10:35:27] 🔒 DESENSITIZATION | RESUME | ✅ SUCCESS | John Doe
[2024-01-15 10:35:27] ⚙️ PROCESSING | RESUME_UPLOAD | ✅ COMPLETE | Successfully parsed: resume_john_doe.pdf

[2024-01-15 10:40:10] ⚙️ PROCESSING | JD_BATCH_UPLOAD | 🚀 START | Processing file: jobs.xlsx
[2024-01-15 10:40:11] ⚙️ PROCESSING | FILE_PARSING | ✅ COMPLETE | Parsed Excel file with 5 jobs
[2024-01-15 10:40:11] ⚙️ PROCESSING | JD_BATCH_PROCESSING | 🚀 START | Processing 5 jobs
[2024-01-15 10:40:11] 🤖 MODEL REQUEST | gemini-1.5-flash | JD_EXTRACTION | Batch item 1/5: Row 2
[2024-01-15 10:40:13] 🤖 MODEL RESPONSE | gemini-1.5-flash | JD_EXTRACTION | ✅ SUCCESS | Output: Extracted: Software Engineer @ TechCorp
[2024-01-15 10:40:13] 🔒 DESENSITIZATION | JD | ✅ SUCCESS | Software Engineer @ TechCorp
[2024-01-15 10:40:13] 📦 BATCH | JD_BATCH_UPLOAD | ✅ (1/5) | Software Engineer @ TechCorp | Successfully inserted into database
```

### 前端浏览器初始化信息
```
🚀 TalentMatch Frontend Logger
📡 已连接后端日志流，实时显示系统运行状态
⌨️  按 Ctrl+Shift+L 切换页面日志显示
============================================================
🔗 Log stream connected
✅ 日志流连接成功
```

## 日志级别说明

- **🚀 START**: 操作开始
- **✅ SUCCESS/COMPLETE**: 操作成功完成
- **❌ ERROR**: 操作出现错误
- **ℹ️ 其他状态**: 操作进行中的状态信息
- **⚠️ WARNING**: 警告信息（非错误但需要注意）

## 调试建议

### 后端调试
1. **性能监控**: 关注 MODEL REQUEST 和 RESPONSE 之间的时间差
2. **错误追踪**: 搜索 ❌ ERROR 标记快速定位问题
3. **批量处理**: 监控 📦 BATCH 日志了解批量操作进度
4. **系统健康**: 检查 SYSTEM_INIT 和 DATABASE_MIGRATION 日志确保系统正常启动

### 前端调试
1. **实时监控**: 在浏览器控制台实时查看后端处理过程
2. **网络问题**: 如果日志流中断，会自动尝试重连
3. **性能分析**: 可以在前端观察API调用的完整生命周期
4. **快捷操作**: 
   - `Ctrl+Shift+L`: 切换页面日志面板
   - 控制台中输入 `frontendLogger.clearLogs()`: 清空所有日志

## 技术实现

### 后端 (Python)
- **日志广播**: 使用内存队列存储日志消息
- **SSE推送**: 通过Server-Sent Events实时推送日志到前端
- **线程安全**: 队列操作支持多线程安全

### 前端 (JavaScript)
- **EventSource**: 使用浏览器原生EventSource API接收SSE
- **智能重连**: 连接中断时自动重连机制
- **环境检测**: 仅在开发环境(localhost)自动启用
- **UI组件**: 可选的浮动日志面板，支持实时滚动和颜色编码

## 注意事项

- 所有日志都包含精确的时间戳，便于时序分析
- 模型调用日志包含输入输出摘要，但不记录完整内容以保护隐私
- 脱敏日志仅记录操作结果，不记录敏感数据内容
- 批量处理提供详细的进度信息，便于监控长时间运行的任务
- **前端日志流**: 仅在开发环境(localhost/127.0.0.1)自动开启，生产环境需手动启用
- **内存使用**: 日志队列最大容量500条，超出后自动清理最老的记录
- **连接管理**: 页面刷新或关闭时会自动断开日志流连接 