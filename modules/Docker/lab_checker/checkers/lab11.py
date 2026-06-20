import json
import os
import re
import statistics
import time
import uuid
from datetime import datetime, timezone

from modules.Docker.lab_checker.core import LabChecker


class Lab11Checker:
    ARCHITECTURES = {
        "x86": ({"i386", "i486", "i586", "i686"}, 10),
        "x64": ({"x86_64", "amd64"}, 7),
        "arm": ({"armv7l", "arm64", "aarch64"}, 3),
    }

    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.image_tag = f"lab11-check-{uuid.uuid4().hex[:12]}"

    def check(self) -> bool:
        """Проверяет Dockerfile и три сценария выполнения параллельно."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №11 ===")

        dockerfile_path = os.path.join(self.checker.project_dir, "Dockerfile")
        if not os.path.isfile(dockerfile_path):
            self.checker.add_result("Наличие Dockerfile", False, "Dockerfile не найден в корне проекта")
            return False
        self.checker.add_result("Наличие Dockerfile", True, "Dockerfile найден")

        try:
            with open(dockerfile_path, "r", encoding="utf-8") as stream:
                dockerfile = stream.read()
        except OSError as exc:
            self.checker.add_result("Чтение Dockerfile", False, str(exc))
            return False

        self._check_dockerfile(dockerfile)
        image = None
        containers = {}
        try:
            try:
                image, _ = self.checker.client.images.build(
                    path=self.checker.project_dir,
                    dockerfile="Dockerfile",
                    tag=self.image_tag,
                    rm=True,
                )
                self.checker.add_result("Сборка образа", True, "Образ успешно собран")
            except Exception as exc:
                self.checker.add_result("Сборка образа", False, f"Сборка завершилась с ошибкой: {exc}")
                return False

            self._check_main_py(image)
            image_cmd = image.attrs.get("Config", {}).get("Cmd") or []
            expected_cmd = ["python3", "-u", "main.py"]
            self.checker.add_result(
                "Итоговая команда образа",
                image_cmd == expected_cmd,
                f"CMD итогового образа: {image_cmd!r}" if image_cmd != expected_cmd else "CMD соответствует заданию",
            )

            # Сценарии запускаются одновременно: долгий штатный интервал не складывается
            # со скрытыми тестами TIME_SLEEP=1 и TIME_SLEEP=2.
            containers["default"] = self.checker.client.containers.run(image.id, detach=True)
            containers["sleep_1"] = self.checker.client.containers.run(
                image.id, detach=True, environment={"TIME_SLEEP": "1"}
            )
            containers["sleep_2"] = self.checker.client.containers.run(
                image.id, detach=True, environment={"TIME_SLEEP": "2"}
            )

            architecture = self._container_architecture(containers["default"])
            category, expected_delay = self._normalize_architecture(architecture)
            logs = self._collect_logs(containers, expected_delay)

            self._check_running_and_errors(containers, logs)
            self._check_architecture(logs["default"], architecture, category)
            self._check_current_time(logs["default"])
            self._check_interval("Интервал по архитектуре", logs["default"], expected_delay, tolerance=0.25, minimum=2)
            self._check_interval("TIME_SLEEP=1", logs["sleep_1"], 1, tolerance=0.45, minimum=3)
            self._check_interval("TIME_SLEEP=2", logs["sleep_2"], 2, tolerance=0.40, minimum=3)

            unix_found = any(re.search(r"(?<!\d)1\d{9}(?:\.\d+)?(?!\d)", line) for line in logs["default"])
            message = (
                "Unix timestamp обнаружен и проверен вместе с текущим временем"
                if unix_found
                else "Интерфейс включения Unix timestamp в задании не задан; отсутствие не снижает результат"
            )
            self.checker.add_result("Unix timestamp (информационно)", True, message)
            return True
        except Exception as exc:
            self.checker.add_result("Выполнение контейнеров", False, f"Ошибка проверки: {exc}")
            return False
        finally:
            for container in containers.values():
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            if image is not None:
                try:
                    self.checker.client.images.remove(image.id, force=True)
                except Exception:
                    pass

    def _check_dockerfile(self, content: str):
        from_ok = bool(re.search(
            r"^\s*FROM(?:\s+--platform=\S+)?\s+python:3\.8-slim-buster(?:\s+AS\s+\S+)?\s*$",
            content, re.I | re.M,
        ))
        self.checker.add_result(
            "Базовый образ", from_ok,
            "Используется python:3.8-slim-buster" if from_ok else "Требуется FROM python:3.8-slim-buster",
        )

        commands = re.findall(r"^\s*CMD\s+(.+?)\s*$", content, re.I | re.M)
        parsed = None
        if commands:
            try:
                parsed = json.loads(commands[-1])
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
        cmd_ok = parsed == ["python3", "-u", "main.py"]
        self.checker.add_result(
            "CMD Dockerfile", cmd_ok,
            "Найден CMD [\"python3\", \"-u\", \"main.py\"]"
            if cmd_ok else "Последний CMD должен точно запускать python3 -u main.py",
        )

    def _check_main_py(self, image):
        probe = None
        found = False
        working_dir = image.attrs.get("Config", {}).get("WorkingDir") or "/"
        path = working_dir.rstrip("/") + "/main.py"
        try:
            probe = self.checker.client.containers.create(image.id, command=["true"])
            probe.get_archive(path)
            found = True
        except Exception:
            found = False
        finally:
            if probe is not None:
                try:
                    probe.remove(force=True)
                except Exception:
                    pass
        self.checker.add_result(
            "Файл main.py в образе", found,
            f"Файл найден: {path}" if found else f"Файл не найден в рабочем каталоге образа: {path}",
        )

    def _container_architecture(self, container):
        try:
            exit_code, output = container.exec_run(["uname", "-m"])
            if exit_code == 0:
                return output.decode("utf-8", errors="replace").strip().lower()
        except Exception:
            pass
        return "unknown"

    def _normalize_architecture(self, architecture):
        for category, (aliases, delay) in self.ARCHITECTURES.items():
            if architecture in aliases:
                return category, delay
        return "unknown", 7

    def _collect_logs(self, containers, expected_delay):
        logs = {name: [] for name in containers}
        start = time.monotonic()
        deadline = start + expected_delay + 4
        extended = False
        while time.monotonic() < deadline:
            for name, container in containers.items():
                try:
                    raw = container.logs().decode("utf-8", errors="replace")
                    logs[name] = [line.strip() for line in raw.splitlines() if line.strip()]
                except Exception:
                    continue

            fast_ready = all(len(self._time_values(logs[name])) >= 3 for name in ("sleep_1", "sleep_2"))
            default_ready = len(self._time_values(logs["default"])) >= 2
            if fast_ready and default_ready:
                break

            # Корректные программы иногда сначала sleep, затем print. Дополнительное
            # ожидание включается только для такого случая, а не для каждой работы.
            if time.monotonic() >= deadline - 0.3 and not extended:
                if len(self._time_values(logs["default"])) == 1:
                    deadline += expected_delay + 1
                    extended = True
            time.sleep(0.2)
        return logs

    def _check_running_and_errors(self, containers, logs):
        for container in containers.values():
            try:
                container.reload()
            except Exception:
                pass
        running = all(container.status == "running" for container in containers.values())
        enough_logs = len(logs["sleep_1"]) >= 3 and len(logs["sleep_2"]) >= 3
        traceback = any("traceback" in line.casefold() for values in logs.values() for line in values)
        self.checker.add_result(
            "Непрерывная работа", running and enough_logs and not traceback,
            "Контейнеры работают, получено не менее трёх сообщений, Traceback отсутствует"
            if running and enough_logs and not traceback
            else "Контейнер завершился, вывел слишком мало сообщений или содержит Traceback",
        )

    def _check_architecture(self, logs, architecture, category):
        joined = " ".join(logs).casefold()
        aliases = self.ARCHITECTURES.get(category, (set(), 0))[0]
        tokens = set(aliases) | ({category} if category != "unknown" else set())
        found = any(re.search(rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])", joined) for token in tokens)
        self.checker.add_result(
            "Определение архитектуры", found,
            f"uname -m={architecture}; программа вывела категорию {category}"
            if found else f"uname -m={architecture}; соответствующее сообщение не найдено",
        )

    def _check_current_time(self, logs):
        values = self._time_values(logs)
        increasing = len(values) >= 2 and all(b > a for a, b in zip(values, values[1:]))
        self.checker.add_result(
            "Актуальное время", increasing,
            "Время распознано, актуально и возрастает" if increasing
            else "Не найдено как минимум двух актуальных возрастающих значений времени",
        )

    def _check_interval(self, name, logs, expected, tolerance, minimum):
        values = self._time_values(logs)
        deltas = [b - a for a, b in zip(values, values[1:]) if 0 < b - a < 60]
        actual = statistics.median(deltas) if deltas else None
        low, high = expected * (1 - tolerance), expected * (1 + tolerance)
        passed = len(values) >= minimum and actual is not None and low <= actual <= high
        message = (
            f"Медианный интервал {actual:.2f} с (ожидалось около {expected} с)"
            if actual is not None else "Недостаточно значений времени для измерения интервала"
        )
        self.checker.add_result(name, passed, message)

    def _time_values(self, logs):
        values = []
        now = time.time()
        for line in logs:
            value = self._parse_time(line, now)
            if value is not None and (not values or value != values[-1]):
                if values and value < values[-1] - 12 * 3600:  # переход через полночь для HH:MM:SS
                    value += 24 * 3600
                values.append(value)
        return values

    @staticmethod
    def _parse_time(line, now):
        unix = re.search(r"(?<!\d)(1\d{9}(?:\.\d+)?)(?!\d)", line)
        if unix:
            value = float(unix.group(1))
            if abs(value - now) <= 30:
                return value

        date_match = re.search(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
            line,
        )
        if date_match:
            raw = date_match.group(0).replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(raw)
                candidates = []
                if parsed.tzinfo is not None:
                    candidates.append(parsed.timestamp())
                else:
                    candidates.extend((parsed.timestamp(), parsed.replace(tzinfo=timezone.utc).timestamp()))
                value = min(candidates, key=lambda candidate: abs(candidate - now))
                if abs(value - now) <= 30:
                    return value
            except ValueError:
                pass

        clock = re.search(r"(?<!\d)([01]\d|2[0-3]):([0-5]\d):([0-5]\d)(?!\d)", line)
        if clock:
            seconds = int(clock.group(1)) * 3600 + int(clock.group(2)) * 60 + int(clock.group(3))
            local_now = datetime.fromtimestamp(now)
            utc_now = datetime.fromtimestamp(now, timezone.utc)
            candidates = []
            for current in (local_now, utc_now):
                current_seconds = current.hour * 3600 + current.minute * 60 + current.second
                candidates.append(now + (seconds - current_seconds))
            value = min(candidates, key=lambda candidate: abs(candidate - now))
            if abs(value - now) <= 30:
                return value
        return None
