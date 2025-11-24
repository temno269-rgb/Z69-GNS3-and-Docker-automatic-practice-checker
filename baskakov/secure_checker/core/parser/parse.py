import asyncio
import json
import os
import re
import time
from collections import defaultdict

from gns3fy import Gns3Connector, Project
from telnetlib3.telnetlib import Telnet

# Команды для разных типов узлов
EXPORT_CMD = b"export\r\n"
QUIT_CMD = b"quit\r\n"

IP_DHCP_CMD = b"ip dhcp\r\n"
SHOW_IP_CMD = b"show ip\r\n"
IP_A_CMD = b"ip a\r\n"

# Удаление ANSI-последовательностей из вывода
ANSI_ESCAPE = re.compile(r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]")


def escape_ansi(line: str) -> str:
    if not line:
        return ""
    return ANSI_ESCAPE.sub("", line)


def parse_export(export_text: str) -> dict:
    """
    Разбор вывода команды export в структуру:
    {
        "/ip address": [
            {"cmd": "add", "address": "...", "interface": "..."},
            ...
        ],
        ...
    }
    """
    lines = export_text.splitlines()
    data = defaultdict(list)
    current_section = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        # Комментарии и системные служебные строки
        if line.startswith("#") or line.startswith("["):
            continue
        # Новая секция
        if line.startswith("/"):
            current_section = line
            continue
        if not current_section:
            continue

        parts = line.split()
        if not parts:
            continue

        cmd = parts[0]
        entry = {"cmd": cmd}

        # Пары ключ=значение
        for token in parts[1:]:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            entry[key.strip('"[]')] = value.strip('"[]')

        data[current_section].append(entry)

    return dict(data)


def qemu_config(node, ip: str, login_bytes: bytes, password_bytes: bytes) -> dict:
    """
    Роутер (QEMU): подключение по Telnet к консоли и export-конфиг.
    Блокирующая функция, выполняется через asyncio.to_thread.
    Делает "умный" сбор экспорта: ждёт появления prompt'а или таймаута.
    """
    try:
        with Telnet(ip, node.console) as telnet:
            # Логин/пароль
            telnet.read_until(b"Login: ", timeout=20)
            telnet.write(login_bytes)

            telnet.read_until(b"Password: ", timeout=20)
            telnet.write(password_bytes)

            telnet.read_until(b">", timeout=30)
            telnet.write(EXPORT_CMD)

            export_data = ""
            deadline = time.time() + 60
            last_nonempty = time.time()

            while time.time() < deadline:
                chunk = telnet.read_very_eager().decode("utf-8", errors="ignore")
                if chunk:
                    export_data += chunk
                    last_nonempty = time.time()

                    # если уже есть конфиг и вернулся prompt MikroTik
                    if "] >" in export_data:
                        time.sleep(1)
                        chunk2 = telnet.read_very_eager().decode("utf-8", errors="ignore")
                        export_data += chunk2
                        break
                else:
                    # если давно ничего не приходило, тоже выходим
                    if time.time() - last_nonempty > 5:
                        break
                    time.sleep(0.5)

            telnet.write(QUIT_CMD)

        cleaned = escape_ansi(export_data)
        return {"export": parse_export(cleaned)}
    except Exception as e:
        print(f"Ошибка при сборе конфига QEMU узла {node.name}: {e}")
        return {"error": str(e)}


def check_vpc(node, ip: str) -> dict:
    """
    VPCS: получаем IP/MASK из show ip, при необходимости несколько попыток DHCP.
    Блокирующая, будет запускаться через asyncio.to_thread.
    """
    try:
        with Telnet(ip, node.console) as telnet:
            data = ""
            attempts = 0

            while attempts < 3:
                telnet.write(IP_DHCP_CMD)
                telnet.read_until(b">", timeout=10)

                telnet.write(SHOW_IP_CMD)
                data = telnet.read_until(b">", timeout=10).decode("utf-8", errors="ignore")

                if "IP" in data:
                    break

                attempts += 1
                time.sleep(3)

        start = data.find("IP/MASK")
        if start == -1:
            return {"raw_output": data}
        return {"ip_info": data[start:start + 55]}
    except Exception as e:
        print(f"Ошибка при проверке VPC узла {node.name}: {e}")
        return {"error": str(e)}


def check_docker(node, ip: str) -> dict:
    """
    Docker: берём последнюю строку с 'inet ... scope'.
    Блокирующая, будет запускаться через asyncio.to_thread.
    """
    port = node.properties.get("aux")
    if port is None:
        return node.properties

    try:
        with Telnet(ip, port) as telnet:
            data = ""
            attempts = 0
            while attempts < 11:
                telnet.write(IP_A_CMD)
                data = telnet.read_until(b"#", timeout=10).decode("utf-8", errors="ignore")
                if data.count("inet ") >= 2:
                    break
                attempts += 1
                time.sleep(3)

        inet_pos = data.rfind("inet ")
        scope_pos = data.rfind("scope")
        if inet_pos == -1 or scope_pos == -1 or scope_pos <= inet_pos:
            return {"raw_output": data}
        return {"ip_info": data[inet_pos:scope_pos]}
    except Exception as e:
        print(f"Ошибка при проверке Docker узла {node.name}: {e}")
        return node.properties


