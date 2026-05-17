"""
Модуль конфигурации для Lab Checker.
Поддержка YAML и JSON конфигурационных файлов.
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum

class LogLevel(str, Enum):
    """Уровни логирования."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

@dataclass
class LabConfig:
    """Конфигурация для конкретной лабораторной работы."""
    
    # Общие настройки
    enabled: bool = True
    timeout: int = 30  # секунд
    
    # Настройки для Lab 10 (Flask приложение)
    expected_ports: List[int] = field(default_factory=lambda: [2020, 8080, 5000, 80])
    expected_content: List[str] = field(default_factory=lambda: [
        "москв", "самар", "температур", "moscow", "samara", "temperature"
    ])
    require_api_integration: bool = True
    
    # Настройки для Lab 11 (Python приложение)
    architecture_checks: bool = True
    sleep_time_variants: List[int] = field(default_factory=lambda: [3, 7, 10])
    require_timestamp: bool = True
    
    # Настройки для Lab 12 (Docker Compose)
    compose_services: List[str] = field(default_factory=lambda: ["prometheus", "grafana"])
    expected_ports: Dict[str, int] = field(default_factory=lambda: {
        "prometheus": 9090,
        "grafana": 3000
    })
    
    # Настройки для Lab 13 (Сети)
    network_checks: bool = True
    expected_networks: List[str] = field(default_factory=list)
    check_port_mapping: bool = True
    check_service_discovery: bool = True
    
    # Настройки для Lab 14 (Оптимизация)
    max_image_size_mb: Optional[float] = None
    check_dockerignore: bool = True
    check_unnecessary_files: bool = True
    allowed_file_patterns: List[str] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LabConfig':
        """Создание конфигурации из словаря."""
        config = cls()
        
        # Обновляем поля из данных
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return config

@dataclass
class GeneralConfig:
    """Общая конфигурация системы."""
    
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[str] = None
    cleanup_images: bool = True
    silent_mode: bool = False
    max_execution_time: int = 300  # секунд
    output_format: str = "json"  # json, text, both
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GeneralConfig':
        """Создание конфигурации из словаря."""
        config = cls()
        
        for key, value in data.items():
            if hasattr(config, key):
                if key == 'log_level' and isinstance(value, str):
                    value = LogLevel(value.upper())
                setattr(config, key, value)
        
        return config

@dataclass
class ImageAnalysisConfig:
    """Конфигурация анализа образов."""
    
    compare_sizes: bool = True
    max_size_mb: Optional[float] = 500
    check_dockerignore: bool = True
    check_layer_efficiency: bool = True
    unnecessary_files: List[str] = field(default_factory=lambda: [
        "*.log", "*.tmp", "*.cache", "__pycache__", ".git",
        "node_modules", "venv", ".env", ".DS_Store"
    ])
    min_savings_percentage: float = 10.0  # Минимальный процент экономии
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImageAnalysisConfig':
        """Создание конфигурации из словаря."""
        config = cls()
        
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return config

@dataclass
class TestSuiteConfig:
    """Конфигурация тестового набора."""
    
    run_tests: bool = True
    correct_solutions_dir: Optional[str] = None
    incorrect_solutions_dir: Optional[str] = None
    expected_success_rate: float = 100.0  # Ожидаемый процент успеха
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TestSuiteConfig':
        """Создание конфигурации из словаря."""
        config = cls()
        
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        return config

