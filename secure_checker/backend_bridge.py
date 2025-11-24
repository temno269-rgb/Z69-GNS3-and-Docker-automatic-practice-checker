# -*- coding: utf-8 -*-
"""
backend_bridge.py - Интеграция парсера и компаратора (с динамическим выбором эталона)

API для GUI:
- set_config(key, value)
- get_config()
- run_parse(example_num=None, log_func=None) → {student_data, similarity, report_path, example_num}
- list_examples() → [1, 2, 3, ...]

Config сохраняется в APPDATA (Windows) или ~/.secure_checker
"""

import os
import json
from pathlib import Path
from typing import Callable, Optional, Tuple, List
from secure_checker.core.parser.parse import parser_main

# ✅ Путь к config.json в пользовательскую папку
appdata = os.getenv('APPDATA')
if appdata:
    config_dir = Path(appdata) / "secure_checker"
else:
    # Fallback
    config_dir = Path.home() / "secure_checker"

config_dir.mkdir(parents=True, exist_ok=True)
CFG = config_dir / "config.json"

DEFAULTS = {
    "ip": "192.168.56.10",
    "port": "80",
    "project": "1",
    "local": False,
    "login": "admin",
    "password": "*",
    "desktop_results": True,
    "example_num": None  # ← Добавлено: номер эталона
}

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def reset_config() -> dict:
    """
    Сбросить конфиг на значения по умолчанию.
    Перезаписывает config.json и возвращает новый словарь.
    """
    cfg = DEFAULTS.copy()
    _save(cfg)
    return cfg

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
        CFG.parent.mkdir(parents=True, exist_ok=True)
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[CONFIG] Ошибка записи в {CFG}: {e}")

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
    
    if key == "example_num":
        try:
            value = int(value) if value else None
        except (ValueError, TypeError):
            value = None
    
    cfg[key] = value
    _save(cfg)
    return cfg

def get_config() -> dict:
    """Получить весь конфиг."""
    return _load()

# ---------------------------------------------------------------------------
# Examples listing
# ---------------------------------------------------------------------------

def list_examples() -> List[int]:
    """
    Получить список доступных номеров эталонов.
    
    Returns:
        Отсортированный список [1, 2, 3, ...]
    """
    try:
        from secure_checker.core.comparator.compare import list_available_examples
        return list_available_examples()
    except Exception as e:
        print(f"[EXAMPLES] Error: {e}")
        return []

# ---------------------------------------------------------------------------
# Main functions
# ---------------------------------------------------------------------------

def run_parse(
    example_num: Optional[int] = None,
    log_func: Optional[Callable[[str], None]] = None
) -> dict:
    """
    Запустить парсер и получить данные студента.
    
    Args:
        example_num: номер эталона (1, 2, 3, ...).
                     Если None, использует последний из конфига
        log_func: функция логирования (опционально)
    
    Returns:
        dict с ключами: student_data, similarity, report_path, example_num
    """
    logger = log_func if callable(log_func) else print
    
    def _logger(line):
        try:
            logger(line)
        except Exception:
            print(line)
    
    cfg = _load()
    
    # ─────────────────────────────────────────────────────────
    # Определяем example_num
    # ─────────────────────────────────────────────────────────
    
    if example_num is None:
        example_num = cfg.get("example_num")
        if example_num:
            _logger(f"📚 Using examples from config: {example_num}")
    
    if not example_num:
        # Пытаемся список доступных
        available = list_examples()
        if available:
            _logger(f"❌ Example number not specified. Available: {available}")
            _logger("   Set example_num in config or pass as parameter")
        else:
            _logger("❌ No examples found in: core/examples")
        return {
            "student_data": {},
            "similarity": 0,
            "report_path": None,
            "example_num": None
        }
    
    # Сохраняем выбранный пример
    if example_num != cfg.get("example_num"):
        cfg["example_num"] = example_num
        _save(cfg)
    
    _logger(f"📚 Using Example{example_num}")
    
    # ─────────────────────────────────────────────────────────
    # Запускаем парсер
    # ─────────────────────────────────────────────────────────
    
    try:
        student_data = parser_main(cfg, logger=_logger)
    except Exception as e:
        _logger(f"❌ Parser error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "student_data": {},
            "similarity": 0,
            "report_path": None,
            "example_num": example_num
        }
    
    # ─────────────────────────────────────────────────────────
    # Запускаем компаратор
    # ─────────────────────────────────────────────────────────
    
    try:
        from secure_checker.core.comparator.compare import run_comparison
        similarity, report_path = run_comparison(
            student_data,
            example_num=example_num,
            log_func=_logger
        )
        _logger(f"✅ Similarity: {similarity:.2f}%")
        if report_path:
            _logger(f"📄 Report: {report_path}")
    except Exception as e:
        _logger(f"❌ Comparator error: {e}")
        import traceback
        traceback.print_exc()
        similarity = 0
        report_path = None
    
    return {
        "student_data": student_data,
        "similarity": similarity,
        "report_path": report_path,
        "example_num": example_num
    }

def run_parse_and_compare(
    student_data: dict,
    example_num: Optional[int] = None,
    log_func: Optional[Callable[[str], None]] = None
) -> Tuple[float, Optional[str]]:
    """
    Запустить компаратор для уже полученных данных студента.
    
    Args:
        student_data: dict из parse.py
        example_num: номер эталона. Если None, использует из конфига
        log_func: функция логирования (опционально)
    
    Returns:
        (similarity_percent, report_path)
    """
    logger = log_func if callable(log_func) else print
    
    def _logger(line):
        try:
            logger(line)
        except Exception:
            print(line)
    
    if example_num is None:
        cfg = _load()
        example_num = cfg.get("example_num")
    
    if not example_num:
        _logger("❌ Example number not specified")
        return 0, None
    
    try:
        from secure_checker.core.comparator.compare import run_comparison
        similarity, report_path = run_comparison(
            student_data,
            example_num=example_num,
            log_func=_logger
        )
        return similarity, report_path
    except Exception as e:
        _logger(f"❌ Comparator error: {e}")
        import traceback
        traceback.print_exc()
        return 0, None
