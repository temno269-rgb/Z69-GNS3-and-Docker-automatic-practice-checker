import ipaddress
import re
import time
from urllib.parse import urlparse

import requests
import yaml

from modules.Docker.lab_checker.checkers.compose_runtime import ComposeRuntime
from modules.Docker.lab_checker.core import LabChecker


class Lab13Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.session = requests.Session()

    def check(self) -> bool:
        """Проверяет топологию и реальный путь MongoDB -> exporter -> Prometheus -> Grafana."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №13 ===")

        runtime = ComposeRuntime(self.checker, "lab13")
        if not runtime.file_name:
            self.checker.add_result(
                "Наличие Compose-файла", False,
                "Ожидался compose.yaml/.yml или docker-compose.yaml/.yml",
            )
            return False
        self.checker.add_result("Наличие Compose-файла", True, f"Найден {runtime.file_name}")
        if not runtime.command:
            self.checker.add_result("Docker Compose", False, "Docker Compose не установлен")
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
        missing = [role for role in ("mongodb", "exporter", "prometheus", "grafana") if role not in roles]
        self.checker.add_result(
            "Состав сервисов", not missing,
            "Найдены MongoDB, MongoDB exporter, Prometheus и Grafana"
            if not missing else "Не найдены компоненты: " + ", ".join(missing),
        )

        topology_ok, topology_message = self._check_topology(compose, services, roles)
        self.checker.add_result("Топология двух сетей", topology_ok, topology_message)

        serialized = yaml.safe_dump(compose, allow_unicode=True)
        hardcoded_ip = re.search(r"(?<!\d)(?:172\.(?:\d{1,3}\.){2}\d{1,3})(?!\d)", serialized)
        self.checker.add_result(
            "Docker DNS вместо IP", hardcoded_ip is None,
            "Статические IP контейнеров не используются"
            if hardcoded_ip is None else f"Найден нестабильный адрес: {hardcoded_ip.group(0)}",
        )

        container_ids = []
        try:
            started, output = runtime.up(build=True)
            self.checker.add_result(
                "Запуск инфраструктуры", started,
                "Compose-проект запущен" if started else output,
            )
            if not started:
                return False

            containers = runtime.wait_for_containers(len(services), timeout=15)
            container_ids = [container.id for container in containers]
            by_service = {runtime.service_name(container): container for container in containers}
            stable, status_message = self._stable(containers, len(services))
            self.checker.add_result("Стабильность контейнеров", stable, status_message)

            prometheus = by_service.get(roles.get("prometheus", ""))
            prom_url = self._service_url(runtime, prometheus, 9090)
            target_ok, target, target_message = self._wait_for_exporter_target(
                prom_url, roles.get("exporter", ""), timeout=18
            )
            self.checker.add_result("Prometheus собирает exporter", target_ok, target_message)

            dns_ok, dns_message = self._check_target_dns(target, roles.get("exporter", ""))
            self.checker.add_result("Service discovery через Docker DNS", dns_ok, dns_message)

            metric_ok, metric_message = self._check_mongodb_metric(prom_url)
            self.checker.add_result("Метрики MongoDB", metric_ok, metric_message)
            self.checker.add_result(
                "Exporter подключён к MongoDB", target_ok and metric_ok,
                "Exporter отдаёт MongoDB-метрики без ошибки scrape"
                if target_ok and metric_ok else "Запущенного контейнера exporter недостаточно: MongoDB-метрики не подтверждены",
            )

            grafana = by_service.get(roles.get("grafana", ""))
            grafana_ok, grafana_message = self._check_grafana(
                runtime, grafana, services.get(roles.get("grafana", ""), {}), roles.get("prometheus", "")
            )
            self.checker.add_result("Grafana подключена к Prometheus", grafana_ok, grafana_message)
            return all((not missing, topology_ok, stable, target_ok, dns_ok, metric_ok, grafana_ok))
        finally:
            self.session.close()
            if runtime.started:
                stopped, message = runtime.down()
                removed = stopped and runtime.project_resources_removed(container_ids)
                self.checker.add_result(
                    "Остановка Compose-проекта", removed,
                    "Контейнеры и сети проекта удалены"
                    if removed else message or "После compose down остались ресурсы",
                )

    @staticmethod
    def _find_roles(services):
        roles = {}
        for name, config in services.items():
            fingerprint = f"{name} {config.get('image', '')}".casefold().replace("_", "-")
            if "exporter" in fingerprint and ("mongo" in fingerprint or "percona" in fingerprint):
                roles.setdefault("exporter", name)
            elif "mongo" in fingerprint:
                roles.setdefault("mongodb", name)
            if "prometheus" in fingerprint and "exporter" not in fingerprint:
                roles.setdefault("prometheus", name)
            if "grafana" in fingerprint:
                roles.setdefault("grafana", name)
        return roles

    @staticmethod
    def _network_names(config):
        networks = config.get("networks", {}) or {}
        return set(networks if isinstance(networks, dict) else networks)

    def _check_topology(self, compose, services, roles):
        declared = set((compose.get("networks", {}) or {}).keys())
        db_network = next((name for name in declared if name.casefold() == "mongodb"), None)
        metrics_network = next((name for name in declared if name.casefold() == "prometheus"), None)
        if not db_network or not metrics_network:
            return False, f"Требуются логические сети mongodb и prometheus; найдены: {sorted(declared)}"
        if any(role not in roles for role in ("mongodb", "exporter", "prometheus", "grafana")):
            return False, "Нельзя проверить распределение: не распознаны все четыре сервиса"

        mongo_nets = self._network_names(services[roles["mongodb"]])
        exporter_nets = self._network_names(services[roles["exporter"]])
        prometheus_nets = self._network_names(services[roles["prometheus"]])
        grafana_nets = self._network_names(services[roles["grafana"]])
        valid = (
            db_network in mongo_nets
            and {db_network, metrics_network}.issubset(exporter_nets)
            and metrics_network in prometheus_nets
            and metrics_network in grafana_nets
        )
        return valid, (
            f"MongoDB={sorted(mongo_nets)}, exporter={sorted(exporter_nets)}, "
            f"Prometheus={sorted(prometheus_nets)}, Grafana={sorted(grafana_nets)}"
        )

    @staticmethod
    def _stable(containers, expected_count):
        statuses = []
        fatal = False
        for container in containers:
            try:
                container.reload()
                logs = container.logs(tail=80).decode("utf-8", errors="replace").casefold()
            except Exception:
                logs = ""
            state = container.attrs.get("State", {})
            status = "restarting" if state.get("Restarting") else container.status
            statuses.append(f"{ComposeRuntime.service_name(container) or container.short_id}={status}")
            fatal = fatal or "fatal error" in logs or "panic:" in logs
        ok = len(containers) >= expected_count and all(item.endswith("=running") for item in statuses) and not fatal
        return ok, ", ".join(statuses) or "Контейнеры проекта не найдены"

    @staticmethod
    def _service_url(runtime, container, internal_port):
        if container is None:
            return None
        ports = runtime.published_ports(container, internal_port)
        return f"http://127.0.0.1:{ports[0]}" if ports else None

    def _wait_for_exporter_target(self, prom_url, exporter_service, timeout):
        if not exporter_service:
            return False, None, "Сервис MongoDB exporter не распознан"
        if not prom_url:
            return False, None, "Порт Prometheus 9090 не опубликован на хост"
        url = prom_url + "/api/v1/targets"
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                response = self.session.get(url, timeout=0.9)
                if response.status_code == 200:
                    targets = response.json().get("data", {}).get("activeTargets", [])
                    for target in targets:
                        fingerprint = " ".join((
                            target.get("scrapeUrl", ""),
                            str(target.get("labels", {})),
                            str(target.get("discoveredLabels", {})),
                        )).casefold()
                        if exporter_service.casefold() in fingerprint or "mongo" in fingerprint:
                            if target.get("health") == "up" and not target.get("lastError"):
                                return True, target, f"Target {target.get('scrapeUrl')} имеет health=up"
                            last_error = target.get("lastError") or f"health={target.get('health')}"
                else:
                    last_error = f"HTTP {response.status_code}"
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.3)
        return False, None, f"MongoDB exporter не стал healthy: {last_error}"

    @staticmethod
    def _check_target_dns(target, exporter_service):
        if not target:
            return False, "Target exporter не найден"
        scrape_url = target.get("scrapeUrl", "")
        host = urlparse(scrape_url).hostname or ""
        try:
            ipaddress.ip_address(host)
            return False, f"Target использует статический IP: {host}"
        except ValueError:
            pass
        valid = bool(host) and (exporter_service.casefold() in host.casefold() or "mongo" in host.casefold())
        return valid, (
            f"Prometheus обращается по DNS-имени {host}"
            if valid else f"Адрес target не похож на имя exporter: {scrape_url}"
        )

    def _check_mongodb_metric(self, prom_url):
        if not prom_url:
            return False, "Prometheus API недоступен"
        try:
            response = self.session.get(prom_url + "/api/v1/label/__name__/values", timeout=2)
            payload = response.json()
            names = payload.get("data", []) if payload.get("status") == "success" else []
            candidates = [name for name in names if name.casefold().startswith(("mongodb_", "mongodb_mongod_"))]
            if not candidates:
                return False, "В Prometheus не найдены метрики с префиксом mongodb_"
            for metric in candidates[:20]:
                query = self.session.get(
                    prom_url + "/api/v1/query", params={"query": metric}, timeout=2
                ).json()
                result = query.get("data", {}).get("result", [])
                if query.get("status") == "success" and result:
                    return True, f"Запрос {metric} вернул {len(result)} временных рядов"
            return False, "MongoDB-метрики зарегистрированы, но запросы вернули пустой результат"
        except (requests.RequestException, ValueError) as exc:
            return False, f"Ошибка Prometheus API: {exc}"

    def _check_grafana(self, runtime, container, service_config, prometheus_service):
        grafana_url = self._service_url(runtime, container, 3000)
        if not grafana_url:
            return False, "Порт Grafana 3000 не опубликован на хост"
        environment = service_config.get("environment", {}) or {}
        if isinstance(environment, list):
            environment = dict(item.split("=", 1) for item in environment if "=" in item)
        user = environment.get("GF_SECURITY_ADMIN_USER", "admin")
        password = environment.get("GF_SECURITY_ADMIN_PASSWORD", "admin")
        auth = (str(user), str(password))

        deadline = time.monotonic() + 15
        last_error = ""
        while time.monotonic() < deadline:
            try:
                health = self.session.get(grafana_url + "/api/health", timeout=0.9)
                if health.status_code != 200:
                    last_error = f"health HTTP {health.status_code}"
                    time.sleep(0.3)
                    continue
                response = self.session.get(grafana_url + "/api/datasources", auth=auth, timeout=1.2)
                if response.status_code != 200:
                    last_error = f"datasources HTTP {response.status_code}"
                    time.sleep(0.3)
                    continue
                datasources = response.json()
                datasource = next(
                    (item for item in datasources if "prometheus" in str(item.get("type", "")).casefold()),
                    None,
                )
                if not datasource:
                    last_error = "datasource типа Prometheus отсутствует"
                    time.sleep(0.3)
                    continue
                ds_url = datasource.get("url", "")
                host = urlparse(ds_url).hostname or ""
                if host in ("localhost", "127.0.0.1", ""):
                    return False, f"Datasource использует неверный адрес {ds_url}"
                if prometheus_service and prometheus_service.casefold() not in host.casefold():
                    return False, f"Datasource URL не использует сервис {prometheus_service}: {ds_url}"

                uid = datasource.get("uid")
                if uid:
                    check = self.session.get(
                        f"{grafana_url}/api/datasources/uid/{uid}/health", auth=auth, timeout=2
                    )
                    if check.status_code != 200:
                        # Grafana 2021 года могла не иметь UID health endpoint.
                        # В таком случае выполняем настоящий запрос через datasource proxy.
                        datasource_id = datasource.get("id")
                        proxy = self.session.get(
                            f"{grafana_url}/api/datasources/proxy/{datasource_id}/api/v1/status/buildinfo",
                            auth=auth,
                            timeout=2,
                        ) if datasource_id is not None else check
                        if proxy.status_code != 200:
                            last_error = (
                                f"datasource health HTTP {check.status_code}, "
                                f"proxy HTTP {proxy.status_code}"
                            )
                            time.sleep(0.3)
                            continue
                return True, f"Prometheus datasource работает через внутренний URL {ds_url}"
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
            time.sleep(0.3)
        return False, f"Grafana datasource не готов: {last_error}"