@dataclass
class Config:
    """Полная конфигурация системы."""
    
    general: GeneralConfig = field(default_factory=GeneralConfig)
    lab10: LabConfig = field(default_factory=LabConfig)
    lab11: LabConfig = field(default_factory=LabConfig)
    lab12: LabConfig = field(default_factory=LabConfig)
    lab13: LabConfig = field(default_factory=LabConfig)
    lab14: LabConfig = field(default_factory=LabConfig)
    image_analysis: ImageAnalysisConfig = field(default_factory=ImageAnalysisConfig)
    test_suite: TestSuiteConfig = field(default_factory=TestSuiteConfig)
    
    @classmethod
    def load(cls, config_path: str) -> 'Config':
        """
        Загрузка конфигурации из файла.
        
        Args:
            config_path: Путь к файлу конфигурации (YAML или JSON)
            
        Returns:
            Загруженная конфигурация
            
        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если формат файла не поддерживается
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Конфигурационный файл не найден: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                data = yaml.safe_load(f)
            elif config_path.endswith('.json'):
                data = json.load(f)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {config_path}")
        
        return cls.from_dict(data)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        """Создание конфигурации из словаря."""
        config = cls()
        
        # Загружаем общую конфигурацию
        if 'general' in data:
            config.general = GeneralConfig.from_dict(data['general'])
        
        # Загружаем конфигурации лабораторных
        lab_configs = {
            'lab10': config.lab10,
            'lab11': config.lab11,
            'lab12': config.lab12,
            'lab13': config.lab13,
            'lab14': config.lab14
        }
        
        for lab_name, lab_config in lab_configs.items():
            if lab_name in data:
                # Обновляем конфигурацию лабораторной
                lab_data = data[lab_name]
                updated_config = LabConfig.from_dict(lab_data)
                
                # Копируем обновленные поля
                for field_name in updated_config.__dataclass_fields__:
                    if hasattr(updated_config, field_name):
                        setattr(lab_config, field_name, getattr(updated_config, field_name))
        
        # Загружаем конфигурацию анализа образов
        if 'image_analysis' in data:
            config.image_analysis = ImageAnalysisConfig.from_dict(data['image_analysis'])
        
        # Загружаем конфигурацию тестового набора
        if 'test_suite' in data:
            config.test_suite = TestSuiteConfig.from_dict(data['test_suite'])
        
        return config
    
    def save(self, config_path: str):
        """
        Сохранение конфигурации в файл.
        
        Args:
            config_path: Путь к файлу конфигурации
        """
        data = self.to_dict()
        
        with open(config_path, 'w', encoding='utf-8') as f:
            if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            elif config_path.endswith('.json'):
                json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Неподдерживаемый формат файла: {config_path}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование конфигурации в словарь."""
        return {
            'general': {
                'log_level': self.general.log_level.value,
                'log_file': self.general.log_file,
                'cleanup_images': self.general.cleanup_images,
                'silent_mode': self.general.silent_mode,
                'max_execution_time': self.general.max_execution_time,
                'output_format': self.general.output_format
            },
            'lab10': self._lab_to_dict(self.lab10),
            'lab11': self._lab_to_dict(self.lab11),
            'lab12': self._lab_to_dict(self.lab12),
            'lab13': self._lab_to_dict(self.lab13),
            'lab14': self._lab_to_dict(self.lab14),
            'image_analysis': {
                'compare_sizes': self.image_analysis.compare_sizes,
                'max_size_mb': self.image_analysis.max_size_mb,
                'check_dockerignore': self.image_analysis.check_dockerignore,
                'check_layer_efficiency': self.image_analysis.check_layer_efficiency,
                'unnecessary_files': self.image_analysis.unnecessary_files,
                'min_savings_percentage': self.image_analysis.min_savings_percentage
            },
            'test_suite': {
                'run_tests': self.test_suite.run_tests,
                'correct_solutions_dir': self.test_suite.correct_solutions_dir,
                'incorrect_solutions_dir': self.test_suite.incorrect_solutions_dir,
                'expected_success_rate': self.test_suite.expected_success_rate
            }
        }
    
    def _lab_to_dict(self, lab_config: LabConfig) -> Dict[str, Any]:
        """Преобразование конфигурации лабораторной в словарь."""
        return {
            'enabled': lab_config.enabled,
            'timeout': lab_config.timeout,
            'expected_ports': lab_config.expected_ports,
            'expected_content': lab_config.expected_content,
            'require_api_integration': lab_config.require_api_integration,
            'architecture_checks': lab_config.architecture_checks,
            'sleep_time_variants': lab_config.sleep_time_variants,
            'require_timestamp': lab_config.require_timestamp,
            'compose_services': lab_config.compose_services,
            'expected_ports': lab_config.expected_ports,
            'network_checks': lab_config.network_checks,
            'expected_networks': lab_config.expected_networks,
            'check_port_mapping': lab_config.check_port_mapping,
            'check_service_discovery': lab_config.check_service_discovery,
            'max_image_size_mb': lab_config.max_image_size_mb,
            'check_dockerignore': lab_config.check_dockerignore,
            'check_unnecessary_files': lab_config.check_unnecessary_files,
            'allowed_file_patterns': lab_config.allowed_file_patterns
        }
    
    def get_lab_config(self, lab_type: str) -> LabConfig:
        """
        Получение конфигурации для конкретной лабораторной.
        
        Args:
            lab_type: Тип лабораторной (lab10, lab11, etc.)
            
        Returns:
            Конфигурация лабораторной
            
        Raises:
            ValueError: Если тип лабораторной не поддерживается
        """
        # Список атрибутов в классе Config, которые являются конфигурациями лаб
        valid_labs = ['lab10', 'lab11', 'lab12', 'lab13', 'lab14']
        
        if lab_type not in valid_labs:
            available = ", ".join(valid_labs)
            raise ValueError(
                f"Неизвестный тип лабораторной: '{lab_type}'. "
                f"Доступные варианты: {available}"
            )
        
        return getattr(self, lab_type)

# Функции для удобной работы с конфигурацией
def load_config(config_path: str) -> Config:
    """Загрузка конфигурации из файла."""
    return Config.load(config_path)

def create_default_config() -> Config:
    """Создание конфигурации по умолчанию."""
    return Config()

def save_default_config(config_path: str):
    """
    Сохранение конфигурации по умолчанию в файл.
    
    Args:
        config_path: Путь к файлу конфигурации
    """
    config = create_default_config()
    config.save(config_path)