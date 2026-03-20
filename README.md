# 企业智能助手

基于 **千问 Qwen-Max（阿里云 DashScope）+ LangGraph + FastAPI + React** 构建的企业内部智能对话助手。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Recharts |
| 后端 | Python 3.11 + FastAPI + LangGraph |
| AI 模型 | 千问 Qwen-Max（阿里云 DashScope） |
| 会话状态 | Redis 7 |
| 持久化 | PostgreSQL 16 |
| 部署 | Docker + 阿里云 ECS + SLB |

## 快速启动（本地开发）

```bash
# 1. 复制环境变量
cp backend/.env.example backend/.env
# 编辑 .env，填入 DASHSCOPE_API_KEY 和各服务地址

# 2. 启动依赖服务（Redis + PostgreSQL）
docker-compose up -d redis postgres

# 3. 启动后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 4. 启动前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
ai-assistant/
├── backend/
│   ├── main.py               # FastAPI 入口，所有路由
│   ├── config.py             # 统一配置（pydantic-settings）
│   ├── graph/
│   │   ├── state.py          # LangGraph 状态定义
│   │   ├── nodes.py          # 各节点逻辑
│   │   ├── edges.py          # 条件路由
│   │   └── builder.py        # 图构建与编译
│   ├── admin/
│   │   └── tool_manager.py   # Tool 动态管理（无需重启）
│   ├── auth/
│   │   └── middleware.py     # JWT 验证 + 权限缓存
│   ├── db/
│   │   ├── database.py       # 连接池 + DDL 初始化
│   │   ├── session_repo.py   # 会话/消息 CRUD
│   │   └── audit_repo.py     # Tool 调用审计日志
│   ├── pause/
│   │   └── resume_handler.py # 流程暂停/恢复
│   ├── services/
│   │   ├── redis_client.py   # Redis 单例
│   │   └── java_client.py    # Java HTTP 调用封装
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── ChatWindow.tsx     # 主界面
│       │   ├── MessageBubble.tsx  # 消息气泡（图文混排）
│       │   ├── ChartMessage.tsx   # 图表渲染（折线/柱/饼/表格）
│       │   └── SessionSidebar.tsx # 历史会话侧边栏
│       └── hooks/
│           └── useSSE.ts          # SSE 流式接收 + 图表解析
├── nginx/
│   └── nginx.conf            # SSE 长连接配置
├── .github/workflows/
│   └── deploy.yml            # CI/CD 滚动部署
└── docker-compose.yml        # 本地开发环境
```

## 核心功能

- **多轮对话**：Redis 保存会话状态，历史会话随时恢复
- **意图识别**：Qwen-Max 自动解析意图，路由到对应 Java 接口
- **动态 Tool 管理**：运营后台配置 Tool，无需重启服务即可生效
- **权限控制**：三层拦截（接入权限 → Tool 权限 → 数据范围），对接公司 Java 权限系统
- **图表输出**：模型返回结构化数据，前端 Recharts 渲染折线/柱状/饼图/表格
- **流式输出**：SSE 打字机效果，支持随时中止
- **暂停/恢复**：多客户选择等场景支持 Human-in-the-loop

## API 文档

启动后访问：http://localhost:8000/docs
