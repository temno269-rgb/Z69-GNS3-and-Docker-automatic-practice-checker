@echo off
chcp 65001 > nul
echo Начинаем установку 
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Установка завершена
pause