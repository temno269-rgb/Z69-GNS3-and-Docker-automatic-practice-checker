import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from core import config
from core.logger import StdRedirector
import sys, os, json, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Импорт парсера
try:
    from core.parser import parser_main
except ImportError as e:
    parser_main = None
    PARSER_ERROR = str(e)
except Exception as e:
    parser_main = None
    PARSER_ERROR = f"Ошибка загрузки парсера: {e}"
else:
    PARSER_ERROR = None

HELP_TEXT = """SecureChecker CLI v1.0
Команды:
  set ip <адрес>
  set port <номер>
  set login <строка>
  set password <строка>
  set project <имя>
  show config
  export
  clear
  help
  exit
"""

class CliApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SecureChecker CLI")
        self.root.geometry("860x520")
        self.root.resizable(True, True)

        self.text = ScrolledText(root, wrap=tk.WORD, font=("Consolas", 11),
                                 bg="#0f0f0f", fg="#e6e6e6", insertbackground="#e6e6e6")
        self.text.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6,0))
        self.entry = tk.Entry(root, font=("Consolas", 11),
                              bg="#111318", fg="#e6e6e6", insertbackground="#e6e6e6")
        self.entry.pack(fill=tk.X, padx=6, pady=6)
        self.entry.bind("<Return>", self.on_enter)
        self.entry.focus_set()

        sys.stdout = StdRedirector(self.text)
        sys.stderr = StdRedirector(self.text, prefix="[ERROR] ")

        self.settings = config.load_settings()
        self.print_welcome()
        print(HELP_TEXT)
        self.prompt()

    def print_welcome(self):
        print("SecureChecker CLI готов. Введите команду (help для списка).\n")

    def prompt(self):
        self.text.insert(tk.END, "> ")
        self.text.see(tk.END)

    def on_enter(self, event):
        cmdline = self.entry.get().strip()
        self.entry.delete(0, tk.END)
        self.text.insert(tk.END, cmdline + "\n")
        if cmdline:
            self.handle_command(cmdline)
        self.prompt()

    def handle_command(self, line: str):
        try:
            parts = line.split()
            if not parts:
                return
            cmd = parts[0].lower()

            if cmd == "help":
                print(HELP_TEXT)
                return
            if cmd == "clear":
                self.text.delete("1.0", tk.END)
                return
            if cmd == "exit":
                self.root.after(50, self.root.destroy)
                return
            if cmd == "show" and len(parts) >= 2 and parts[1].lower() == "config":
                print(json.dumps(self.settings, ensure_ascii=False, indent=2))
                return
            if cmd == "set" and len(parts) >= 3:
                key = parts[1].lower()
                value = " ".join(parts[2:])
                if key not in {"ip","port","login","password","project"}:
                    print(f"[WARN] Неизвестный параметр: {key}")
                    return
                if key == "port" and not value.isdigit():
                    print("[ERROR] Порт должен быть числом.")
                    return
                if key == "ip" and len(value.split(".")) != 4:
                    print("[WARN] Нестандартный IP, проверьте корректность.")
                self.settings["gns3_server"]["project_name" if key=="project" else key] = value
                config.save_settings(self.settings)
                print(f"[OK] {key} = {value}")
                return
            if cmd == "export":
                if parser_main is None:
                    error_msg = PARSER_ERROR if PARSER_ERROR else "Парсер не найден"
                    print(f"[ERROR] Парсер недоступен: {error_msg}")
                    print("[INFO] Убедитесь, что установлены зависимости: pip install gns3fy telnetlib3")
                    return
                try:
                    parsed = parser_main()
                except Exception as e:
                    print(f"[ERROR] Ошибка при выполнении парсера: {e}")
                    traceback.print_exc()
                    return
                project = parsed.get("project") or self.settings["gns3_server"].get("project_name") or "Export"
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                export_path = os.path.join(desktop, project)
                os.makedirs(export_path, exist_ok=True)
                data = parsed.get("data", {})
                for name, payload in data.items():
                    fname = os.path.join(export_path, f"{name}.json")
                    with open(fname, "w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                print(f"[export] Готово. Файлы сохранены: {export_path}")
                return

            print("Неизвестная команда. Введите help.")

        except Exception:
            traceback.print_exc()

def launch_cli():
    root = tk.Tk()
    CliApp(root)
    root.mainloop()
