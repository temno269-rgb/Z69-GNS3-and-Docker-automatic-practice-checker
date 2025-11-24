# -*- coding: utf-8 -*-
"""
compare.py - Компаратор результатов (с динамическим выбором эталона)

Основная функция для интеграции: run_comparison(student_data, log_func=None)
Возвращает: (similarity_percent, report_path)
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Set, Callable
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ← Поднялись на уровень выше
CORE_DIR = PROJECT_ROOT / "core"
EXAMPLES_DIR = CORE_DIR / "examples"  # ← Эталоны в core/examples
STUDENTS_ROOT = PROJECT_ROOT / "results"
STATE_PATH = STUDENTS_ROOT / ".last_example"  # ← Состояние: какой пример был выбран

Diff = Tuple[str, str, Any, Any]

MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}

# ════════════════════════════════════════════════════════════════
# 🔍 ФУНКЦИИ ДЛЯ РАБОТЫ С ЭТАЛОНАМИ
# ════════════════════════════════════════════════════════════════

def list_available_examples() -> List[int]:
    """
    Получить список номеров доступных эталонов.
    
    Ищет папки вида: Example1, Example2, Example3, ...
    
    Returns:
        Отсортированный список номеров [1, 2, 3, ...]
    """
    if not EXAMPLES_DIR.exists():
        return []
    
    examples = []
    for item in EXAMPLES_DIR.iterdir():
        if item.is_dir() and item.name.startswith("Example"):
            try:
                num = int(item.name[7:])  # "Example2" → 2
                examples.append(num)
            except ValueError:
                pass
    
    return sorted(examples)

def get_example_dir(example_num: int) -> Optional[Path]:
    """
    Получить путь к эталону по номеру.
    
    Args:
        example_num: номер лабораторной работы (1, 2, 3, ...)
    
    Returns:
        Path к папке Example{num} или None если не существует
    """
    example_path = EXAMPLES_DIR / f"Example{example_num}"
    if example_path.exists() and example_path.is_dir():
        return example_path
    return None

def choose_example_interactive() -> Optional[int]:
    """
    Интерактивно выбрать номер эталона (для консоли).
    
    Returns:
        Номер эталона (1, 2, 3, ...) или None если пользователь отменил
    """
    available = list_available_examples()
    
    if not available:
        print("❌ No examples found in:", EXAMPLES_DIR)
        return None
    
    # Пытаемся загрузить последний выбранный
    last_example = None
    try:
        if STATE_PATH.exists():
            last_example = int(STATE_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, Exception):
        pass
    
    # Выводим меню
    print("\n📚 Available examples:")
    for num in available:
        marker = " ← last used" if num == last_example else ""
        print(f"  {num}{marker}")
    
    # Ждём ввода
    while True:
        prompt = f"Enter examples number (default {last_example}): " if last_example else "Enter examples number: "
        user_input = input(prompt).strip()
        
        if not user_input:
            if last_example and last_example in available:
                return last_example
            else:
                print("❌ No default examples. Please enter a number.")
                continue
        
        try:
            num = int(user_input)
            if num in available:
                # Сохраняем выбор
                try:
                    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    STATE_PATH.write_text(str(num), encoding="utf-8")
                except Exception:
                    pass
                return num
            else:
                print(f"❌ Example {num} not found. Available: {available}")
        except ValueError:
            print(f"❌ Invalid input. Please enter a number from {available}")

# ════════════════════════════════════════════════════════════════
# ⭐ ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ИНТЕГРАЦИИ
# ════════════════════════════════════════════════════════════════

def run_comparison(
    student_data: dict,
    example_num: Optional[int] = None,
    student_folder: Optional[str] = None,
    log_func: Optional[Callable[[str], None]] = None
) -> Tuple[float, Optional[str]]:
    """
    Запустить сравнение данных студента с эталоном.
    
    Args:
        student_data: dict из parse.py (узлы и конфиги)
        example_num: номер эталона (1, 2, 3, ...). 
                     Если None, спрашивает интерактивно или использует последний
        student_folder: имя папки студента. Если None, использует последнюю
        log_func: функция логирования (опционально)
    
    Returns:
        (similarity_percent: float, report_path: str or None)
    """
    logger = log_func if callable(log_func) else lambda x: None
    
    def _log(msg: str):
        try:
            if logger:
                logger(msg)
        except Exception:
            pass
    
    try:
        # ─────────────────────────────────────────────────────────
        # 1. Выбираем эталон
        # ─────────────────────────────────────────────────────────
        
        if example_num is None:
            # Пытаемся загрузить последний выбранный
            try:
                if STATE_PATH.exists():
                    example_num = int(STATE_PATH.read_text(encoding="utf-8").strip())
                    _log(f"📚 Using last examples: {example_num}")
            except (ValueError, Exception):
                pass
            
            # Если всё ещё не определён, спрашиваем интерактивно
            if example_num is None:
                _log("🔍 No examples specified. Available examples:")
                available = list_available_examples()
                if available:
                    for num in available:
                        _log(f"  - Example{num}")
                    # В режиме GUI спрашиваем через логирование
                    # (В консоли это была бы интерактивная функция)
                    _log("⚠️  Please specify example_num parameter")
                else:
                    _log("❌ No examples found in: " + str(EXAMPLES_DIR))
                return 0, None
        
        # Проверяем, существует ли эталон
        example_dir = get_example_dir(example_num)
        if not example_dir:
            _log(f"❌ Example{example_num} not found at: {EXAMPLES_DIR / f'Example{example_num}'}")
            return 0, None
        
        _log(f"✅ Using Example{example_num} from: {example_dir}")
        
        # Сохраняем как последний выбранный
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(str(example_num), encoding="utf-8")
        except Exception:
            pass
        
        # ─────────────────────────────────────────────────────────
        # 2. Выбираем папку студента
        # ─────────────────────────────────────────────────────────
        
        if not student_folder:
            # Пытаемся загрузить последнюю
            state_path_student = STUDENTS_ROOT / ".last_student_folder"
            if state_path_student.exists():
                try:
                    student_folder = state_path_student.read_text(encoding="utf-8").strip()
                except Exception:
                    pass
        
        if not student_folder:
            _log("❌ Student folder not specified")
            return 0, None
        
        student_dir = STUDENTS_ROOT / student_folder
        
        if not student_dir.exists():
            _log(f"❌ Student directory does not exist: {student_dir}")
            return 0, None
        
        _log(f"📁 Comparing student data from: {student_folder}")
        
        # ─────────────────────────────────────────────────────────
        # 3. Сравниваем
        # ─────────────────────────────────────────────────────────
        
        # Получаем все устройства
        expected_devices = set(p.stem for p in example_dir.iterdir() if p.is_file())
        actual_devices = set(p.stem for p in student_dir.iterdir() if p.is_file())
        all_devices = sorted(expected_devices | actual_devices)
        
        _log(f"📊 Found {len(all_devices)} devices to compare")
        
        # Создаём папку результатов
        results_root = STUDENTS_ROOT / student_folder
        results_root.mkdir(parents=True, exist_ok=True)
        
        # Загружаем предыдущие ошибки для отслеживания новых
        prev_txt_path = find_previous_txt(results_root)
        prev_errors_by_device: Dict[str, Set[str]] = {}
        
        if prev_txt_path and prev_txt_path.exists():
            try:
                prev_text = prev_txt_path.read_text(encoding="utf-8")
                prev_errors_by_device = parse_prev_errors_by_device(prev_text)
            except Exception:
                pass
        
        # Сравниваем каждое устройство
        total_atoms = 0
        total_mismatches = 0
        device_reports: List[str] = []
        
        for device in all_devices:
            expected = load_first_existing_by_stem(example_dir, device)
            actual = load_first_existing_by_stem(student_dir, device)
            
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
            
            prev_errs = prev_errors_by_device.get(device)
            device_text = build_device_report(device, diffs, prev_errs)
            device_reports.append(device_text)
        
        # Вычисляем процент совпадения
        similarity = round(100.0 * max(0, total_atoms - total_mismatches) / max(1, total_atoms), 2)
        
        _log(f"✅ Similarity calculated: {similarity:.2f}%")
        
        # Генерируем отчёт
        header = f"Example{example_num} | Совпадение: {similarity:.2f}%"
        final_text = header + "\n\n\n" + ("\n\n\n".join(device_reports) if device_reports else "")
        
        # Сохраняем в файл с временной меткой
        now = datetime.now()
        month_name = MONTHS_RU[now.month]
        file_time_fs = f"{now.day} {month_name} {now.hour:02d}-{now.minute:02d}"
        out_name = f"{student_folder}_Example{example_num}_{file_time_fs}.txt"
        out_path = results_root / out_name
        
        out_path.write_text(final_text, encoding="utf-8")
        
        _log(f"📄 Report saved: {out_path}")
        
        return similarity, str(out_path)
    
    except Exception as e:
        _log(f"❌ Comparison error: {e}")
        import traceback
        traceback.print_exc()
        return 0, None

# ════════════════════════════════════════════════════════════════
# Утилиты для сравнения (БЕЗ ИЗМЕНЕНИЙ)
# ════════════════════════════════════════════════════════════════

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

def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def load_first_existing_by_stem(folder: Path, stem: str) -> Optional[Any]:
    candidates = [folder / stem, folder / f"{stem}.json"]
    for p in candidates:
        if p.exists() and p.is_file():
            return _load_json(p)
    return None

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

def find_previous_txt(results_root: Path) -> Optional[Path]:
    txts = sorted(results_root.glob("*.txt"))
    return txts[-1] if txts else None

def parse_prev_errors_by_device(txt: str) -> Dict[str, Set[str]]:
    errors: Dict[str, Set[str]] = {}
    current = None
    for line in txt.splitlines():
        if line.endswith(":") and not line.startswith(" "):
            current = line[:-1].strip()
            if current not in errors:
                errors[current] = set()
            continue
        if current and line.startswith(" - "):
            errors[current].add(line)
    return errors

def build_device_report(device: str, diffs, prev_errors_for_device: Optional[Set[str]]) -> str:
    lines: List[str] = [f"{device}:"]
    
    if len(diffs) == 1 and diffs[0][0] == "missing_in_student" and diffs[0][1] == device and diffs[0][3] is None:
        lines.append("ОТСУТСТВУЕТ")
        return "\n".join(lines)
    
    if not diffs:
        lines.append("OK")
        return "\n".join(lines)
    
    first = True
    for kind, path, exp, act in diffs:
        if not first:
            lines.append("")
        first = False
        
        if kind == "missing_in_student":
            lines.append(f" - Отсутствует у студента: {path}")
        elif kind == "extra_in_student":
            lines.append(f" - Лишний ключ у студента: {path}")
        elif kind == "missing_item_in_student":
            lines.append(f" - Отсутствует элемент у студента: {path}")
        elif kind == "extra_item_in_student":
            lines.append(f" - Лишний элемент у студента: {path}")
        elif kind == "list_len_diff":
            lines.append(f" - Разная длина списка: {path} — эталон={exp}, студент={act}")
        elif kind == "type_diff":
            lines.append(f" - Разный тип данных: {path} — эталон={exp}, студент={act}")
        elif kind == "value_diff":
            lines.append(f" - Разное значение: {path}")
            exp_s = str(exp) if len(str(exp)) <= 200 else str(exp)[:200] + "…"
            act_s = str(act) if len(str(act)) <= 200 else str(act)[:200] + "…"
            lines.append(f" ожидается: {exp_s}")
            lines.append(f" у студента: {act_s}")
        else:
            lines.append(f" - Различие: {path}")
    
    if prev_errors_for_device is not None:
        current_errors = {l for l in lines if l.startswith(" - ")}
        new_errs = [e for e in current_errors if e not in prev_errors_for_device]
        
        if new_errs:
            lines.append("")
            lines.append("----------------------------")
            lines.append("Новые ошибки:")
            lines.extend(sorted(new_errs))
    
    return "\n".join(lines)

# ════════════════════════════════════════════════════════════════
# Интерактивный режим (для консоли)
# ════════════════════════════════════════════════════════════════

def main() -> None:
    """Запуск в режиме консоли (для отладки)."""
    # Выбираем эталон
    example_num = choose_example_interactive()
    if not example_num:
        print("❌ No examples selected")
        return
    
    # Выбираем папку студента (если нужно)
    student_folder = input("Enter student folder: ").strip()
    if not student_folder:
        print("❌ Student folder not specified")
        return
    
    student_data = {}
    
    similarity, report_path = run_comparison(
        student_data,
        example_num=example_num,
        student_folder=student_folder
    )
    print(f"\n✅ Similarity: {similarity:.2f}%")
    if report_path:
        print(f"📄 Report saved: {report_path}")

if __name__ == "__main__":
    main()
