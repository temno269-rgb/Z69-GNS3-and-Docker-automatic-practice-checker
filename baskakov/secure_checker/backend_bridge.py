# -*- coding: utf-8 -*-
"""
backend_bridge.py

Thin API for GUI:
- set_config(key, value)
- get_config()
- run_parse(log_func=None) # log_func(line: str) -> None

Config is persisted in user-writable location (APPDATA on Windows).
"""

import os
import json
from pathlib import Path
from typing import Callable, Optional

from secure_checker.core.parser.Parse import parser_main

# ✅ Получить путь к config.json в пользовательскую папку
appdata = os.getenv('APPDATA')
if appdata:
    config_dir = Path(appdata) / "secure_checker"
else:
    # Fallback, если APPDATA недоступна
    config_dir = Path.home() / "secure_checker"

# Создаём папку, если её нет
config_dir.mkdir(parents=True, exist_ok=True)
CFG = config_dir / "config.json"

DEFAULTS = {
    "ip": "10.242.192.200",
    "port": "80",
    "project": "Lab2_1_Test_v_o4ko",
    "local": False,
    "login": "admin",
    "password": "*",
    "desktop_results": True
}


def _load() -> dict:
    """Загрузить конфиг из файла."""
    if CFG.exists():
        try:
            with open(CFG, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            print(f"[CONFIG] Ошибка чтения {CFG}: {e}")
            d = {}
    else:
        d = {}
    
    # Мерджим с дефолтами
    x = DEFAULTS.copy()
    x.update(d)
    return x


def _save(cfg: dict) -> None:
    """Сохранить конфиг в файл."""
    try:
        # Убеждаемся, что папка существует
        CFG.parent.mkdir(parents=True, exist_ok=True)
        
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CONFIG] Ошибка записи в {CFG}: {e}")
        print(f"[CONFIG] Проверьте права доступа к {CFG.parent}")


def set_config(key: str, value):
    """Установить значение конфига и сохранить."""
    cfg = _load()
    
    # Coerce types for known keys
    if key in ("local", "desktop_results"):
        if isinstance(value, str):
            value = value.strip().lower() in ("1", "true", "yes", "y", "on")
        else:
            value = bool(value)
    
    if key == "port":
        value = str(value)
    
    cfg[key] = value
    _save(cfg)
    return cfg


def get_config() -> dict:
    """Получить весь конфиг."""
    return _load()


def run_parse(log_func: Optional[Callable[[str], None]] = None) -> dict:
    """Запустить парсер с конфигом."""
    logger = log_func if callable(log_func) else print
    
    def _logger(line):
        try:
            logger(line)
        except Exception:
            # Fallback to stdout
            print(line)
    
    cfg = _load()
    return parser_main(cfg, logger=_logger)
