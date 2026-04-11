import sys
import os
from pathlib import Path
from agent_00 import agent   # Make sure this imports correctly from your agent_00.py

# Directories to completely skip (common noise/junk folders)
EXCLUDE_DIRS = {
    'venv', 'env', '.venv', '.env', 
    '__pycache__', 
    'node_modules', 
    '.git', 
    '.idea', 
    '.vscode', 
    'build', 
    'dist', 
    'eggs', 
    '*.egg-info'
}

def should_skip_path(path: Path) -> bool:
    """Return True if this path should be skipped."""
    # Skip if any part of the path contains an excluded directory
    parts = path.parts
    for part in parts:
        part_lower = part.lower()
        if part_lower in EXCLUDE_DIRS:
            return True
        # Also skip hidden directories (except .env files if needed)
        if part.startswith('.') and part not in {'.env', '.env.example'}:
            return True
    return False


def get_python_files(target: str):
    """Get all .py files, skipping venv and other junk directories."""
    path = Path(target).resolve()

    if path.is_file() and path.suffix == '.py':
        return [path]

    python_files = []
    
    for file in path.rglob("*.py"):
        if should_skip_path(file):
            continue
        python_files.append(file)

    return python_files


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scan.py <folder_or_file>")
        print("Examples:")
        print("  python scan.py .                    # scan current project")
        print("  python scan.py src/                 # scan specific folder")
        print("  python scan.py test-secret.py       # scan single file")
        sys.exit(1)

    target = sys.argv[1]
    
    print("🚀 Starting security scan...\n")
    print("Note: Skipping venv, .git, __pycache__, node_modules, etc.\n")

    files_to_scan = get_python_files(target)

    if not files_to_scan:
        print(f"No Python files found in: {target}")
        sys.exit(0)

    print(f"Found {len(files_to_scan)} Python file(s) to scan.\n")

    for file_path in files_to_scan:
        relative_path = file_path.relative_to(Path(target).resolve()) if Path(target).resolve() in file_path.parents else file_path
        
        print(f"{'='*90}")
        print(f"🔍 Scanning: {relative_path}")
        print(f"{'='*90}")

        try:
            result = agent.invoke({
                "messages": [{
                    "role": "user",
                    "content": f"Review this file for security issues: {file_path}"
                }]
            })

            # Clean output extraction
            output = result
            if isinstance(result, dict):
                if "messages" in result and result["messages"]:
                    output = result["messages"][-1].content
                elif "output" in result:
                    output = result["output"]

            print(output)
            print("\n")

        except Exception as e:
            print(f"❌ Error scanning {relative_path}: {e}\n")

    print("✅ Folder security scan completed!")