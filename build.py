import PyInstaller.__main__
import os

def build_app():
    print("Начинаем сборку приложения Z69...")
    
    PyInstaller.__main__.run([
        'main_ui.py',  # ВАЖНО: Замени на реальный стартовый файл твоего приложения!
        '--name=Z69',     # Имя итогового .exe файла
        '--onefile',          # Упаковать всё в один файл
        
        # ВРЕМЕННО ЗАКОММЕНТИРОВАНО ДЛЯ ОТЛАДКИ. 
        # Верни обратно, когда убедишься, что всё запускается без ошибок в консоли.
         '--windowed',       
        
        # Добавляем папку с картинками и шрифтами
        # Формат: 'исходная_папка;папка_внутри_exe' (для Windows разделитель точка с запятой)
        '--add-data=assets;assets',
        
        # Явно указываем скрытые импорты чекеров из core.py
        '--hidden-import=modules.Docker.lab_checker.checkers.lab10',
        '--hidden-import=modules.Docker.lab_checker.checkers.lab11',
        '--hidden-import=modules.Docker.lab_checker.checkers.lab12',
        '--hidden-import=modules.Docker.lab_checker.checkers.lab13',
        '--hidden-import=modules.Docker.lab_checker.checkers.lab14',
    ])

if __name__ == "__main__":
    build_app()