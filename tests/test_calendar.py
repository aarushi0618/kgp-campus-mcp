"""Tests for the Calendar Adapter."""
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter

def test_calendar_regex_parsing():
    """Test that the adapter correctly parses the messy IIT KGP text."""
    adapter = CalendarAdapter(url="http://fake-url.com/calendar.pdf")
    
    # Exact messy lines from the PDF you provided
    messy_lines = [
        "(a)Date of opening of link in ERP for SAIP application for 2nd Yr UG students12.06.2026Friday",
        "3Last date for dropping of Additional Subjects11.09.2026Friday",
        "32MID-SPRING SEMESTER EXAMINATION for all theory subjects22.02.2027 to 05.03.2027Monday to Friday",
        "6MID-AUTUMN SEMESTER EXAMINATION for all theory subjects21.09.2026 to 01.10.2026Monday to Thursday"
    ]
    
    for line in messy_lines:
        entity = adapter._parse_line(line)
        assert entity is not None, f"Failed to parse: {line}"
        assert entity.entity_type == "calendar_entry"
        assert entity.metadata["date"] is not None
        assert entity.metadata["day"] is not None
        print(f"\nParsed Event: {entity.title}")
        print(f"Date: {entity.metadata['date']} | Day: {entity.metadata['day']}")

def test_calendar_ignores_headers():
    """Test that headers and short lines are ignored."""
    adapter = CalendarAdapter()
    assert adapter._parse_line("SI. No. EVENT DATE DAY") is None
    assert adapter._parse_line("") is None
    assert adapter._parse_line("1") is None