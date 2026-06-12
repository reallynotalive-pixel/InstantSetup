#!/usr/bin/env python3
"""
setup_machine.py — Interactive machine setup tool
Asks what you do with your computer, then installs the right packages.
Supports: apt (system), pip (Python), npm -g (Node globals)
Compatible: Ubuntu 24.04 LTS / Debian 12+
"""

import subprocess
import sys
import shutil
import os
import re
from pathlib import Path


# ─── Package Definitions ────────────────────────────────────────────────────

CATEGORIES = {
    "use_cases": {
        "label": "Primary use case(s)",
        "options": {
            "1": {
                "label": "Software Development",
                "apt": ["git", "curl", "wget", "build-essential", "make", "gcc", "g++",
                        "pkg-config", "libssl-dev", "unzip", "zip", "jq", "htop", "tree"],
                "pip": ["black", "ruff", "httpie", "rich", "pre-commit"],
                "npm": [],
            },
            "2": {
                "label": "Gaming / Media",
                "apt": ["ffmpeg", "vlc", "imagemagick", "yt-dlp", "pulseaudio",
                        "pavucontrol", "steam-installer"],
                "pip": ["yt-dlp"],
                "npm": [],
            },
            "3": {
                "label": "Security / Pentesting",
                "apt": ["nmap", "netcat-openbsd", "wireshark", "tcpdump", "john",
                        "hydra", "sqlmap", "dirb", "nikto", "aircrack-ng",
                        "net-tools", "dnsutils", "whois", "traceroute"],
                "pip": ["impacket", "scapy", "requests", "paramiko"],
                "npm": [],
            },
            "4": {
                "label": "General / Productivity",
                "apt": ["vim", "nano", "tmux", "screen", "rsync", "openssh-client",
                        "ca-certificates", "gnupg", "lsb-release", "neofetch",
                        "bat", "ripgrep", "fd-find"],
                "pip": ["tldr", "speedtest-cli"],
                "npm": [],
            },
        },
    },
    "environments": {
        "label": "Development environment(s)",
        "options": {
            "1": {
                "label": "Python",
                "apt": ["python3", "python3-pip", "python3-venv", "python3-dev",
                        "python3-setuptools", "pipx"],
                "pip": ["virtualenv", "ipython", "pytest", "mypy", "pip-tools"],
                "npm": [],
            },
            "2": {
                "label": "Node.js / Web",
                "apt": [],
                "pip": [],
                "npm": ["typescript", "ts-node", "nodemon", "prettier",
                        "eslint", "serve", "http-server"],
                "needs_node": True,
            },
            "3": {
                "label": "Docker / DevOps",
                "apt": ["docker.io", "docker-compose", "ansible", "terraform",
                        "kubectl", "helm"],
                "pip": ["ansible", "docker", "boto3"],
                "npm": [],
            },
            "4": {
                "label": "Databases (PostgreSQL, SQLite)",
                "apt": ["postgresql", "postgresql-client", "sqlite3", "libsqlite3-dev",
                        "libpq-dev", "pgcli", "redis-tools"],
                "pip": ["psycopg2-binary", "sqlalchemy", "alembic", "aiosqlite"],
                "npm": [],
            },
        },
    },
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def print_header():
    print("\n" + "═" * 58)
    print("  Machine Setup Tool — Interactive Package Installer")
    print("  Ubuntu 24.04 LTS / Debian 12+")
    print("═" * 58 + "\n")


def print_section(title: str):
    print(f"\n{'─' * 58}")
    print(f"  {title}")
    print(f"{'─' * 58}")


def prompt_multiselect(label: str, options: dict) -> list[str]:
    """Display a numbered menu and return selected option keys."""
    print(f"\n{label}:")
    for key, opt in options.items():
        print(f"  [{key}] {opt['label']}")
    print(f"  [A] All of the above")
    print(f"  [0] Skip / None")
    print()

    while True:
        raw = input("  Enter numbers separated by commas (e.g. 1,3): ").strip().lower()
        if raw == "0":
            return []
        if raw == "a":
            return list(options.keys())
        keys = [k.strip() for k in raw.split(",")]
        valid = [k for k in keys if k in options]
        if not valid:
            print("  ✗ Invalid input. Try again.")
            continue
        invalid = [k for k in keys if k not in options]
        if invalid:
            print(f"  ✗ Unrecognized: {', '.join(invalid)}. Continuing with valid selections.")
        return valid


def merge_packages(selections: list[dict]) -> dict:
    """Merge all selected package lists, deduplicating across categories."""
    merged = {"apt": set(), "pip": set(), "npm": set()}
    for sel in selections:
        for manager in merged:
            merged[manager].update(sel.get(manager, []))
    return {k: sorted(v) for k, v in merged.items()}


NODE_LTS_MAJOR = 20  # bump this to update the NodeSource LTS target


def check_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def get_node_version() -> str | None:
    """Return installed node semver string or None."""
    if not check_command("node"):
        return None
    try:
        out = subprocess.check_output(["node", "--version"], text=True).strip()
        return out.lstrip("v")
    except Exception:
        return None


def get_npm_prefix() -> Path:
    """Return the configured npm global prefix directory."""
    try:
        out = subprocess.check_output(["npm", "config", "get", "prefix"], text=True).strip()
        return Path(out)
    except Exception:
        return Path.home() / ".npm-global"


def run(cmd: list[str], label: str) -> bool:
    print(f"\n  ▶ {label}")
    print(f"  $ {' '.join(cmd)}\n")
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n  ✗ Command failed (exit code {e.returncode})")
        return False
    except FileNotFoundError:
        print(f"\n  ✗ Command not found: {cmd[0]}")
        return False


def preview(packages: dict):
    print_section("Installation Preview")
    has_any = False
    for manager, pkgs in packages.items():
        if pkgs:
            has_any = True
            print(f"\n  [{manager.upper()}] — {len(pkgs)} package(s):")
            for p in pkgs:
                print(f"    • {p}")
    if not has_any:
        print("\n  Nothing to install.")
    print()


# ─── Pre-install Dependency Resolution ───────────────────────────────────────

def ensure_node(needs_node: bool) -> bool:
    """
    If npm packages are queued and node is missing (or outdated), install
    Node.js LTS via the official NodeSource setup script.
    Returns True if node is ready, False if install failed.
    """
    if not needs_node:
        return True

    current = get_node_version()
    if current:
        major = int(current.split(".")[0])
        if major >= NODE_LTS_MAJOR:
            print(f"\n  ✓ Node.js v{current} already installed — skipping Node install.")
            return True
        else:
            print(f"\n  ⚠  Node.js v{current} found but is below LTS v{NODE_LTS_MAJOR}.")
            upgrade = input(f"  Upgrade to Node.js LTS v{NODE_LTS_MAJOR}? [y/N]: ").strip().lower()
            if upgrade != "y":
                print("  Skipping Node.js upgrade — using existing version.")
                return True

    print_section(f"Installing Node.js LTS v{NODE_LTS_MAJOR} via NodeSource")

    if not check_command("curl"):
        print("  ✗ curl is required to download the NodeSource setup script.")
        print("  Run:  sudo apt-get install curl")
        return False

    setup_url = f"https://deb.nodesource.com/setup_{NODE_LTS_MAJOR}.x"
    ok = run(
        ["sudo", "bash", "-c", f"curl -fsSL {setup_url} | bash -"],
        "Fetching and running NodeSource setup script"
    )
    if not ok:
        return False

    return run(
        ["sudo", "apt-get", "install", "-y", "nodejs"],
        "Installing nodejs from NodeSource"
    )


def setup_npm_prefix() -> bool:
    """
    Configure a user-local npm global prefix (~/.npm-global) so that
    `npm install -g` never requires sudo. Adds the bin path to ~/.profile
    if not already present, and patches PATH for the current process.
    """
    npm_global = Path.home() / ".npm-global"
    npm_bin = npm_global / "bin"

    current_prefix = get_npm_prefix()
    if current_prefix == npm_global:
        print(f"\n  ✓ npm prefix already set to {npm_global} — no changes needed.")
    else:
        print(f"\n  ▶ Configuring npm global prefix → {npm_global}")
        npm_global.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["npm", "config", "set", "prefix", str(npm_global)],
                check=True
            )
            print(f"  ✓ npm prefix set to {npm_global}")
        except subprocess.CalledProcessError:
            print("  ✗ Failed to set npm prefix.")
            return False

    profile_path = Path.home() / ".profile"
    export_line = f'export PATH="{npm_bin}:$PATH"'

    try:
        existing = profile_path.read_text() if profile_path.exists() else ""
    except OSError:
        existing = ""

    if str(npm_bin) in existing:
        print(f"  ✓ {npm_bin} already present in ~/.profile")
    else:
        with open(profile_path, "a") as f:
            f.write(f"\n# npm global bin (added by setup_machine.py)\n{export_line}\n")
        print(f"  ✓ Added {npm_bin} to ~/.profile")
        print("  ℹ  Run `source ~/.profile` or open a new shell to activate PATH change.")

    os.environ["PATH"] = f"{npm_bin}:{os.environ.get('PATH', '')}"
    return True


