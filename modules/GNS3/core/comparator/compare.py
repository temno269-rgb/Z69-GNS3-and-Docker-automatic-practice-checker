import json
from typing import Any, Dict, List, Tuple, Optional, Set
import shutil
import os
import sys
from pathlib import Path
from modules.GNS3.core.advanced_logger import get_logger


def get_project_root():
    if getattr(sys, 'frozen', False):
        # Root _MEI66882/ (where assets/, core/)
        return Path(sys._MEIPASS)
    else:  # Development: project root
        return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = get_project_root()
EXAMPLES_ROOT = PROJECT_ROOT / "Examples"  # _MEI/Examples/
STUDENTS_ROOT = PROJECT_ROOT / "core" / "Student"  # _MEI/core/Student/
appdata = os.getenv('APPDATA')
RESULT_PATH = Path(appdata) / "Z69" / "results"

Diff = Tuple[str, str, Any, Any]
MONTHS_RU = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def choose_lab_name() -> str:
    """Select lab by name (interactive mode)"""
    available_labs = []
    for p in EXAMPLES_ROOT.iterdir():
        if p.is_dir() and p.name.startswith(""):
            available_labs.append(p.name)
    if not available_labs:
        print("ERROR: No * folders found in " + str(EXAMPLES_ROOT))
        raise SystemExit(1)
    available_labs.sort()
    print(f"Available labs: {', '.join(available_labs)}")
    while True:
        user_input = input("Enter lab number (e.g., 1): ").strip()
        if user_input in available_labs:
            return user_input
        print(f"ERROR: Lab '{user_input}' not found. Choose from: {available_labs}")


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


CANDIDATE_KEYS = ("id", "name", "key", "uid", "uuid", "index", "hostname", "title", "address", "dst-address", "default-name")

# Keys ignored during comparison (dynamic or non-critical parameters)
IGNORE_KEYS = {
    "uptime", "last-link-up-time", "invalid", "dynamic", "running", "actual-mtu", 
    "last-cap-update", "interface-type", "mtu", "l2mtu", "up", "age", "active"
}


def _detect_list_key(items: List[Any], path: str = "") -> Optional[str]:
    """
    Determines key for matching list items.
    Added specific keys for MikroTik sections.
    """
    # Specific rules for MikroTik sections
    if "/ip address" in path:
        return "address"
    if "/ip route" in path:
        return "dst-address"
    if "/interface ethernet" in path:
        return "default-name"
    if "/system identity" in path:
        return "name"

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
    
    # Type conversion for value comparison (number vs string)
    if not isinstance(expected, (dict, list)) and not isinstance(actual, (dict, list)):
        if str(expected).strip() != str(actual).strip():
            diffs.append(("value_diff", path or ".", expected, actual))
        return diffs

    if type(expected) is type(actual):
        if isinstance(expected, dict):
            diffs.extend(_compare_dicts(expected, actual, path))
        elif isinstance(expected, list):
            diffs.extend(_compare_lists(expected, actual, path))
        else:
            if expected != actual:
                diffs.append(("value_diff", path or ".", expected, actual))
    else:
        # Try to compare as strings if types differ
        if str(expected).strip() != str(actual).strip():
            diffs.append(("type_diff", path or ".", type(expected).__name__, type(actual).__name__))
    return diffs


def _compare_dicts(exp: Dict[str, Any], act: Dict[str, Any], path: str) -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []
    
    # Filter ignored keys
    exp_filtered = {k: v for k, v in exp.items() if k not in IGNORE_KEYS}
    act_filtered = {k: v for k, v in act.items() if k not in IGNORE_KEYS}
    
    exp_keys = set(exp_filtered.keys())
    act_keys = set(act_filtered.keys())
    
    for k in sorted(exp_keys - act_keys):
        diffs.append(("missing_in_student", _path_join(path, k), exp_filtered[k], None))
    for k in sorted(act_keys - exp_keys):
        # Evaluate extra keys more leniently or ignore if not in reference
        diffs.append(("extra_in_student", _path_join(path, k), None, act_filtered[k]))
    for k in sorted(exp_keys & act_keys):
        diffs.extend(compare_json(exp_filtered[k], act_filtered[k], _path_join(path, k)))
    return diffs


