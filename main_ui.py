import json
from pathlib import Path

from PyQt5.QtCore import Qt, QRect, QEasingCurve, QPropertyAnimation, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QPixmap, QIcon, QPainter, QPen, QFontMetrics,
    QColor, QPalette, QFontDatabase, QFont, QTextCharFormat, QTextCursor
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel,
    QTextEdit, QFrame, QLineEdit, QProxyStyle, QStyle, QFileDialog
)
import sys
import os
import threading
from pathlib import Path

# Add project root to sys.path so GNS3 imports work when running script directly
current_file = Path(__file__).resolve()
# Так как файл в корне Z69, его родителем и является корень проекта
project_root = current_file.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
from modules.GNS3.cli_commands import handle_command
from modules.GNS3.backend_bridge import run_parse, _load, run_compare
from modules.GNS3.core.advanced_logger import init_logger, get_logger, set_gui_callback, get_default_log_path


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


class ConsoleDragHandle(QFrame):
    """
    A custom QFrame to act as a draggable handle for the ConsoleFrame.
    """
    def __init__(self, parent=None, console_frame=None):
        super().__init__(parent)
        self.console_frame = console_frame # Reference to the parent ConsoleFrame
        self.drag_pos = None
        self.setStyleSheet("background-color: black;")
        self.setCursor(Qt.PointingHandCursor) # Pointing hand cursor

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            if self.console_frame:
                # Move the parent ConsoleFrame relative to its parent (MainWindow)
                self.console_frame.move(self.console_frame.parent().mapFromGlobal(event.globalPos() - self.drag_pos))
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

class ConsoleFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: black;")
        
        self.drag_handle = ConsoleDragHandle(self, console_frame=self)
        self.drag_handle.setGeometry(0, 0, self.width(), 25) # Initial geometry, will be updated in resizeEvent

        # Move close_btn to drag_handle
        self.close_btn = QPushButton("×", self.drag_handle) # Parent is now drag_handle
        self.close_btn.setStyleSheet(
            "QPushButton {border: none; background: black; color: white; font-size: 16px;}"
            " QPushButton:hover {background: #cc4c4c;}"
        )
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.move(self.drag_handle.width() - self.close_btn.width() - 5, 3) # Position relative to drag_handle
        self.close_btn.raise_() # Ensure close button is on top of drag_handle
        
        self.output = QTextEdit(self)
        self.output.setReadOnly(True)
        self.output.setStyleSheet(
            "border: none; background: black; color: white; font-family: Consolas; font-size: 16px;"
        )

        self.input = CmdLineEdit(self)

    def resizeEvent(self, event):
        # Ensure child widgets resize correctly with the console frame
        w = self.width()
        h = self.height()
        
        self.drag_handle.setGeometry(0, 0, w, 25)
        self.close_btn.move(w - self.close_btn.width() - 5, 3) # Position relative to drag_handle

        output_top = self.drag_handle.height() + 5 # Output starts below drag_handle
        input_height = 22
        input_bottom_margin = 8
        
        self.output.setGeometry(5, output_top, w - 10, h - output_top - input_height - input_bottom_margin)
        self.input.setGeometry(5, h - input_height - input_bottom_margin, w - 10, input_height)
        
        super().resizeEvent(event)

    def write(self, text: str, level="INFO"):
        """Write text with optional color based on level."""
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # Define colors
        if level == "ERROR":
            color = QColor("#ff6b6b")  # red
        else:
            color = QColor("#ffffff")  # white
        
        format = QTextCharFormat()
        format.setForeground(color)
        cursor.setCharFormat(format)
        cursor.insertText(text + "\n")
        self.output.moveCursor(QTextCursor.End)

    def update_progress(self, text: str):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        if getattr(self, '_progress_mode', False):
            cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
        else:
            self._progress_mode = True
            if cursor.positionInBlock() > 0:
                cursor.insertText("\n")
                
        format = QTextCharFormat()
        format.setForeground(QColor("#55aaff")) # Голубой цвет загрузки
        cursor.setCharFormat(format)
        cursor.insertText(text)
        self.output.moveCursor(QTextCursor.End)

    def finish_progress(self, prefix="", msg=""):
        if getattr(self, '_progress_mode', False):
            cursor = self.output.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cursor.removeSelectedText()
            
            bar_str = "█" * 20
            text = f"{prefix:<22} [{bar_str}] {msg}"
            
            format = QTextCharFormat()
            format.setForeground(QColor("#00ff00")) # Зеленый цвет завершения
            cursor.setCharFormat(format)
            cursor.insertText(text + "\n")
            
            self._progress_mode = False
            self.output.moveCursor(QTextCursor.End)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        super().paintEvent(event)


