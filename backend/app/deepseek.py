from langchain_openai import ChatOpenAI

from app.config import get_settings


SUPPORTED_MODELS = {
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
}

THINKING_MODELS = {"deepseek-v4-pro", "deepseek-reasoner"}


def normalize_model(model_name: str | None) -> str:
    settings = get_settings()
    selected = (model_name or settings.deepseek_model or "deepseek-v4-flash").strip()
    if selected not in SUPPORTED_MODELS:
        allowed = "、".join(sorted(SUPPORTED_MODELS))
        raise ValueError(f"不支持的 DeepSeek 模型：{selected}。可选模型：{allowed}")
    return selected


def create_deepseek_chat_model(model_name: str | None = None, streaming: bool = False) -> ChatOpenAI:
    settings = get_settings()
    selected = normalize_model(model_name)
    kwargs = {
        "model": selected,
        "base_url": settings.deepseek_base_url,
        "api_key": settings.deepseek_api_key,
        "streaming": streaming,
    }
    if selected in THINKING_MODELS:
        kwargs["reasoning_effort"] = "high"
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    return ChatOpenAI(**kwargs)