def _compare_lists(exp_list: List[Any], act_list: List[Any], path: str) -> List[Tuple[str, str, Any, Any]]:
    diffs: List[Tuple[str, str, Any, Any]] = []
    list_key = _detect_list_key(exp_list, path) or _detect_list_key(act_list, path)
    if list_key:
        # Build maps by key, considering only dicts with this key
        exp_map: Dict[Any, Any] = {}
        for item in exp_list:
            if isinstance(item, dict) and list_key in item:
                exp_map[str(item[list_key])] = item
        
        act_map: Dict[Any, Any] = {}
        for item in act_list:
            if isinstance(item, dict) and list_key in item:
                act_map[str(item[list_key])] = item

        exp_keys = set(exp_map.keys())
        act_keys = set(act_map.keys())
        
        for k in sorted(exp_keys - act_keys):
            diffs.append(("missing_item_in_student", _path_key(path, list_key, k), exp_map[k], None))
        for k in sorted(act_keys - exp_keys):
            diffs.append(("extra_item_in_student", _path_key(path, list_key, k), None, act_map[k]))
        for k in sorted(exp_keys & act_keys):
            diffs.extend(compare_json(exp_map[k], act_map[k], _path_key(path, list_key, k)))
        
        # Process elements without key
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
    for kind, path, exp, act in diffs:
        # Skip type differences if values match after string conversion
        if kind == "type_diff":
            if str(exp).strip() == str(act).strip():
                continue
            mismatches += 1
        elif kind == "value_diff":
            mismatches += 1
        elif kind == "list_len_diff":
            # Reduce impact of list length difference
            mismatches += min(abs((exp or 0) - (act or 0)), 5) 
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
        lines.append("MISSING")
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
            lines.append(f" - Missing in student: {path}")
        elif kind == "extra_in_student":
            lines.append(f" - Extra key in student: {path}")
        elif kind == "missing_item_in_student":
            lines.append(f" - Missing item in student: {path}")
        elif kind == "extra_item_in_student":
            lines.append(f" - Extra item in student: {path}")
        elif kind == "list_len_diff":
            lines.append(f" - Different list length: {path} — reference={exp}, student={act}")
        elif kind == "type_diff":
            lines.append(f" - Different data type: {path} — reference={exp}, student={act}")
        elif kind == "value_diff":
            lines.append(f" - Different value: {path}")
            exp_s = str(exp) if len(str(exp)) <= 200 else str(exp)[:200] + "…"
            act_s = str(act) if len(str(act)) <= 200 else str(act)[:200] + "…"
            lines.append(f" expected: {exp_s}")
            lines.append(f" student: {act_s}")
        else:
            lines.append(f" - Difference: {path}")
    if prev_errors_for_device is not None:
        current_errors = {l for l in lines if l.startswith(" - ")}
        new_errs = [e for e in current_errors if e not in prev_errors_for_device]
        if new_errs:
            lines.append("")
            lines.append("----------------------------")
            lines.append("New errors:")
            lines.extend(sorted(new_errs))
    return "\n".join(lines)


# NEW FUNCTIONS FOR NORMALIZED SCORING
ROUTER_KEYWORDS = {'router', 'rtr', 'cisco', 'mikrotik', 'routeur', 'маршрутизатор'}


def is_router_device(device_name: str) -> bool:
    """Determines if device is a router by file name"""
    return any(keyword in device_name.lower() for keyword in ROUTER_KEYWORDS)


