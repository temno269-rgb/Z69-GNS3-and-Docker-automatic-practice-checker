import os
import re
import time
import requests
from modules.Docker.lab_checker.core import LabChecker

class Lab10Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker

    def check(self) -> bool:
        """Проверка лабораторной работы №10: Flask в Docker."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №10 ===")

        # 1. Ищем Dockerfile
        if not os.path.exists(os.path.join(self.checker.project_dir, 'Dockerfile')):
            self.checker.add_result("Наличие Dockerfile", False, "Dockerfile не найден в корне проекта")
            return False
        self.checker.add_result("Наличие Dockerfile", True, "Dockerfile найден")

        # 2. Проверяем наличие docker-compose.yml
        compose_files = ['docker-compose.yml', 'docker-compose.yaml']
        has_compose = any(os.path.exists(os.path.join(self.checker.project_dir, f)) for f in compose_files)
        
        if not has_compose:
            self.checker.add_result("Файл docker-compose", False, "docker-compose.yml не найден. В этой работе ожидается запуск через compose.")
            return False
        self.checker.add_result("Файл docker-compose", True, "Файл docker-compose найден")

        # 3. Сборка и запуск контейнеров
        self.checker.log("Запускаем docker-compose up -d --build...")
        # Используем новый метод run_subprocess из переписанного core.py
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "up", "-d", "--build"])
        
        if code != 0:
            self.checker.add_result("Запуск приложения", False, f"Ошибка при сборке/запуске: {stderr}")
            return False
        self.checker.add_result("Запуск приложения", True, "Контейнеры успешно собраны и запущены")

        # Даем Flask-серверу пару секунд на инициализацию
        time.sleep(3)

        # 4. Ищем порт, который студент пробросил наружу
        port = self._find_exposed_port()
        if not port:
            self.checker.add_result("Сетевые настройки", False, "Не удалось найти проброшенный наружу порт. Проверьте секцию ports в docker-compose.yml")
            return False
        self.checker.add_result("Сетевые настройки", True, f"Обнаружен проброшенный порт: {port}")

        # 5. HTTP проверка доступности и контента (по ТЗ)
        url = f"http://localhost:{port}"
        try:
            response = requests.get(url, timeout=5)
            # Иногда Flask возвращает 500, если студент накосячил с кодом, но сервер жив
            if response.status_code == 200:
                self.checker.add_result("Доступность веб-интерфейса", True, f"HTTP 200 OK по адресу {url}")
                content = response.text.lower()
                
                expected_words = self.checker.config.lab10.expected_content
                # Проверяем, какие слова из списка найдены на странице
                found_words = [word for word in expected_words if word.lower() in content]
                missing_words = [word for word in expected_words if word.lower() not in content]

                if len(found_words) >= 2: # Если найдено хотя бы 2 слова (города) из списка
                    self.checker.add_result("Логика приложения", True, f"Найдено совпадений: {', '.join(found_words)}")
                else:
                    self.checker.add_result("Логика приложения", False, f"Требуемые города не найдены. Отсутствуют: {', '.join(missing_words)}")
            else:
                self.checker.add_result("Доступность веб-интерфейса", False, f"Приложение вернуло HTTP код {response.status_code} вместо 200")
        except Exception as e:
            self.checker.add_result("Доступность веб-интерфейса", False, f"Ошибка подключения к {url}: {str(e)}")

        # Ядро (core.py) само сделает docker-compose down в блоке finally, нам не нужно об этом думать
        return True

    def _find_exposed_port(self) -> int:
        """Динамически вычисляет, какой порт docker-compose пробросил на хост."""
        # Способ 1: Спросить у самого docker-compose
        code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "ps", "--format", "json"])
        if code == 0 and stdout:
            try:
                import json
                # Вывод может состоять из нескольких JSON строк (JSONL)
                for line in stdout.strip().split('\n'):
                    if not line.strip(): continue
                    container_info = json.loads(line)
                    if 'Publishers' in container_info and container_info['Publishers']:
                        for pub in container_info['Publishers']:
                            if 'PublishedPort' in pub and pub['PublishedPort']:
                                return int(pub['PublishedPort'])
            except Exception as e:
                self.checker.log(f"Не удалось распарсить 'docker-compose ps': {e}", "DEBUG")

        # Способ 2: Резервный вариант через docker-py (ищем по имени проекта)
        try:
            # По умолчанию compose называет проект по имени папки
            project_name = os.path.basename(os.path.abspath(self.checker.project_dir)).lower()
            project_name = re.sub(r'[^a-z0-9]', '', project_name)
            
            containers = self.checker.client.containers.list(filters={"label": f"com.docker.compose.project={project_name}"})
            for c in containers:
                ports = c.attrs.get('NetworkSettings', {}).get('Ports', {})
                for internal, external in ports.items():
                    if external:  # Если есть проброс наружу
                        return int(external[0]['HostPort'])
        except Exception as e:
            self.checker.log(f"Поиск портов через docker-py не удался: {e}", "DEBUG")

        # Способ 3: Глупый перебор (на случай, если все сломалось)
        for default_port in self.checker.config.lab10.expected_ports:
            try:
                requests.get(f"http://localhost:{default_port}", timeout=1)
                return default_port
            except:
                pass

        return None