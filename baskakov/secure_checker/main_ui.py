import json
import os
import sys
import threading
from pathlib import Path
from datetime import datetime

from PyQt5.QtCore import Qt, QRect, QEasingCurve, QPropertyAnimation, QSize, QTimer
from PyQt5.QtGui import (
    QPixmap, QIcon, QPainter, QPen, QFontMetrics,
    QColor, QPalette, QFontDatabase, QFont
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QTextEdit, QFrame, QLineEdit, QProxyStyle, QStyle
)

from secure_checker.cli_commands import handle_command
from secure_checker.backend_bridge import run_parse
from secure_checker.core.comparator.compare import compare_configs


class NoCursorStyle(QProxyStyle):
    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PM_TextCursorWidth:
            return 0
        return super().pixelMetric(metric, option, widget)


class CmdLineEdit(QLineEdit):
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
        pr = self.cursorRect()
        x = pr.x()
        y = pr.bottom() - 3
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawRect(x + 6, y, 10, 2)


class ConsoleFrame(QFrame):
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
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JSON Comparator")
        self.setGeometry(100, 100, 1000, 800)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: #fafafa; color: black;")
        self.drag_pos = None

        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        assets_dir = os.path.join(base_dir, "assets")

        # Загрузка шрифта
        font_path = os.path.join(assets_dir, "ChakraPetch-Regular.otf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                family = QFontDatabase.applicationFontFamilies(font_id)[0]
                chakra_font = QFont(family, 16, QFont.Bold)
            else:
                chakra_font = QFont("Arial", 16, QFont.Bold)
        else:
            chakra_font = QFont("Arial", 16, QFont.Bold)

        # Кнопка меню (консоль)
        self.menu_btn = QPushButton(self)
        self.menu_btn.setGeometry(12, 7, 35, 35)
        icon_path = os.path.join(assets_dir, "icons8-консоль-48 (1).png")
        if os.path.exists(icon_path):
            self.menu_btn.setIcon(QIcon(icon_path))
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

        # Кнопки управления окном
        self.min_btn = QPushButton(self)
        self.min_btn.setGeometry(910, 7, 25, 25)
        minus_path = os.path.join(assets_dir, "minus.png")
        if os.path.exists(minus_path):
            self.min_btn.setIcon(QIcon(minus_path))
            self.min_btn.setIconSize(QSize(17, 17))

        self.max_btn = QPushButton(self)
        self.max_btn.setGeometry(940, 7, 25, 25)
        square_path = os.path.join(assets_dir, "square.png")
        if os.path.exists(square_path):
            self.max_btn.setIcon(QIcon(square_path))
            self.max_btn.setIconSize(QSize(17, 17))

        self.close_btn = QPushButton(self)
        self.close_btn.setGeometry(970, 7, 25, 25)
        close_path = os.path.join(assets_dir, "close.png")
        if os.path.exists(close_path):
            self.close_btn.setIcon(QIcon(close_path))
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
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.close)

        # Главное изображение
        self.main_img = QLabel(self)
        self.main_img.setGeometry(2, 64, 996, 620)
        main_img_path = os.path.join(assets_dir, "main_image.png")
        if os.path.exists(main_img_path):
            pixmap = QPixmap(main_img_path)
            scaled = pixmap.scaled(1825, 858, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.main_img.setPixmap(scaled)
        self.main_img.setAlignment(Qt.AlignCenter)

        # Кнопка "Проверить"
        self.check_btn = QPushButton("Проверить", self)
        self.check_btn.setGeometry(433, 324, 100, 49)
        self.check_btn.raise_()
        self.check_btn.setFont(chakra_font)
        self.check_btn.setStyleSheet(
            "QPushButton {border: 0.5px solid black; background: white; font-size: 16px; font-weight: bold;}"
            " QPushButton:hover {background: #e6e6e6;}"
        )

        # Надпись "Ваш результат: --%"
        self.result_label = QLabel("Ваш результат: --%", self)
        self.result_label.setGeometry(0, 30, self.width(), 30)
        self.result_label.setAlignment(Qt.AlignCenter)
        result_font = QFont(chakra_font)
        result_font.setPointSize(18)
        self.result_label.setFont(result_font)
        self.result_label.hide()

        # Обработчик кнопки "Проверить" - теперь запускает парсер и компаратор
        self.check_btn.clicked.connect(self.run_check)

        # Консоль
        self.console = ConsoleFrame(self)
        self.console.setGeometry(-780, -520, 780, 520)
        self.console.hide()
        self.console.close_btn.clicked.connect(self.hide_console)
        self.menu_btn.clicked.connect(self.toggle_console)
        self.console.input.returnPressed.connect(self._submit_console_input)

        self.is_maximized = False
        self.anim = None

    def write_to_console(self, text: str):
        self.console.write(text)

    def _submit_console_input(self):
        text = self.console.input.text()
        if text.strip():
            # эхо команды
            self.console.write(text)
            cmd = text.strip().lower()

            # запуск парсера
            if cmd in ("run", "parse", "start"):
                self.console.write("Запуск парсера...")
                th = threading.Thread(target=self._run_backend_parse, daemon=True)
                th.start()
            else:
                # команды настройки (ip, port, project, login, password, local, desktop, show, help)
                try:
                    feedback = handle_command(text)
                except Exception as e:
                    feedback = f"Ошибка команды: {e}"
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
                self.console.write("Система запущена.")
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

    def run_check(self):
        """
        Обработчик кнопки "Проверить" - запускает парсер и компаратор
        """
        self.result_label.setText("Ваш результат: проверка...")
        self.result_label.show()
        
        # Запускаем в отдельном потоке
        th = threading.Thread(target=self._run_check_thread, daemon=True)
        th.start()

    def _run_check_thread(self):
        """
        Полный цикл: парсер -> компаратор -> отображение результата
        """
        try:
            # Определяем путь к %APPDATA%/Z69
            appdata = os.getenv('APPDATA')
            if appdata:
                base_dir = Path(appdata) / "Z69"
            else:
                base_dir = Path.home() / "Z69"
            
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Шаг 1: Запуск парсера
            self.write_to_console("[1/3] Запуск парсера GNS3...")
            result = run_parse(log_func=self.write_to_console)
            
            if not result or "data" not in result:
                self.write_to_console("✘ Ошибка: парсер не вернул данные")
                self.result_label.setText("Ваш результат: Ошибка парсера")
                return
            
            student_data = result.get("data", {})
            
            
            # Шаг 3: Запуск компаратора
        self.write_to_console("[2/2] Сравнение с эталоном...")            
            results_dir = base_dir / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            
            csv_file = results_dir / f"report_{timestamp}.csv"
            
            similarity = compare_configs(student_data, csv_file)
            
            # Отображение результата
            self.result_label.setText(f"Ваш результат: {similarity:.2f}%")
            
            self.write_to_console(f"\n✓ Проверка завершена!")
            self.write_to_console(f"Результат: {similarity:.2f}%")
            self.write_to_console(f"Отчёт сохранён: {csv_file}")
            
        except Exception as e:
            self.write_to_console(f"\n✘ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            self.result_label.setText("Ваш результат: Ошибка")

    def _run_backend_parse(self):
        """
        Запуск парсера из консоли (без компаратора)
        """
        try:
            # Определяем путь к %APPDATA%/Z69
            appdata = os.getenv('APPDATA')
            if appdata:
                base_dir = Path(appdata) / "Z69"
            else:
                base_dir = Path.home() / "Z69"
            
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Запускаем парсер
            result = run_parse(log_func=self.write_to_console)
            
            # Сохраняем результаты
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            parse_file = base_dir / f"parse_{timestamp}.json"
            
            with parse_file.open("w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            self.write_to_console(f"\n✓ Результаты сохранены: {parse_file}")
            
            # Сохраняем каждый узел отдельно
            data = result.get("data", {})
            for node_name, node_config in data.items():
                node_file = base_dir / f"{node_name}_{timestamp}.json"
                with node_file.open("w", encoding="utf-8") as f:
                    json.dump(node_config, f, ensure_ascii=False, indent=2)
            
            self.write_to_console(f"Сохранено {len(data)} конфигов узлов")
            
        except Exception as e:
            self.write_to_console(f"✘ Ошибка запуска парсера: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
