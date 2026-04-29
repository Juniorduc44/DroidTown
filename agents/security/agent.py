import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent / "shared"))

from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool

from reporter import generate_professional_report
from model_select import select_model
from runtime import get_llm, RUNTIME, Runtime, print_runtime_banner
from token_counter import SessionCounter, OllamaTokenCallback, print_token_summary

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


def build_agent(model_name: str = None):
    """Create the agent. Uses unified runtime — Ollama or Claude API."""
    if model_name:
        llm = ChatOllama(model=model_name, temperature=0.0)
    else:
        llm = get_llm(droid="reviewer")
        if llm is None:
            return None  # Claude Code runtime — no agent process needed
    return create_agent(model=llm, tools=[review_code], system_prompt=SYSTEM_PROMPT)

# Module-level agent for imports from scan.py — initialized lazily
agent = None

def get_agent():
    """Get or create the agent. Used by scan.py imports."""
    global agent
    if agent is None:
        model_name = select_model()
        os.environ["DROIDTOWN_MODEL"] = model_name
        agent = build_agent(model_name)
    return agent


# ====================== Main CLI ======================
if __name__ == "__main__":
    print_runtime_banner()
    counter  = SessionCounter()
    callback = OllamaTokenCallback(counter)
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

    active_agent = get_agent()
    # Attach token callback to the underlying LLM
    if hasattr(active_agent, "agent") and hasattr(active_agent.agent, "llm"):
        active_agent.agent.llm.callbacks = [callback]

    # Run security audit
    result = active_agent.invoke({
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
    print_token_summary(counter, os.environ.get("DROIDTOWN_MODEL", ""))