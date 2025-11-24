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
    with Telnet(ip, node.console) as telnet:
        # Логин/пароль
        telnet.read_until(b"Login: ", timeout=20)
        telnet.write(login_bytes)

        telnet.read_until(b"Password: ", timeout=20)
        telnet.write(password_bytes)

        telnet.read_until(b">", timeout=30)
        telnet.write(EXPORT_CMD)

        export_data = ""
        deadline = time.time() + 60  # максимум 60 секунд на экспорт
        last_nonempty = time.time()

        while time.time() < deadline:
            chunk = telnet.read_very_eager().decode("utf-8", errors="ignore")
            if chunk:
                export_data += chunk
                last_nonempty = time.time()

                # если уже есть конфиг и вернулся prompt MikroTik
                if "] >" in export_data:
                    # немного подождём ещё, вдруг досыпется хвост
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


def check_vpc(node, ip: str) -> str:
    """
    VPCS: получаем IP/MASK из show ip, при необходимости несколько попыток DHCP.
    Блокирующая, будет запускаться через asyncio.to_thread.
    """
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
        return data
    return data[start:start + 55]


def check_docker(node, ip: str):
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

    except Exception as e:
        print(e)
        return node.properties

    inet_pos = data.rfind("inet ")
    scope_pos = data.rfind("scope")
    if inet_pos == -1 or scope_pos == -1 or scope_pos <= inet_pos:
        return data
    return data[inet_pos:scope_pos]


def switch_config(node):
    """Свитч: просто возвращаем properties (настройки внутри GNS3)."""
    return node.properties


async def nodes_config_async(lab: Project, ip: str, login_bytes: bytes, password_bytes: bytes) -> dict:
    """
    Асинхронный сбор конфигов/информации по всем узлам проекта.
    ВАЖНО: сначала обрабатываются все, кроме роутеров (qemu),
    потом — роутеры (как в твоём оригинальном коде).
    """
    other_tasks = []
    router_tasks = []

    for node in lab.nodes:
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

    total = {}

    # Сначала VPCS / switches / docker
    if other_tasks:
        names = [name for name, _ in other_tasks]
        coros = [c for _, c in other_tasks]
        results = await asyncio.gather(*coros)
        total.update({name: res for name, res in zip(names, results)})

    # Потом роутеры
    if router_tasks:
        print("Обработка роутеров (qemu) после остальных узлов...")
        names = [name for name, _ in router_tasks]
        coros = [c for _, c in router_tasks]
        results = await asyncio.gather(*coros)
        total.update({name: res for name, res in zip(names, results)})

    return total