def ensure_pip() -> str | None:
    """
    Detect and return the appropriate pip invocation. Handles PEP 668
    externally-managed environments by prompting for --break-system-packages
    or pipx fallback.
    Returns: 'pip3', 'pip', 'pipx', or None to skip.
    """
    pip_cmd = "pip3" if check_command("pip3") else ("pip" if check_command("pip") else None)

    if not pip_cmd:
        print("\n  ✗ pip not found.")
        if check_command("pipx"):
            print("  pipx is available as a fallback for CLI tools.")
            use_pipx = input("  Use pipx instead? [y/N]: ").strip().lower()
            return "pipx" if use_pipx == "y" else None
        print("  Tip: sudo apt-get install python3-pip")
        return None

    probe = subprocess.run(
        [pip_cmd, "install", "--dry-run", "pip"],
        capture_output=True, text=True
    )
    is_managed = "externally-managed-environment" in (probe.stderr or "")

    if is_managed:
        print("\n  ⚠  PEP 668 detected — this Python is managed by the OS (Ubuntu 24.04+).")
        print("  Options:")
        print("    [1] --break-system-packages  (install system-wide, use with caution)")
        print("    [2] pipx                     (isolated installs, safest for CLI tools)")
        print("    [3] Skip pip installs")
        choice = input("  Choose [1/2/3]: ").strip()
        if choice == "1":
            return pip_cmd
        elif choice == "2":
            if not check_command("pipx"):
                print("  Installing pipx via apt...")
                subprocess.run(["sudo", "apt-get", "install", "-y", "pipx"], check=False)
                subprocess.run(["pipx", "ensurepath"], check=False)
            return "pipx"
        else:
            return None

    return pip_cmd


