import time

import requests

from modules.Docker.lab_checker.checkers.compose_runtime import ComposeRuntime
from modules.Docker.lab_checker.checkers.lab11 import Lab11Checker
from modules.Docker.lab_checker.core import LabChecker


class Lab12Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.session = requests.Session()
        self.lab11_parser = Lab11Checker(checker)

    def check(self) -> bool:
        """Проверяет обе части работы №12 через Compose и фактические сервисы."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №12 ===")

        runtime = ComposeRuntime(self.checker, "lab12")
        if not runtime.file_name:
            self.checker.add_result(
                "Наличие Compose-файла", False,
                "Ожидался compose.yaml/.yml или docker-compose.yaml/.yml",
            )
            return False
        self.checker.add_result("Наличие Compose-файла", True, f"Найден {runtime.file_name}")
        if not runtime.command:
            self.checker.add_result("Docker Compose", False, "Не найдены docker-compose и docker compose")
            return False

        valid, compose, error = runtime.config()
        self.checker.add_result(
            "Валидация Compose", valid,
            "docker compose config выполнен успешно" if valid else error,
        )
        if not valid:
            return False

        services = compose.get("services", {}) or {}
        roles = self._find_roles(services)
        app_services = [name for name in services if name not in set(roles.values())]
        self.checker.add_result(
            "Программа из лабораторной №11", bool(app_services),
            f"Сервисы приложения: {', '.join(app_services)}"
            if app_services else "Не найден отдельный сервис программы из №11",
        )
        missing = [role for role in ("prometheus", "grafana") if role not in roles]
        self.checker.add_result(
            "Prometheus и Grafana", not missing,
            "Оба приложения описаны в Compose"
            if not missing else "Не найдены компоненты: " + ", ".join(missing),
        )

        containers = []
        container_ids = []
        try:
            started, output = runtime.up(build=True)
            self.checker.add_result(
                "Запуск через Compose", started,
                "Проект собран и запущен" if started else output,
            )
            if not started:
                return False

            containers = runtime.wait_for_containers(len(services), timeout=12)
            container_ids = [container.id for container in containers]
            by_service = {runtime.service_name(container): container for container in containers}
            statuses = self._statuses(containers)
            stable = len(containers) >= len(services) and all(status == "running" for status in statuses.values())
            self.checker.add_result(
                "Состояние контейнеров", stable,
                ", ".join(f"{name}={status}" for name, status in statuses.items())
                or "Контейнеры проекта не найдены",
            )

            app_ok, app_message = self._wait_for_app_logs(by_service, app_services, timeout=9)
            self.checker.add_result("Логи программы №11", app_ok, app_message)

            prometheus = by_service.get(roles.get("prometheus", ""))
            grafana = by_service.get(roles.get("grafana", ""))
            prom_ok, prom_message = self._wait_for_http_service(
                runtime, prometheus, 9090, "/-/ready", "prometheus", timeout=12
            )
            self.checker.add_result("Web API Prometheus", prom_ok, prom_message)
            grafana_ok, grafana_message = self._wait_for_http_service(
                runtime, grafana, 3000, "/api/health", "grafana", timeout=15
            )
            self.checker.add_result("Web API Grafana", grafana_ok, grafana_message)
            return stable and app_ok and prom_ok and grafana_ok
        finally:
            self.session.close()
            if runtime.started:
                stopped, message = runtime.down()
                removed = stopped and runtime.project_resources_removed(container_ids)
                self.checker.add_result(
                    "Остановка через Compose", removed,
                    "Контейнеры и временная сеть проекта удалены"
                    if removed else message or "После compose down остались ресурсы проекта",
                )

    @staticmethod
    def _find_roles(services):
        roles = {}
        for name, config in services.items():
            fingerprint = f"{name} {config.get('image', '')}".casefold()
            if "prometheus" in fingerprint and "exporter" not in fingerprint:
                roles.setdefault("prometheus", name)
            if "grafana" in fingerprint:
                roles.setdefault("grafana", name)
        return roles

    @staticmethod
    def _statuses(containers):
        result = {}
        for container in containers:
            try:
                container.reload()
            except Exception:
                pass
            name = ComposeRuntime.service_name(container) or container.short_id
            state = container.attrs.get("State", {})
            status = "restarting" if state.get("Restarting") else container.status
            result[name] = status
        return result

    def _wait_for_app_logs(self, by_service, app_services, timeout):
        if not app_services:
            return False, "Сервис программы №11 отсутствует"
        deadline = time.monotonic() + timeout
        best = ""
        while time.monotonic() < deadline:
            for service in app_services:
                container = by_service.get(service)
                if not container:
                    continue
                try:
                    text = container.logs().decode("utf-8", errors="replace")
                except Exception:
                    continue
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if any("traceback" in line.casefold() for line in lines):
                    return False, f"В логах {service} найден Traceback"
                values = self.lab11_parser._time_values(lines)
                architecture = any(
                    token in text.casefold()
                    for token in ("x86", "x64", "amd64", "x86_64", "arm", "aarch64")
                )
                best = f"{service}: строк={len(lines)}, значений времени={len(values)}"
                if values and architecture:
                    return True, best + "; архитектура указана"
            time.sleep(0.25)
        return False, best or "Логи приложения недоступны или не содержат актуальное время"

    def _wait_for_http_service(self, runtime, container, internal_port, path, kind, timeout):
        if container is None:
            return False, f"Контейнер {kind} не найден"
        ports = runtime.published_ports(container, internal_port)
        if not ports:
            return False, f"Порт {internal_port} контейнера {kind} не опубликован на хост"
        url = f"http://127.0.0.1:{ports[0]}{path}"
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                response = self.session.get(url, timeout=0.8)
                if response.status_code == 200:
                    if kind == "grafana":
                        try:
                            payload = response.json()
                        except ValueError:
                            payload = {}
                        if not isinstance(payload, dict) or not payload:
                            last_error = "Grafana вернула не JSON"
                            time.sleep(0.25)
                            continue
                    return True, f"{url} вернул HTTP 200"
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(0.25)
        return False, f"{url} не готов: {last_error}"
