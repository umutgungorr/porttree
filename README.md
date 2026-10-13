<div align="center">

```text
  ██████╗  ██████╗ ██████╗ ████████╗████████╗██████╗ ███████╗███████╗
  ██╔══██╗██╔═══██╗██╔══██╗╚══██╔══╝╚══██╔══╝██╔══██╗██╔════╝██╔════╝
  ██████╔╝██║   ██║██████╔╝   ██║      ██║   ██████╔╝█████╗  █████╗  
  ██╔═══╝ ██║   ██║██╔══██╗   ██║      ██║   ██╔══██╗██╔══╝  ██╔══╝  
  ██║     ╚██████╔╝██║  ██║   ██║      ██║   ██║  ██║███████╗███████╗
  ╚═╝      ╚═════╝ ╚═╝  ╚═╝   ╚═╝      ╚═╝   ╚═╝  ╚═╝╚══════╝╚══════╝
```

### See Through Every Open Port. Instantly.

**A zero-dependency CLI socket scanner and process tree resolver that unmasks Docker containers, links active Git branches, diagnoses Windows NAT exclusions, and kills zombie worker trees in one command.**

[![CI](https://github.com/umutgungorr/porttree/actions/workflows/ci.yml/badge.svg)](https://github.com/umutgungorr/porttree/actions)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-PortTree%20Action-green?logo=githubactions&logoColor=white)](https://github.com/marketplace/actions/porttree-port-collision-socket-inspector)
[![Version](https://img.shields.io/badge/version-v0.1.0-green.svg?logo=git&logoColor=white)](https://github.com/umutgungorr/porttree/releases)
[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB.svg?logo=python&logoColor=white)](https://github.com/umutgungorr/porttree)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-0%20external-success.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-100%25%20passing-brightgreen.svg)](#test-suite)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

[⚡ Quickstart](#quickstart) •
[💥 Problem vs. Solution](#problem-solution) •
[📊 Feature Comparison](#feature-comparison) •
[🤖 GitHub Actions CI](#github-actions-ci) •
[📦 Installation](#installation) •
[⚙️ CLI Reference](#cli-reference) •
[🐳 Docker Unmasker](#docker-unmasker) •
[🪟 Windows NAT Diagnoser](#windows-nat-diagnoser) •
[🌲 Graceful Tree Killer](#graceful-tree-killer) •
[🔬 Architecture](#architecture) •
[🤝 Contributing](#contributing)

</div>

---

<a id="problem-solution"></a>
## 💥 The Problem vs. Solution

Every developer has stared at:
```text
Error: listen EADDRINUSE: address already in use :::3000
```
Or attempted to spin up Postgres, Vite, Next.js, Redis, or Docker Compose only to have the port rejected.

### The Pain with Traditional Tools:
1. **Opaque Process Names**: `lsof -i :3000` says `node 48291`. Which project? Which repo? Which branch? Is it Next.js, nodemon, or Vitest?
2. **The Docker Proxy Blind Spot**: `docker-proxy 19284` reveals zero information about which container, Docker Compose project, or service is occupying port `5432` or `80`.
3. **The Ghost Windows Bug**: On Windows, `netstat -ano | findstr :50025` returns **empty**, yet socket binds throw `WSAEACCES / EADDRINUSE` because Hyper-V / WinNAT kernel port exclusions silently locked the range.
4. **Zombie Worker Leaks**: Running `kill -9 <PID>` terminates the master orchestrator, leaving 4 child worker processes orphaned and holding the port forever.

### Side-by-Side Terminal Comparison

```text
┌────────────────────────────────────────────────────────┐   ┌────────────────────────────────────────────────────────┐
│           BEFORE: Traditional lsof / netstat           │   │                  AFTER: With PortTree                  │
├────────────────────────────────────────────────────────┤   ├────────────────────────────────────────────────────────┤
│ $ lsof -i :3000                                        │   │ $ porttree 3000                                        │
│ COMMAND   PID USER   FD   TYPE DEVICE SIZE NODE NAME   │   │                                                        │
│ node    48291 user   23u  IPv6 0x...   0t0  TCP *:3000 │   │ PORT 3000 (TCP) [LISTEN] • 0.0.0.0:3000                │
│                                                        │   │  └─ npm run dev (PID 48280) [git: feat/auth (frontend)]│
│ (Which node? What repo? What branch? What workers?)    │   │     └─ nodemon (PID 48285)                             │
│                                                        │   │        └─ node server.js (PID 48291)                   │
│ $ lsof -i :5432                                        │   │           ├─ node worker.js (PID 48295)                │
│ docker-pr 19284 root 4u IPv4 0x... 0t0 TCP *:5432      │   │           └─ node worker.js (PID 48296)                │
│ (Which container? What service? Which compose file?)   │   │                                                        │
│                                                        │   │ $ porttree 5432                                        │
│ $ netstat -ano | findstr :50025                        │   │ PORT 5432 (TCP) [LISTEN] • 0.0.0.0:5432                │
│ (Returns nothing! Port still throws EADDRINUSE!)       │   │  ├─ 🐳 Docker: postgres-db [db @ my-saas-app] (pg:16)  │
│                                                        │   │  └─ docker-proxy (PID 19284)                           │
│ $ kill -9 48291                                        │   │                                                        │
│ (Worker 48295 is now orphaned and still locks port!)   │   │ $ porttree free 3000 -y                                │
│                                                        │   │ ✅ Successfully freed port 3000. Terminated 5 processes.│
└────────────────────────────────────────────────────────┘   └────────────────────────────────────────────────────────┘
```

---

<a id="feature-comparison"></a>
## 📊 Feature Comparison

| Capability | PortTree | `lsof` | `netstat` | `ss` | `fuser` | `psutil` CLI |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Zero Dependencies (<15ms Cold Start)** | ✅ **Yes** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes | ❌ Requires C wheels |
| **Hierarchical Process Tree (Parent + Children)** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ❌ No | ⚠️ Flat list |
| **Active Git Branch & Repo Linking** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Docker Container & Compose Unmasking** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Windows Hyper-V / WinNAT Exclusion Detector**| ✅ **Yes** | ❌ N/A | ❌ No | ❌ N/A | ❌ N/A | ❌ No |
| **1-Command Tree Killer (`porttree free`)** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ⚠️ `-k` (no tree) | ❌ Manual script |
| **Pre-Flight Stack Collision Checker** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |
| **Native Cross-Platform (Linux, macOS, Win)** | ✅ **Yes** | ❌ macOS/Linux | ⚠️ Windows format | ❌ Linux only | ❌ Linux only | ✅ Yes |
| **Rich ANSI & Machine-Readable JSON** | ✅ **Both** | ❌ Plaintext | ❌ Plaintext | ❌ Plaintext | ❌ Plaintext | ⚠️ Custom code |
| **Official GitHub Action for CI** | ✅ **Yes** | ❌ No | ❌ No | ❌ No | ❌ No | ❌ No |

---

<a id="quickstart"></a>
## ⚡ Quickstart

Run PortTree instantly without installing using `uvx`:

```bash
# Scan all open listening ports and view process trees
uvx porttree

# Inspect specific port 3000
uvx porttree 3000

# Free port 3000 and all spawned child workers
uvx porttree free 3000 -y

# Pre-flight check docker-compose.yml and package.json before dev boot
uvx porttree check --fail
```

Or install globally via `pip` or `pipx`:

```bash
pip install porttree
# or
pipx install porttree
```

---

<a id="docker-unmasker"></a>
## 🐳 Docker Container Unmasking

When running Docker Desktop or Podman, binding ports like `8080:80` or `5432:5432` causes `docker-proxy` to listen on the host. Standard system tools only report `docker-proxy (PID 19284)`.

**PortTree unmasks the underlying container metadata:**
- Container Name (`web-api-1`)
- Docker Image (`postgres:16-alpine`)
- Docker Compose Project (`ecommerce-backend`)
- Docker Compose Service (`postgres`)
- Compose Working Directory (`/home/user/apps/ecommerce`)

```bash
$ porttree 5432

PORT 5432 (TCP) [LISTEN] • 0.0.0.0:5432
 ├─ 🐳 Docker: postgres-db-1 (postgres:16-alpine) [db @ ecommerce-backend]
 └─ docker-proxy (PID 19284)
      $ /usr/bin/docker-proxy -proto tcp -host-ip 0.0.0.0 -host-port 5432 -container-ip 172.18.0.2 -container-port 5432
```

---

<a id="windows-nat-diagnoser"></a>
## 🪟 Windows Hyper-V / WSL2 Dynamic Port Exclusion Diagnoser

On Windows 10/11 and Windows Server, Hyper-V and WSL2 frequently reserve large dynamic port ranges for container networking. When a developer service tries to bind to a port within these ranges, the OS returns `WSAEACCES / EADDRINUSE` even though **no process is visible in netstat or Task Manager**.

PortTree detects these kernel-level exclusions and prints copy-paste remediation commands:

```bash
$ porttree winnat 50025

⚠️  Port 50025 is reserved by Windows Kernel (Hyper-V / WinNAT / WSL2)
   Range: 50000 – 50059 (TCP) [Administered]

   Root Cause:
   Windows NAT (WinNAT) or Hyper-V reserved this port range for internal container/WSL2 routing.
   No user-space PID exists in netstat or Task Manager, yet socket binds fail with EADDRINUSE (WinError 10013).

   Recommended Solutions:
   1. Restart WinNAT (instant fix, frees reserved pool):
      powershell -Command "net stop winnat; net start winnat"

   2. Reconfigure dynamic port pool (prevents future collision with dev ports):
      netsh int ipv4 set dynamicport tcp start=49152 num=16384

   3. Restart Host Network Service (if running Docker/WSL2):
      net stop hns && net start hns
```

---

<a id="graceful-tree-killer"></a>
## 🌲 Graceful Process Tree Killer (`porttree free`)

Modern developer stacks spawn trees of processes:
`npm run dev` ➔ `nodemon` ➔ `node cluster master` ➔ `node worker 1..4`.

Killing just the PID returned by `lsof` frequently leaves orphaned workers still listening on the socket, or causes `nodemon` to respawn them immediately.

`porttree free <PORT>`:
1. Discovers the socket owner and all descendant worker processes recursively.
2. Displays the full process tree and prompts for confirmation (or use `-y` / `--yes`).
3. Sends `SIGTERM` to the entire tree (children first, then parent).
4. Monitors graceful shutdown for up to 3.0 seconds (`-t 3.0`).
5. Automatically escalates to `SIGKILL` (or `taskkill /F /T` on Windows) if processes refuse to terminate.
6. Re-scans the port to verify that the socket is 100% free.

```bash
# Preview what would be terminated without killing anything
porttree free 3000 --dry-run

# Gracefully terminate parent and workers
porttree free 3000

# Immediate force kill for unresponsive servers
porttree kill 8080 -f -y
```

---

<a id="github-actions-ci"></a>
## 🤖 GitHub Actions CI Integration

Stop mysterious `port already allocated` or `EADDRINUSE` failures in CI pipelines before running integration tests or starting test containers:

```yaml
- name: Pre-Flight Port Collision Check
  uses: umutgungorr/porttree@v1
  with:
    check-file: 'docker-compose.yml, package.json'
    fail-on-conflict: 'true'
    summary: 'true'
```

### Action Outputs & Features:
- Populates `$GITHUB_STEP_SUMMARY` with a formatted Markdown report.
- Provides step outputs: `steps.porttree.outputs.open-ports`, `steps.porttree.outputs.conflict-count`.
- Fails with exit code 1 if any declared port is already occupied.

---

<a id="cli-reference"></a>
## ⚙️ CLI Reference

### 1. Port Inspection & Scanning
```bash
porttree                    # Scan all listening sockets
porttree 3000               # Inspect port 3000
porttree 3000,8080,5432     # Inspect specific comma-separated ports
porttree 8000-8010          # Inspect port range
porttree --tcp              # Filter for TCP only
porttree --udp              # Filter for UDP only
porttree --compact          # Tabular 1-line per port summary
porttree --json             # Raw machine-readable JSON
porttree --no-color         # Plaintext output (also honors NO_COLOR=1)
porttree --ascii            # Use ASCII tree branches (|--, \--)
```

### 2. Freeing & Killing Ports
```bash
porttree free 3000          # Graceful kill with confirmation prompt
porttree free 3000 -y       # Skip confirmation (non-interactive)
porttree kill 3000 -f -y    # Force kill immediately with SIGKILL
porttree free 3000 -t 5.0   # Graceful wait timeout of 5 seconds
porttree free 3000 --dry-run# Preview processes without terminating
```

### 3. Pre-Flight Stack Check
```bash
porttree check              # Auto-scans docker-compose.yml, package.json, and .env
porttree check --fail       # Exit code 1 if conflicts found (ideal for CI/git hooks)
porttree check compose.yml  # Scan explicit compose file
porttree check -p 3000,8080 # Add explicit port checks
```

### 4. Windows NAT Diagnostics
```bash
porttree winnat             # List all Windows Dynamic Port Exclusion ranges
porttree winnat 50025       # Diagnose specific port collision
```

---

<a id="architecture"></a>
## 🔬 Pipeline Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          PORTTREE ARCHITECTURE                         │
└────────────────────────────────────────────────────────────────────────┘

  [ Operating System Layer ]
  ┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
  │         Linux         │  │         macOS         │  │        Windows        │
  │ /proc/net/tcp, ss,    │  │  lsof -iTCP -sTCP:    │  │ netstat -ano,         │
  │ /proc/[pid]/fd socket │  │  LISTEN, lsof -p cwd  │  │ Win32_Process, netsh  │
  └───────────┬───────────┘  └───────────┬───────────┘  └───────────┬───────────┘
              │                          │                          │
              └──────────────────┬───────┴──────────────────────────┘
                                 ▼
                     [ Cross-Platform Scanner ]
                     Extracts: Protocol, IP, Port, PID
                                 │
                                 ▼
                     [ Process Tree Resolver ]
                     • Resolves parent orchestrator (npm, nodemon, cargo)
                     • Traverses child worker hierarchies
                     • Resolves CWD & inspects .git/HEAD for branch name
                                 │
                                 ▼
                     [ Docker / Runtime Unmasker ]
                     • Queries docker/podman daemon for exposed port mappings
                     • Resolves container names, images, Compose project & service
                                 │
                                 ▼
                     [ Windows NAT Exclusion Detector ]
                     • Parses dynamic port ranges from netsh
                     • Diagnoses WinNAT / Hyper-V kernel reservations
                                 │
                                 ▼
                     [ ANSI Tree / JSON Formatter ]
                     • Rich UTF-8 ANSI tree renderer with badges
                     • Compact table & JSON output modes
```

---

<a id="contributing"></a>
## 🤝 Contributing

Contributions are warmly welcomed! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for local development setup, test execution guidelines, and code standards.

```bash
# Clone the repository
git clone https://github.com/umutgungorr/porttree.git
cd porttree

# Run tests
uv run --with pytest --with pytest-cov pytest

# Lint and format
uv run --with ruff ruff check .
uv run --with ruff ruff format .
```

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).  
Copyright (c) 2026 **Umut Güngör**.
