# -*- coding: utf-8 -*-
"""
main_ui.py - GUI приложения для сравнения конфигураций

Поддерживает:
- Интерактивную консоль для команд
- Динамический выбор эталона (examples 1, examples 2, ...)
- Запуск парсера и компаратора
- Отображение результатов с картинками
"""

import json
from pathlib import Path
from PyQt5.QtCore import Qt, QRect, QEasingCurve, QPropertyAnimation, QSize, QTimer
from PyQt5.QtGui import (
    QPixmap, QIcon, QPainter, QPen, QFontMetrics,
    QColor, QPalette, QFontDatabase, QFont
)
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QTextEdit, QFrame, QLineEdit, QProxyStyle, QStyle
)

import sys
import os
import random
import threading

from secure_checker.cli_commands import handle_command
from secure_checker.backend_bridge import run_parse, reset_config, list_examples, set_config, get_config


class NoCursorStyle(QProxyStyle):
    """Скрывает текстовый курсор в поле ввода."""
    
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_TextCursorWidth:
            return 0
        return super().pixelMetric(metric, option, widget)


class CmdLineEdit(QLineEdit):
    """Поле ввода командной строки с чёрным фоном, белым текстом и пользовательским курсором."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyle(NoCursorStyle())
        
        pal = self.palette()
        pal.setColor(QPalette.Text, Qt.white)
        pal.setColor(QPalette.Base, Qt.black)
        self.setPalette(pal)
        self.setStyleSheet(
            "border: none; background: black; color: white; font-family: Consolas; font-size: 16px;"
        )
        
        self._blink_visible = True
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._toggle_blink)
        self._blink.start(600)
    
    def _toggle_blink(self):
        self._blink_visible = not self._blink_visible
        self.update()
    
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.hasFocus() or not self._blink_visible:
            return
        
        fm = QFontMetrics(self.font())
        uw = max(fm.averageCharWidth(), 8)
        pr = self.cursorRect()
        x = pr.x()
        y = pr.bottom() - 3
        
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawRect(x + 6, y, 10, 2)
    
    def insertFromMimeData(self, source):  # type: ignore[override]
        """Отключить вставку из буфера обмена."""
        return
    
    def contextMenuEvent(self, event):
        """Удалить опцию вставки из контекстного меню."""
        menu = super().createStandardContextMenu()
        for action in menu.actions():
            text = action.text().lower().strip()
            if ("paste" in text) or ("встав" in text):
                menu.removeAction(action)
        menu.exec_(event.globalPos())
    
    def keyPressEvent(self, event):  # type: ignore[override]
        """Отключить Ctrl+V и другие сочетания для вставки."""
        if event.matches(QKeySequence.Paste):
            return
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_Insert:
            return
        super().keyPressEvent(event)


class ConsoleFrame(QFrame):
    """Консоль для ввода команд и вывода логов."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: black;")
        
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "border: none; background: black; color: white; font-family: Consolas; font-size: 16px;"
        )
        
        self.input = CmdLineEdit(self)
        
        self.close_btn = QPushButton("×", self)
        self.close_btn.setStyleSheet(
            "QPushButton {border: none; background: black; color: white; font-size: 16px;}"
            " QPushButton:hover {background: #cc4c4c;}"
        )
        self.close_btn.setFixedSize(22, 22)
    
    def resizeEvent(self, event):
        w = self.width()
        h = self.height()
        left, right_margin, bottom_margin = 0, 0, 8
        top = -5
        
        self.close_btn.move(w - self.close_btn.width() - 5, 3)
        self.output.setGeometry(left + 5, top, w - right_margin - 10, h - top - bottom_margin - 28)
        self.input.setGeometry(left + 5, h - bottom_margin - 24, w - right_margin - 10, 22)
        
        super().resizeEvent(event)
    
    def write(self, text: str):
        self.output.append(text)
        self.output.moveCursor(self.output.textCursor().End)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        super().paintEvent(event)


