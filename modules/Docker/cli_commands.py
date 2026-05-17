# -*- coding: utf-8 -*-
"""
cli_commands.py
Парсер терминальных команд для модуля Docker.
"""

from modules.Docker.backend_bridge import set_config, get_config

HELP = """Available commands:
proj <path> - set the path to the Docker project folder.
lab <number> - the name of the laboratory work (e.g. lab10).
show - show current settings.
check - run verification on selected folder.
help - show this help message.
"""

def handle_docker_command(line: str) -> str:
    """Обрабатывает введенную команду, обновляет конфиг и возвращает ответ для консоли."""
    if not line:
        return ""
    parts = line.strip().split()
    if not parts:
        return ""
    cmd = parts[0].lower()
    args = parts[1:]
    
    if cmd == "help":
        return HELP
    
    if cmd == "show":
        config = get_config()
        output = [
            f"   project path: {config.get('project_path', 'Not set')}",
            f"   laboratory: {config.get('lab', 'Not set')}"
        ]
        return "\n".join(output)
        
    if cmd in ("proj", "lab"):
        if not args:
            return f"Specify a value for {cmd}"
        val = " ".join(args)
        key_map = {"proj": "project_path", "lab": "lab"}
        try:
            set_config(key_map[cmd], val)
            return f"OK: {cmd}={val}"
        except ValueError as e:
            return f"ERROR: {e}"
            
    # Запуск 'check' перехватывается в main_ui.py, чтобы запускаться в фоновом потоке
    if cmd == "check":
        return "COMMAND_CHECK"
        
    return f"Unknown command: {cmd}\n{HELP}"