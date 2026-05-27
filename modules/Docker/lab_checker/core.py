import docker
import logging
import sys
import os
import time
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from .types import LabType, CheckResult
from .config import Config

class LabChecker:
    def __init__(self, config: Config):
        """
        Инициализация LabChecker.
        Принимает объект Config и настраивает окружение.
        """
        self.config = config
        self.silent_mode = config.general.silent_mode
        self.project_dir = None
        
        self.execution_logs = []
        
        # Настройка логирования
        self.logger = logging.getLogger('lab_checker')
        self.logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Избегаем дублирования хэндлеров при повторных вызовах
        if not self.logger.handlers:
            if not self.silent_mode:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setLevel(logging.DEBUG)
                console_handler.setFormatter(formatter)
                self.logger.addHandler(console_handler)
            # Логирование в файл полностью убрано, чтобы не создавать дубликатов на диске
        
        self.log(f"Инициализация LabChecker (папка проекта ожидается)")
        
        try:
            self.client = docker.from_env(timeout=300)
            self.client.ping()
            self.log("Docker клиент успешно подключен", "DEBUG")
        except Exception as e:
            self.client = None
            self.log(f"Ошибка подключения к Docker: {str(e)}", "ERROR")
            raise Exception(f"Failed to connect to Docker: {str(e)}")
        
        self.results: List[CheckResult] = []
        self.lab_type = None
        self.start_time = datetime.now()
        
    def log(self, message: str, level: str = "INFO"):
        """Универсальный метод логирования."""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        self.execution_logs.append({"timestamp": timestamp, "level": level, "message": message})

        if self.silent_mode:
            import json
            print(json.dumps({"type": "progress_log", "level": level, "message": message}, ensure_ascii=False), flush=True)
            return

        if level == "DEBUG": self.logger.debug(message)
        elif level == "INFO": self.logger.info(message)
        elif level == "WARNING": self.logger.warning(message)
        elif level == "ERROR": self.logger.error(message)
        elif level == "CRITICAL": self.logger.critical(message)
        else: self.logger.info(message)
    
    def add_result(self, name: str, passed: bool, message: str, details: Dict = None):
        """Фиксация результата проверки для итогового отчета."""
        result = CheckResult(name=name, passed=passed, message=message, details=details)
        self.results.append(result)
        
        log_level = "INFO" if passed else "ERROR"
        status = "УСПЕХ" if passed else "НЕУДАЧА"
        self.log(f"[{status}] {name}: {message}", level=log_level)

    def run_subprocess(self, cmd: List[str], cwd: Optional[str] = None) -> Tuple[int, str, str]:
        """
        Безопасное выполнение консольных команд через subprocess.
        cwd по умолчанию — текущая папка проекта.
        """
        work_dir = cwd or self.project_dir
        if not work_dir:
            return -1, "", "Project directory not set"

        self.log(f"Выполнение команды: {' '.join(cmd)}", "DEBUG")
        
        # Настраиваем аргументы для скрытия всплывающих окон консоли в Windows
        kwargs = {
            'cwd': work_dir,
            'capture_output': True,
            'text': True,
            'check': False
        }
        
        if os.name == 'nt':
            # CREATE_NO_WINDOW = 0x08000000
            kwargs['creationflags'] = 0x08000000

        try:
            result = subprocess.run(
                cmd, **kwargs
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except Exception as e:
            self.log(f"Ошибка при вызове subprocess: {str(e)}", "ERROR")
            return -1, "", str(e)

    def cleanup(self):
        """
        Очистка ресурсов Docker. 
        ВНИМАНИЕ: Удаление папок (shutil.rmtree) отключено для безопасности локальных данных.
        """
        if self.project_dir and os.path.exists(self.project_dir):
            self.log("Завершение: остановка контейнеров...", "INFO")
            # Мягко останавливаем compose проект и удаляем тома
            self.run_subprocess(["docker-compose", "down", "-v"])

    def get_results_json(self) -> Dict:
        """Формирование итогового JSON отчета."""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        return {
            'lab_type': self.lab_type.value if self.lab_type else 'unknown',
            'project_dir': self.project_dir,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'results': [result.to_dict() for result in self.results],
            'summary': {
                'total_checks': total,
                'passed_checks': passed,
                'failed_checks': total - passed,
                'success_rate': f"{(passed / total * 100):.1f}%" if total > 0 else "0.0%"
            },
            'logs': self.execution_logs
        }
    
    def print_summary(self):
        """Вывод текстовой сводки в консоль."""
        if self.silent_mode: return
        print("\n" + "=" * 60)
        print(f"ИТОГИ ПРОВЕРКИ: {self.lab_type.value.upper() if self.lab_type else 'UNKNOWN'}")
        print("=" * 60)
        for result in self.results:
            status = "✓" if result.passed else "✗"
            print(f"{status} {result.name:.<40} {result.message}")
        print("=" * 60)
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        print(f"Статистика: {passed}/{total} успешно.")
        print("=" * 60)
    
    def check_lab(self, project_path: str, lab_type: LabType):
        """
        Главная точка входа.
        Принимает путь к папке и запускает соответствующий чекер.
        """
        self.results = []
        self.project_dir = os.path.abspath(project_path)
        self.lab_type = lab_type
        
        self.log(f"Начало проверки: {lab_type.value}. Директория: {self.project_dir}", "INFO")
        
        if not os.path.isdir(self.project_dir):
            self.add_result("Подготовка", False, f"Путь не является папкой или не существует: {self.project_dir}")
            return self.get_results_json()

        try:
            # Загружаем только тот чекер, который запросили в терминале
            if lab_type == LabType.LAB10:
                from modules.Docker.lab_checker.checkers.lab10 import Lab10Checker as CheckerClass
            elif lab_type == LabType.LAB11:
                from modules.Docker.lab_checker.checkers.lab11 import Lab11Checker as CheckerClass
            elif lab_type == LabType.LAB12:
                from modules.Docker.lab_checker.checkers.lab12 import Lab12Checker as CheckerClass
            elif lab_type == LabType.LAB13:
                from modules.Docker.lab_checker.checkers.lab13 import Lab13Checker as CheckerClass
            elif lab_type == LabType.LAB14:
                from modules.Docker.lab_checker.checkers.lab14 import Lab14Checker as CheckerClass
            else:
                raise ValueError(f"Неизвестный тип лабораторной: {lab_type}")
                
            checker_instance = CheckerClass(self)
            checker_instance.check()
            
        except Exception as e:
            self.add_result("Критическая ошибка", False, f"В процессе проверки произошел сбой: {str(e)}")
            self.log(f"Ошибка выполнения: {str(e)}", "CRITICAL")
        finally:
            self.cleanup()
            if not self.silent_mode: self.print_summary()
        return self.get_results_json()