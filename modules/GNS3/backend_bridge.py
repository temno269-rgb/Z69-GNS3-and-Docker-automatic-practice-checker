# -*- coding: utf-8 -*-
"""
backend_bridge.py

Thin API for GUI:
- set_config(key, value)
- get_config()
- run_parse(log_func=None) # log_func(line: str) -> None
- validate_connection() # проверка подключения к GNS3

Config is persisted in user-writable location (APPDATA on Windows).
"""

import os
import json
from pathlib import Path
from typing import Callable, Optional

from modules.GNS3.core.comparator.compare import comparator_main
from modules.GNS3.core.parser.parse import parser_main
from modules.GNS3.core.advanced_logger import get_logger, init_logger

# Get path to config.json in user folder
appdata = os.getenv('APPDATA')
if appdata:
    config_dir = Path(appdata) / "Z69"
else:
    # Fallback if APPDATA is not available
    config_dir = Path.home() / "Z69"

# Create folder if it doesn't exist
config_dir.mkdir(parents=True, exist_ok=True)
CFG = config_dir / "config.json"

DEFAULTS = {
    "ip": "10.242.192.200",
    "port": "80",
    "project": "1",
    "login": "admin",
    "password": "*",
}


def _load() -> dict:
    """Load config from file."""
    if CFG.exists():
        try:
            with open(CFG, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            get_logger().error(f"Configuration read error", technical=str(e))
            d = {}
    else:
        d = {}
    
    # Merge with defaults
    x = DEFAULTS.copy()
    x.update(d)
    return x


def _save(cfg: dict) -> None:
    """Save config to file."""
    try:
        # Ensure folder exists
        CFG.parent.mkdir(parents=True, exist_ok=True)
        
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        get_logger().error(f"Configuration write error", technical=str(e))


def set_config(key: str, value):
    """
    Set config value and save.
    Returns updated config.
    """
    cfg = _load()
    
    # Parameter validation
    if key == "port":
        try:
            port = int(value)
            if port < 1 or port > 65535:
                raise ValueError("Port must be between 1 and 65535")
            value = str(port)
        except ValueError:
            raise ValueError(f"Invalid port number: {value}")
    
    elif key == "ip":
        # Simple IP address validation
        import re
        ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
        if not re.match(ip_pattern, value):
            raise ValueError(f"Invalid IP address format: {value}")
    
    elif key == "lab":
        if not value or not str(value).strip():
            raise ValueError("Lab number cannot be empty")
        
        # Check if lab folder exists
        try:
            from pathlib import Path
            current_dir = Path(__file__).resolve().parent
            examples_dir = current_dir / "core" / "Examples"
            lab_folder = examples_dir / f"{value}"
            if not lab_folder.exists():
                matching_labs = []
                for p in examples_dir.iterdir():
                    if p.is_dir() and p.name.startswith(f"{value}_"):
                        matching_labs.append(p.name)
                
                if matching_labs:
                    raise ValueError(f"lab '{value}' not found. Available labs: 1, 2_1, 2_2, 2_3, 3_1, 3_2, 4, 5, 6")
                else:
                    # Show all available labs
                    available_labs = []
                    for p in examples_dir.iterdir():
                        if p.is_dir() and p.name.startswith(""):
                            available_labs.append(p.name)
                    raise ValueError(f"lab '{value}' not found. Available labs: 1, 2_1, 2_2, 2_3, 3_1, 3_2, 4, 5, 6")
        except Exception as e:
            raise ValueError(f"Error validating lab: {e}")
    
    elif key == "project":
        if not value or not str(value).strip():
            raise ValueError("Project name cannot be empty")
    
    elif key in ("login", "password"):
        if not value or not str(value).strip():
            raise ValueError(f"{key} cannot be empty")
    
    cfg[key] = value
    _save(cfg)
    get_logger().info(f"Parameter '{key}' set.")
    return cfg


def get_config() -> dict:
    """Get entire config."""
    cfg = _load()
    cfg['config_file'] = str(CFG)
    return cfg


def validate_connection() -> tuple[bool, str]:
    try:
        from gns3fy import Gns3Connector
        cfg = _load()
        ip = cfg.get('ip', DEFAULTS['ip'])
        port = cfg.get('port', DEFAULTS['port'])
        base_url = f"http://{ip}:{port}"
        connector = Gns3Connector(base_url)
        # Try to get project list
        connector.projects
        return True, f"GNS3 server accessible at {base_url}"
    except Exception as e:
        return False, f"Failed to connect to GNS3 server: {e}"


def run_parse(log_func: Optional[Callable[[str], None]] = None) -> dict:
    """Run parser with config."""
    logger = log_func if callable(log_func) else get_logger().info
    
    def _logger(line):
        try:
            logger(line)
        except Exception:
            # Fallback to stdout
            print(line)
    
    cfg = _load()
    # Log start of parsing
    get_logger().info("Starting configuration collection from GNS3...")
    return parser_main(cfg, logger=_logger)


def run_compare(lab):
    """Run comparison with reference."""
    get_logger().info(f"Starting comparison for lab {lab}...")
    return comparator_main(lab, True)