def calculate_weighted_score(routers: List[Tuple[int, int]], pcs: List[Tuple[int, int]]) -> Tuple[float, float, float]:
    """Calculates weighted score: routers 60%, PCs 40%"""

    def group_score(group: List[Tuple[int, int]], total_weight: float) -> float:
        if not group:
            return total_weight  # No devices = full weight
        total_atoms = sum(atoms for atoms, _ in group)
        total_mismatches = sum(mismatches for _, mismatches in group)
        matches = max(0, total_atoms - total_mismatches)
        return total_weight * (matches / max(1, total_atoms))

    routers_score = group_score(routers, 60.0)
    pcs_score = group_score(pcs, 40.0)
    final_score = round((routers_score + pcs_score) / 100 * 100, 2)

    return final_score, routers_score, pcs_score


def comparator_main(lab: str, verbose: bool = True) -> float:
    """
    Compares student work with reference and creates report.
    NORMALIZED SCORE: routers 60%, PCs 40%.
    Args:
        lab: lab number (e.g., "1")
        verbose: Whether to print report to console (default True)
    Returns:
        float: final score percentage
    Raises:
        FileNotFoundError: If lab or student folder not found
    """
    example_dir = EXAMPLES_ROOT / (lab)
    student_dir = STUDENTS_ROOT / lab

    # Check folder existence
    if not example_dir.exists():
        raise FileNotFoundError(f"Lab folder not found: {example_dir}")
    if not student_dir.exists():
        raise FileNotFoundError(f"Student folder not found: {student_dir}")

    if verbose:
        get_logger().info(f"Lab: {lab}")

    expected_devices = set(p.stem for p in example_dir.iterdir() if p.is_file())
    actual_devices = set(p.stem for p in student_dir.iterdir() if p.is_file())
    all_devices = sorted(expected_devices | actual_devices)

    results_root = RESULT_PATH / lab
    results_root.mkdir(parents=True, exist_ok=True)

    prev_txt_path = find_previous_txt(results_root)
    prev_errors_by_device: Dict[str, Set[str]] = {}
    if prev_txt_path and prev_txt_path.exists():
        try:
            prev_text = prev_txt_path.read_text(encoding="utf-8")
            prev_errors_by_device = parse_prev_errors_by_device(prev_text)
        except Exception:
            prev_errors_by_device = {}

    # NEW WEIGHTED CALCULATION
    routers: List[Tuple[int, int]] = []  # (atoms, mismatches)
    pcs: List[Tuple[int, int]] = []
    device_reports: List[str] = []

    for device in all_devices:
        expected = load_first_existing_by_stem(example_dir, device)
        actual = load_first_existing_by_stem(student_dir, device)

        if expected is None and actual is None:
            continue
        elif expected is None:
            diffs = [("extra_in_student", device, None, "<entire file>")]
            expected_root = {}
        elif actual is None:
            diffs = [("missing_in_student", device, "<entire file>", None)]
            expected_root = expected
        else:
            diffs = compare_json(expected, actual, "")
            expected_root = expected

        device_atoms = count_atoms(expected_root)
        device_mismatches = count_mismatched_atoms(diffs)

        # Classification and weight accumulation
        if is_router_device(device):
            routers.append((device_atoms, device_mismatches))
        else:
            pcs.append((device_atoms, device_mismatches))

        prev_errs = prev_errors_by_device.get(device)
        device_text = build_device_report(device, diffs, prev_errs)
        device_reports.append(device_text)

    # CALCULATE NORMALIZED SCORE
    final_score, routers_weight, pcs_weight = calculate_weighted_score(routers, pcs)

    header = f"Match: {final_score:.2f}% (Routers: {routers_weight:.1f}%, PCs: {pcs_weight:.1f}%)"
    final_text = header + "\n\n\n" + ("\n\n\n".join(device_reports) if device_reports else "")

    out_name = f"{lab}.csv"
    out_path = results_root / out_name
    out_path.write_text(final_text, encoding="utf-8")

    if verbose:
        get_logger().info(final_text)
        get_logger().info(f"Report saved: {out_path}")

    shutil.rmtree(student_dir)
    return final_score


def main() -> None:
    """Interactive mode"""
    lab_name = choose_lab_name()
    try:
        comparator_main(lab_name.split("_")[1], verbose=True)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
