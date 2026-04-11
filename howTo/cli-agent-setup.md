# CLI Agent — Setup & Usage Guide

The CLI Agent is an AI-powered filesystem and shell assistant. Give it a task in plain English and it will read, write, move, copy, delete files, run commands, and manage environment variables on your behalf.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running with the `glm-5.1:cloud` model
- Git

## Setup

### Step 1: Clone the Repository (skip if already cloned)

```bash
git clone git@github.com:cbman0/DroidTown.git
cd DroidTown
```

### Step 2: Set Up the Virtual Environment

```bash
cd cli-agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

## Usage

There are two ways to use the CLI Agent.

### Interactive Mode (REPL)

Launch the agent and type tasks one at a time in a loop:

```bash
cd cli-agent
source venv/bin/activate
python agent.py
```

You'll see a prompt:

```
> list all files in /home/user/projects
> create a folder called backup and copy config.yaml into it
> read the contents of /etc/hostname
> exit
```

Type `exit`, `quit`, or `q` to leave.

### Single Command Mode

Pass the task directly as an argument:

```bash
cd cli-agent
source venv/bin/activate
python agent.py "create a file called notes.txt with the text Hello World"
```

The agent runs the task and prints the result.

## Available Tools

The agent has access to the following tools:

| Tool | Description |
|------|-------------|
| `read_file` | Read the contents of any file |
| `write_file` | Write content to a file (creates parent dirs, overwrites if exists) |
| `append_file` | Append content to the end of a file |
| `list_directory` | List all files and folders in a directory |
| `move_path` | Move a file or folder to a new location |
| `copy_path` | Copy a file or folder to a new location |
| `delete_path` | Delete a file or folder (recursive for directories) |
| `create_directory` | Create a directory and any parent directories |
| `run_command` | Run any shell command (30 second timeout) |
| `get_env` | Get the value of an environment variable |
| `set_env` | Set an environment variable for the current session |

## Example Tasks

Here are some things you can ask the agent to do:

```
> list everything in my home directory
> create a folder called logs and put an empty file called app.log inside
> read the file at /etc/os-release
> move notes.txt to backup/notes.txt
> copy the entire src folder to src_backup
> delete the temp directory
> run the command: df -h
> what is the PATH environment variable set to?
> set MY_VAR to hello and then print it
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'langchain_ollama'"
Make sure you activated the virtual environment before running:
```bash
source venv/bin/activate
```

### Ollama connection errors
Make sure Ollama is running:
```bash
ollama serve
```
And that the model is available:
```bash
ollama list
```

### Command times out
The `run_command` tool has a 30-second timeout. For long-running processes, break the task into smaller steps or run the command directly in your terminal.

### Agent doesn't do what I asked
Try being more specific. Instead of "organize my files", try "move all .txt files from Downloads to Documents/notes".
