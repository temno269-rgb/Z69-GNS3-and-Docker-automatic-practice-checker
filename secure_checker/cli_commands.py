# -*- coding: utf-8 -*-
"""
cli_commands.py
Parse terminal-like commands to set config.
Usage from GUI:
  from cli_commands import handle_command
  output = handle_command("ip 10.0.0.1")  # returns feedback string
"""

from secure_checker.backend_bridge import (
    set_config,
    get_config,
)


HELP = """Доступные команды:
  ip <addr>             - установить IP сервера GNS3
  port <num>            - установить порт сервера
  project <name|path>   - имя проекта (или путь к .gns3project при local=true)
  login <user>          - логин для telnet
  password <pass>       - пароль для telnet
  local <true|false>    - режим локального импорта проекта
  desktop <true|false>  - сохранять результаты на Рабочий стол
  show                  - показать текущие настройки
  help                  - список команд
"""

def handle_command(line: str) -> str:
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
        return str(get_config())
    if cmd in ("ip","port","project","login","password","local","desktop"):
        if not args:
            return f"Укажите значение для {cmd}"
        val = " ".join(args)
        key = "desktop_results" if cmd=="desktop" else cmd
        cfg = set_config(key, val)
        return f"OK: {key}={cfg.get(key)}"
    return f"Неизвестная команда: {cmd}\n{HELP}"
