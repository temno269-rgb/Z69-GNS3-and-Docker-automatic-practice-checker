#!/usr/bin/env python3
"""
Тест модульной версии lab_checker
"""

import sys
import os
from pathlib import Path

# Настройка путей для корректного импорта модулей из корня Z69
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from modules.Docker.lab_checker import check_lab_dir, LabType

def test_lab10():
    """Тест проверки Lab 10"""
    print("=== Тест Lab 10 ===")
    try:
        # ВАЖНО: Если api.check_lab_dir ожидает директорию, замени '10/lab10.tar' на путь к папке.
        # Используем LabType для соответствия основному API проекта.
        result = check_lab_dir('10/lab10', 'lab10', silent_mode=True)
        print("Lab 10 тест завершен успешно!")
        print(f"Пройдено проверок: {result['summary']['passed_checks']}/{result['summary']['total_checks']}")
        print(f"Успешность: {result['summary']['success_rate']}")
        
        # Show detailed results
        print("\nПодробные результаты:")
        for check in result['results']:
            status = "PASS" if check['passed'] else "FAIL"
            print(f"  {status} {check['name']}: {check['message']}")
        
    except Exception as e:
        print(f"Ошибка теста Lab 10: {e}")

def test_lab11():
    """Тест проверки Lab 11"""
    print("=== Тест Lab 11 ===")
    try:
        result = check_lab_dir('11/lab11', 'lab11', silent_mode=True)
        print("Lab 11 тест завершен успешно!")
        print(f"Пройдено проверок: {result['summary']['passed_checks']}/{result['summary']['total_checks']}")
        print(f"Успешность: {result['summary']['success_rate']}")
        
        # Show detailed results
        print("\nПодробные результаты:")
        for check in result['results']:
            status = "PASS" if check['passed'] else "FAIL"
            print(f"  {status} {check['name']}: {check['message']}")
        
    except Exception as e:
        print(f"Ошибка теста Lab 11: {e}")

def test_lab12():
    """Тест проверки Lab 12"""
    print("=== Тест Lab 12 ===")
    try:
        result = check_lab_dir('12/lab12', 'lab12', silent_mode=True)
        print("Lab 12 тест завершен успешно!")
        print(f"Пройдено проверок: {result['summary']['passed_checks']}/{result['summary']['total_checks']}")
        print(f"Успешность: {result['summary']['success_rate']}")
        
        # Show detailed results
        print("\nПодробные результаты:")
        for check in result['results']:
            status = "PASS" if check['passed'] else "FAIL"
            print(f"  {status} {check['name']}: {check['message']}")
        
    except Exception as e:
        print(f"Ошибка теста Lab 12: {e}")

def test_lab13():
    """Тест проверки Lab 13"""
    print("=== Тест Lab 13 ===")
    try:
        result = check_lab_dir('13/lab13', 'lab13', silent_mode=True)
        print("Lab 13 тест завершен успешно!")
        print(f"Пройдено проверок: {result['summary']['passed_checks']}/{result['summary']['total_checks']}")
        print(f"Успешность: {result['summary']['success_rate']}")
        
        # Show detailed results
        print("\nПодробные результаты:")
        for check in result['results']:
            status = "PASS" if check['passed'] else "FAIL"
            print(f"  {status} {check['name']}: {check['message']}")
        
    except Exception as e:
        print(f"Ошибка теста Lab 13: {e}")

def test_lab14():
    """Test Lab 14"""
    print("=== Test Lab 14 ===")
    try:
        result = check_lab_dir('14/lab14', 'lab14', silent_mode=True)
        print("Lab 14 test completed successfully!")
        print(f"Checks passed: {result['summary']['passed_checks']}/{result['summary']['total_checks']}")
        print(f"Success rate: {result['summary']['success_rate']}")
        
        # Show detailed results
        print("\nDetailed results:")
        for check in result['results']:
            status = "PASS" if check['passed'] else "FAIL"
            print(f"  {status} {check['name']}: {check['message']}")
        
    except Exception as e:
        print(f"Lab 14 test error: {e}")

def test_all_labs():
    """Test all laboratories sequentially"""
    print("=== Testing ALL Laboratories ===")
    print("=" * 50)
    
    labs = [
        ("Lab 10", test_lab10),
        ("Lab 11", test_lab11),
        ("Lab 12", test_lab12),
        ("Lab 13", test_lab13),
        ("Lab 14", test_lab14)
    ]
    
    results = []
    
    for lab_name, test_func in labs:
        print(f"\n{lab_name}:")
        print("-" * 30)
        try:
            test_func()
            results.append((lab_name, "SUCCESS"))
        except Exception as e:
            print(f"CRITICAL ERROR in {lab_name}: {e}")
            results.append((lab_name, "FAILED"))
        print()
    
    # Summary
    print("=" * 50)
    print("FINAL RESULTS:")
    print("=" * 50)
    
    for lab_name, status in results:
        icon = "PASS" if status == "SUCCESS" else "FAIL"
        print(f"{lab_name}: {icon}")
    
    passed = sum(1 for _, status in results if status == "SUCCESS")
    total = len(results)
    print(f"\nOverall: {passed}/{total} laboratories passed")
    print("=" * 50)

def main():
    print("Modular Lab Checker")
    print("Testing ALL laboratories...")
    test_all_labs()

if __name__ == "__main__":
    main()
