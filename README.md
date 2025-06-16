# Talent Match - AI人才匹配平台

一个基于AI的智能人才匹配平台，通过先进的算法实现候选人与职位的精准匹配，提升招聘效率和匹配质量。

## 🎯 产品特色

- 🧠 **AI智能匹配** - 基于机器学习算法的候选人-职位匹配
- 📝 **简历管理** - 完整的候选人简历信息管理系统
- 💼 **职位管理** - 全面的职位描述(JD)管理功能
- 📊 **匹配分析** - 详细的匹配度分析和改进建议
- 🎨 **现代界面** - 响应式设计，支持多设备访问
- ⚡ **高效操作** - 直观的用户界面，简化招聘流程

## 🚀 核心功能

### 1. 简历管理模块
- 添加和管理候选人简历信息
- 支持完整的个人信息、技能、经验、教育背景录入
- 简历列表展示和快速操作
- 支持简历删除和编辑功能

### 2. 职位管理模块  
- 创建和管理职位描述(JD)
- 包含职位要求、公司信息、薪资待遇等完整信息
- 职位列表管理和快速操作
- 支持职位信息的增删改查

### 3. AI匹配模块
- 智能候选人-职位匹配算法
- 实时匹配度评分(0-100%)
- 详细的匹配分析报告
- 匹配优势和改进建议
- 匹配历史记录和追踪

## 📁 项目结构

```
talentMatchDemo/
├── app.py                 # Flask应用主文件，包含所有路由和API
├── config.py              # 应用配置管理
├── requirements.txt       # Python依赖包列表
├── README.md             # 项目说明文档
├── .gitignore            # Git忽略文件配置
├── templates/            # Jinja2模板文件
│   ├── base.html         # 基础模板，包含导航和布局
│   ├── resume.html       # 简历管理页面
│   ├── jd.html           # 职位管理页面
│   ├── matching.html     # AI匹配页面
│   └── 404.html          # 404错误页面
└── static/               # 静态资源文件
    ├── css/
    │   └── style.css     # 自定义样式文件
    └── js/
        └── main.js       # 前端JavaScript逻辑
```

## 🛠️ 技术栈

- **后端框架**: Python Flask
- **前端框架**: Bootstrap 5 + JavaScript
- **模板引擎**: Jinja2
- **图标库**: Bootstrap Icons
- **数据存储**: 内存存储(演示用，生产建议使用数据库)
- **API设计**: RESTful API

## 📦 快速开始

### 环境要求
- Python 3.7+
- pip 包管理器

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd talentMatchDemo
```

2. **安装依赖**
```bash
pip install -r requirements.txt
```

3. **运行应用**
```bash
python app.py
```

4. **访问应用**
打开浏览器访问：http://localhost:8000

## 🌐 API接口

### 简历管理API
- `POST /api/resume` - 添加新简历
- `DELETE /api/resume/<id>` - 删除指定简历

### 职位管理API  
- `POST /api/jd` - 添加新职位
- `DELETE /api/jd/<id>` - 删除指定职位

### AI匹配API
- `POST /api/match` - 执行AI匹配分析
- `GET /api/matches` - 获取匹配历史记录

## 💡 使用指南

### 基本工作流程

1. **添加简历** - 在简历管理页面录入候选人信息
2. **添加职位** - 在职位管理页面创建招聘需求
3. **执行匹配** - 在AI匹配页面选择简历和职位进行智能匹配
4. **查看结果** - 分析匹配度和详细建议，制定招聘决策

### 匹配算法说明

当前版本使用模拟匹配算法演示功能，匹配度基于：
- 技能匹配程度
- 经验要求符合度  
- 教育背景匹配
- (生产版本将集成真实的AI匹配模型)

## 🚀 扩展功能

基于当前架构，可以进一步扩展：

- **用户认证系统** - 多用户支持和权限管理
- **数据库集成** - MySQL/PostgreSQL数据持久化
- **文件上传** - 支持简历文档上传和解析
- **邮件通知** - 匹配结果邮件推送
- **数据导出** - Excel/PDF格式报告导出
- **高级匹配** - 集成真实的AI/ML匹配算法
- **数据分析** - 招聘数据统计和可视化
- **移动端应用** - React Native/Flutter移动应用

## 🎨 界面预览

- **现代化设计** - 基于Bootstrap 5的现代界面
- **响应式布局** - 完美适配桌面端和移动端
- **直观操作** - 简洁明了的用户交互体验
- **数据可视化** - 清晰的匹配结果展示

## 📄 许可证

MIT License - 详见 LICENSE 文件

## 🤝 贡献指南

欢迎提交Issue和Pull Request来改进项目！

1. Fork 本项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 📞 支持与反馈

如有问题或建议，请通过以下方式联系：
- 提交 GitHub Issue
- 发送邮件至项目维护者

---

**Talent Match** - 让AI为招聘赋能，让匹配更加精准！ 