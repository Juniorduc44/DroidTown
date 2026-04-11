import sys
from pathlib import Path
from agent import agent          # ← Updated import (agent.py)
from reporter import generate_professional_report

# Directories to skip
EXCLUDE_DIRS = {'venv', 'env', '.venv', '.env', '__pycache__', 'node_modules', '.git', '.idea', '.vscode', 'build', 'dist'}

def should_skip_path(path: Path) -> bool:
    return any(ex.lower() in p.lower() for p in path.parts for ex in EXCLUDE_DIRS)

def get_python_files(target: str):
    path = Path(target).resolve()
    if path.is_file() and path.suffix == '.py':
        return [path]
    
    return [f for f in path.rglob("*.py") if not should_skip_path(f)]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scan.py <folder_or_file>")
        print("Examples:")
        print("  python scan.py .")
        print("  python scan.py src/")
        sys.exit(1)

    target = sys.argv[1]
    print("🚀 Starting full security scan with professional report...\n")

    files_to_scan = get_python_files(target)
    if not files_to_scan:
        print(f"No Python files found in: {target}")
        sys.exit(0)

    print(f"Found {len(files_to_scan)} Python file(s).\n")

    all_findings = []

    for file_path in files_to_scan:
        relative = file_path.relative_to(Path.cwd()) if file_path.is_relative_to(Path.cwd()) else file_path
        print(f"🔍 Scanning: {relative}")

        result = agent.invoke({
            "messages": [{"role": "user", "content": f"Review this file for security issues: {file_path}"}]
        })

        output = result["messages"][-1].content if isinstance(result, dict) and "messages" in result else str(result)
        all_findings.append({"file": str(relative), "findings": output})

    # Generate nice report
    print("\n" + "="*90)
    print("📋 Generating Professional Security Report...")
    print("="*90)
    generate_professional_report(all_findings)

    print("\n✅ Scan and report generation completed!")