class MainWindow(QMainWindow):
    """Главное окно приложения."""
    
    def __init__(self):
        super().__init__()
        
        # Сбросить конфиг при старте
        try:
            reset_config()
        except Exception:
            pass
        
        self.setWindowTitle("JSON Comparator")
        self.setGeometry(100, 100, 1000, 800)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: #fafafa; color: black;")
        
        self.drag_pos = None
        
        # ─────────────────────────────────────────────────────────
        # Определяем пути ресурсов (для PyInstaller)
        # ─────────────────────────────────────────────────────────
        
        def resource_path(relpath: str) -> str:
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base = sys._MEIPASS
            else:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            return os.path.join(base, relpath)
        
        assets_dir = resource_path("assets")
        
        # Загружаем шрифт
        font_id = QFontDatabase.addApplicationFont(
            os.path.join(assets_dir, "../../../../Downloads/ChakraPetch-Regular.otf")
        )
        families = QFontDatabase.applicationFontFamilies(font_id)
        family = families[0] if families else "Arial"
        chakra_font = QFont(family, 16, QFont.Bold)
        
        # ─────────────────────────────────────────────────────────
        # Кнопка меню (консоль)
        # ─────────────────────────────────────────────────────────
        
        self.menu_btn = QPushButton(self)
        self.menu_btn.setGeometry(12, 7, 35, 35)
        self.menu_btn.setIcon(QIcon(os.path.join(assets_dir, "console.png")))
        self.menu_btn.setIconSize(QSize(33, 33))
        self.menu_btn.setFlat(True)
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #bfbfbf;
                border-radius: 3px;
            }
        """)
        
        # ─────────────────────────────────────────────────────────
        # Кнопки управления окном
        # ─────────────────────────────────────────────────────────
        
        self.min_btn = QPushButton(self)
        self.min_btn.setGeometry(940, 7, 25, 25)
        self.min_btn.setIcon(QIcon(os.path.join(assets_dir, "minus.png")))
        self.min_btn.setIconSize(QSize(17, 17))
        
        self.max_btn = QPushButton(self)
        self.max_btn.setGeometry(0, 0, 0, 0)
        self.max_btn.hide()
        
        self.close_btn = QPushButton(self)
        self.close_btn.setGeometry(970, 7, 25, 25)
        self.close_btn.setIcon(QIcon(os.path.join(assets_dir, "close.png")))
        self.close_btn.setIconSize(QSize(17, 17))
        
        hover_style = "QPushButton:hover {background-color: #bfbfbf; border: none;}"
        for b in [self.min_btn, self.max_btn]:
            b.setFlat(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(hover_style)
        
        self.close_btn.setFlat(True)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("QPushButton:hover {background-color: #cc4c4c; border: none;}")
        
        self.min_btn.clicked.connect(self.showMinimized)
        self.close_btn.clicked.connect(self.close)
        
        # ─────────────────────────────────────────────────────────
        # Главное изображение
        # ─────────────────────────────────────────────────────────
        
        self.main_img = QLabel(self)
        self.main_img.setGeometry(2, 64, 996, 620)
        pixmap = QPixmap(os.path.join(assets_dir, "main_image.png"))
        scaled = pixmap.scaled(1825, 858, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.main_img.setPixmap(scaled)
        self.main_img.setAlignment(Qt.AlignCenter)
        
        # ─────────────────────────────────────────────────────────
        # Кнопка "Check"
        # ─────────────────────────────────────────────────────────
        
        self.check_btn = QPushButton("Check", self)
        self.check_btn.setGeometry(433, 324, 100, 49)
        self.check_btn.raise_()
        self.check_btn.setFont(chakra_font)
        self.check_btn.setStyleSheet(
            "QPushButton {"
            " background-color: #ececec;"
            " border: 2px solid #cbcbcb;"
            " border-radius: 8px;"
            " padding: 5px;"
            "}"
            "QPushButton:hover {background-color: #dfdfdf;}"
            "QPushButton:pressed {background-color: #c8c8c8;}"
        )
        
        # ─────────────────────────────────────────────────────────
        # Лейбл с результатом
        # ─────────────────────────────────────────────────────────
        
        self.result_label = QLabel("Your result: --%", self)
        self.result_label.setGeometry(0, 30, self.width(), 30)
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.setFont(QFont(family, 18, QFont.Bold))
        self.result_label.hide()
        
        # ─────────────────────────────────────────────────────────
        # Папки с результатами
        # ─────────────────────────────────────────────────────────
        
        self.low_pack_dir = os.path.join(assets_dir, "fail_pack")
        self.high_pack_dir = os.path.join(assets_dir, "success_pack")
        
        self._fail_pixmaps = None
        self._success_pixmaps = None
        self._result_images = []
        
        # ─────────────────────────────────────────────────────────
        # Подключаем обработчики
        # ─────────────────────────────────────────────────────────
        
        self.check_btn.clicked.connect(self._start_check_thread)
        
        # ─────────────────────────────────────────────────────────
        # Консоль
        # ─────────────────────────────────────────────────────────
        
        self.console = ConsoleFrame(self)
        self.console.setGeometry(-780, -520, 780, 520)
        self.console.hide()
        
        self.console.close_btn.clicked.connect(self.hide_console)
        self.menu_btn.clicked.connect(self.toggle_console)
        self.console.input.returnPressed.connect(self._submit_console_input)
        
        self.is_maximized = False
        self.anim = None
        
        # Фиксированный размер окна
        self.setFixedSize(self.size())
    
    def write_to_console(self, text: str):
        """Написать текст в консоль."""
        self.console.write(text)
    
    def _submit_console_input(self):
        """Обработать команду из консоли."""
        text = self.console.input.text()
        
        if not text.strip():
            return
        
        # Выводим команду в консоль
        self.console.write(text)
        
        cmd = text.strip().lower()
        
        # ─────────────────────────────────────────────────────────
        # Команда для запуска парсера + компаратора
        # ─────────────────────────────────────────────────────────
        
        if cmd in (
            "run", "parse", "start",
            "begin", "initiate_parsing",
            "initiate_data_parsing_and_comparison",
            "execute_data_parsing_and_comparison"
        ):
            self.console.write("Launching parser...")
            th = threading.Thread(target=self._run_backend_parse, daemon=True)
            th.start()
            self.console.input.clear()
            return
        
        # ─────────────────────────────────────────────────────────
        # Команда помощи
        # ─────────────────────────────────────────────────────────
        
        if cmd in ("help", "show_help", "display_help_information", "present_available_commands_help_information"):
            help_text = (
                "Available commands:\n"
                " examples <N>  - Select examples (1, 2, 3, ...)\n"
                " examples     - Show available examples\n"
                " ip <addr>    - Set GNS3 server IP\n"
                " port <N>     - Set server port\n"
                " project <P>  - Set project name or .gns3project path\n"
                " login <user> - Set telnet login\n"
                " password <p> - Set telnet password\n"
                " local <T/F>  - Enable local import mode\n"
                " desktop <T/F>- Save results to Desktop\n"
                " show / status- Show current settings\n"
                " help         - Show this help\n"
                " run / parse  - Execute parsing and comparison\n"
            )
            for ln in help_text.splitlines():
                self.console.write(ln)
            self.console.input.clear()
            return
        
        # ─────────────────────────────────────────────────────────
        # ⭐ НОВОЕ: Команда для выбора эталона
        # ─────────────────────────────────────────────────────────
        
        if cmd == "examples" or text.strip().lower().startswith("examples "):
            parts = text.strip().split()
            if len(parts) < 2:
                available = list_examples()
                if available:
                    self.console.write(f"Available examples: {available}")
                    self.console.write("Usage: examples <number>")
                else:
                    self.console.write("No examples found")
            else:
                try:
                    num = int(parts[1])
                    set_config("example_num", num)
                    self.console.write(f"OK: example_num={num}")
                except ValueError:
                    self.console.write(f"Invalid examples number: {parts[1]}")
            self.console.input.clear()
            return
        
        # ─────────────────────────────────────────────────────────
        # ⭐ НОВОЕ: Команда для показа доступных эталонов
        # ─────────────────────────────────────────────────────────
        
        if cmd == "examples":
            examples = list_examples()
            if examples:
                self.console.write(f"Available examples: {examples}")
            else:
                self.console.write("No examples found in core/examples")
            self.console.input.clear()
            return
        
        # ─────────────────────────────────────────────────────────
        # ⭐ НОВОЕ: Команда для показа текущей конфигурации
        # ─────────────────────────────────────────────────────────
        
        if cmd in ("show", "status"):
            cfg = get_config()
            status_text = (
                f"Current configuration:\n"
                f"  IP: {cfg.get('ip')}\n"
                f"  Port: {cfg.get('port')}\n"
                f"  Project: {cfg.get('project')}\n"
                f"  Example: {cfg.get('example_num') or 'not set'}\n"
                f"  Local: {cfg.get('local')}\n"
                f"  Login: {cfg.get('login')}"
            )
            for ln in status_text.splitlines():
                self.console.write(ln)
            self.console.input.clear()
            return
        
        # ─────────────────────────────────────────────────────────
        # Остальные команды обрабатываются cli_commands
        # ─────────────────────────────────────────────────────────
        
        try:
            feedback = handle_command(text)
        except Exception as e:
            feedback = f"Command error: {e}"
        
        if feedback:
            for ln in feedback.splitlines():
                self.console.write(ln)
        
        self.console.input.clear()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.console.isVisible() and not self.console.geometry().contains(event.pos()):
                self.hide_console()
            else:
                self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()
    
    def toggle_maximize(self):
        if self.is_maximized:
            self.showNormal()
        else:
            self.showMaximized()
        self.is_maximized = not self.is_maximized
    
    def toggle_console(self, event=None):
        if self.console.isVisible():
            self.hide_console()
        else:
            self.console.show()
            anim = QPropertyAnimation(self.console, b"geometry")
            anim.setDuration(200)
            anim.setStartValue(QRect(-780, -520, 780, 520))
            anim.setEndValue(QRect(2, 2, 780, 520))
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self.anim = anim
            
            if not getattr(self.console, "_boot_msg", False):
                self.console.write("System started.")
                self.console.write("Type 'help' for available commands.")
                self.console.write("=" * 60)
                self.console._boot_msg = True
            
            self.console.input.setFocus()
    
    def hide_console(self):
        anim = QPropertyAnimation(self.console, b"geometry")
        anim.setDuration(200)
        anim.setStartValue(QRect(2, 2, 780, 520))
        anim.setEndValue(QRect(-780, -520, 780, 520))
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.start()
        self.anim = anim
        anim.finished.connect(self.console.hide)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
    
    def _run_backend_parse(self):
        """Запустить парсер и компаратор."""
        try:
            # Загружаем текущий выбранный пример
            cfg = get_config()
            example_num = cfg.get("example_num")
            
            # Если пример не выбран, спрашиваем
            if not example_num:
                examples = list_examples()
                if not examples:
                    self.write_to_console("❌ No examples found in core/examples")
                    return
                
                self.write_to_console(f"📚 Available examples: {examples}")
                self.write_to_console("⚠️  Please select examples using command:")
                self.write_to_console("   examples <number>")
                self.write_to_console("   Example: examples 2")
                return
            
            # Запускаем парсер + компаратор
            result = run_parse(example_num=example_num, log_func=self.write_to_console)
            
            # Извлекаем результаты
            student_data = result.get("student_data", {})
            similarity = result.get("similarity", 0)
            report_path = result.get("report_path")
            example_num = result.get("example_num")
            
            # Выводим результаты в консоль
            self.write_to_console(f"✅ Similarity: {similarity:.2f}%")
            if report_path:
                self.write_to_console(f"📄 Report: {report_path}")
            
            # Отображаем графический результат
            self.show_result(similarity)
        
        except Exception as e:
            self.write_to_console(f"❌ Error during check: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_check_thread(self):
        """Запустить проверку в отдельном потоке."""
        th = threading.Thread(target=self._run_backend_parse, daemon=True)
        th.start()
    
    def _load_pack_pixmaps(self, img_dir):
        """Загрузить все изображения из директории."""
        pixmaps = []
        if not os.path.isdir(img_dir):
            return pixmaps
        
        for fname in sorted(os.listdir(img_dir)):
            if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
                continue
            
            path = os.path.join(img_dir, fname)
            pm = QPixmap(path)
            if pm.isNull():
                continue
            
            pm = pm.scaled(125, 125, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pixmaps.append(pm)
        
        return pixmaps
    
    def show_result(self, value: float):
        """Отобразить результат сравнения."""
        # Пороговое значение: < 99 → неуспех, ≥ 99 → успех
        if value < 99.0:
            img_dir = self.low_pack_dir
        else:
            img_dir = self.high_pack_dir
        
        # Обновляем текст результата
        self.result_label.setText(f"Your result: {value:.2f}%")
        self.result_label.show()
        
        # Удаляем старые изображения
        for lbl in self._result_images:
            lbl.setParent(None)
            lbl.deleteLater()
        self._result_images.clear()
        
        # Выбираем набор картинок
        if img_dir == self.low_pack_dir:
            if self._fail_pixmaps is None:
                self._fail_pixmaps = self._load_pack_pixmaps(self.low_pack_dir)
            pixmaps = self._fail_pixmaps
        else:
            if self._success_pixmaps is None:
                self._success_pixmaps = self._load_pack_pixmaps(self.high_pack_dir)
            pixmaps = self._success_pixmaps
        
        if not pixmaps:
            return
        
        # Выбираем случайное изображение
        pm = random.choice(pixmaps)
        
        # Позиция: центр по горизонтали, внизу
        img_w = pm.width()
        img_h = pm.height()
        x = max(0, (self.width() - img_w) // 2)
        
        y_candidate = self.main_img.y() + self.main_img.height() + 10
        y_bottom = self.height() - img_h - 10
        y = min(y_candidate, y_bottom)
        
        lbl = QLabel(self)
        lbl.setPixmap(pm)
        lbl.setGeometry(x, y, img_w, img_h)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.show()
        
        self._result_images.append(lbl)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
