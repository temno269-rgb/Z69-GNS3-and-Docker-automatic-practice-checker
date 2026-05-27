@echo off
chcp 65001 > nul
echo ========================================================
echo Начинаем установку необходимых библиотек для Z69...
echo ========================================================
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Установка успешно завершена! Теперь можно запускать приложение.
pause