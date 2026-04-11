import sys
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool

# Import the reporter function
from reporter import generate_professional_report

SYSTEM_PROMPT = """You are a strict security auditor. Your sole job is to scan every file provided or discovered for security vulnerabilities. Be extremely thorough.

What to look for:
- Hardcoded credentials, API keys, tokens, passwords, secrets
- SQL injection risks
- Unsafe code execution (eval, exec, shell=True, etc.)
- Weak cryptography
- Insecure patterns (disabled TLS, permissive CORS, etc.)

Return findings ONLY as a clean markdown list with severity (CRITICAL / HIGH / MEDIUM / LOW) and exact location. 
If no issues: return '## Findings\n\nNo security issues detected.'"""

@tool
def review_code(file_path: str) -> str:
    """Read the content of a file so the security auditor can analyze it for vulnerabilities."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return f"--- File: {file_path} ---\n\n{content}"
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"


llm = ChatOllama(model="glm-5.1:cloud", temperature=0.0)

agent = create_agent(
    model=llm,
    tools=[review_code],
    system_prompt=SYSTEM_PROMPT
)


# ====================== Main CLI ======================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py <file_path>")
        print("Example: python agent.py test-secret.py")
        print("         python agent.py src/main.py")
        sys.exit(1)

    file_path = sys.argv[1]
    path = Path(file_path)

    if not path.exists():
        print(f"❌ Error: File '{file_path}' not found.")
        sys.exit(1)

    if not path.is_file():
        print(f"❌ Error: '{file_path}' is not a file. Use scan.py for folders.")
        sys.exit(1)

    print(f"🔍 Scanning file: {path.name}\n")

    # Run security audit
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"Review this file for security issues: {file_path}"
        }]
    })

    output = result["messages"][-1].content if isinstance(result, dict) and "messages" in result else str(result)

    # Wrap single file result into professional report format
    findings_list = [{"file": str(path.name), "findings": output}]

    print("\n" + "="*80)
    print("📋 Generating Professional Report...")
    print("="*80)

    generate_professional_report(findings_list)