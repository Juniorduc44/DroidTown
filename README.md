# DroidTown

An AI-powered security scanning tool that audits your code for vulnerabilities, hardcoded secrets, and insecure patterns.

## Quick Start

```bash
git clone git@github.com:cbman0/DroidTown.git
cd DroidTown
cd security-agent && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
chmod +x scan
```

Run a scan:

```bash
./scan myfile.py    # scan a single file
./scan src/         # scan a folder
./scan .            # scan current directory
```

## Global Install

Want to use `scan` from anywhere on your system? Follow the setup guide:

**[How to set up the global `scan` command](howTo/global-scan-setup.md)**
