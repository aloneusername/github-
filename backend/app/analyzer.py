import json
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from app.config import get_settings
from app.deepseek import create_deepseek_chat_model, normalize_model


ProgressCallback = Callable[[str, int, dict[str, Any] | None], None]

IGNORE_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".venv",
    "venv",
    "target",
}

LANG_BY_SUFFIX = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript React",
    ".jsx": "React",
    ".vue": "Vue",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".kt": "Kotlin",
    ".php": "PHP",
    ".rb": "Ruby",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
}

TEXT_SUFFIXES = set(LANG_BY_SUFFIX) | {
    ".md",
    ".txt",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".html",
    ".css",
    ".scss",
    ".sql",
}


def analyze_repository(
    repo_path: Path,
    repo_url: str,
    emit: ProgressCallback | None = None,
    model_name: str | None = None,
) -> dict[str, Any]:
    def progress(message: str, percent: int, payload: dict[str, Any] | None = None) -> None:
        if emit:
            emit(message, percent, payload)

    progress("扫描项目文件与目录", 15)
    files = list(iter_source_files(repo_path))
    tree = build_tree(repo_path)

    progress("识别语言、框架和依赖", 35)
    languages = detect_languages(files)
    tech_stack = detect_tech_stack(repo_path, files)

    progress("提取核心模块和入口文件", 55)
    important_files = rank_important_files(repo_path, files)
    modules = summarize_modules(repo_path, important_files)

    progress("梳理数据流、设计模式和阅读路径", 75)
    report = {
        "repo_url": repo_url,
        "overview": build_overview(repo_path, languages, tech_stack),
        "tech_stack": tech_stack,
        "directory_structure": tree,
        "core_modules": modules,
        "data_flow": infer_data_flow(tech_stack, important_files),
        "design_patterns": infer_patterns(files),
        "reading_guide": build_reading_guide(important_files, tech_stack),
        "stats": {
            "file_count": len(files),
            "languages": languages,
        },
    }

    progress("生成通俗分析报告", 90)
    enhanced = maybe_enhance_with_llm(report, model_name=model_name)
    progress("分析完成", 100, {"report": enhanced})
    return enhanced


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 300_000:
            files.append(path)
    return files[:1200]


def build_tree(root: Path, max_depth: int = 3, max_entries: int = 180) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS for part in rel.parts) or len(rel.parts) > max_depth:
            continue
        entries.append({"path": rel.as_posix(), "type": "dir" if path.is_dir() else "file"})
        if len(entries) >= max_entries:
            break
    return entries


