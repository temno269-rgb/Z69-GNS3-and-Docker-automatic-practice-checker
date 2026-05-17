import os
import time
import requests
import yaml
from modules.Docker.lab_checker.core import LabChecker

class Lab12Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker

    def check(self) -> bool:
        """Проверка лабораторной работы №12: Docker Compose (Prometheus + Grafana)."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №12 ===")

        # 1. Ищем файл docker-compose
        compose_file = None
        for filename in ['docker-compose.yml', 'docker-compose.yaml']:
            path = os.path.join(self.checker.project_dir, filename)
            if os.path.exists(path):
                compose_file = path
                break
                
        if not compose_file:
            self.checker.add_result("Наличие docker-compose", False, "Файл docker-compose.yml не найден в корне проекта")
            return False
            
        self.checker.add_result("Наличие docker-compose", True, f"Найден файл: {os.path.basename(compose_file)}")

        # 2. Анализируем содержимое docker-compose.yml (ищем Prometheus и Grafana)
        prom_port = None
        grafana_port = None
        
        try:
            with open(compose_file, 'r', encoding='utf-8') as f:
                compose_data = yaml.safe_load(f)
                
            services = compose_data.get('services', {})
            has_prometheus = False
            has_grafana = False
            
            for service_name, service_config in services.items():
                image = service_config.get('image', '').lower()
                
                # Ищем Prometheus
                if 'prometheus' in image:
                    has_prometheus = True
                    prom_port = self._extract_host_port(service_config.get('ports', []), default=self.checker.config.lab12.expected_ports.get("prometheus", 9090))
                    
                # Ищем Grafana
                if 'grafana' in image:
                    has_grafana = True
                    grafana_port = self._extract_host_port(service_config.get('ports', []), default=self.checker.config.lab12.expected_ports.get("grafana", 3000))

            if has_prometheus and has_grafana:
                self.checker.add_result("Структура docker-compose", True, "В файле обнаружены сервисы Prometheus и Grafana")
            else:
                missing = []
                if not has_prometheus: missing.append("Prometheus")
                if not has_grafana: missing.append("Grafana")
                self.checker.add_result("Структура docker-compose", False, f"В файле не найдены образы для: {', '.join(missing)} (по заданию №2)")
                # Не прерываем выполнение, попробуем запустить то, что есть (студент мог сделать только задание 1)
                
        except Exception as e:
            self.checker.add_result("Анализ YAML", False, f"Ошибка при чтении docker-compose.yml: {str(e)}")

        # 3. Запуск стека через docker-compose
        self.checker.log("Поднимаем стек через docker-compose up -d...")
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "up", "-d"])
        
        if code != 0:
            self.checker.add_result("Запуск проекта", False, f"Ошибка docker-compose up: {stderr}")
            return False
            
        self.checker.add_result("Запуск проекта", True, "Стек успешно запущен")

        # Даем тяжелым сервисам (Grafana) время на запуск базы данных и инициализацию
        self.checker.log("Ожидание инициализации сервисов (10 секунд)...")
        time.sleep(10)

        # 4. Проверка состояния контейнеров
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "ps"])
        if "Exit" in stdout or "restarting" in stdout.lower():
            self.checker.add_result("Статус контейнеров", False, "Некоторые контейнеры упали или постоянно перезапускаются (CrashLoop)")
        else:
            self.checker.add_result("Статус контейнеров", True, "Все контейнеры стабильно работают (Up)")

        # 5. Проверка доступности Web UI (задание 2)
        if prom_port:
            self._check_web_ui("Prometheus", prom_port, "/api/v1/query?query=up")
        if grafana_port:
            self._check_web_ui("Grafana", grafana_port, "/api/health")

        return True

    def _extract_host_port(self, ports_list: list, default: int) -> int:
        """Извлекает порт хоста из секции ports (например, '8080:3000' -> 8080)"""
        if not ports_list:
            return default
            
        for port_mapping in ports_list:
            # Форматы могут быть '9090:9090', '0.0.0.0:8080:3000/tcp', или dict (в новом синтаксисе)
            if isinstance(port_mapping, dict):
                return int(port_mapping.get('published', default))
            elif isinstance(port_mapping, str):
                parts = port_mapping.split(':')
                if len(parts) == 2:  # '8080:3000'
                    return int(parts[0])
                elif len(parts) >= 3:  # '0.0.0.0:8080:3000'
                    return int(parts[1])
        return default

    def _check_web_ui(self, service_name: str, port: int, health_endpoint: str):
        """Проверяет доступность веб-интерфейса сервиса."""
        url = f"http://localhost:{port}"
        try:
            # Сначала пробуем дернуть Health-эндпоинт (он надежнее)
            response = requests.get(f"{url}{health_endpoint}", timeout=5)
            if response.status_code == 200:
                self.checker.add_result(f"Web UI: {service_name}", True, f"Интерфейс доступен на порту {port} (HTTP 200)")
                return
                
            # Если Health не ответил, пробуем корень
            response_root = requests.get(url, timeout=5)
            if response_root.status_code == 200:
                self.checker.add_result(f"Web UI: {service_name}", True, f"Интерфейс доступен на порту {port}")
            else:
                self.checker.add_result(f"Web UI: {service_name}", False, f"Интерфейс вернул код {response_root.status_code}")
                
        except requests.exceptions.ConnectionError:
            self.checker.add_result(f"Web UI: {service_name}", False, f"Отказ в соединении по порту {port}. Проверьте проброс портов.")
        except Exception as e:
            self.checker.add_result(f"Web UI: {service_name}", False, f"Ошибка HTTP-запроса: {str(e)}")