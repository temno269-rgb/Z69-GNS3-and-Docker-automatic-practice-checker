
import sys
from pathlib import Path

# Добавляем в sys.path директорию secure_checker (там лежит ui/)
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ui.cli_app import launch_cli

if __name__ == "__main__":
    launch_cli()
