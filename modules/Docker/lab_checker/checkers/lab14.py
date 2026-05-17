import os
import time
import re
from modules.Docker.lab_checker.core import LabChecker

class Lab14Checker:
    def __init__(self, checker: LabChecker):
        self.checker = checker

    def check(self) -> bool:
        """Проверка лабораторной работы №14: Оптимизация образов и компиляция C-кода."""
        if not self.checker.silent_mode:
            print("\n=== Проверка лабораторной работы №14 ===")

        # 1. Проверка наличия .dockerignore
        dockerignore_path = os.path.join(self.checker.project_dir, '.dockerignore')
        if os.path.exists(dockerignore_path):
            self.checker.add_result("Использование .dockerignore", True, "Файл .dockerignore найден")
        else:
            self.checker.add_result("Использование .dockerignore", False, "Файл .dockerignore не найден. Рекомендуется для уменьшения контекста сборки.")

        # 2. Создаем реальный hello.c в папке студента (чтобы Dockerfile мог его скопировать)
        hello_c_path = os.path.join(self.checker.project_dir, 'hello.c')
        with open(hello_c_path, 'w', encoding='utf-8') as f:
            f.write('''#include "stdio.h"
int main () {
    #if defined(_WIN32)
        printf("hello, windows\\n");
    #elif defined(__linux__)
        printf("hello, linux\\n");
    #elif defined(__APPLE__)
        printf("hello, Apple\\n");
    #elif defined(BSD)
        printf("hello, BSD\\n"); 
    #endif
    return 0;
}''')
        self.checker.log("Создан тестовый файл hello.c на хост-машине", "INFO")

        # 3. Определяем способ запуска (compose или обычный Dockerfile)
        compose_files = ['docker-compose.yml', 'docker-compose.yaml']
        has_compose = any(os.path.exists(os.path.join(self.checker.project_dir, f)) for f in compose_files)

        image_name = "lab14_test_image"
        container = None
        images_to_check = []

        if has_compose:
            self.checker.log("Обнаружен docker-compose, запускаем сборку...")
            code, stdout, stderr = self.checker.run_subprocess(["docker-compose", "up", "--build", "-d"])
            if code != 0:
                self.checker.add_result("Сборка и запуск (Compose)", False, f"Ошибка: {stderr}")
                return False
            self.checker.add_result("Сборка и запуск (Compose)", True, "Успешно собрано")
            time.sleep(5) # Даем время на компиляцию
            
            # Ищем образы этого compose-проекта
            project_name = os.path.basename(os.path.abspath(self.checker.project_dir)).lower()
            project_name = re.sub(r'[^a-z0-9]', '', project_name)
            images_to_check = self.checker.client.images.list(filters={"label": f"com.docker.compose.project={project_name}"})
            
        else:
            self.checker.log("docker-compose не найден, собираем образ напрямую из Dockerfile...")
            code, stdout, stderr = self.checker.run_subprocess(["docker", "build", "-t", image_name, "."])
            if code != 0:
                self.checker.add_result("Сборка образа", False, f"Ошибка компиляции/сборки: {stderr}")
                return False
            self.checker.add_result("Сборка образа", True, "Образ успешно собран")
            
            try:
                images_to_check = [self.checker.client.images.get(image_name)]
            except:
                pass
            
            # Запускаем контейнер с монтированием директории, чтобы получить out.txt на хост
            try:
                container = self.checker.client.containers.run(
                    image_name, 
                    detach=True,
                    # Пробрасываем текущую директорию внутрь, чтобы скрипт студента мог записать туда out.txt
                    volumes={self.checker.project_dir: {'bind': '/app', 'mode': 'rw'}},
                    working_dir='/app'
                )
                container.wait(timeout=10)
            except Exception as e:
                self.checker.log(f"Контейнер завершился или не запустился штатно: {e}", "DEBUG")

        # 4. Проверка Задания 1: Оптимизация размера образов
        if images_to_check:
            for img in images_to_check:
                size_mb = img.attrs['Size'] / (1024 * 1024)
                tags = img.tags[0] if img.tags else "Unknown"
                
                # ИСПОЛЬЗУЕМ КОНФИГ
                max_allowed = self.checker.config.image_analysis.max_size_mb or 50
                
                if size_mb < max_allowed:
                    self.checker.add_result("Оптимизация размера", True, f"Размер ({tags}): {size_mb:.1f} МБ")
                else:
                    self.checker.add_result("Оптимизация размера", False, f"Образ слишком большой: {size_mb:.1f} МБ")
        # 5. Проверка Задания 2: Передача артефакта
        out_txt_path = os.path.join(self.checker.project_dir, 'out.txt')
        file_content = None

        # Сценарий А (Студент сделал умный Volume, файл появился на хосте)
        if os.path.exists(out_txt_path):
            self.checker.add_result("Локация артефакта", True, "Файл out.txt успешно передан на хост-машину (через Volume)")
            with open(out_txt_path, 'r', encoding='utf-8') as f:
                file_content = f.read().lower()

        # Сценарий Б (Студент выбрал Вариант 2 из методички - docker cp)
        elif container:
            self.checker.log("Файл на хосте не найден, ищем out.txt внутри контейнера (Вариант 2)...", "DEBUG")
            try:
                # Пытаемся прочитать файл прямо из файловой системы остановленного контейнера
                exit_code, output = container.exec_run("cat out.txt")
                if exit_code == 0:
                    self.checker.add_result("Локация артефакта", True, "Файл out.txt найден внутри контейнера. Доступен для 'docker cp' (Вариант 2)")
                    file_content = output.decode('utf-8').lower()
                else:
                    self.checker.add_result("Локация артефакта", False, "Файл out.txt не найден ни на хосте, ни внутри контейнера")
            except Exception as e:
                self.checker.add_result("Локация артефакта", False, f"Ошибка поиска файла в контейнере: {e}")

        # Финальная проверка содержимого (для обоих сценариев)
        if file_content:
            if 'hello' in file_content:
                self.checker.add_result("Компиляция C-кода", True, f"Код успешно скомпилирован! Содержимое: {file_content.strip()}")
            else:
                self.checker.add_result("Компиляция C-кода", False, f"Файл out.txt содержит неверный текст: {file_content}")

        # --- ВАЖНО: УБОРКА ЗА СОБОЙ ---
        for temp_file in [hello_c_path, out_txt_path]:
            if os.path.exists(temp_file):
                os.remove(temp_file)

        return True