async def collect_gns3_configs(
        login: str,
        password: str,
        ip: str,
        port: str,
        project_name: str,
        base_output_dir: str = "Student/results",
) -> None:
    """
    Главная асинхронная функция:
    - подключается к GNS3 серверу;
    - открывает проект;
    - запускает все узлы;
    - параллельно собирает конфиг/инфу со всех устройств;
    - сохраняет всё по узлам в JSON;
    - останавливает узлы и закрывает проект.
    """
    server = Gns3Connector(f"http://{ip}:{port}")
    lab = Project(name=project_name, connector=server)

    try:
        lab.get()
    except Exception as e:
        print("Ошибка при получении проекта:", e)
        return

    if lab.status == "closed":
        lab.open()
        # небольшая пауза, чтобы GNS3 успел открыть проект
        time.sleep(5)

    # Запускаем все узлы и ждём их запуска
    for node in lab.nodes:
        print(f"Старт узла {node.name}...")
        node.start()
        # ждём не более 60 секунд
        for _ in range(60):
            node.get()
            if node.status == "started":
                break
            time.sleep(1)

    print("Все узлы запущены, начинаем сбор конфигурации...")

    login_bytes = login.encode("ascii") + b"\r\n"
    password_bytes = password.encode("ascii") + b"\r\n"

    nodes_data = await nodes_config_async(lab, ip, login_bytes, password_bytes)

    # Путь для сохранения результатов
    output_dir = os.path.join(base_output_dir, project_name)
    os.makedirs(output_dir, exist_ok=True)

    for name, data in nodes_data.items():
        file_path = os.path.join(output_dir, f"{name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"Сохранён конфиг для {name} -> {file_path}")

    # Останавливаем узлы и закрываем проект
    print("Останавливаем все узлы...")
    for node in lab.nodes:
        node.stop()
        time.sleep(0.5)

    lab.close()
    print("Проект закрыт, работа завершена.")


def run(
        login: str,
        password: str,
        ip: str,
        port: str,
        project_name: str,
        base_output_dir: str = "Student/results",
) -> None:
    """
    Обёртка над collect_gns3_configs, чтобы можно было просто вызвать:
        from this_script import run
        run("admin", "123", "192.168.56.10", "80", "untitled")
    """
    asyncio.run(
        collect_gns3_configs(
            login=login,
            password=password,
            ip=ip,
            port=port,
            project_name=project_name,
            base_output_dir=base_output_dir,
        )
    )

def parser_main(cfg: dict = None, logger=print) -> dict:
    """
    Функция-обёртка для интерфейса (ui.cli_app).

    Не принимает аргументов, берёт настройки подключения к GNS3 из core.config
    и возвращает словарь формата:

        {
            "project": <имя_проекта>,
            "data": {
                "<имя_узла>": {...},
                ...
            }
        }

    Именно такой формат ожидает ui/cli_app.py в команде 'export'.
    """
    if cfg is None:
        try:
            from secure_checker.core import config as core_config
            settings = core_config.load_settings()
            gns = settings.get("gns3_server", {})
        except Exception as e:
            logger(f"[parser] Ошибка импорта конфига: {e}")
            # Fallback на дефолты
            gns = {
                "login": "admin",
                "password": "*",
                "ip": "192.168.56.101",
                "port": "80",
                "project": "k"
            }
    else:
        # Используем переданный конфиг напрямую
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

        if not getattr(lab, "opened", False):
            logger("[parser] Открываем проект...")
            lab.open()

        # Запускаем все узлы перед сбором конфигов
        logger("[parser] Запускаем все узлы проекта...")
        for node in lab.nodes:
            try:
                node.start()
                time.sleep(0.5)
            except Exception as e:
                logger(f"[parser][WARN] Не удалось запустить узел {node.name}: {e}")

        # Подготовка логина/пароля для Telnet
        login_bytes = (login + "\r\n").encode("utf-8")
        password_bytes = (password + "\r\n").encode("utf-8")

        # Асинхронный сбор информации по всем узлам (используем твою nodes_config_async)
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
                node.stop()
                time.sleep(0.5)
            except Exception as e:
                logger(f"[parser][WARN] Не удалось остановить узел {node.name}: {e}")

        lab.close()
        logger("[parser] Проект закрыт, данные собраны.")
        return {
            "project": project_name,
            "data": nodes_data,
        }
    except Exception as e:
        print(e)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Сбор конфигураций узлов GNS3 проекта (CLI аргументы необязательны)"
    )
    parser.add_argument("--login", help="Логин для роутеров (QEMU)")
    parser.add_argument("--password", help="Пароль для роутеров (QEMU)")
    parser.add_argument("--ip", help="IP GNS3-сервера")
    parser.add_argument("--port", help="Порт GNS3-сервера (обычно 80 или 3080)")
    parser.add_argument("--project", help="Имя проекта в GNS3")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Базовая папка для сохранения результатов (по умолчанию Student/results)",
    )

    args = parser.parse_args()

    def ask(value, prompt_text, default=None):
        """
        Если value уже передан из командной строки — возвращаем его.
        Иначе спрашиваем через input, с отображением дефолта.
        """
        if value:
            return value
        if default is not None:
            prompt = f"{prompt_text} [{default}]: "
        else:
            prompt = f"{prompt_text}: "
        user_input = input(prompt).strip()
        if not user_input and default is not None:
            return default
        return user_input

    login = ask(args.login, "Введите логин", default="admin")
    password = ask(args.password, "Введите пароль", default="*")
    ip = ask(args.ip, "Введите IP GNS3-сервера", default="192.168.56.10")
    port = ask(args.port, "Введите порт GNS3-сервера", default="80")
    project_name = ask(args.project, "Введите имя проекта", default="untitled")
    output_dir = ask(args.output_dir, "Папка для результатов", default="Student/results")

    run(
        login=login,
        password=password,
        ip=ip,
        port=port,
        project_name=project_name,
        base_output_dir=output_dir,
    )
