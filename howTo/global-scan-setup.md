# Setting Up the `scan` Command Globally

This guide walks you through making the `scan` command available system-wide so you can run it from any directory.

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
chmod +x scan
```

## Step 4: Create a Symlink in Your PATH

Choose the option that fits your system:

### Option A: User-level install (no sudo required)

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/scan" ~/.local/bin/scan
```

Make sure `~/.local/bin` is in your PATH. If it isn't, add this to your `~/.bashrc` or `~/.zshrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload your shell:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

### Option B: System-wide install (requires sudo)

```bash
sudo ln -sf "$(pwd)/scan" /usr/local/bin/scan
```

## Step 5: Verify It Works

```bash
scan
```

You should see:

```
Usage: scan <file_or_folder>

Examples:
  scan myfile.py          # scan a single file
  scan .                  # scan current directory
  scan src/               # scan a folder
```

## Usage

```bash
# Scan a single file
scan path/to/file.py

# Scan an entire directory
scan path/to/project/

# Scan current directory
scan .
```

## Troubleshooting

### "venv not found" error
Go back to [Step 2](#step-2-set-up-the-virtual-environment) and make sure the virtual environment was created inside `agents/`.

### "scan: command not found"
Make sure the symlink directory is in your PATH. Run `echo $PATH` to check. See [Step 4](#step-4-create-a-symlink-in-your-path) for adding it.

### Ollama connection errors
Make sure Ollama is running (`ollama serve`) and the `glm-5.1:cloud` model is available.

## Uninstall

To remove the global command:

```bash
rm ~/.local/bin/scan        # Option A
# or
sudo rm /usr/local/bin/scan # Option B
```
