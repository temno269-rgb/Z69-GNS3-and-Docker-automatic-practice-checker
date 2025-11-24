import tkinter as tk
import sys

class StdRedirector:
    def __init__(self, text_widget, prefix=""):
        self.text_widget = text_widget
        self.prefix = prefix

    def write(self, s):
        if not s:
            return
        self.text_widget.insert(tk.END, f"{self.prefix}{s}")
        self.text_widget.see(tk.END)

    def flush(self):
        pass
