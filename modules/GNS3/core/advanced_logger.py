"""
Enhanced logger for Z69 application.
Supports logging levels, file writing, and GUI output.
"""
import logging
import sys
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
import os

# Logging levels
LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

class StudentSafeLogger:
    """
    Logger that hides technical details from students.
    """
    def __init__(self, log_file: Optional[str] = None, student_mode: bool = True):
        """
        :param log_file: path to log file (if None, no file logging)
        :param student_mode: if True, hide technical details
        """
        self.student_mode = student_mode
        self.gui_callback: Optional[Callable[[str, str], None]] = None
        self.log_file = log_file
        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Standard logging setup
        self.logger = logging.getLogger("Z69")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()
        
        # Format for file
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        # Format for console/GUI
        console_formatter = logging.Formatter('%(message)s')
        
        if log_file:
            fh = logging.FileHandler(log_file, encoding='utf-8')
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(file_formatter)
            self.logger.addHandler(fh)
        
        # Handler for redirecting to GUI via callback
        class GuiHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
                self.setFormatter(console_formatter)
            
            def emit(self, record):
                if self.callback:
                    msg = self.format(record)
                    self.callback(msg, record.levelname)
        
        if self.gui_callback:
            gh = GuiHandler(self.gui_callback)
            gh.setLevel(logging.INFO if student_mode else logging.DEBUG)
            self.logger.addHandler(gh)
    
    def set_gui_callback(self, callback: Callable[[str, str], None]):
        """Set callback for outputting messages to GUI."""
        self.gui_callback = callback
        # Update handlers
        for handler in self.logger.handlers:
            if isinstance(handler, logging.FileHandler):
                continue
            self.logger.removeHandler(handler)
        
        console_formatter = logging.Formatter('%(message)s')
        class GuiHandler(logging.Handler):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback
                self.setFormatter(console_formatter)
            
            def emit(self, record):
                if self.callback:
                    msg = self.format(record)
                    self.callback(msg, record.levelname)
        
        gh = GuiHandler(callback)
        gh.setLevel(logging.INFO if self.student_mode else logging.DEBUG)
        self.logger.addHandler(gh)
    
    def debug(self, msg: str, technical: Optional[str] = None):
        """Debug message, shown only if student_mode=False."""
        if not self.student_mode:
            self.logger.debug(msg)
        else:
            # In student mode, debug not shown
            pass
    
    def info(self, msg: str):
        """Informational message for user."""
        self.logger.info(msg)
    
    def warning(self, msg: str, technical: Optional[str] = None):
        """Warning."""
        if self.student_mode and technical:
            # Hide technical details
            self.logger.warning(msg)
        else:
            self.logger.warning(f"{msg} ({technical})" if technical else msg)
    
    def error(self, msg: str, technical: Optional[str] = None):
        """Error."""
        if self.student_mode:
            self.logger.error(msg)
            if technical:
                # Technical details written only to file
                self.logger.debug(f"Technical info: {technical}")
        else:
            self.logger.error(f"{msg} ({technical})" if technical else msg)
    
    def critical(self, msg: str, technical: Optional[str] = None):
        """Critical error."""
        if self.student_mode:
            self.logger.critical(msg)
        else:
            self.logger.critical(f"{msg} ({technical})" if technical else msg)

# Global logger instance
_logger_instance: Optional[StudentSafeLogger] = None

def init_logger(log_file: Optional[str] = None, student_mode: bool = True):
    """Initialize global logger."""
    global _logger_instance
    _logger_instance = StudentSafeLogger(log_file, student_mode)
    return _logger_instance

def get_logger() -> StudentSafeLogger:
    """Get global logger."""
    if _logger_instance is None:
        init_logger()
    return _logger_instance

def set_gui_callback(callback: Callable[[str, str], None]):
    """Set callback for GUI."""
    logger = get_logger()
    logger.set_gui_callback(callback)

# Utilities for creating log paths
def get_default_log_path() -> Path:
    """Returns path to logs folder in APPDATA."""
    appdata = os.getenv('APPDATA')
    if appdata:
        log_dir = Path(appdata) / "Z69" / "logs"
    else:
        log_dir = Path.home() / "Z69" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return log_dir / f"check_{timestamp}.log"