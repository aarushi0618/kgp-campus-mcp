"""Personalized Student ERP Timetable Sync Daemon (Shadow Sync Pipeline)."""
import sys
from pathlib import Path
import importlib.util

# Load scripts/erp_shadow_sync.py by file path to bypass win32/scripts conflict on Windows
_script_path = Path(__file__).resolve().parent / "scripts" / "erp_shadow_sync.py"
_spec = importlib.util.spec_from_file_location("kgp_erp_shadow_sync", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

main = _mod.main
run_sync = _mod.run_sync
parse_visual_grid = _mod.parse_visual_grid
fetch_student_timetable_html = _mod.fetch_student_timetable_html

__all__ = ["main", "run_sync", "parse_visual_grid", "fetch_student_timetable_html"]

if __name__ == "__main__":
    main()
