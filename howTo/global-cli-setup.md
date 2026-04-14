# Setting Up the `cli` Command Globally

This guide makes the DroidTown CLI Agent available system-wide so you can run it from any directory.

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.com/) installed and running
- Git

## Step 1: Clone the Repository

```bash
git clone git@github.com:cbman0/DroidTown.git
cd DroidTown
```

## Step 2: Set Up the Virtual Environment

```bash
cd agents
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..
```

## Step 3: Make the Script Executable

```bash
chmod +x cli
```

## Step 4: Create a Symlink in Your PATH

Choose the option that fits your system:

### Option A: User-level install (no sudo required)

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/cli" ~/.local/bin/cli
```

Make sure `~/.local/bin` is in your PATH. If it is not, add this to your `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

### Option B: System-wide install (requires sudo)

```bash
sudo ln -sf "$(pwd)/cli" /usr/local/bin/cli
```

## Step 5: Verify It Works

```bash
cli
```

You should see the interactive DroidTown CLI Agent prompt.

## Usage

```bash
# Interactive mode
cli

# Single task mode
cli "list all files in the current directory"
```

The launcher preserves your current directory as the CLI agent working scope, so relative paths resolve where you ran `cli`.

## Troubleshooting

### "venv not found" error

Go back to Step 2 and ensure the virtual environment exists at `DroidTown/agents/venv`.

### "cli: command not found"

Ensure the symlink directory is in your PATH (`echo $PATH`) and that Step 4 completed successfully.

### Ollama connection errors

Confirm Ollama is running (`ollama serve`) and a model is available (`ollama list`).

## Uninstall

```bash
rm ~/.local/bin/cli        # Option A
# or
sudo rm /usr/local/bin/cli # Option B
```
