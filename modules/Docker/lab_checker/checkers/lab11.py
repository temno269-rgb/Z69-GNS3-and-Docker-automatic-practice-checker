import os
import re
import time
from modules.Docker.lab_checker.core import LabChecker

class Lab11Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker
        self.image_name = "lab11_student_image"

    def check(self) -> bool:
        """Проверка лабораторной работы №11: Сборка образов и ENV."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №11 ===")

        # 1. Поиск и статический анализ Dockerfile
        dockerfile_path = os.path.join(self.checker.project_dir, 'Dockerfile')
        if not os.path.exists(dockerfile_path):
            self.checker.add_result("Наличие Dockerfile", False, "Dockerfile не найден в корне проекта")
            return False
        self.checker.add_result("Наличие Dockerfile", True, "Dockerfile найден")

        with open(dockerfile_path, 'r', encoding='utf-8') as df:
            content = df.read().lower()
            
            # Проверка базового образа по ТЗ
            if 'python:3.8-slim-buster' not in content:
                self.checker.add_result("Базовый образ", False, "По заданию требуется использовать образ python:3.8-slim-buster")
            else:
                self.checker.add_result("Базовый образ", True, "Используется правильный базовый образ (python:3.8-slim-buster)")
            
            # Проверка флага небуферизованного вывода (иначе логи не появятся в реальном времени)
            if '-u' not in content and 'python3' in content:
                self.checker.add_result("Небуферизованный вывод", False, "В инструкции CMD не найден флаг '-u'. Логи могут отображаться с задержкой.")
            else:
                self.checker.add_result("Небуферизованный вывод", True, "Флаг '-u' присутствует в CMD")

        # 2. Сборка образа
        self.checker.log("Сборка образа из Dockerfile...")
        code, stdout, stderr = self.checker.run_subprocess(["docker", "build", "-t", self.image_name, "."])
        if code != 0:
            self.checker.add_result("Сборка образа", False, f"Сборка завершилась с ошибкой: {stderr}")
            return False
        self.checker.add_result("Сборка образа", True, "Образ успешно собран")

        # 3. ТЕСТ 1: Работа по умолчанию (Проверка архитектуры и таймстемпов)
        self.checker.log("Запуск контейнера (базовая логика)...")
        container1 = None
        try:
            container1 = self.checker.client.containers.run(self.image_name, detach=True)
            
            # Ждем 15 секунд (по ТЗ максимальный интервал для x86 - 10 секунд)
            time.sleep(15)
            
            logs = container1.logs().decode('utf-8').strip().split('\n')
            logs = [log for log in logs if log.strip()] # Убираем пустые строки
            
            if len(logs) == 0:
                self.checker.add_result("Вывод логов", False, "За 15 секунд работы контейнер не вывел ни одной строки в логи")
            else:
                self.checker.add_result("Вывод логов", True, f"Получено строк лога: {len(logs)}")

                # Ищем Unix Timestamp (10-значное число, начинающееся с 16, 17, 18, 19)
                has_timestamp = any(re.search(r'\b1[6-9]\d{8}\b', log) for log in logs)
                if has_timestamp:
                    self.checker.add_result("Unix timestamp", True, "В логах успешно обнаружен формат Unix timestamp")
                else:
                    self.checker.add_result("Unix timestamp", False, "Unix timestamp не найден (ожидалось 10-значное число)")

                # Ищем определение архитектуры
                arch_found = False
                for arch in ['x86', 'x64', 'arm']:
                    if any(arch in log.lower() for log in logs):
                        arch_found = True
                        self.checker.add_result("Определение архитектуры", True, f"Обнаружено сообщение об архитектуре: {arch}")
                        break
                if not arch_found:
                    self.checker.add_result("Определение архитектуры", False, "В логах не найдено упоминание архитектуры (x86, x64 или arm)")

        except Exception as e:
            self.checker.add_result("Базовая логика скрипта", False, f"Ошибка при выполнении: {str(e)}")
        finally:
            if container1:
                container1.remove(force=True)

        # 4. ТЕСТ 2: Переопределение через ENV TIME_SLEEP
        self.checker.log("Запуск контейнера с переопределенной переменной TIME_SLEEP=2...")
        container2 = None
        try:
            # Задаем маленькую задержку, чтобы быстро проверить
            container2 = self.checker.client.containers.run(self.image_name, detach=True, environment={"TIME_SLEEP": "2"})
            
            # Ждем 7 секунд. При интервале 2с должно быть напечатано 3-4 строки
            self.checker.config.lab11.sleep_time_variants
            
            logs2 = container2.logs().decode('utf-8').strip().split('\n')
            logs2 = [log for log in logs2 if log.strip()]
            
            if len(logs2) >= 3:
                self.checker.add_result("Переменная TIME_SLEEP", True, "Интервал успешно изменен через ENV TIME_SLEEP (зафиксировано быстрое появление логов)")
            else:
                self.checker.add_result("Переменная TIME_SLEEP", False, f"TIME_SLEEP проигнорирована или скрипт упал (получено строк: {len(logs2)}, ожидалось >= 3)")

        except Exception as e:
            self.checker.add_result("Тест TIME_SLEEP", False, f"Ошибка: {str(e)}")
        finally:
            if container2:
                container2.remove(force=True)
            
            # Убираем за собой собранный образ
            try:
                self.checker.client.images.remove(self.image_name, force=True)
            except:
                pass

        return True