# ─── Installation ─────────────────────────────────────────────────────────────

def install_apt(packages: list[str]) -> bool:
    if not packages:
        return True
    print_section("Installing system packages via apt")
    run(["sudo", "apt-get", "update", "-y"], "Updating package index")
    return run(
        ["sudo", "apt-get", "install", "-y"] + packages,
        f"Installing {len(packages)} apt package(s)"
    )


def install_pip(packages: list[str]) -> bool:
    if not packages:
        return True

    print_section("Installing Python packages")
    pip_cmd = ensure_pip()

    if pip_cmd is None:
        print("  Skipping pip installs.")
        return False

    if pip_cmd == "pipx":
        ok = True
        for pkg in packages:
            if not run(["pipx", "install", pkg], f"pipx install {pkg}"):
                ok = False
        return ok

    probe = subprocess.run(
        [pip_cmd, "install", "--dry-run", "pip"],
        capture_output=True, text=True
    )
    is_managed = "externally-managed-environment" in (probe.stderr or "")
    cmd = [pip_cmd, "install"]
    if is_managed:
        cmd.append("--break-system-packages")
    cmd += packages

    return run(cmd, f"Installing {len(packages)} pip package(s)")


def install_npm(packages: list[str], needs_node: bool) -> bool:
    if not packages:
        return True

    if not ensure_node(needs_node):
        print("  ✗ Node.js install failed. Skipping npm packages.")
        return False

    if not check_command("npm"):
        print("  ✗ npm not found even after Node.js install. Check your PATH.")
        return False

    print_section("Configuring npm global prefix (no-sudo installs)")
    if not setup_npm_prefix():
        print("  ⚠  npm prefix setup failed — falling back to sudo npm install -g")
        base_cmd = ["sudo", "npm", "install", "-g"]
    else:
        base_cmd = ["npm", "install", "-g"]

    print_section("Installing global Node packages via npm")
    return run(base_cmd + packages, f"Installing {len(packages)} npm package(s)")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print_header()

    all_selections: list[dict] = []
    needs_node = False

    for group_key, group in CATEGORIES.items():
        selected_keys = prompt_multiselect(group["label"], group["options"])
        for key in selected_keys:
            opt = group["options"][key]
            all_selections.append(opt)
            if opt.get("needs_node"):
                needs_node = True

    packages = merge_packages(all_selections)
    preview(packages)

    total = sum(len(v) for v in packages.values())
    if total == 0:
        print("  Nothing selected. Exiting.\n")
        sys.exit(0)

    confirm = input(f"  Install {total} package(s) now? [y/N]: ").strip().lower()
    if confirm != "y":
        print("\n  Aborted. No changes made.\n")
        sys.exit(0)

    results: dict[str, bool | None] = {}
    results["apt"] = install_apt(packages["apt"])
    results["pip"] = install_pip(packages["pip"])
    results["npm"] = install_npm(packages["npm"], needs_node)

    print_section("Summary")
    for manager, success in results.items():
        pkgs = packages[manager]
        if not pkgs:
            print(f"  {manager.upper():6s}  — skipped (nothing queued)")
            continue
        status = "✓ Done  " if success else "✗ Failed"
        print(f"  {manager.upper():6s}  {status}  ({len(pkgs)} package(s))")

    failed = [m for m, ok in results.items() if ok is False and packages[m]]
    if failed:
        print(f"\n  Some installs failed: {', '.join(failed)}")
        print("  Check output above for details.\n")
        sys.exit(1)
    else:
        print("\n  All done! You may need to run `source ~/.profile` or open a new shell.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
