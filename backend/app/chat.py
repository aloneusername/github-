import asyncio
from pathlib import Path
from typing import AsyncIterator

from app.analyzer import IGNORE_DIRS, read_small
from app.config import get_settings
from app.deepseek import create_deepseek_chat_model, normalize_model


class SourceToolkit:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_tree(self, max_entries: int = 120) -> str:
        rows: list[str] = []
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root)
            if any(part in IGNORE_DIRS for part in rel.parts):
                continue
            rows.append(("DIR  " if path.is_dir() else "FILE ") + rel.as_posix())
            if len(rows) >= max_entries:
                break
        return "\n".join(rows)

    def read_file(self, relative_path: str) -> str:
        path = self._safe_path(relative_path)
        if not path.exists() or not path.is_file():
            return f"文件不存在：{relative_path}"
        return read_small(path, 30_000)

    def search_code(self, keyword: str, max_results: int = 30) -> str:
        keyword_lower = keyword.lower()
        matches: list[str] = []
        for path in self.root.rglob("*"):
            rel = path.relative_to(self.root)
            if any(part in IGNORE_DIRS for part in rel.parts) or not path.is_file() or path.stat().st_size > 300_000:
                continue
            content = read_small(path, 80_000)
            for idx, line in enumerate(content.splitlines(), start=1):
                if keyword_lower in line.lower():
                    matches.append(f"{rel.as_posix()}:{idx}: {line.strip()[:220]}")
                    break
            if len(matches) >= max_results:
                break
        return "\n".join(matches) or f"没有搜索到：{keyword}"

    def _safe_path(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("路径越界")
        return path


async def stream_answer(project: dict, question: str, model_name: str | None = None) -> AsyncIterator[str]:
    toolkit = SourceToolkit(Path(project["local_path"]))
    settings = get_settings()
    if not settings.deepseek_api_key:
        async for token in fallback_answer(toolkit, project, question):
            yield token
        return

    try:
        async for token in llm_answer(toolkit, project, question, model_name=model_name):
            yield token
    except Exception as exc:
        yield f"\n\nDeepSeek/LangChain 调用失败，改用本地回答。错误：{exc}\n\n"
        async for token in fallback_answer(toolkit, project, question):
            yield token


async def llm_answer(
    toolkit: SourceToolkit,
    project: dict,
    question: str,
    model_name: str | None = None,
) -> AsyncIterator[str]:
    selected_model = normalize_model(model_name)
    context = build_context(toolkit, question)
    model = create_deepseek_chat_model(selected_model, streaming=True)
    prompt = f"""
你是 project-helper 的源码学习 Agent。你需要用大白话回答用户问题，结论必须基于工具读取到的源码上下文。

项目：{project["repo_name"]}
用户问题：{question}

你已经自主调用了这些源码工具：
- list_tree：了解目录结构
- search_code：按问题关键词搜索代码
- read_file：读取最可能相关的文件片段

工具结果：
{context}

请用中文回答。结构要求：
1. 先给一句话结论
2. 再解释关键代码路径
3. 给初学者阅读建议
如果上下文不足，明确说还需要看哪些文件。
"""
    async for chunk in model.astream(prompt):
        text = getattr(chunk, "content", "")
        if text:
            yield str(text)


def build_context(toolkit: SourceToolkit, question: str) -> str:
    keywords = [word.strip("，。,.?？:：`'\"()[]{}") for word in question.split() if len(word.strip()) >= 2]
    keyword = keywords[0] if keywords else question[:24]
    tree = toolkit.list_tree()
    search = toolkit.search_code(keyword)
    files = []
    for line in search.splitlines()[:3]:
        if ":" in line:
            files.append(line.split(":", 1)[0])
    snippets = "\n\n".join(f"--- {file} ---\n{toolkit.read_file(file)[:5000]}" for file in files)
    return f"目录结构：\n{tree}\n\n搜索 `{keyword}`：\n{search}\n\n相关文件：\n{snippets}"


async def fallback_answer(toolkit: SourceToolkit, project: dict, question: str) -> AsyncIterator[str]:
    context = build_context(toolkit, question)
    answer = (
        "一句话结论：我已经根据本地源码工具做了检索，但当前没有配置 `DEEPSEEK_API_KEY`，所以这是本地启发式回答。\n\n"
        f"项目 `{project['repo_name']}` 的相关线索如下：\n\n"
        f"{context[:6000]}\n\n"
        "阅读建议：先看目录结构和 README，再沿着搜索结果中的文件逐个打开；如果问题涉及接口，就优先看 router/api；"
        "如果涉及业务逻辑，就优先看 service/core；如果涉及数据结构，就优先看 model/schema。"
    )
    for char in answer:
        yield char
        await asyncio.sleep(0.002)
