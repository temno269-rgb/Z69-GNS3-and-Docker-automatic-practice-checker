import os
import time
import requests
import yaml
from modules.Docker.lab_checker.core import LabChecker

class Lab13Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker

    def check(self) -> bool:
        """Проверка лабораторной работы №13: Сети в Docker (Изоляция и маршрутизация)."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №13 ===")

        # 1. Поиск файла docker-compose
        compose_file = None
        for filename in ['docker-compose.yml', 'docker-compose.yaml']:
            path = os.path.join(self.checker.project_dir, filename)
            if os.path.exists(path):
                compose_file = path
                break
                
        if not compose_file:
            self.checker.add_result("Наличие docker-compose", False, "Файл docker-compose.yml не найден. Архитектура из 4 сервисов требует compose.")
            return False
            
        self.checker.add_result("Наличие docker-compose", True, "Файл конфигурации сетей найден")

        # 2. Парсинг топологии сетей из YAML
        # Используем отдельный конфиг для lab13, если он есть, или общий дефолт
        prom_port = getattr(self.checker.config, 'lab13', self.checker.config.lab12).expected_ports.get("prometheus", 9090)
        try:
            with open(compose_file, 'r', encoding='utf-8') as f:
                compose_data = yaml.safe_load(f)
                
            networks = compose_data.get('networks', {})
            services = compose_data.get('services', {})
            
            # Проверка количества сетей
            if len(networks) >= 2:
                self.checker.add_result("Объявление сетей", True, f"Найдено объявление минимум двух сетей: {list(networks.keys())}")
            else:
                self.checker.add_result("Объявление сетей", False, "По заданию №2 необходимо создать минимум две изолированные сети")

            # Проверка подключения сервисов к сетям (поиск "моста")
            bridge_services = []
            isolated_services = []
            
            for service_name, service_config in services.items():
                # Ищем Prometheus для дальнейшего API-запроса
                if 'prometheus' in service_config.get('image', '').lower() or 'prometheus' in service_name.lower():
                    prom_port = self._extract_host_port(service_config.get('ports', []), default=prom_port)

                srv_networks = service_config.get('networks', [])
                if isinstance(srv_networks, dict):
                    srv_networks = list(srv_networks.keys())
                    
                if len(srv_networks) >= 2:
                    bridge_services.append(service_name)
                elif len(srv_networks) == 1:
                    isolated_services.append(service_name)

            if bridge_services:
                self.checker.add_result("Маршрутизация (Мост)", True, f"Найден сервис-мост, подключенный к нескольким сетям: {bridge_services[0]}")
            else:
                self.checker.add_result("Маршрутизация (Мост)", False, "Ни один сервис не подключен к двум сетям одновременно (ожидался exporter в качестве моста)")

        except Exception as e:
            self.checker.add_result("Анализ топологии", False, f"Ошибка при чтении docker-compose.yml: {str(e)}")

        # 3. Запуск инфраструктуры
        self.checker.log("Поднимаем стек через docker-compose up -d...")
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "up", "-d"])
        
        if code != 0:
            self.checker.add_result("Запуск сети", False, f"Ошибка при запуске инфраструктуры: {stderr}")
            return False
            
        self.checker.add_result("Запуск сети", True, "Все сервисы и сети успешно созданы")

        # Даем время на запуск баз данных и сбор метрик (Prometheus собирает раз в 5с по дефолту)
        self.checker.log("Ожидание инициализации сервисов и сбора метрик (15 секунд)...")
        time.sleep(15)

        # 4. Проверка состояния контейнеров
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "ps"])
        if "Exit" in stdout or "restarting" in stdout.lower():
            self.checker.add_result("Стабильность контейнеров", False, "Некоторые сервисы упали (возможно, ошибка в конфигах Prometheus или MongoDB)")
        else:
            self.checker.add_result("Стабильность контейнеров", True, "Все контейнеры успешно работают в своих сетях")

        # 5. Активная сетевая проверка через API Prometheus
        # Если сети настроены верно, Prometheus сможет достучаться до exporter'а
        self._check_prometheus_targets(prom_port)

        return True

    def _extract_host_port(self, ports_list: list, default: int) -> int:
        """Извлекает порт хоста из секции ports."""
        if not ports_list:
            return default
        for port_mapping in ports_list:
            if isinstance(port_mapping, dict):
                return int(port_mapping.get('published', default))
            elif isinstance(port_mapping, str):
                parts = port_mapping.split(':')
                if len(parts) == 2:
                    return int(parts[0])
                elif len(parts) >= 3:
                    return int(parts[1])
        return default

    def _check_prometheus_targets(self, prom_port: int):
        """Опрашивает API Prometheus для проверки связи с exporter'ом по внутренней сети."""
        url = f"http://localhost:{prom_port}/api/v1/targets"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                active_targets = data.get('data', {}).get('activeTargets', [])
                
                # Ищем таргет, который не является самим локалхостом прометея
                exporter_up = False
                for target in active_targets:
                    # Исключаем дефолтный таргет самого prometheus
                    if 'localhost:9090' not in target.get('discoveredLabels', {}).get('__address__', ''):
                        if target.get('health') == 'up':
                            exporter_up = True
                            target_url = target.get('scrapeUrl', 'unknown')
                            self.checker.add_result("Сетевая связность (Prometheus -> Exporter)", True, 
                                f"Prometheus успешно видит exporter по внутреннему адресу: {target_url}")
                            break
                            
                if not exporter_up:
                    self.checker.add_result("Сетевая связность (Prometheus -> Exporter)", False, 
                        "Prometheus запущен, но не может подключиться к exporter'у. Проверьте настройки сетей и prometheus.yml")
            else:
                self.checker.add_result("Доступность Prometheus API", False, f"API вернуло код {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            self.checker.add_result("Связь с Prometheus", False, f"Отказ в соединении. Проверьте, проброшен ли порт {prom_port}.")
        except Exception as e:
            self.checker.add_result("Связь с Prometheus", False, f"Ошибка при запросе к API: {str(e)}")