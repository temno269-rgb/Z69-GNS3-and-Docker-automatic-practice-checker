import html
import os
import re
import time
import uuid

import requests

from modules.Docker.lab_checker.core import LabChecker


class Lab10Checker:
    COMPOSE_FILES = ("compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml")
    COMMON_PORTS = (8080, 5000, 80, 2020)

    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.session = requests.Session()

    def check(self) -> bool:
        """Функциональная проверка Flask-приложения без привязки к структуре проекта."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №10 ===")

        dockerfile_path = os.path.join(self.checker.project_dir, "Dockerfile")
        if not os.path.isfile(dockerfile_path):
            self.checker.add_result("Наличие Dockerfile", False, "Dockerfile не найден в корне проекта")
            return False
        self.checker.add_result("Наличие Dockerfile", True, "Dockerfile найден")

        compose_file = next(
            (name for name in self.COMPOSE_FILES
             if os.path.isfile(os.path.join(self.checker.project_dir, name))),
            None,
        )
        container = None
        image = None

        try:
            if compose_file:
                containers = self._start_compose(compose_file)
                if not containers:
                    return False
            else:
                image, container = self._build_and_start_dockerfile(dockerfile_path)
                if not container:
                    return False
                containers = [container]

            endpoints = self._published_endpoints(containers)
            if not endpoints:
                self.checker.add_result(
                    "Сетевые настройки", False,
                    "У контейнера нет опубликованного HTTP-порта",
                )
                return False
            self.checker.add_result(
                "Сетевые настройки", True,
                "Найдены опубликованные порты: " + ", ".join(str(port) for port in endpoints),
            )

            response, url = self._wait_for_valid_response(containers, endpoints, timeout=8)
            if response is None:
                self.checker.add_result(
                    "Доступность веб-интерфейса", False,
                    "Приложение не вернуло HTTP 200 за 8 секунд",
                )
                return False

            self.checker.add_result("Доступность веб-интерфейса", True, f"HTTP 200 OK: {url}")
            temperatures = self._find_temperatures(response)
            missing = [city for city in ("Москва", "Самара") if city not in temperatures]
            if missing:
                self.checker.add_result(
                    "Температуры городов", False,
                    "Не найдена связка «город + числовая температура» для: " + ", ".join(missing),
                )
                return False

            self.checker.add_result(
                "Температуры городов", True,
                f"Москва: {temperatures['Москва']:g}; Самара: {temperatures['Самара']:g}",
            )
            return True
        finally:
            self.session.close()
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            if image is not None:
                try:
                    self.checker.client.images.remove(image.id, force=True)
                except Exception:
                    pass

    def _start_compose(self, compose_file: str):
        compose_cmd = self.checker.get_compose_command()
        if not compose_cmd:
            self.checker.add_result("Запуск приложения", False, "Docker Compose не найден")
            return []

        project = f"lab10_{uuid.uuid4().hex[:10]}"
        self.checker.active_compose_file = compose_file
        self.checker.active_compose_project = project
        base_command = compose_cmd + ["-p", project, "-f", compose_file]
        self.checker.log(f"Сборка и запуск через {compose_file}...")
        code, _, stderr = self.checker.run_subprocess(
            base_command + ["up", "-d", "--build"], timeout=180
        )
        if code != 0:
            self.checker.add_result("Запуск приложения", False, f"Ошибка Compose: {stderr}")
            return []

        code, stdout, stderr = self.checker.run_subprocess(
            base_command + ["ps", "-q"], timeout=20
        )
        container_ids = [line.strip() for line in stdout.splitlines() if line.strip()] if code == 0 else []
        containers = []
        for container_id in container_ids:
            try:
                containers.append(self.checker.client.containers.get(container_id))
            except Exception:
                continue
        if not containers:
            self.checker.add_result("Запуск приложения", False, stderr or "Compose не создал контейнеры")
            return []

        self.checker.add_result("Запуск приложения", True, "Образ собран, контейнер запущен через Compose")
        return containers

    def _build_and_start_dockerfile(self, dockerfile_path: str):
        tag = f"lab10-check-{uuid.uuid4().hex[:12]}"
        self.checker.log("Сборка Dockerfile через Docker API...")
        try:
            image, _ = self.checker.client.images.build(
                path=self.checker.project_dir,
                dockerfile=os.path.basename(dockerfile_path),
                tag=tag,
                rm=True,
            )
            self.checker.add_result("Сборка образа", True, "Dockerfile успешно собран")
        except Exception as exc:
            self.checker.add_result("Сборка образа", False, f"Ошибка docker build: {exc}")
            return None, None

        ports = self._candidate_container_ports(image, dockerfile_path)
        try:
            container = self.checker.client.containers.run(
                image.id,
                detach=True,
                ports={f"{port}/tcp": None for port in ports},
            )
            self.checker.add_result("Запуск приложения", True, "Контейнер успешно запущен")
            return image, container
        except Exception as exc:
            self.checker.add_result("Запуск приложения", False, f"Контейнер не запустился: {exc}")
            return image, None

    def _candidate_container_ports(self, image, dockerfile_path: str):
        ports = set(self.COMMON_PORTS)
        exposed = image.attrs.get("Config", {}).get("ExposedPorts", {}) or {}
        for value in exposed:
            match = re.match(r"(\d+)", value)
            if match:
                ports.add(int(match.group(1)))
        try:
            content = open(dockerfile_path, "r", encoding="utf-8").read()
            for value in re.findall(r"(?:--port(?:=|\s+)|EXPOSE\s+)(\d+)", content, re.I):
                ports.add(int(value))
        except OSError:
            pass
        return sorted(ports)

    def _published_endpoints(self, containers):
        endpoints = set()
        for container in containers:
            try:
                container.reload()
                bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
                for published in bindings.values():
                    for binding in published or []:
                        if binding.get("HostPort"):
                            endpoints.add(int(binding["HostPort"]))
            except Exception:
                continue
        return sorted(endpoints)

    def _wait_for_valid_response(self, containers, endpoints, timeout: float):
        deadline = time.monotonic() + timeout
        last_200 = (None, None)
        while time.monotonic() < deadline:
            running = False
            for container in containers:
                try:
                    container.reload()
                    running = running or container.status in ("running", "created")
                except Exception:
                    continue
            if not running:
                break

            for port in endpoints:
                url = f"http://127.0.0.1:{port}"
                try:
                    response = self.session.get(url, timeout=0.7)
                    if response.status_code == 200:
                        last_200 = (response, url)
                        if len(self._find_temperatures(response)) == 2:
                            return response, url
                except requests.RequestException:
                    pass
            time.sleep(0.25)
        return last_200

    def _find_temperatures(self, response):
        result = {}
        aliases = {"Москва": ("москва", "moscow"), "Самара": ("самара", "samara")}

        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            lowered = {str(key).casefold(): value for key, value in payload.items()}
            for city, names in aliases.items():
                for name in names:
                    value = lowered.get(name)
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and -100 <= value <= 100:
                        result[city] = float(value)
                        break

        text = html.unescape(response.text).casefold()
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        numbers = []
        for match in re.finditer(r"[-+]?\d+(?:[.,]\d+)?", text):
            value = float(match.group(0).replace(",", "."))
            if -100 <= value <= 100:
                numbers.append((match.span(), value))

        # Одно и то же число нельзя засчитать сразу обоим городам. Выбираем
        # ближайшие уникальные пары «название города — числовое значение».
        candidates = []
        all_city_names = tuple(name for names in aliases.values() for name in names)
        for city, names in aliases.items():
            if city in result:
                continue
            for name in names:
                for city_match in re.finditer(re.escape(name), text, re.I):
                    city_start, city_end = city_match.span()
                    for number_index, ((number_start, number_end), value) in enumerate(numbers):
                        if number_start >= city_end:
                            distance = number_start - city_end
                            allowed = distance <= 60
                            between = text[city_end:number_start]
                            score = distance
                        elif number_end <= city_start:
                            distance = city_start - number_end
                            allowed = distance <= 30
                            between = text[number_end:city_start]
                            if ";" in between:
                                allowed = False
                            # Формат «18 °C — Москва» столь же естественен, как
                            # «Москва: 18». Символ градуса усиливает эту связь.
                            score = max(0, distance - (20 if "°" in between else 1))
                        else:
                            distance, between, score, allowed = 0, "", 0, True
                        crosses_other_city = any(name in between for name in all_city_names)
                        if allowed and not crosses_other_city:
                            candidates.append((score, city, number_index, value))

        used_numbers = set()
        for _, city, number_index, value in sorted(candidates):
            if city in result or number_index in used_numbers:
                continue
            result[city] = value
            used_numbers.add(number_index)
        return result
