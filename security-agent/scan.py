import sys
import os
from pathlib import Path
from agent import agent   # Import the agent from your agent.py

def get_python_files(path: str):
    """Get all .py files in a directory (recursive)"""
    path = Path(path)
    if path.is_file():
        return [path]
    
    python_files = []
    for ext in ['*.py', '*.pyw']:
        python_files.extend(path.rglob(ext))
    return python_files


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scan.py <folder_or_file>")
        print("Example:")
        print("  python scan.py .                    # scan current folder")
        print("  python scan.py src/                 # scan src folder")
        print("  python scan.py test-secret.py       # scan single file")
        sys.exit(1)

    target = sys.argv[1]
    
    print("🚀 Starting security scan...\n")
    
    files_to_scan = get_python_files(target)
    
    if not files_to_scan:
        print(f"No Python files found in: {target}")
        sys.exit(1)

    print(f"Found {len(files_to_scan)} Python file(s) to scan.\n")

    for file_path in files_to_scan:
        print(f"{'='*80}")
        print(f"🔍 Scanning: {file_path}")
        print(f"{'='*80}")

        try:
            result = agent.invoke({
                "messages": [{
                    "role": "user",
                    "content": f"Review this file for security issues: {file_path}"
                }]
            })

            # Extract clean output
            output = result
            if isinstance(result, dict):
                if "messages" in result and result["messages"]:
                    output = result["messages"][-1].content
                elif "output" in result:
                    output = result["output"]

            print(output)
            print("\n")

        except Exception as e:
            print(f"Error scanning {file_path}: {e}\n")

    print("✅ Folder scan completed!")
