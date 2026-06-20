import io
import os
import re
import shutil
import tarfile
import tempfile
import time
import uuid

import yaml

from modules.Docker.lab_checker.checkers.lab10 import Lab10Checker
from modules.Docker.lab_checker.checkers.lab11 import Lab11Checker
from modules.Docker.lab_checker.core import LabChecker


class Lab14Checker:
    HIDDEN_TOKEN = "hidden-token-48271"

    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.images = []
        self.containers = []

    def check(self) -> bool:
        """Проверяет оптимизацию и реальную компиляцию, не изменяя архив студента."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №14 ===")

        dockerfile = os.path.join(self.checker.project_dir, "Dockerfile")
        hello_c = os.path.join(self.checker.project_dir, "hello.c")
        if not os.path.isfile(dockerfile):
            self.checker.add_result("Наличие Dockerfile", False, "Dockerfile не найден")
            return False
        self.checker.add_result("Наличие Dockerfile", True, "Dockerfile найден")

        dockerignore = os.path.isfile(os.path.join(self.checker.project_dir, ".dockerignore"))
        self.checker.add_result(
            ".dockerignore (рекомендация)", True,
            "Файл .dockerignore используется"
            if dockerignore else "Файл отсутствует; это рекомендация, а не обязательный способ оптимизации",
        )

        try:
            optimization_ok = self._check_optimization_if_comparable()
            if not os.path.isfile(hello_c):
                self.checker.add_result("Наличие hello.c", False, "hello.c не найден в плоском архиве")
                return False
            self.checker.add_result("Наличие hello.c", True, "hello.c найден")

            with tempfile.TemporaryDirectory(prefix="lab14-check-") as temp_root:
                context = os.path.join(temp_root, "submission")
                self._copy_submission(context)
                canonical_source = os.path.join(context, "hello.c")
                self._remove_outputs(context)

                canonical_image = self._build(context, "canonical")
                if canonical_image is None:
                    return False
                canonical = self._run_and_collect(canonical_image, context, temp_root, "canonical")
                canonical_ok = canonical["exit_code"] == 0 and canonical["content"] == "hello, linux"
                self.checker.add_result(
                    "Каноническая компиляция", canonical_ok,
                    self._run_message(canonical, "hello, linux"),
                )

                with open(canonical_source, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(
                        "#include <stdio.h>\n"
                        "int main(void) {\n"
                        f'    printf("{self.HIDDEN_TOKEN}\\n");\n'
                        "    return 0;\n"
                        "}\n"
                    )
                self._remove_outputs(context)

                hidden_image = self._build(context, "hidden")
                if hidden_image is None:
                    return False
                hidden = self._run_and_collect(hidden_image, context, temp_root, "hidden")
                hidden_ok = hidden["exit_code"] == 0 and hidden["content"] == self.HIDDEN_TOKEN
                self.checker.add_result(
                    "Скрытый тест компиляции", hidden_ok,
                    self._run_message(hidden, self.HIDDEN_TOKEN),
                )
                self.checker.add_result(
                    "Передача out.txt на хост", bool(hidden.get("host_artifact")) and hidden_ok,
                    hidden.get("location") or "Новый out.txt не получен через bind mount или Docker API",
                )
                self.checker.add_result(
                    "Завершение контейнера", hidden["exit_code"] == 0 and not hidden["running"],
                    f"exit code={hidden['exit_code']}; running={hidden['running']}",
                )
                return optimization_ok and canonical_ok and hidden_ok
        finally:
            for container in self.containers:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            for image in self.images:
                try:
                    self.checker.client.images.remove(image.id, force=True)
                except Exception:
                    pass

    def _copy_submission(self, destination):
        ignored = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".idea")
        shutil.copytree(self.checker.project_dir, destination, ignore=ignored)

    @staticmethod
    def _remove_outputs(context):
        for current, _, files in os.walk(context):
            for name in files:
                if name.casefold() == "out.txt":
                    os.remove(os.path.join(current, name))

    def _build(self, context, suffix):
        tag = f"lab14-{suffix}-{uuid.uuid4().hex[:10]}"
        try:
            image, _ = self.checker.client.images.build(
                path=context,
                dockerfile="Dockerfile",
                tag=tag,
                rm=True,
            )
            self.images.append(image)
            self.checker.add_result(
                f"Сборка образа ({suffix})", True,
                f"Образ собран, размер {image.attrs.get('Size', 0) / (1024 * 1024):.1f} МБ",
            )
            return image
        except Exception as exc:
            self.checker.add_result(f"Сборка образа ({suffix})", False, f"Ошибка сборки: {exc}")
            return None

    def _run_and_collect(self, image, context, temp_root, suffix):
        output_dir = os.path.join(temp_root, f"output-{suffix}")
        os.makedirs(output_dir, exist_ok=True)
        result = {
            "exit_code": None,
            "running": False,
            "content": None,
            "host_artifact": False,
            "location": "",
        }
        container = None
        try:
            container = self.checker.client.containers.create(
                image.id,
                volumes={output_dir: {"bind": "/output", "mode": "rw"}},
            )
            self.containers.append(container)
            container.start()
            try:
                wait_result = container.wait(timeout=15)
                result["exit_code"] = wait_result.get("StatusCode")
            except Exception:
                container.reload()
                if container.status == "running":
                    container.stop(timeout=2)
                    result["running"] = True
                    result["location"] = "Контейнер не завершился самостоятельно за 15 секунд"
                    return result

            container.reload()
            result["running"] = container.status == "running"
            content, location, host_artifact = self._find_output(
                container, image, output_dir, context
            )
            result.update(content=content, location=location, host_artifact=host_artifact)
            return result
        except Exception as exc:
            result["location"] = f"Ошибка запуска: {exc}"
            return result

    def _find_output(self, container, image, output_dir, context):
        host_candidates = []
        for root in (output_dir, context):
            for current, _, files in os.walk(root):
                if "out.txt" in files:
                    host_candidates.append(os.path.join(current, "out.txt"))
        for path in host_candidates:
            try:
                with open(path, "r", encoding="utf-8") as stream:
                    content = self._normalize(stream.read())
                return content, f"Новый файл получен на хосте: {path}", True
            except OSError:
                continue

        working_dir = image.attrs.get("Config", {}).get("WorkingDir") or "/"
        candidates = {
            "/out.txt", "/app/out.txt", "/output/out.txt", "/src/out.txt",
            working_dir.rstrip("/") + "/out.txt",
        }
        dockerfile_path = os.path.join(context, "Dockerfile")
        try:
            with open(dockerfile_path, "r", encoding="utf-8") as stream:
                dockerfile = stream.read()
            for token in re.findall(r"(?:^|[\s\"'])(/?[A-Za-z0-9_./${}-]*out\.txt)", dockerfile, re.I):
                if token.startswith("/"):
                    candidates.add(token)
                else:
                    candidates.add(working_dir.rstrip("/") + "/" + token)
        except OSError:
            pass

        for path in candidates:
            try:
                stream, _ = container.get_archive(path)
                archive = io.BytesIO(b"".join(stream))
                with tarfile.open(fileobj=archive, mode="r:*") as tar:
                    member = next((item for item in tar.getmembers() if item.isfile()), None)
                    if member is None:
                        continue
                    extracted = tar.extractfile(member)
                    if extracted is None:
                        continue
                    content = self._normalize(extracted.read().decode("utf-8", errors="replace"))
                return content, f"out.txt извлечён на хост через Docker API из {path}", True
            except Exception:
                continue
        return None, "out.txt не найден после запуска контейнера", False

    def _check_optimization_if_comparable(self):
        original = os.path.join(self.checker.project_dir, "original")
        optimized = os.path.join(self.checker.project_dir, "optimized")
        comparable = all(os.path.isfile(os.path.join(path, "Dockerfile")) for path in (original, optimized))
        if not comparable:
            self.checker.log(
                "Архив имеет принятый плоский формат: уменьшение относительно исходного образа "
                "невозможно доказать автоматически; статические приёмы выводятся как рекомендации.",
                "WARNING",
            )
            self._optimization_diagnostics(os.path.join(self.checker.project_dir, "Dockerfile"))
            return True

        original_image = self._build(original, "original")
        optimized_image = self._build(optimized, "optimized")
        if original_image is None or optimized_image is None:
            self.checker.add_result("Сравнение размеров", False, "Один из сравниваемых образов не собрался")
            return False
        original_size = original_image.attrs.get("Size", 0)
        optimized_size = optimized_image.attrs.get("Size", 0)
        reduction = ((original_size - optimized_size) / original_size * 100) if original_size else 0
        passed = optimized_size < original_size
        self.checker.add_result(
            "Оптимизированный образ меньше", passed,
            f"Исходный: {original_size / 1048576:.1f} МБ; оптимизированный: "
            f"{optimized_size / 1048576:.1f} МБ; уменьшение: {reduction:.1f}%",
        )
        self._optimization_diagnostics(os.path.join(optimized, "Dockerfile"))
        lab_number = self._optimized_lab_number()
        original_functional = self._probe_previous_lab(original_image, lab_number)
        optimized_functional = self._probe_previous_lab(optimized_image, lab_number)
        function_ok = bool(original_functional and optimized_functional)
        self.checker.add_result(
            "Функциональная эквивалентность образов", function_ok,
            f"Адаптер lab{lab_number}: original={original_functional}, optimized={optimized_functional}"
            if lab_number else "В submission.yaml не указан optimized_lab",
        )
        return passed and function_ok

    def _optimized_lab_number(self):
        manifest_path = os.path.join(self.checker.project_dir, "submission.yaml")
        try:
            with open(manifest_path, "r", encoding="utf-8") as stream:
                manifest = yaml.safe_load(stream) or {}
            value = str(manifest.get("optimized_lab", "")).casefold().replace("lab", "").strip()
            return int(value) if value.isdigit() else None
        except (OSError, yaml.YAMLError):
            return None

    def _probe_previous_lab(self, image, lab_number):
        if lab_number == 10:
            container = None
            helper = Lab10Checker(self.checker)
            try:
                container = self.checker.client.containers.run(
                    image.id,
                    detach=True,
                    ports={f"{port}/tcp": None for port in helper.COMMON_PORTS},
                )
                self.containers.append(container)
                endpoints = helper._published_endpoints([container])
                response, _ = helper._wait_for_valid_response([container], endpoints, timeout=8)
                return response is not None and len(helper._find_temperatures(response)) == 2
            except Exception:
                return False
            finally:
                helper.session.close()
        if lab_number == 11:
            container = None
            parser = Lab11Checker(self.checker)
            try:
                container = self.checker.client.containers.run(
                    image.id, detach=True, environment={"TIME_SLEEP": "1"}
                )
                self.containers.append(container)
                deadline = time.monotonic() + 5
                lines = []
                while time.monotonic() < deadline:
                    text = container.logs().decode("utf-8", errors="replace")
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    if len(parser._time_values(lines)) >= 3:
                        container.reload()
                        return container.status == "running" and not any(
                            "traceback" in line.casefold() for line in lines
                        )
                    time.sleep(0.2)
                return False
            except Exception:
                return False
        # Для Compose-лабораторных единичный image недостаточен: нужен manifest
        # с сервисом сравнения. Не выдаём фиктивный положительный результат.
        return False

    def _optimization_diagnostics(self, dockerfile_path):
        try:
            with open(dockerfile_path, "r", encoding="utf-8") as stream:
                content = stream.read().casefold()
        except OSError:
            return
        observations = []
        if len(re.findall(r"^\s*from\s+", content, re.M)) > 1:
            observations.append("multi-stage")
        if "--no-cache-dir" in content:
            observations.append("pip без кэша")
        if "/var/lib/apt/lists" in content:
            observations.append("очистка apt")
        if "slim" in content or "alpine" in content:
            observations.append("компактный базовый образ")
        self.checker.log(
            "Приёмы оптимизации: " + (", ".join(observations) if observations else "явные приёмы не распознаны"),
            "INFO",
        )

    @staticmethod
    def _normalize(content):
        return content.replace("\r\n", "\n").strip().casefold()

    @staticmethod
    def _run_message(result, expected):
        return (
            f"Получено {result['content']!r}, ожидалось {expected!r}; "
            f"exit code={result['exit_code']}; {result['location']}"
        )
