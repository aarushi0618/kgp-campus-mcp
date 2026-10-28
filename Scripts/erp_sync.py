"""Admin Script: Logs into ERP and scrapes ALL academic unit timetables."""
from Scripts.erp_full_sync import main, parse_timetable_table  # noqa: F401

if __name__ == "__main__":
    main()
