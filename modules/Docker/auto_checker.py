import os
import sys
import argparse
import json
from pathlib import Path

# Настройка путей для корректного импорта модулей из корня Z69
# Это необходимо, так как скрипт запускается как отдельный процесс из main_ui.py
current_file = Path(__file__).resolve()
# project_root = Z69/
project_root = current_file.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Импортируем строго через пакет lab_checker
try:
    # РЕФАКТОРИНГ: Вместо импорта низкоуровневых компонентов, используем высокоуровневую функцию из api.py.
    # Это упрощает зависимости и централизует логику.
    # Теперь, если в api.py или его зависимостях (core, types) будет ошибка, она будет поймана и выведена как JSON.
    from modules.Docker.api import check_lab_dir, load_config
except ImportError as e:
    print(json.dumps({"error": f"Ошибка структуры проекта: {e}", "success": False}))
    sys.exit(1)
    
def main():
    parser = argparse.ArgumentParser(description="CLI для проверки лабораторных работ Docker")
    parser.add_argument("--lab", type=str, required=True, choices=["lab10", "lab11", "lab12", "lab13", "lab14"], help="Тип лабораторной (например, lab10)")
    parser.add_argument("--dir", type=str, required=True, help="Абсолютный путь к папке с проектом студента")
    parser.add_argument("--config", type=str, default=None, help="Путь к файлу конфигурации (config.yaml/json)")
    parser.add_argument("--output", type=str, default=None, help="Путь для сохранения JSON отчета (опционально)")
    parser.add_argument("--silent", action="store_true", help="Вернуть в stdout только JSON (для интеграции с другими приложениями)")

    args = parser.parse_args()

    # 1. Проверка существования директории
    if not os.path.isdir(args.dir):
        error_res = {"error": f"Указанная директория не найдена: {args.dir}", "success": False}
        print(json.dumps(error_res, ensure_ascii=False))
        sys.exit(1)

    # 2. Загрузка конфигурации
    try:
        if args.config and os.path.exists(args.config):
            config = load_config(args.config)
        else:
            # Если конфиг не передан, api.py создаст его сам
            config = None

    except Exception as e:
        error_res = {"error": f"Ошибка загрузки конфигурации: {str(e)}", "success": False}
        print(json.dumps(error_res, ensure_ascii=False))
        sys.exit(1)

    # 3. Запуск проверки через API
    try:
        result_json = check_lab_dir(
            project_dir=args.dir,
            lab_type=args.lab,
            config=config,
            silent_mode=args.silent
        )

        # 4. Обработка вывода
        if args.silent:
            # Идеально для вашего GUI-приложения: в консоль выпадает только чистый JSON
            print(json.dumps(result_json, ensure_ascii=False, indent=2))
        
        if args.output:
            # Сохранение лога на диск
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result_json, f, ensure_ascii=False, indent=2)
            if not args.silent:
                print(f"\n[INFO] Результаты сохранены в файл: {args.output}")

    except Exception as e:
        error_res = {"error": f"Критическая ошибка работы чекера: {str(e)}", "success": False}
        print(json.dumps(error_res, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()