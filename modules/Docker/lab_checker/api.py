"""
API модуль для Lab Checker.
Предоставляет функции для программного вызова проверок.
"""

import os
from typing import Dict, Optional
from .core import LabChecker
from .types import LabType
from .config import Config, load_config as load_config_func

def check_lab_dir(project_dir: str, lab_type: str, config: Optional[Config] = None, silent_mode: bool = False) -> Dict:
    """
    Проверка лабораторной работы в указанной локальной директории.
    
    Args:
        project_dir: Абсолютный путь к папке с файлами студента
        lab_type: Тип лабораторной (lab10, lab11, etc.)
        config: Объект конфигурации (опционально)
        silent_mode: Режим без вывода лишнего текста в консоль
        
    Returns:
        Словарь (JSON) с результатами проверки
    """
    if not config:
        config = Config()
        
    config.general.silent_mode = silent_mode
    
    # Нормализуем ввод (поддержка как строк любого регистра, так и объектов Enum)
    lab_key = lab_type.lower() if isinstance(lab_type, str) else lab_type.value

    # Инициализация ядра
    checker = LabChecker(config)
    
    # Проверяем, включена ли лаба в конфиге
    lab_config = config.get_lab_config(lab_key)
    if not lab_config.enabled:
        return {
            'lab_type': lab_key,
            'project_dir': project_dir,
            'error': f'Лабораторная {lab_key} отключена в конфигурации',
            'success': False,
            'summary': {'total_checks': 0, 'passed_checks': 0, 'failed_checks': 0, 'success_rate': '0%'}
        }
    
    # Запуск
    result = checker.check_lab(project_dir, LabType(lab_key))
    result['config_used'] = True
    
    return result

def load_config(config_path: str) -> Config:
    """Загрузка конфигурации из файла."""
    return load_config_func(config_path)