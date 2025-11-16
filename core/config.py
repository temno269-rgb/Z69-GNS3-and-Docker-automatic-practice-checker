import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

def load_settings() -> dict:
    if not CONFIG_PATH.exists():
        defaults = {
            "gns3_server": {
                "ip": "10.242.192.200",
                "port": "3080",
                "project_name": "",
                "login": "admin",
                "password": "*"
            }
        }
        save_settings(defaults)
        return defaults
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
