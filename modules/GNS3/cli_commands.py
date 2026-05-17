# -*- coding: utf-8 -*-
"""
cli_commands.py
Parse terminal-like commands to set config.
Usage from GUI:
  from cli_commands import handle_command
  output = handle_command("ip 10.0.0 1")  # returns feedback string
"""

from modules.GNS3.backend_bridge import (
    set_config,
    get_config,
    validate_connection,
)
from modules.GNS3.core.advanced_logger import get_logger

HELP = """Available commands:
ip <ip> - set the IP of the GNS3.
port <port> - set the server port.
proj <name> - the name of the project.
lab <number> - the number of the laboratory work.
login <username> - login for telnet.
pass <password> - password for telnet.
show - show current settings.
test - test connection to GNS3 server.
run - run check with current settings.
help - show this help message.
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
        config = get_config()
        output = []
        output.append(f"   project name: {config.get('project', 'Not set')}")
        output.append(f"   laboratory: {config.get('lab', 'Not set')}")
        output.append(f"   ip: {config.get('ip', 'Not set')}")
        output.append(f"   port: {config.get('port', 'Not set')}")
        output.append(f"   login: {config.get('login', 'Not set')}")
        output.append(f"   password: {'*' * len(config.get('password', '')) if config.get('password') else 'Not set'}")
        return "\n".join(output)
    
    if cmd == "test":
        success, msg = validate_connection()
        if success:
            return f"OK: {msg}"
        else:
            return f"ERROR: {msg}"
    
    if cmd == "run":
        try:
            from modules.GNS3.backend_bridge import run_parse, run_compare
            config = get_config()
            
            # Validation of required parameters
            if not config.get('project') or config.get('project') == '1':
                return "ERROR: Please set a valid project name first using 'proj <name>'"
            if not config.get('lab'):
                return "ERROR: Please set a valid lab number first using 'lab <number>'"
            
            # Connection test before starting
            success, conn_msg = validate_connection()
            if not success:
                return f"ERROR: Cannot start check: {conn_msg}"
            
            output = []
            result = run_parse(log_func=lambda x: output.append(x))
            output.append("")
            compare_result = run_compare(config['lab'])
            output.append("")
            output.append(f"Analysis completed! Result: {compare_result}%")
            return "\n".join(output)
        except Exception as e:
            get_logger().error(f"Error during execution", technical=str(e))
            return f"ERROR: Error during execution: {e}"
    
    if cmd in ("ip","port","proj","login","pass","lab"):
        if not args:
            return f"Specify a value for {cmd}"
        val = " ".join(args)
        key = cmd
        try:
            cfg = set_config(key, val)
            # After setting IP/port suggest testing connection
            if key in ("ip", "port"):
                return f"OK: {key}={cfg.get(key)}\n   Use 'test' to verify connection."
            return f"OK: {key}={cfg.get(key)}"
        except ValueError as e:
            return f"ERROR: {e}"
    
    return f"Unknown command: {cmd}\n{HELP}"
