import os
import yaml
import docker
import requests
import time
import json
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass
from modules.Docker.lab_checker.core import LabChecker
from modules.Docker.lab_checker.types import CheckResult

@dataclass
class ComposeCheckResult:
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None

class LabComposeChecker:
    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.results: List[ComposeCheckResult] = []
        
    def log(self, message: str):
        """Вывод сообщения с учетом уровня детализации."""
        if self.checker.verbose:
            self.checker.log(message)
    
    def add_result(self, name: str, passed: bool, message: str, details: Optional[Dict] = None):
        """Добавление результата проверки."""
        result = ComposeCheckResult(name=name, passed=passed, message=message, details=details)
        self.results.append(result)
        self.checker.add_result(name, passed, message)
    
    def check_compose_file(self, project_path: str) -> bool:
        """Проверка наличия и корректности docker-compose.yml файла."""
        compose_file = None
        possible_names = ['docker-compose.yml', 'docker-compose.yaml', 'docker-compoes.yml']
        
        for name in possible_names:
            file_path = os.path.join(project_path, name)
            if os.path.exists(file_path):
                compose_file = file_path
                break
        
        if not compose_file:
            self.add_result("Файл docker-compose", False, "Файл docker-compose.yml не найден")
            return False
        
        self.add_result("Файл docker-compose", True, f"Найден файл: {os.path.basename(compose_file)}")
        
        try:
            with open(compose_file, 'r', encoding='utf-8') as f:
                compose_config = yaml.safe_load(f)
            
            # Проверка версии
            if 'version' in compose_config:
                version = compose_config['version']
                self.add_result("Версия docker-compose", True, f"Указана версия: {version}")
            else:
                self.add_result("Версия docker-compose", False, "Версия не указана")
            
            # Проверка наличия сервисов
            if 'services' not in compose_config:
                self.add_result("Секции services", False, "Отсутствует секция services")
                return False
            
            services = compose_config['services']
            if not services:
                self.add_result("Сервисы", False, "Секция services пуста")
                return False
            
            self.add_result("Сервисы", True, f"Найдено сервисов: {len(services)}")
            
            # Анализ каждого сервиса
            for service_name, service_config in services.items():
                self.check_service(service_name, service_config)
            
            return True
            
        except yaml.YAMLError as e:
            self.add_result("Парсинг YAML", False, f"Ошибка синтаксиса YAML: {str(e)}")
            return False
        except Exception as e:
            self.add_result("Чтение файла", False, f"Ошибка чтения файла: {str(e)}")
            return False
    
    def check_service(self, service_name: str, service_config: Dict):
        """Проверка конфигурации отдельного сервиса."""
        self.log(f"Проверка сервиса: {service_name}")
        
        # Проверка образа
        if 'image' in service_config:
            image = service_config['image']
            self.add_result(f"Сервис {service_name}: образ", True, f"Используется образ: {image}")
        else:
            self.add_result(f"Сервис {service_name}: образ", False, "Не указан образ")
        
        # Проверка портов
        if 'ports' in service_config:
            ports = service_config['ports']
            if isinstance(ports, list) and ports:
                self.add_result(f"Сервис {service_name}: порты", True, f"Проброшено портов: {len(ports)}")
            else:
                self.add_result(f"Сервис {service_name}: порты", False, "Секция портов пуста")
        else:
            self.add_result(f"Сервис {service_name}: порты", False, "Не указаны порты")
        
        # Проверка переменных окружения
        if 'environment' in service_config:
            env = service_config['environment']
            if isinstance(env, dict) and env:
                self.add_result(f"Сервис {service_name}: окружение", True, f"Переменных окружения: {len(env)}")
            elif isinstance(env, list) and env:
                self.add_result(f"Сервис {service_name}: окружение", True, f"Переменных окружения: {len(env)}")
            else:
                self.add_result(f"Сервис {service_name}: окружение", False, "Секция окружения пуста")
        else:
            self.add_result(f"Сервис {service_name}: окружение", False, "Не указаны переменные окружения")
        
        # Проверка volumes
        if 'volumes' in service_config:
            volumes = service_config['volumes']
            if isinstance(volumes, list) and volumes:
                self.add_result(f"Сервис {service_name}: volumes", True, f"Примонтировано volumes: {len(volumes)}")
            else:
                self.add_result(f"Сервис {service_name}: volumes", False, "Секция volumes пуста")
        
        # Проверка политики перезапуска
        if 'restart' in service_config:
            restart = service_config['restart']
            self.add_result(f"Сервис {service_name}: restart", True, f"Политика перезапуска: {restart}")
        else:
            self.add_result(f"Сервис {service_name}: restart", False, "Не указана политика перезапуска")
    
    def check_compose_functionality(self, project_path: str) -> bool:
        """Проверка функциональности docker-compose проекта."""
        self.checker.log("=== Проверка функциональности docker-compose ===")
        
        try:
            # Переход в директорию проекта
            original_cwd = os.getcwd()
            os.chdir(project_path)
            
            # Проверка запуска через docker-compose
            self.log("Запуск docker-compose up -d...")
            result = os.system("docker-compose up -d")
            if result == 0:
                self.add_result("Запуск docker-compose", True, "Проект успешно запущен")
            self.log("Запуск docker-compose up -d --build...")
            code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "up", "-d", "--build"])
            if code == 0:
                self.add_result("Запуск docker-compose", True, "Проект успешно запущен", details={"stdout": stdout, "stderr": stderr})
            else:
                self.add_result("Запуск docker-compose", False, "Ошибка запуска проекта")
                return False
            
            # Ожидание запуска сервисов
            time.sleep(10)
            
            # Проверка статуса контейнеров
            self.log("Проверка статуса контейнеров...")
            try:
                containers = self.checker.client.containers.list()
                running_containers = [c for c in containers if c.status == 'running']
                if running_containers:
                    self.add_result("Статус контейнеров", True, f"Запущено контейнеров: {len(running_containers)}")
                else:
                    self.add_result("Статус контейнеров", False, "Нет запущенных контейнеров")
            except Exception as e:
                self.add_result("Статус контейнеров", False, f"Ошибка проверки: {str(e)}")
            
            # Проверка доступности веб-интерфейсов
            self.check_web_interfaces()
            
            # Остановка проекта
            self.log("Остановка docker-compose...")
            stop_result = os.system("docker-compose down")
            if stop_result == 0:
                self.add_result("Остановка docker-compose", True, "Проект успешно остановлен")
            code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "down"])
            if code == 0:
                self.add_result("Остановка docker-compose", True, "Проект успешно остановлен", details={"stdout": stdout, "stderr": stderr})
            else:
                self.add_result("Остановка docker-compose", False, "Ошибка остановки проекта")
            
            # Возврат в исходную директорию
            os.chdir(original_cwd)
            return True
            
        except Exception as e:
            self.add_result("Функциональная проверка", False, f"Ошибка: {str(e)}")
            os.chdir(original_cwd)
            return False
    
    def check_web_interfaces(self):
        """Проверка доступности веб-интерфейсов."""
        # Проверка стандартных портов для Prometheus и Grafana
        common_ports = [
            (9090, "Prometheus"),
            (3000, "Grafana"),
            (8080, "Flask"),
            (2020, "Flask Lab10"),
            (80, "HTTP"),
            (8081, "HTTP Alt")
        ]
        
        for port, service_name in common_ports:
            try:
                response = requests.get(f'http://localhost:{port}', timeout=3)
                if response.status_code == 200:
                    self.add_result(f"Веб-интерфейс {service_name}", True, f"Доступен на порту {port}")
                else:
                    self.add_result(f"Веб-интерфейс {service_name}", False, f"Статус: {response.status_code}")
            except requests.exceptions.ConnectionError:
                pass  # Порт не доступен - это нормально
            except Exception as e:
                self.log(f"Ошибка проверки порта {port}: {str(e)}")
    
    def check(self, project_path: str) -> bool:
        """Запуск всех проверок docker-compose."""
        self.checker.log(f"Проверка docker-compose проекта: {project_path}")
        
        # Проверка файла конфигурации
        if not self.check_compose_file(project_path):
            return False
        
        # Проверка функциональности
        if not self.check_compose_functionality(project_path):
            return False
        
        return True
