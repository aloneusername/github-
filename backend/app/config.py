from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "project-helper"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    database_url: str = "sqlite:///./data/project_helper.db"
    project_workspace: str = "./workspace"
    allow_private_git: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def workspace_path(self) -> Path:
        return Path(self.project_workspace).resolve()

    @property
    def database_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// DATABASE_URL is supported in this app.")
        return Path(self.database_url.replace("sqlite:///", "", 1)).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
