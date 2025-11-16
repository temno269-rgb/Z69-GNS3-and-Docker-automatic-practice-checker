from datetime import datetime
import random

def run_comparison(student_data: dict):
    project = student_data.get("project", "Без_имени")
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    similarity = random.uniform(70, 99)
    report = (
        f"Проект: {project}\n"
        f"Время проверки: {now}\n"
        f"Совпадение: {similarity:.2f}%\n"
        f"(сравнение отключено — офлайн-режим)"
    )
    return similarity, report