class MainWindow(QMainWindow):
    log_message_signal = pyqtSignal(str, str, str) # console_type, msg, level
    docker_progress_msg_signal = pyqtSignal(str)
    docker_progress_state_signal = pyqtSignal(int, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Z69")
        self.setGeometry(100, 100, 1030, 800)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: #fafafa; color: black;")
        self.drag_pos = None

        # --- ИЗМЕНЕНО: Ширина левой панели ---
        self.LEFT_MARGIN = 53

        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            # Гарантируем, что base_dir указывает на корень Z69 для доступа к assets
            base_dir = os.path.dirname(os.path.abspath(__file__))

        assets_dir = os.path.join(base_dir, "assets")
        
        font_id = QFontDatabase.addApplicationFont(os.path.join(assets_dir, "ChakraPetch-Regular.otf"))
        # Проверка на успешную загрузку шрифта, чтобы избежать IndexError
        if font_id != -1 and QFontDatabase.applicationFontFamilies(font_id):
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
        else:
            family = "Arial"
        chakra_font = QFont(family, 16, QFont.Bold)

        # Initialize logger
        log_file = get_default_log_path()
        init_logger(log_file=str(log_file), student_mode=True)
        self.log_message_signal.connect(self._handle_log_message)
        set_gui_callback(self._log_to_console)
        self.docker_progress_msg_signal.connect(self._handle_docker_progress_msg)
        self.docker_progress_state_signal.connect(self._set_docker_progress_state)
        
        self.docker_progress_timer = QTimer(self)
        self.docker_progress_timer.timeout.connect(self._animate_docker_progress)
        self.docker_progress_step = 0
        self.docker_progress_stage = 0 # 0: выкл, 1: тех. процессы, 2: проверка
        self.docker_progress_msg = ""

        # --- НОВОЕ: Стили для кнопок консоли ---
        button_style = """
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 1px;
            }
            QPushButton:hover {
                background-color: #bfbfbf;
                border-radius: 3px;
            }
        """
        self.button_style_normal = button_style
        self.button_style_active = """
            QPushButton {
                background: #bfbfbf; /* Gray background */
                border: none;
                padding: 1px;
                border-radius: 3px;
            }
        """

        self.console_btn_1 = QPushButton(self)
        self.console_btn_1.setGeometry(11, 7, 35, 35)
        self.console_btn_1.setIcon(QIcon(os.path.join(assets_dir, "gns3.png")))
        self.console_btn_1.setIconSize(QSize(33, 33))
        self.console_btn_1.setFlat(True)
        self.console_btn_1.setCursor(Qt.PointingHandCursor)
        self.console_btn_1.setStyleSheet(self.button_style_normal)

        self.console_btn_2 = QPushButton(self)
        self.console_btn_2.setGeometry(12, 52, 35, 35)
        self.console_btn_2.setIcon(QIcon(os.path.join(assets_dir, "docker.png")))
        self.console_btn_2.setIconSize(QSize(38, 38))
        self.console_btn_2.setFlat(True)
        self.console_btn_2.setCursor(Qt.PointingHandCursor)
        self.console_btn_2.setStyleSheet(self.button_style_normal)

        self.console_btn_3 = QPushButton(self)
        self.console_btn_3.setGeometry(12, 97, 35, 35)
        self.console_btn_3.setIcon(QIcon(os.path.join(assets_dir, "folder.png")))
        self.console_btn_3.setIconSize(QSize(33, 33))
        self.console_btn_3.setFlat(True)
        self.console_btn_3.setCursor(Qt.PointingHandCursor)
        self.console_btn_3.setStyleSheet(self.button_style_normal)

        self.active_console_button = None # Для отслеживания активной кнопки консоли

        # Window control buttons
        self.min_btn = QPushButton(self)
        self.min_btn.setGeometry(self.width() - 90, 4, 25, 25)
        self.min_btn.setIcon(QIcon(os.path.join(assets_dir, "minus.png")))
        self.min_btn.setIconSize(QSize(17, 17))

        self.max_btn = QPushButton(self)
        self.max_btn.setGeometry(self.width() - 60, 4, 25, 25)
        self.max_btn.setIcon(QIcon(os.path.join(assets_dir, "square.png")))
        self.max_btn.setIconSize(QSize(17, 17))

        self.close_btn = QPushButton(self)
        self.close_btn.setGeometry(self.width() - 30, 4, 25, 25)
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

        # Main image
        self.main_img = QLabel(self)
        self.main_img.setGeometry(2 + self.LEFT_MARGIN, 64, 996, 620)
        pixmap = QPixmap(os.path.join(assets_dir, "main_image.png"))
        self.main_img.setPixmap(pixmap.scaled(1825, 858, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.main_img.setAlignment(Qt.AlignCenter)

        # --- NEW: Central icon for GNS3/Docker mode ---
        self.central_icon_label = QLabel(self)
        self.gns3_central_icon_size = QSize(56, 56) # Отдельный размер для иконки GNS3
        self.docker_central_icon_size = QSize(68, 68) # Отдельный размер для иконки Docker
        self.gns3_icon_pixmap = QPixmap(os.path.join(assets_dir, "gns3.png")).scaled(self.gns3_central_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.docker_icon_pixmap = QPixmap(os.path.join(assets_dir, "docker.png")).scaled(self.docker_central_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.central_icon_label_x = 522 # Приблизительная центральная координата X
        self.central_icon_label_y = 314 # Приблизительная центральная координата Y
        self.central_icon_label.setGeometry(self.central_icon_label_x, self.central_icon_label_y, self.gns3_central_icon_size.width(), self.gns3_central_icon_size.height()) # Изначально устанавливаем размер GNS3
        self.central_icon_label.setStyleSheet("background-color: transparent;") # Устанавливаем прозрачный фон
        self.central_icon_label.setAlignment(Qt.AlignCenter)
        self.central_icon_label.hide()


        # --- ИЗМЕНЕНО: Две независимые консоли ---
        self.gns3_console = ConsoleFrame(self)
        self.gns3_console.setGeometry(self.LEFT_MARGIN - 780, 2, 780, 520)
        self.gns3_console.hide()
        self.gns3_console.close_btn.clicked.connect(self.hide_console)
        self.gns3_console.input.returnPressed.connect(self._submit_gns3_input)

        self.docker_console = ConsoleFrame(self)
        self.docker_console.setGeometry(self.LEFT_MARGIN - 780, 2, 780, 520)
        self.docker_console.hide()
        self.docker_console.close_btn.clicked.connect(self.hide_console)
        self.docker_console.input.returnPressed.connect(self._submit_docker_input)

        self.console_btn_1.clicked.connect(self._on_console_button_clicked)
        self.console_btn_2.clicked.connect(self._on_console_button_clicked)
        self.console_btn_3.clicked.connect(self._on_folder_button_clicked)

        self.is_maximized = False
        self.folder_button_active = False # New state for folder button
        self.anim = None

    def _log_to_console(self, message: str, level: str):
        """Logger callback: outputs message to console with color."""
        # Перенаправляем вызов в безопасный для потоков сигнал
        self.log_message_signal.emit("both", message, level)

    def _handle_log_message(self, console: str, message: str, level: str):
        """Thread-safe logging to GUI"""
        if console == "docker":
            self.docker_console.write(message, level)
        elif console == "gns3":
            self.gns3_console.write(message, level)
        elif console == "both":
            color_level = "ERROR" if level in ("ERROR", "CRITICAL") else "INFO"
            if self.gns3_console.isVisible() or level == "ERROR":
                self.gns3_console.write(message, color_level)
            if self.docker_console.isVisible() or level == "ERROR":
                self.docker_console.write(message, color_level)

    def _handle_docker_progress_msg(self, msg: str):
        if "Начало проверки" in msg or "Проверка лабораторной" in msg:
            if self.docker_progress_stage == 1:
                self._set_docker_progress_state(2, msg)
            else:
                self.docker_progress_msg = msg
        else:
            self.docker_progress_msg = msg

    def _set_docker_progress_state(self, stage: int, initial_msg: str):
        if self.docker_progress_stage != 0 and self.docker_progress_stage != stage:
            prefix = "[Технические процессы]" if self.docker_progress_stage == 1 else "[Проверка файлов]"
            self.docker_console.finish_progress(prefix, "Завершено")
            
        if stage == 0:
            if self.docker_progress_stage != 0:
                prefix = "[Технические процессы]" if self.docker_progress_stage == 1 else "[Проверка файлов]"
                self.docker_console.finish_progress(prefix, "Завершено")
            self.docker_progress_timer.stop()
            self.docker_progress_stage = 0
        else:
            self.docker_progress_stage = stage
            self.docker_progress_msg = initial_msg
            self.docker_progress_timer.start(100) # Обновление анимации каждые 100мс

    def _animate_docker_progress(self):
        self.docker_progress_step += 1
        prefix = "[Технические процессы]" if self.docker_progress_stage == 1 else "[Проверка файлов]"
        
        bar_len = 20
        pos = self.docker_progress_step % (bar_len * 2 - 2)
        if pos >= bar_len:
            pos = (bar_len * 2 - 2) - pos
            
        bar = ["-"] * bar_len
        bar[pos] = "█"
        bar_str = "".join(bar)
        
        msg = self.docker_progress_msg
        if len(msg) > 35:
            msg = msg[:32] + "..."
            
        text = f"{prefix:<22} [{bar_str}] {msg}"
        self.docker_console.update_progress(text)

    def write_to_console(self, text: str):
        """Legacy method for backward compatibility."""
        self.gns3_console.write(text, "INFO")

    def _submit_gns3_input(self):
        """Обработчик ввода для консоли GNS3"""
        text = self.gns3_console.input.text()
        if text.strip():
            # echo command
            self.gns3_console.write(f"> {text}", "INFO")
            cmd = text.strip().lower()

            # run parser
            if cmd:
                try:
                    feedback = handle_command(text)
                except Exception as e:
                    feedback = f"Command error: {e}"
                if feedback:
                    # Determine level by content
                    if feedback.startswith("ERROR"):
                        level = "ERROR"
                    else:
                        level = "INFO"
                    for ln in feedback.splitlines():
                        self.gns3_console.write(ln, level)

        self.gns3_console.input.clear()

    def _submit_docker_input(self):
        """Обработчик ввода для консоли Docker"""
        text = self.docker_console.input.text()
        if text.strip():
            self.docker_console.write(f"> {text}", "INFO")
            from modules.Docker.cli_commands import handle_docker_command
            
            try:
                feedback = handle_docker_command(text)
                
                if feedback == "COMMAND_CHECK":
                    from modules.Docker.backend_bridge import get_config
                    config = get_config()
                    if not config.get('project_path'):
                        self.docker_console.write("ERROR: Please set a valid Docker project folder first (proj <path>).", "ERROR")
                    else:
                        self.docker_console.write(f"Starting Docker check for path: {config.get('project_path')}", "INFO")
                        threading.Thread(target=self._run_docker_backend, daemon=True).start()
                elif feedback:
                    level = "ERROR" if feedback.startswith("ERROR") else "INFO"
                    for ln in feedback.splitlines():
                        self.docker_console.write(ln, level)
            except Exception as e:
                self.docker_console.write(f"Command error: {e}", "ERROR")

        self.docker_console.input.clear()

    def get_active_console(self, button=None):
        btn = button or self.active_console_button
        if btn == self.console_btn_1:
            return self.gns3_console
        elif btn == self.console_btn_2:
            return self.docker_console
        return None

    def mousePressEvent(self, event):
        # Allow dragging the main window from any point not occupied by the console.
        if event.button() == Qt.LeftButton:
            click_on_console = False
            if self.gns3_console.isVisible() and self.gns3_console.geometry().contains(event.pos()):
                click_on_console = True
            if self.docker_console.isVisible() and self.docker_console.geometry().contains(event.pos()):
                click_on_console = True
                
            if click_on_console:
                pass
            else:
                # Click is outside the console or console is not visible, so it's for the main window.
                self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept() # Accept the event to prevent further propagation if it's for the main window.

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_pos:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = None
        super().mouseReleaseEvent(event)

    def _on_folder_button_clicked(self):
        """Обработчик кнопки выбора папки проекта Docker"""
        directory = QFileDialog.getExistingDirectory(self, "Select Docker Project Directory")
        
        if directory:
            from modules.Docker.backend_bridge import set_config
            set_config("project_path", directory)
            self.docker_console.write(f"Docker project path successfully set to:\n{directory}", "INFO")
            
            # Автоматически открываем консоль Docker, если она закрыта
            if self.active_console_button != self.console_btn_2:
                self.console_btn_2.click()

    def _on_console_button_clicked(self):
        sender_button = self.sender()
        target_console = self.get_active_console(sender_button)
        current_console = self.get_active_console()

        if current_console and current_console.isVisible():
            if self.active_console_button == sender_button:
                # Нажали на ту же кнопку, что и открыли консоль -> закрываем
                self.hide_console()
            else:
                # Нажали на другую кнопку -> меняем активную кнопку, консоль остается открытой
                current_console.hide() # Быстро прячем старую консоль
                self.show_console(sender_button)
        else:
            # Консоль закрыта -> открываем
            self.show_console(sender_button)

    def show_console(self, button):
        if self.active_console_button:
            self.active_console_button.setStyleSheet(self.button_style_normal)
            
        # Устанавливаем активную кнопку и её стиль
        self.active_console_button = button
        self.active_console_button.setStyleSheet(self.button_style_active)
        self._update_central_icon()

        console_to_show = self.get_active_console()
        console_to_show.show()
        console_to_show.raise_() # Убедиться, что консоль всегда поверх
        
        anim = QPropertyAnimation(console_to_show, b"geometry")
        anim.setDuration(200)
        anim.setStartValue(QRect(self.LEFT_MARGIN - 780, 2, 780, 520)) # ИЗМЕНЕНО: начальная позиция
        anim.setEndValue(QRect(self.LEFT_MARGIN, 2, 780, 520)) # ИЗМЕНЕНО: конечная позиция
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self.anim = anim
        
        if not getattr(console_to_show, "_boot_msg", False):
            self._show_startup_info(console_to_show)
            console_to_show._boot_msg = True
            
        console_to_show.input.setFocus()

    def hide_console(self):
        console_to_hide = self.get_active_console()
        
        # Сбрасываем стиль активной кнопки
        if self.active_console_button:
            self.active_console_button.setStyleSheet(self.button_style_normal)
            self.active_console_button = None
        self._update_central_icon()

        if console_to_hide:
            anim = QPropertyAnimation(console_to_hide, b"geometry")
            anim.setDuration(200)
            anim.setStartValue(QRect(self.LEFT_MARGIN, 2, 780, 520))
            anim.setEndValue(QRect(self.LEFT_MARGIN - 780, 2, 780, 520))
            anim.setEasingCurve(QEasingCurve.InCubic)
            anim.start()
            self.anim = anim
            anim.finished.connect(console_to_hide.hide)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Корректное позиционирование кнопок управления окном при изменении размера
        if hasattr(self, 'min_btn'):
            self.min_btn.move(self.width() - 90, 4)
            self.max_btn.move(self.width() - 60, 4)
            self.close_btn.move(self.width() - 30, 4)

    def _update_central_icon(self):
        if self.active_console_button == self.console_btn_1:
            self.central_icon_label.setPixmap(self.gns3_icon_pixmap)
            self.central_icon_label.setGeometry(self.central_icon_label_x, self.central_icon_label_y, self.gns3_central_icon_size.width(), self.gns3_central_icon_size.height())
            self.central_icon_label.show()
        elif self.active_console_button == self.console_btn_2:
            self.central_icon_label.setPixmap(self.docker_icon_pixmap)
            self.central_icon_label.setGeometry(self.central_icon_label_x, self.central_icon_label_y, self.docker_central_icon_size.width(), self.docker_central_icon_size.height())
            self.central_icon_label.show()
        else:
            self.central_icon_label.hide()

    def toggle_maximize(self):
        if self.is_maximized:
            self.showNormal()
        else:
            self.showMaximized()
        self.is_maximized = not self.is_maximized

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setPen(QPen(Qt.black, 1))
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)
        painter.drawLine(self.LEFT_MARGIN, 0, self.LEFT_MARGIN, self.height())

    def _run_backend(self):
        try:
            # Run parser
            result = run_parse(log_func=lambda x: get_logger().info(x))
            PROJECT_ROOT = Path(__file__).resolve().parent
            config = _load()
            # Исправлен путь к результатам с учетом папки modules и переименования
            results_dir = PROJECT_ROOT / "modules" / "GNS3" / "core" / "Student" / config["project"]
            os.makedirs(results_dir, exist_ok=True)
            data = result.get("data", {})
            for node_name, node_config in data.items():
                node_file = os.path.join(results_dir, f"{node_name}.json")
                with open(node_file, "w", encoding="utf-8") as f:
                    json.dump(node_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            get_logger().error("Parser startup error", technical=str(e))

        try:
            # Run comparator
            config = _load()
            result = run_compare(config["project"])
        except Exception as e:
            get_logger().error("Comparator startup error", technical=str(e))

        try:
            # Display result
            self.result_label.setText(f"Result: {result}%")
            self.result_label.show()
        except Exception as e:
            get_logger().error("Result display error", technical=str(e))

    def show_result(self, result=0):
        if not getattr(self.gns3_console, "_boot_msg", False):
            self.gns3_console.write("The system is running.", "INFO")
            self.gns3_console._boot_msg = True
        get_logger().info("Starting check...")
        th = threading.Thread(target=self._run_backend, daemon=True)
        th.start()

    def _run_docker_backend(self):
        import subprocess
        import json
        import sys
        import os
        import time
        import threading
        from modules.Docker.backend_bridge import get_config
        
        config = get_config()
        lab_type = config.get('lab', 'lab10')
        auto_checker_path = os.path.join(project_root, "modules", "Docker", "auto_checker.py")
        
        if not os.path.exists(auto_checker_path):
            self.log_message_signal.emit("docker", f"ERROR: Checker not found at {auto_checker_path}", "ERROR")
            return
            
        cmd = [sys.executable, auto_checker_path, "--lab", lab_type, "--dir", config.get('project_path'), "--silent"]
        
        self.docker_progress_state_signal.emit(1, "Подготовка...")

        try:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', env=env, bufsize=1
            )
            
            stderr_lines = []
            def read_stderr():
                for eline in iter(process.stderr.readline, ''):
                    if eline:
                        stderr_lines.append(eline.strip())

            err_thread = threading.Thread(target=read_stderr, daemon=True)
            err_thread.start()
            stdout_lines = []
            start_time = time.time()
            
            def check_timeout():
                if time.time() - start_time > 300:
                    process.kill()
                    return True
                return False

            while True:
                if check_timeout():
                    break
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                    
                line_str = line.strip()
                if not line_str:
                    continue
                    
                if line_str.startswith('{"type": "progress_log"'):
                    try:
                        log_data = json.loads(line_str)
                        self.docker_progress_msg_signal.emit(log_data.get("message", ""))
                    except Exception:
                        pass
                else:
                    stdout_lines.append(line_str)
            
            err_thread.join(timeout=1)
            stderr = "\n".join(stderr_lines)
            stdout = "\n".join(stdout_lines)
            
            self.docker_progress_state_signal.emit(0, "")
            
            if time.time() - start_time > 300:
                self.log_message_signal.emit("docker", "CRITICAL ERROR: Docker check timed out (5 minutes limit) and was forcefully aborted.", "ERROR")
                return

            if stderr:
                self.log_message_signal.emit("docker", f"Warning/Error: {stderr.strip()}", "ERROR")
                
            if not stdout:
                if not stderr:
                    self.log_message_signal.emit("docker", "ERROR: Checker script finished silently with no output.", "ERROR")
                return

            try:
                result = json.loads(stdout)
                
                if not result.get("success", True):
                    self.log_message_signal.emit("docker", f"Error: {result.get('error', 'Unknown error')}", "ERROR")
                    return
                
                self.log_message_signal.emit("docker", f"--- Results for {lab_type} ---", "INFO")
                results_list = result.get('results', [])
                for res in results_list:
                    passed = res.get('passed', False)
                    status = "[PASSED]" if passed else "[FAILED]"
                    level = "INFO" if passed else "ERROR"
                    self.log_message_signal.emit("docker", f"{status} {res.get('name')}: {res.get('message')}", level)
                    
                summary = result.get('summary', {})
                self.log_message_signal.emit("docker", f"Total: {summary.get('total_checks', 0)} | Passed: {summary.get('passed_checks', 0)} | Failed: {summary.get('failed_checks', 0)}", "INFO")
                self.log_message_signal.emit("docker", f"Success Rate: {summary.get('success_rate', '0%')}", "INFO")
                
            except json.JSONDecodeError:
                self.log_message_signal.emit("docker", "Failed to parse checker output. Raw output:", "ERROR")
                self.log_message_signal.emit("docker", stdout.strip(), "INFO")
                
        except Exception as e:
            self.docker_progress_state_signal.emit(0, "")
            self.log_message_signal.emit("docker", f"Failed to execute Docker checker: {e}", "ERROR")

    def _show_startup_info(self, target_console):
        """Displays configuration information when console starts"""
        target_console.write("System is running.", "INFO")
        if target_console == self.gns3_console:
            try:
                from modules.GNS3.backend_bridge import get_config
                config = get_config()
                target_console.write(f"   project name: {config.get('project', 'Not set')}", "INFO")
                target_console.write(f"   laboratory: {config.get('lab', 'Not set')}", "INFO")
                target_console.write(f"   ip: {config.get('ip', 'Not set')}", "INFO")
                target_console.write(f"   port: {config.get('port', 'Not set')}", "INFO")
                target_console.write(f"   login: {config.get('login', 'Not set')}", "INFO")
                target_console.write(f"   password: {'*' * len(config.get('password', '')) if config.get('password') else 'Not set'}", "INFO")
            except ImportError:
                target_console.write("   [GNS3 Backend Not Configured]", "ERROR")
            target_console.write("Type 'help' for available GNS3 commands", "INFO")
            
        elif target_console == self.docker_console:
            try:
                from modules.Docker.backend_bridge import get_config
                config = get_config()
                target_console.write("   Module: Docker & NetworkTech", "INFO")
                target_console.write(f"   current lab: {config.get('lab', 'lab10')}", "INFO")
                target_console.write(f"   project path: {config.get('project_path', 'Not set (use Folder icon)')}", "INFO")
            except ImportError:
                target_console.write("   [Docker Backend Not Configured]", "ERROR")
            target_console.write("Type 'check' to verify the Docker lab, or 'help' for commands.", "INFO")
            
        target_console.write("", "INFO")


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        w = MainWindow()
        w.show()
        sys.exit(app.exec_())
    except Exception as e:
        print(f"CRITICAL ERROR DURING STARTUP: {e}")
        input("Press Enter to exit...")
