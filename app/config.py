from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RESOURCES_DIR = BASE_DIR / "resources"
IMPORT_DIR = RESOURCES_DIR / "import"
PRODUCT_IMAGES_DIR = RESOURCES_DIR / "product_images"
PLACEHOLDER_IMAGE = IMPORT_DIR / "picture.png"


# Загружает настройки подключения из локального .env, если он создан.
def load_env_file() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# Собирает параметры подключения к MySQL из переменных окружения.
def get_database_config(include_database: bool = True) -> dict:
    load_env_file()
    config = {
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "charset": "utf8mb4",
        "use_unicode": True,
    }
    if include_database:
        config["database"] = os.getenv("MYSQL_DATABASE", "mebelorg")
    return config


# Сохраняем пути к файлам относительно папки проекта, чтобы проект можно было переносить.
def relative_to_base(path: Path) -> str:
    return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()


# Восстанавливает абсолютный путь к ресурсу и подставляет заглушку, если файла нет.
def absolute_from_base(relative_path: str | None) -> Path:
    if not relative_path:
        return PLACEHOLDER_IMAGE
    path = BASE_DIR / relative_path
    return path if path.exists() else PLACEHOLDER_IMAGE
