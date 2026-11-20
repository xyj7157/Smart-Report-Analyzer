import pdfplumber

def read_pdf_text(pdf_path: str) -> str:
    print(f"正在解析文件: {pdf_path} ...")
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:20]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text