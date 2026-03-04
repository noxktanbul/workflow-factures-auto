import json
import os
import subprocess
import sys
import platform

def run_command(command):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

def check_python_version():
    return sys.version

def check_tesseract():
    # Try common default installation paths
    paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in paths:
        if os.path.exists(p):
            ver_output = run_command(f'"{p}" --version')
            return {"installed": True, "path": p, "version": ver_output.split('\n')[0] if ver_output else "Unknown"}
    
    # Try system PATH
    ver_output = run_command("tesseract --version")
    if "tesseract" in ver_output.lower():
        return {"installed": True, "path": "in PATH", "version": ver_output.split('\n')[0]}
    
    return {"installed": False}

def check_ghostscript():
    paths = [
        r"C:\Program Files\gs\gs*\bin\gswin64c.exe",
        r"C:\Program Files (x86)\gs\gs*\bin\gswin32c.exe"
    ]
    import glob
    for p in paths:
        found = glob.glob(p)
        if found:
            ver_output = run_command(f'"{found[0]}" --version')
            return {"installed": True, "path": found[0], "version": ver_output}
    return {"installed": False}

def check_poppler():
     # Poppler is usually needed for pdf2image if we process PDFs via images
     paths = [
         r"C:\poppler*\bin\pdfinfo.exe",
         r"C:\Program Files\poppler*\bin\pdfinfo.exe"
     ]
     import glob
     for p in paths:
        found = glob.glob(p)
        if found:
            return {"installed": True, "path": os.path.dirname(found[0])}
     return {"installed": False}

def check_z_drive():
    return os.path.exists("Z:\\")

def generate_report():
    report = {
        "os": platform.platform(),
        "python": check_python_version(),
        "tesseract_ocr": check_tesseract(),
        "ghostscript": check_ghostscript(),
        "poppler": check_poppler(),
        "z_drive_accessible": check_z_drive()
    }
    
    with open("audit_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4)
    print("Audit completed. Report saved to audit_report.json")

if __name__ == "__main__":
    generate_report()