def detect_languages(files: list[Path]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for file in files:
        lang = LANG_BY_SUFFIX.get(file.suffix.lower())
        if lang:
            counter[lang] += 1
    return dict(counter.most_common())


def detect_tech_stack(root: Path, files: list[Path]) -> list[dict[str, str]]:
    stack: list[dict[str, str]] = []
    names = {file.name.lower(): file for file in files}
    if "package.json" in names:
        package = safe_json(names["package.json"])
        deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
        for key in ["vue", "react", "next", "vite", "express", "tailwindcss", "pinia"]:
            if key in deps:
                stack.append({"name": key, "reason": f"package.json 依赖 {key}"})
    if "requirements.txt" in names or "pyproject.toml" in names:
        stack.append({"name": "Python", "reason": "存在 Python 依赖声明文件"})
    if (root / "app").exists() or any("fastapi" in read_small(file).lower() for file in files[:200]):
        stack.append({"name": "FastAPI", "reason": "检测到 FastAPI 相关代码或 app 目录"})
    if "dockerfile" in names or "docker-compose.yml" in names:
        stack.append({"name": "Docker", "reason": "存在容器化配置"})
    return dedupe_stack(stack)


def rank_important_files(root: Path, files: list[Path]) -> list[Path]:
    weights = ["readme", "main.", "app.", "server.", "index.", "router", "service", "model", "schema", "config"]
    scored: list[tuple[int, Path]] = []
    for file in files:
        rel = file.relative_to(root).as_posix().lower()
        score = sum(5 for key in weights if key in rel)
        score += max(0, 5 - len(file.relative_to(root).parts))
        scored.append((score, file))
    return [file for _, file in sorted(scored, key=lambda item: (-item[0], item[1].as_posix()))[:18]]


def summarize_modules(root: Path, files: list[Path]) -> list[dict[str, str]]:
    modules = []
    for file in files:
        content = read_small(file, limit=6000)
        rel = file.relative_to(root).as_posix()
        modules.append(
            {
                "path": rel,
                "role": infer_file_role(rel, content),
                "summary": summarize_text(content),
            }
        )
    return modules


def build_overview(root: Path, languages: dict[str, int], stack: list[dict[str, str]]) -> str:
    readme = next((p for p in root.iterdir() if p.name.lower().startswith("readme") and p.is_file()), None)
    if readme:
        first = summarize_text(read_small(readme, 4000))
        if first:
            return f"这个项目大概率是：{first}"
    top_lang = next(iter(languages), "未知语言")
    stack_names = "、".join(item["name"] for item in stack[:5]) or "未识别到明显框架"
    return f"这是一个以 {top_lang} 为主的开源项目，主要技术线索包括 {stack_names}。建议先从入口文件和 README 建立全局地图。"


def infer_data_flow(stack: list[dict[str, str]], files: list[Path]) -> list[str]:
    names = {item["name"].lower() for item in stack}
    flow = ["用户入口或命令行参数进入应用", "路由/控制器接收请求并调用业务模块", "业务模块读取配置、文件或数据库", "结果经过格式化后返回给用户"]
    if "vue" in names or "react" in names:
        flow.insert(0, "浏览器页面触发交互，请求后端 API")
    if "fastapi" in names:
        flow = ["客户端请求 FastAPI 路由", "Pydantic 校验输入", "服务层执行业务逻辑", "返回 JSON 或流式响应"]
    return flow


def infer_patterns(files: list[Path]) -> list[str]:
    text = "\n".join(file.as_posix().lower() for file in files[:500])
    patterns = []
    if "router" in text:
        patterns.append("路由分层：接口入口和业务逻辑拆开，便于扩展")
    if "service" in text:
        patterns.append("Service 层：把核心业务从 Web 框架中抽离")
    if "model" in text or "schema" in text:
        patterns.append("数据模型/Schema：用结构化对象约束输入输出")
    if "factory" in text:
        patterns.append("工厂模式：集中创建复杂对象")
    return patterns or ["当前项目结构较直接，重点看入口文件如何串起各模块"]


def build_reading_guide(files: list[Path], stack: list[dict[str, str]]) -> list[str]:
    guide = ["先读 README，弄清楚项目解决什么问题", "再找 main/app/server/index 这类入口文件，看程序从哪里启动"]
    guide.extend(f"重点阅读 `{file.name}`，它可能是核心路径的一部分" for file in files[:5])
    if stack:
        guide.append("最后按技术栈逐个查框架文档，理解约定目录和生命周期")
    return guide


def maybe_enhance_with_llm(report: dict[str, Any], model_name: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    selected_model = normalize_model(model_name)
    report["model"] = selected_model
    if not settings.deepseek_api_key:
        report["llm_note"] = "未配置 DEEPSEEK_API_KEY，当前报告由本地启发式分析生成。"
        return report
    try:
        model = create_deepseek_chat_model(selected_model)
        prompt = (
            "你是源码导读老师。请把下面 JSON 报告润色成更通俗的结构化 JSON，保留原字段，"
            "让初学者也能读懂。只输出 JSON。\n"
            f"{json.dumps(report, ensure_ascii=False)[:18000]}"
        )
        response = model.invoke(prompt)
        content = getattr(response, "content", "")
        parsed = json.loads(strip_json_fence(str(content)))
        return parsed if isinstance(parsed, dict) else report
    except Exception as exc:
        report["llm_note"] = f"LLM 增强失败，已使用本地报告：{exc}"
        return report


def infer_file_role(path: str, content: str) -> str:
    lower = path.lower()
    if "readme" in lower:
        return "项目说明书，适合第一个阅读"
    if any(key in lower for key in ["main.", "app.", "server.", "index."]):
        return "应用入口，负责启动或挂载核心能力"
    if "router" in lower or "api" in lower:
        return "接口路由，定义外部如何访问功能"
    if "service" in lower:
        return "业务服务，承载主要处理流程"
    if "model" in lower or "schema" in lower:
        return "数据结构，说明系统里有哪些核心对象"
    if "test" in lower:
        return "测试代码，能反推模块预期行为"
    if "class " in content or "def " in content or "function " in content:
        return "功能代码，包含可复用函数或类"
    return "辅助文件"


def summarize_text(content: str) -> str:
    lines = [line.strip("# -\t ") for line in content.splitlines() if line.strip()]
    useful = [line for line in lines if len(line) > 12 and not line.startswith(("import ", "from "))]
    return " ".join(useful[:3])[:360]


def read_small(path: Path, limit: int = 20_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def safe_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(read_small(path))
    except json.JSONDecodeError:
        return {}


def dedupe_stack(stack: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for item in stack:
        key = item["name"].lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def strip_json_fence(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]
    return content.strip()
