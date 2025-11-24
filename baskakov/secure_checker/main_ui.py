import json
from pathlib import Path

from PyQt5.QtCore import Qt, QRect, QEasingCurve, QPropertyAnimation, QSize, QTimer
from PyQt5.QtGui import (
    QPixmap, QIcon, QPainter, QPen, QFontMetrics,
    QColor, QPalette, QFontDatabase, QFont
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QTextEdit, QFrame, QLineEdit, QProxyStyle, QStyle
)
import sys
import os
import random
import threading


from secure_checker.cli_commands import handle_command
from secure_checker.backend_bridge import run_parse




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
        uw = max(fm.averageCharWidth(), 8)  # если захочешь использовать в будущем
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

        self.drag_pos = None

        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        assets_dir = os.path.join(base_dir, "assets")

        font_id = QFontDatabase.addApplicationFont(os.path.join(assets_dir, "ChakraPetch-Regular.otf"))
        family = QFontDatabase.applicationFontFamilies(font_id)[0]
        chakra_font = QFont(family, 16, QFont.Bold)

        # Кнопка меню (консоль)
        self.menu_btn = QPushButton(self)
        self.menu_btn.setGeometry(12, 7, 35, 35)
        self.menu_btn.setIcon(QIcon(os.path.join(assets_dir, "icons8-консоль-48 (1).png")))
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
        self.min_btn.setIcon(QIcon(os.path.join(assets_dir, "minus.png")))
        self.min_btn.setIconSize(QSize(17, 17))

        self.max_btn = QPushButton(self)
        self.max_btn.setGeometry(940, 7, 25, 25)
        self.max_btn.setIcon(QIcon(os.path.join(assets_dir, "square.png")))
        self.max_btn.setIconSize(QSize(17, 17))

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
        self.max_btn.clicked.connect(self.toggle_maximize)
        self.close_btn.clicked.connect(self.close)

        # Главное изображение
        self.main_img = QLabel(self)
        self.main_img.setGeometry(2, 64, 996, 620)
        pixmap = QPixmap(os.path.join(assets_dir, "main_image.png"))
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
        self.result_label.setFont(QFont(family, 18, QFont.Bold))
        self.result_label.hide()

        # Папки с картинками
        self.low_pack_dir = os.path.join(assets_dir, "fail_pack")
        self.high_pack_dir = os.path.join(assets_dir, "success_pack")


        # Кешированные пиксмэпы, чтобы не грузить картинки каждый раз
        self._fail_pixmaps = None
        self._success_pixmaps = None

        # QLabel с картинками результата
        self._result_images = []

        # Обработчик кнопки "Проверить"
        self.check_btn.clicked.connect(self.show_result)

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

    def _run_backend_parse(self):
        try:
            # Запускаем парсер
            result = run_parse(log_func=self.write_to_console)
            print(result)

            # ✅ Сохраняем результаты на рабочий стол
            desktop_path = str(Path.home() / "Desktop")

            # Создаём папку для результатов парса (например "parse_results_2025-11-17")
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            results_dir = os.path.join(desktop_path, f"parse_results_{timestamp}")

            os.makedirs(results_dir, exist_ok=True)

            # Сохраняем результаты в JSON
            output_file = os.path.join(results_dir, "parse_results.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            self.write_to_console(f"✅ Результаты сохранены: {output_file}")
            self.write_to_console(f"   Открыть папку: {results_dir}")

            # (Опционально) Сохраняем каждый узел в отдельный файл
            data = result.get("data", {})
            for node_name, node_config in data.items():
                node_file = os.path.join(results_dir, f"{node_name}.json")
                with open(node_file, "w", encoding="utf-8") as f:
                    json.dump(node_config, f, ensure_ascii=False, indent=2)

            self.write_to_console(f"💾 Сохранено {len(data)} конфигов узлов")

        except Exception as e:
            self.write_to_console(f"❌ Ошибка запуска парсера: {e}")

    def _load_pack_pixmaps(self, img_dir):
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

    def show_result(self):
        # 66% — < 99.0, 34% — >= 99.0
        if random.random() < 0.66:
            value = round(random.uniform(1.0, 99.0), 1)
            img_dir = self.low_pack_dir
        else:
            value = round(random.uniform(99.0, 100.0), 1)
            img_dir = self.high_pack_dir

        # Обновляем текст результата
        self.result_label.setText(f"Ваш результат: {value}%")
        self.result_label.show()

        # Удаляем старое изображение (если было)
        for lbl in self._result_images:
            lbl.setParent(None)
            lbl.deleteLater()
        self._result_images.clear()

        # Выбираем набор картинок для текущего диапазона
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

        # Берём ОДНО случайное изображение из набора
        pm = random.choice(pixmaps)

        # Координаты: центр по горизонтали, снизу, но без заезда на main_img
        img_w = pm.width()
        img_h = pm.height()

        x = max(0, (self.width() - img_w) // 2)

        # Позиция по вертикали: сначала пробуем сразу под main_img
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
