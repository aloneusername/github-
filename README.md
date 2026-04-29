# project-helper

项目学习助手：输入 GitHub 仓库地址，自动克隆并分析源码，生成通俗易懂的项目报告，并支持基于源码工具的交互式问答。

## 功能

- GitHub 仓库克隆与缓存，重复分析直接复用结果
- FastAPI + SQLite 后端，SSE 实时推送分析进度
- DeepSeek OpenAI-compatible API + LangChain Agent 工具调用
- Vue 3 前端，舒适阅读、科技感界面、代码高亮
- 无 API Key 时可运行本地启发式分析，方便开发测试

## 快速启动

后端：

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

打开 `http://localhost:5173`。

## DeepSeek 配置

在 `backend/.env` 中填写：

```env
DEEPSEEK_API_KEY=你的 key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 测试

```bash
cd backend
pytest
```

```bash
cd frontend
npm run build
```
