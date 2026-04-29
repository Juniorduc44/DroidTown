"""
DroidTown agent-workspace helpers.

Droids add task-specific utilities here. Core runtime (gpu_detect, model_select,
runtime) stays in agents/shared/. Put reusable task primitives here.
"""

from pathlib import Path
import subprocess
import json
import os

WORKSPACE = Path(__file__).resolve().parent
DOMAIN_SKILLS = WORKSPACE / "domain-skills"
REPORTS_DIR = Path(os.environ.get("SCAN_OUTPUT_DIR", "."))


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def write_report(name: str, content: str) -> Path:
    """Write a markdown report to the output directory. Returns the path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Domain-skill helpers
# ---------------------------------------------------------------------------

def load_skill(domain: str, skill: str) -> str | None:
    """Load a domain skill markdown file. Returns content or None if missing."""
    path = DOMAIN_SKILLS / domain / f"{skill}.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def save_skill(domain: str, skill: str, content: str) -> Path:
    """Save a learned skill for a domain. Droids call this when they discover something reusable."""
    skill_dir = DOMAIN_SKILLS / domain
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / f"{skill}.md"
    path.write_text(content, encoding="utf-8")
    return path


def list_skills(domain: str | None = None) -> list[str]:
    """List available domain skills. Pass domain to filter, or None for all."""
    if domain:
        base = DOMAIN_SKILLS / domain
        if not base.exists():
            return []
        return [f.stem for f in base.glob("*.md")]
    results = []
    for d in DOMAIN_SKILLS.iterdir():
        if d.is_dir():
            results.extend(f"{d.name}/{f.stem}" for f in d.glob("*.md"))
    return results


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------

def run(cmd: str, cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout,
        cwd=cwd or os.getcwd()
    )
    return result.returncode, result.stdout, result.stderr


def run_ok(cmd: str, cwd: str | None = None) -> str:
    """Run a shell command, raise on non-zero exit. Returns stdout."""
    code, out, err = run(cmd, cwd=cwd)
    if code != 0:
        raise RuntimeError(f"Command failed ({code}): {cmd}\n{err}")
    return out


# ---------------------------------------------------------------------------
# Context board helpers
# ---------------------------------------------------------------------------

CONTEXT_FILE = Path(__file__).resolve().parent.parent / "context.md"


def update_context_task(droid: str, task: str, status: str, output: str = "—") -> None:
    """Update the last droid activity table in context.md."""
    if not CONTEXT_FILE.exists():
        return
    content = CONTEXT_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if line.startswith(f"| {droid} |"):
            new_lines.append(f"| {droid} | {task[:60]} | {status} | {output} |")
        else:
            new_lines.append(line)
    CONTEXT_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
