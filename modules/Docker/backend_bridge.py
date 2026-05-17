import json
import os
from pathlib import Path

try:
    from modules.GNS3.core.advanced_logger import get_logger
except ImportError:
    import logging
    def get_logger(): return logging.getLogger()

def get_project_root():
    return Path(__file__).resolve().parent.parent.parent

# Конфигурационный файл будет храниться внутри модуля Docker
DOCKER_CONFIG_FILE = get_project_root() / "modules" / "Docker" / "config.json"

def _load() -> dict:
    """Загрузка конфигурации из файла."""
    if not DOCKER_CONFIG_FILE.exists():
        return {}
    try:
        with open(DOCKER_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        get_logger().error(f"JSON decode error in Docker config: {e}", technical=str(e))
        return {}
    except Exception as e:
        get_logger().error(f"Error reading Docker config: {e}", technical=str(e))
        return {}

def _save(data: dict):
    """Сохранение конфигурации в файл."""
    os.makedirs(DOCKER_CONFIG_FILE.parent, exist_ok=True)
    with open(DOCKER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_config() -> dict:
    return _load()

def set_config(key: str, value: str) -> dict:
    data = _load()
    data[key] = value
    _save(data)
    return data