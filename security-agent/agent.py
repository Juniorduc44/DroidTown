from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool

# Your SYSTEM_PROMPT (keep as is)
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
    """Read the content of a file so the security auditor can analyze it for vulnerabilities.
    
    Args:
        file_path: Full path to the file to review.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return f"--- File: {file_path} ---\n\n{content}"
    except Exception as e:
        return f"Error reading file {file_path}: {str(e)}"


llm = ChatOllama(
    model="glm-5.1:cloud",
    temperature=0.0,
)

# This combination works in most current setups
agent = create_agent(
    model=llm,
    tools=[review_code],
    system_prompt=SYSTEM_PROMPT
)

print("✅ Security Agent is ready! (using GLM-5.1:cloud)")
