import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
def load_settings() -> dict:
    if not CONFIG_PATH.exists():
        defaults = {
  "ip": "192.168.56.10",
  "port": "80",
  "project": "1",
  "local": False,
  "login": "admin",
  "password": "*",
  "desktop_results": True
}
        save_settings(defaults)
        return defaults
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_settings(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        print(data)
