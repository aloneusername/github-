import hashlib
import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings


GITHUB_RE = re.compile(r"^https://github\.com/[\w.-]+/[\w.-]+/?$")


def normalize_repo_url(repo_url: str) -> str:
    clean = repo_url.strip().removesuffix(".git").rstrip("/")
    if not GITHUB_RE.match(clean):
        raise ValueError("只支持公开 GitHub 仓库地址，例如 https://github.com/owner/repo")
    return clean


def project_id_for_url(repo_url: str) -> str:
    return hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:16]


def repo_name_from_url(repo_url: str) -> str:
    parsed = urlparse(repo_url)
    return parsed.path.strip("/").replace("/", "__")


def local_path_for_repo(repo_url: str) -> Path:
    settings = get_settings()
    return settings.workspace_path / project_id_for_url(repo_url)


def clone_or_update(repo_url: str, force: bool = False) -> Path:
    settings = get_settings()
    settings.workspace_path.mkdir(parents=True, exist_ok=True)
    target = local_path_for_repo(repo_url)
    if target.exists() and is_valid_git_repo(target):
        update_existing_clone(target, repo_url, force=force)
        return target
    if target.exists():
        archive_invalid_directory(target)
    result = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(format_git_error("克隆仓库失败", result))
    return target


def is_valid_git_repo(target: Path) -> bool:
    if not (target / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def update_existing_clone(target: Path, repo_url: str, force: bool = False) -> None:
    remote = subprocess.run(
        ["git", "-C", str(target), "remote", "set-url", "origin", repo_url],
        check=False,
        capture_output=True,
        text=True,
    )
    if remote.returncode != 0:
        raise RuntimeError(format_git_error("更新仓库地址失败", remote))

    if force:
        fetch = subprocess.run(
            ["git", "-C", str(target), "fetch", "--depth", "1", "origin"],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if fetch.returncode != 0:
            raise RuntimeError(format_git_error("强制刷新仓库失败", fetch))
        reset = subprocess.run(
            ["git", "-C", str(target), "reset", "--hard", "FETCH_HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if reset.returncode != 0:
            raise RuntimeError(format_git_error("重置仓库到最新版本失败", reset))
        return

    result = subprocess.run(["git", "-C", str(target), "pull", "--ff-only"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(format_git_error("更新仓库失败", result))


def archive_invalid_directory(target: Path) -> None:
    archived = target.with_name(f"{target.name}.broken-{int(time.time())}")
    try:
        target.rename(archived)
        return
    except OSError:
        remove_non_git_directory(target)


def remove_non_git_directory(target: Path) -> None:
    try:
        shutil.rmtree(target, onerror=make_writable_and_retry)
    except PermissionError as exc:
        raise RuntimeError(f"工作区目录被占用，无法删除：{target}。请关闭占用该目录的程序后重试。原始错误：{exc}") from exc


def make_writable_and_retry(function, path: str, exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def format_git_error(title: str, result: subprocess.CompletedProcess[str]) -> str:
    detail = (result.stderr or result.stdout or "").strip()
    hint = ""
    if "127.0.0.1" in detail and "Could not connect to server" in detail:
        hint = "检测到 Git 正在使用本地代理 127.0.0.1，但代理服务不可用。请启动代理，或清理 Git 的 http.proxy/https.proxy 配置。"
    return f"{title}：Git 退出码 {result.returncode}。{detail}{(' ' + hint) if hint else ''}"
