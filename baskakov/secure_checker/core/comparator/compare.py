import json
import csv
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Set
from datetime import datetime
from collections import defaultdict

Diff = Tuple[str, str, Any, Any]

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def _path_join(path: str, segment: str) -> str:
    segment = str(segment).strip()
    if not path:
        return segment
    if segment.startswith(("/", "[", ".")) or path.endswith("/"):
        return f"{path}{segment}"
    return f"{path}/{segment}"


def _path_index(path: str, index: int) -> str:
    if not path:
        return f"[{index}]"
    return f"{path}[{index}]"


def _path_key(path: str, list_key: str, key_value: Any) -> str:
    if not path:
        return f"[{list_key}={key_value}]"
    return f"{path}[{list_key}={key_value}]"


CANDIDATE_KEYS = ("id", "name", "key", "uid", "uuid", "index", "hostname", "title")


def _detect_list_key(items: List[Any]) -> Optional[str]:
    dicts = [x for x in items if isinstance(x, dict)]
    if not dicts:
        return None

    best_key = None
    best_cnt = 0
    half = max(1, len(dicts) // 2)

    for k in CANDIDATE_KEYS:
        cnt = sum(1 for d in dicts if k in d)
        if cnt > best_cnt and cnt >= half:
            best_cnt, best_key = cnt, k

    return best_key


def compare_json(expected: Any, actual: Any, path: str = "") -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []

    if type(expected) is type(actual):
        if isinstance(expected, dict):
            diffs.extend(_compare_dicts(expected, actual, path))
        elif isinstance(expected, list):
            diffs.extend(_compare_lists(expected, actual, path))
        else:
            if expected != actual:
                diffs.append(("value_diff", path or ".", expected, actual))
    else:
        diffs.append(("type_diff", path or ".", type(expected).__name__, type(actual).__name__))

    return diffs


def _compare_dicts(exp: Dict[str, Any], act: Dict[str, Any], path: str) -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []
    exp_keys = set(exp.keys())
    act_keys = set(act.keys())

    for k in sorted(exp_keys - act_keys):
        diffs.append(("missing_in_student", _path_join(path, k), exp[k], None))

    for k in sorted(act_keys - exp_keys):
        diffs.append(("extra_in_student", _path_join(path, k), None, act[k]))

    for k in sorted(exp_keys & act_keys):
        diffs.extend(compare_json(exp[k], act[k], _path_join(path, k)))

    return diffs


def _compare_lists(exp_list: List[Any], act_list: List[Any], path: str) -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []

    list_key = _detect_list_key(exp_list) or _detect_list_key(act_list)

    if list_key:
        exp_map: Dict[Any, Any] = {item[list_key]: item for item in exp_list if isinstance(item, dict) and list_key in item}
        act_map: Dict[Any, Any] = {item[list_key]: item for item in act_list if isinstance(item, dict) and list_key in item}

        exp_keys = set(exp_map.keys())
        act_keys = set(act_map.keys())

        for k in sorted(exp_keys - act_keys):
            diffs.append(("missing_item_in_student", _path_key(path, list_key, k), exp_map[k], None))

        for k in sorted(act_keys - exp_keys):
            diffs.append(("extra_item_in_student", _path_key(path, list_key, k), None, act_map[k]))

        for k in sorted(exp_keys & act_keys):
            diffs.extend(compare_json(exp_map[k], act_map[k], _path_key(path, list_key, k)))

        no_key_exp = [x for x in exp_list if not (isinstance(x, dict) and list_key in x)]
        no_key_act = [x for x in act_list if not (isinstance(x, dict) and list_key in x)]

        if no_key_exp or no_key_act:
            diffs.extend(_compare_lists_positional(no_key_exp, no_key_act, f"{path}[*no_key]" if path else "[*no_key]"))

        return diffs

    return _compare_lists_positional(exp_list, act_list, path)


def _compare_lists_positional(exp_list: List[Any], act_list: List[Any], path: str) -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []

    if len(exp_list) != len(act_list):
        diffs.append(("list_len_diff", path or ".", len(exp_list), len(act_list)))

    for i, (e_item, a_item) in enumerate(zip(exp_list, act_list)):
        diffs.extend(compare_json(e_item, a_item, _path_index(path, i)))

    if len(exp_list) > len(act_list):
        for i in range(len(act_list), len(exp_list)):
            diffs.append(("missing_item_in_student", _path_index(path, i), exp_list[i], None))
    elif len(act_list) > len(exp_list):
        for i in range(len(exp_list), len(act_list)):
            diffs.append(("extra_item_in_student", _path_index(path, i), None, act_list[i]))

    return diffs


def count_atoms(node: Any) -> int:
    if isinstance(node, dict):
        return sum(count_atoms(v) for v in node.values())
    if isinstance(node, list):
        return sum(count_atoms(v) for v in node)
    return 1


def count_mismatched_atoms(diffs):
    mismatches = 0
    for kind, _, exp, act in diffs:
        if kind in ("value_diff", "type_diff"):
            mismatches += 1
        elif kind == "list_len_diff":
            mismatches += abs((exp or 0) - (act or 0))
        elif kind in ("missing_in_student", "extra_in_student",
                      "missing_item_in_student", "extra_item_in_student"):
            mismatches += 1
    return mismatches


def load_examples_from_core() -> Dict[str, Any]:
    """
    Загружает эталонные конфигурации из папки core/examples.
    Возвращает словарь {имя_устройства: конфигурация}
    """
    examples_dir = Path(__file__).parent.parent / "examples"
    
    if not examples_dir.exists():
        print(f"Предупреждение: папка examples не найдена: {examples_dir}")
        return {}
    
    examples = {}
    for file_path in examples_dir.glob("*.json"):
        try:
            with file_path.open("r", encoding="utf-8") as f:
                examples[file_path.stem] = json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки {file_path}: {e}")
    
    return examples


def compare_configs(student_data: Dict[str, Any], output_path: Path) -> float:
    """
    Сравнивает данные студента с эталонными конфигурациями.
    
    Args:
        student_data: словарь {имя_устройства: конфигурация}
        output_path: путь для сохранения CSV отчёта
    
    Returns:
        процент совпадения (0.0 - 100.0)
    """
    # Загружаем эталоны
    examples = load_examples_from_core()
    
    if not examples:
        print("Ошибка: эталонные конфигурации не найдены")
        return 0.0
    
    # Получаем все устройства
    all_devices = sorted(set(examples.keys()) | set(student_data.keys()))
    
    total_atoms = 0
    total_mismatches = 0
    device_reports = []
    
    for device in all_devices:
        expected = examples.get(device)
        actual = student_data.get(device)
        
        diffs = []
        if expected is None and actual is None:
            continue
        elif expected is None:
            diffs = [("extra_in_student", device, None, "<весь файл>")]
            expected_root = {}
        elif actual is None:
            diffs = [("missing_in_student", device, "<весь файл>", None)]
            expected_root = expected
        else:
            diffs = compare_json(expected, actual, "")
            expected_root = expected
        
        total_atoms += count_atoms(expected_root)
        total_mismatches += count_mismatched_atoms(diffs)
        
        # Формируем отчёт по устройству
        device_report = {
            "device": device,
            "status": "OK" if not diffs else "ERRORS",
            "errors_count": len(diffs),
            "diffs": diffs
        }
        device_reports.append(device_report)
    
    # Вычисляем процент совпадения
    similarity = round(100.0 * max(0, total_atoms - total_mismatches) / max(1, total_atoms), 2)
    
    # Сохраняем CSV отчёт
    save_csv_report(device_reports, similarity, output_path)
    
    return similarity


def save_csv_report(device_reports: List[Dict], similarity: float, output_path: Path):
    """
    Сохраняет отчёт в CSV формате.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8-sig", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter=";")
        
        # Заголовок отчёта
        writer.writerow([f"Результат проверки: {similarity:.2f}%"])
        writer.writerow([])
        
        # Заголовки таблицы
        writer.writerow(["Устройство", "Тип ошибки", "Путь", "Ожидается", "У студента"])
        
        # Данные
        for report in device_reports:
            device = report["device"]
            
            if report["status"] == "OK":
                writer.writerow([device, "OK", "-", "-", "-"])
            else:
                for kind, path, exp, act in report["diffs"]:
                    error_type = {
                        "missing_in_student": "Отсутствует",
                        "extra_in_student": "Лишний ключ",
                        "missing_item_in_student": "Отсутствует элемент",
                        "extra_item_in_student": "Лишний элемент",
                        "list_len_diff": "Разная длина списка",
                        "type_diff": "Разный тип данных",
                        "value_diff": "Разное значение"
                    }.get(kind, kind)
                    
                    # Обрезаем длинные значения
                    exp_str = str(exp) if exp is not None and len(str(exp)) <= 100 else (str(exp)[:100] + "...") if exp is not None else "-"
                    act_str = str(act) if act is not None and len(str(act)) <= 100 else (str(act)[:100] + "...") if act is not None else "-"
                    
                    writer.writerow([device, error_type, path, exp_str, act_str])
                
                # Пустая строка между устройствами
                writer.writerow([])
