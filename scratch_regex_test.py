"""Scratch script to test our Regex parsing without needing a valid PDF file."""
from kgp_mcp.adapters.calendar_adapter import CalendarAdapter

def test_parsing():
    adapter = CalendarAdapter(url="local_test")
    
    # These are the EXACT messy strings from your uploaded document
    messy_lines = [
        "(a)Date of opening of link in ERP for SAIP application for 2nd Yr UG students12.06.2026Friday",
        "1SAIP /SAPP Application(a)Date of opening...25.06.2026Thursday",
        "3Last date for dropping of Additional Subjects11.09.2026Friday",
        "32MID-SPRING SEMESTER EXAMINATION for all theory subjects22.02.2027 to 05.03.2027Monday to Friday",
        "6MID-AUTUMN SEMESTER EXAMINATION for all theory subjects21.09.2026 to 01.10.2026Monday to Thursday",
        "18Winter break [for UG (except Dual Degree V Year), LLB, LLM, MBA, MHRM students]01.12.2026 to 01.01.2027Tuesday to Thursday"
    ]
    
    print("Testing Regex Parser...\n")
    success_count = 0
    
    for line in messy_lines:
        entity = adapter._parse_line(line)
        if entity:
            success_count += 1
            print(f"✅ SUCCESS")
            print(f"   Event: {entity.title}")
            print(f"   Date:  {entity.metadata['date']}")
            print(f"   Day:   {entity.metadata['day']}\n")
        else:
            print(f"❌ FAILED to parse: {line}\n")

    print(f"Total parsed: {success_count}/{len(messy_lines)}")

if __name__ == "__main__":
    test_parsing()