def switch_config(node) -> dict:
    """Свитч: просто возвращаем properties (настройки внутри GNS3)."""
    return node.properties


async def nodes_config_async(lab: Project, ip: str, login_bytes: bytes, password_bytes: bytes) -> dict:
    """
    Асинхронный сбор конфигов/информации по всем узлам проекта.
    ВАЖНО: сначала обрабатываются все, кроме роутеров (qemu),
    потом — роутеры.
    """
    other_tasks = []
    router_tasks = []

    for node in lab.nodes:
        try:
            node.get()
            print(f"Обработка узла: {node.name} ({node.node_type})")

            if node.node_type == "qemu":
                coro = asyncio.to_thread(qemu_config, node, ip, login_bytes, password_bytes)
                router_tasks.append((node.name, coro))

            elif node.node_type == "vpcs":
                coro = asyncio.to_thread(check_vpc, node, ip)
                other_tasks.append((node.name, coro))

            elif node.node_type == "ethernet_switch":
                coro = asyncio.to_thread(switch_config, node)
                other_tasks.append((node.name, coro))

            elif node.node_type == "docker":
                coro = asyncio.to_thread(check_docker, node, ip)
                other_tasks.append((node.name, coro))
        except Exception as e:
            print(f"Ошибка при обработке узла {node.name}: {e}")

    total = {}

    # Сначала VPCS / switches / docker
    if other_tasks:
        names = [name for name, _ in other_tasks]
        coros = [c for _, c in other_tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                total[name] = {"error": str(res)}
            else:
                total[name] = res

    # Потом роутеры
    if router_tasks:
        print("Обработка роутеров (qemu) после остальных узлов...")
        names = [name for name, _ in router_tasks]
        coros = [c for _, c in router_tasks]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for name, res in zip(names, results):
            if isinstance(res, Exception):
                total[name] = {"error": str(res)}
            else:
                total[name] = res

    return total


def parser_main(cfg: dict = None, logger=print) -> dict:
    """
    Функция-обёртка для интерфейса GUI.

    Возвращает словарь формата:
        {
            "project": <имя_проекта>,
            "data": {
                "<имя_узла>": {...},
                ...
            }
        }
    """
    if cfg is None:
        try:
            from secure_checker.core import config as core_config
            settings = core_config.load_settings()
            gns = settings.get("gns3_server", {})
        except Exception as e:
            logger(f"[parser] Ошибка импорта конфига: {e}")
            gns = {
                "login": "admin",
                "password": "*",
                "ip": "192.168.56.101",
                "port": "80",
                "project": "k"
            }
    else:
        gns = cfg
    
    try:
        login = gns.get("login") or "admin"
        password = gns.get("password") or "*"
        ip = gns.get("ip") or "192.168.56.101"
        port = gns.get("port") or "80"
        project_name = gns.get("project") or "k"

        base_url = f"http://{ip}:{port}"
        logger(f"[parser] Подключение к GNS3 серверу {base_url}, проект '{project_name}'")

        # Подключаемся к GNS3 и получаем проект
        connector = Gns3Connector(base_url)
        lab = Project(name=project_name, connector=connector)
        lab.get()

        if not getattr(lab, "project_id", None):
            raise RuntimeError(f"Проект '{project_name}' не найден на сервере {base_url}")

        # Проверяем статус проекта
        if hasattr(lab, 'status') and lab.status == "closed":
            logger("[parser] Открываем проект...")
            lab.open()
            time.sleep(3)

        # Запускаем все узлы перед сбором конфигов
        logger("[parser] Запускаем все узлы проекта...")
        for node in lab.nodes:
            try:
                if hasattr(node, 'status') and node.status != "started":
                    node.start()
                    time.sleep(0.5)
            except Exception as e:
                logger(f"[parser][WARN] Не удалось запустить узел {node.name}: {e}")

        # Подготовка логина/пароля для Telnet
        login_bytes = (login + "\r\n").encode("utf-8")
        password_bytes = (password + "\r\n").encode("utf-8")

        # Асинхронный сбор информации по всем узлам
        logger("[parser] Собираем конфиги/информацию по узлам...")
        nodes_data = asyncio.run(
            nodes_config_async(
                lab=lab,
                ip=ip,
                login_bytes=login_bytes,
                password_bytes=password_bytes,
            )
        )

        # Останавливаем узлы и закрываем проект
        logger("[parser] Останавливаем все узлы...")
        for node in lab.nodes:
            try:
                if hasattr(node, 'status') and node.status == "started":
                    node.stop()
                    time.sleep(0.5)
            except Exception as e:
                logger(f"[parser][WARN] Не удалось остановить узел {node.name}: {e}")

        if hasattr(lab, 'close'):
            lab.close()
        logger("[parser] Проект закрыт, данные собраны.")
        
        return {
            "project": project_name,
            "data": nodes_data,
        }
    except Exception as e:
        logger(f"[parser] Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return {
            "project": gns.get("project", "unknown"),
            "data": {},
            "error": str(e)
        }
