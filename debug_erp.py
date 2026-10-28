import asyncio
from bs4 import BeautifulSoup
import iitkgp_erp_login.erp as erp
import requests

def main():
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    sessionToken, ssoToken = erp.login(headers, session)
    
    url = "https://erp.iitkgp.ac.in/Acad/timetable_track.jsp?action=second&dept=CH"
    response = session.get(url)
    
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", id="disptab")
    
    # Find the cell that contains CH21202
    for cell in table.find_all("td"):
        if "CH21202" in cell.get_text():
            print("\n--- RAW HTML OF THE CELL ---")
            print(cell.prettify())
            break

if __name__ == "__main__":
    main()