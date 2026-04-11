import sys
import os
import shutil
import subprocess
import httpx
from pathlib import Path
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


def check_ollama_auth():
    """Verify Ollama is running and cloud model auth works before starting."""
    try:
        resp = httpx.post(
            "http://localhost:11434/api/chat",
            json={"model": "glm-5.1:cloud", "messages": [{"role": "user", "content": "hi"}], "stream": False},
            timeout=15,
        )
        if resp.status_code == 401 or "unauthorized" in resp.text.lower():
            console.print(Panel(
                "[bold red]Ollama cloud model requires authentication.[/bold red]\n\n"
                "Run the following in your terminal to sign in:\n\n"
                "  [bold cyan]ollama signin[/bold cyan]\n\n"
                "Then try again.",
                title="❌ Unauthorized", border_style="red"
            ))
            sys.exit(1)
    except httpx.ConnectError:
        console.print(Panel(
            "[bold red]Cannot connect to Ollama.[/bold red]\n\n"
            "Make sure Ollama is running:\n\n"
            "  [bold cyan]ollama serve[/bold cyan]",
            title="❌ Connection Error", border_style="red"
        ))
        sys.exit(1)
    except Exception:
        pass

SYSTEM_PROMPT = """You are a CLI assistant with full filesystem access. You can read, write, create, move, copy, delete, and list files and folders. You can also run shell commands and manage environment variables.

When given a task:
1. Break it down into steps
2. Use the available tools to complete each step
3. Confirm what you did with a brief summary

Be precise and careful. Always confirm destructive actions (delete, overwrite) in your response. If a path doesn't exist, say so clearly. Use absolute paths when possible."""


@tool
def read_file(file_path: str) -> str:
    """Read the contents of a file."""
    try:
        path = Path(file_path).resolve()
        if not path.exists():
            return f"Error: '{file_path}' does not exist."
        if not path.is_file():
            return f"Error: '{file_path}' is not a file."
        content = path.read_text(encoding="utf-8")
        return f"--- {path} ---\n\n{content}"
    except Exception as e:
        return f"Error reading '{file_path}': {e}"


@tool
def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Creates the file and parent directories if they don't exist. Overwrites existing content."""
    try:
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing to '{file_path}': {e}"


@tool
def append_file(file_path: str, content: str) -> str:
    """Append content to the end of a file. Creates the file if it doesn't exist."""
    try:
        path = Path(file_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully appended to {path}"
    except Exception as e:
        return f"Error appending to '{file_path}': {e}"


@tool
def list_directory(directory_path: str) -> str:
    """List all files and folders in a directory."""
    try:
        path = Path(directory_path).resolve()
        if not path.exists():
            return f"Error: '{directory_path}' does not exist."
        if not path.is_dir():
            return f"Error: '{directory_path}' is not a directory."
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            prefix = "📁" if entry.is_dir() else "📄"
            size = f" ({entry.stat().st_size} bytes)" if entry.is_file() else ""
            lines.append(f"{prefix} {entry.name}{size}")
        return f"Contents of {path}:\n\n" + "\n".join(lines) if lines else f"{path} is empty."
    except Exception as e:
        return f"Error listing '{directory_path}': {e}"


@tool
def move_path(source: str, destination: str) -> str:
    """Move a file or folder from source to destination."""
    try:
        src = Path(source).resolve()
        dst = Path(destination).resolve()
        if not src.exists():
            return f"Error: source '{source}' does not exist."
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved {src} -> {dst}"
    except Exception as e:
        return f"Error moving '{source}' to '{destination}': {e}"


@tool
def copy_path(source: str, destination: str) -> str:
    """Copy a file or folder from source to destination."""
    try:
        src = Path(source).resolve()
        dst = Path(destination).resolve()
        if not src.exists():
            return f"Error: source '{source}' does not exist."
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))
        return f"Copied {src} -> {dst}"
    except Exception as e:
        return f"Error copying '{source}' to '{destination}': {e}"


@tool
def delete_path(target_path: str) -> str:
    """Delete a file or folder. Folders are deleted recursively."""
    try:
        path = Path(target_path).resolve()
        if not path.exists():
            return f"Error: '{target_path}' does not exist."
        if path.is_dir():
            shutil.rmtree(str(path))
            return f"Deleted directory: {path}"
        else:
            path.unlink()
            return f"Deleted file: {path}"
    except Exception as e:
        return f"Error deleting '{target_path}': {e}"


@tool
def create_directory(directory_path: str) -> str:
    """Create a directory and any necessary parent directories."""
    try:
        path = Path(directory_path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return f"Created directory: {path}"
    except Exception as e:
        return f"Error creating directory '{directory_path}': {e}"


@tool
def run_command(command: str) -> str:
    """Run a shell command and return its output. Use for tasks like grep, find, chmod, etc."""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}"
        if not output:
            output = "(no output)"
        return f"Exit code: {result.returncode}\n{output}"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after 30 seconds."
    except Exception as e:
        return f"Error running command: {e}"


@tool
def get_env(variable_name: str) -> str:
    """Get the value of an environment variable."""
    value = os.environ.get(variable_name)
    if value is None:
        return f"Environment variable '{variable_name}' is not set."
    return f"{variable_name}={value}"


@tool
def set_env(variable_name: str, value: str) -> str:
    """Set an environment variable for the current session."""
    os.environ[variable_name] = value
    return f"Set {variable_name}={value}"


TOOLS = [
    read_file,
    write_file,
    append_file,
    list_directory,
    move_path,
    copy_path,
    delete_path,
    create_directory,
    run_command,
    get_env,
    set_env,
]

llm = ChatOllama(model="glm-5.1:cloud", temperature=0.0)

agent = create_agent(
    model=llm,
    tools=TOOLS,
    system_prompt=SYSTEM_PROMPT
)


def run_task(task: str):
    """Run a single task through the agent with error handling."""
    console.print(Panel(f"[bold]{task}[/bold]", title="📋 Task", border_style="cyan"))
    try:
        result = agent.invoke({
            "messages": [{"role": "user", "content": task}]
        })
        output = result["messages"][-1].content if isinstance(result, dict) and "messages" in result else str(result)
        console.print(Panel(Markdown(output), title="✅ Result", border_style="green", padding=(1, 2)))
    except Exception as e:
        err = str(e)
        if "unauthorized" in err.lower() or "401" in err:
            console.print(Panel(
                "[bold red]Authentication expired or invalid.[/bold red]\n\n"
                "Run: [bold cyan]ollama signin[/bold cyan]",
                title="❌ Unauthorized", border_style="red"
            ))
        else:
            console.print(Panel(f"[bold red]{err}[/bold red]", title="❌ Error", border_style="red"))


if __name__ == "__main__":
    check_ollama_auth()

    if len(sys.argv) > 1:
        run_task(" ".join(sys.argv[1:]))
    else:
        console.print(Panel(
            "[bold cyan]DroidTown CLI Agent[/bold cyan]\nType a task and press Enter. Type 'exit' to quit.",
            border_style="blue"
        ))
        while True:
            try:
                task = console.input("[bold yellow]> [/bold yellow]")
            except (EOFError, KeyboardInterrupt):
                break
            if task.strip().lower() in ("exit", "quit", "q"):
                console.print("[dim]Goodbye.[/dim]")
                break
            if not task.strip():
                continue
            run_task(task)
