from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_LOADED = False


def load_env() -> None:
    """
    约定：
    - 本机运行：优先加载项目根目录的 .env（若存在）
    - 容器/生产：环境变量通常由平台注入，.env 可不存在
    """
    global _LOADED
    if _LOADED:
        return

    # app/ 的上一级就是项目根目录
    root_dir = Path(__file__).resolve().parent.parent
    load_dotenv(dotenv_path=root_dir / ".env", override=False)
    _LOADED = True

