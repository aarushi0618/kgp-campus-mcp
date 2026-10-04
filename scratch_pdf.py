"""Scratch script with pypdf fallback."""
import pdfplumber
from pypdf import PdfReader

PDF_PATH = "ACADEMIC_CALENDAR_2026_27.pdf"

def explore_pdf():
    print(f"Opening PDF: {PDF_PATH}...\n")
    
    # Method 1: pdfplumber
    print("--- pdfplumber ---")
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"Total pages: {len(pdf.pages)}")
        for i, page in enumerate(pdf.pages[:2]):
            text = page.extract_text()
            if text:
                print(f"Page {i+1} text preview: {text[:300]}")
            else:
                print(f"Page {i+1}: NO TEXT (probably image-based)")

    # Method 2: pypdf fallback
    print("\n--- pypdf (fallback) ---")
    try:
        reader = PdfReader(PDF_PATH)
        print(f"Total pages: {len(reader.pages)}")
        for i, page in enumerate(reader.pages[:2]):
            text = page.extract_text()
            if text:
                print(f"Page {i+1} text preview: {text[:300]}")
            else:
                print(f"Page {i+1}: NO TEXT")
    except Exception as e:
        print(f"pypdf failed: {e}")

if __name__ == "__main__":
    explore_pdf()