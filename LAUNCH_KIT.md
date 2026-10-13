# 🚀 PortTree Launch & Distribution Kit

> **Goal**: Position **PortTree** as the definitive modern replacement for `lsof -i` and `netstat -ano`, driving 1,000+ GitHub stars across developer communities.
>
> Live Repository: [https://github.com/umutgungorr/porttree](https://github.com/umutgungorr/porttree)  
> GitHub Marketplace Action: `uses: umutgungorr/porttree@v1`

---

## 📅 High-Impact Launch Schedule (Timing Blueprint)

To capture maximum algorithm velocity across international tech hubs:

| Platform | Recommended Day & Time (EST) | Turkey Time (TRT / UTC+3) | Target Community & Tone |
|---|---|---|---|
| **Hacker News (Show HN)** | Tuesday or Wednesday, 08:30–09:00 AM EST | 15:30–16:00 | Engineering purists, zero-dependency enthusiasts, CLI architects |
| **Reddit (`r/Python`, `r/commandline`)** | Tuesday or Wednesday, 10:30 AM EST | 17:30 | Terminal junkies, Python builders, CLI developers |
| **Reddit (`r/devops`, `r/webdev`)** | Wednesday or Thursday, 09:30 AM EST | 16:30 | Fullstack engineers, DevOps SREs, Docker operators |
| **X / Twitter (Global)** | Simultaneous with HN (Tue 09:00 AM EST) | 16:00 | High-contrast visual terminal screenshots and code thread |
| **LinkedIn (Global & TR)** | Wednesday, 11:00 AM EST | 18:00 | Engineering leads, DevOps professionals, open-source supporters |
| **Product Hunt** | Tuesday or Thursday 00:01 AM PST | 10:01 TRT | Productivity tool hunters, indie hackers |

---

## 1. 🟠 Hacker News (Show HN)

### Title Options (Pick One)
1. **Recommended**: `Show HN: PortTree – Zero-dependency CLI to see through ports, Git branches, and Docker proxies`
2. **Alternative A**: `Show HN: PortTree – An ANSI process tree resolver for mysterious EADDRINUSE collisions`
3. **Alternative B**: `Show HN: PortTree – Unmask docker-proxy, map Git repos to ports, and tree-kill zombie workers`

---

### First Comment (OP Introduction — Post Immediately After Submitting)

```markdown
Hey HN! I built PortTree because I was tired of wrestling with `Error: listen EADDRINUSE: address already in use :::3000` and getting virtually useless answers from standard OS tools.

Whenever a port collision occurs during local development:
1. `lsof -i :3000` just says `node 48291`. It doesn't tell you which project it belongs to, what Git branch you were working on, whether it's Next.js or nodemon, or what child worker processes it spawned.
2. If Docker or Podman is running, `lsof` and `netstat` only reveal `docker-proxy 19284`. Zero clue which container, Compose project, or service is holding port 5432 or 80.
3. On Windows, developers run `netstat -ano | findstr :50025` and find NOTHING. Yet socket binds throw EADDRINUSE because Hyper-V / WinNAT dynamic kernel exclusions silently locked the range.
4. When you finally run `kill -9 48291`, the parent terminates but leaves orphaned child worker processes hanging onto the socket as zombies.

PortTree (`porttree`) is a zero-dependency CLI written entirely in Python standard library to solve this:

- 🌲 **Hierarchical Process Trees**: Displays listening sockets mapped to their parent orchestrator (npm, nodemon, cargo), active child worker processes, and full command arguments.
- 🌿 **Git Context Linking**: Detects process CWD and parses `.git/HEAD` in pure Python, showing active branch and repository name right next to the port.
- 🐳 **Docker Unmasker**: Unmasks opaque `docker-proxy` PIDs into real container names, Compose projects, services, and container images.
- 🪟 **Windows NAT / Hyper-V Exclusion Diagnoser**: Scans kernel port exclusions and prints instant remediation commands (`net stop winnat`).
- ⚡ **Graceful Tree Killer (`porttree free <PORT>`)**: Terminates parent and all child workers (SIGTERM with timeout, then SIGKILL escalation), confirming the port is 100% free.
- 🔍 **Pre-Flight Stack Checker (`porttree check`)**: Scans `docker-compose.yml`, `package.json`, and `.env` before server startup to flag collisions before your build breaks.
- 🤖 **GitHub Action (`uses: umutgungorr/porttree@v1`)**: Drops into CI pipelines to pre-check runner ports and publish a rich Markdown report to `$GITHUB_STEP_SUMMARY`.

Cold startup is sub-15ms, and it works natively across Linux (procfs/ss/lsof), macOS (lsof), and Windows (netstat/PowerShell).

You can run it instantly without installing:
`uvx porttree`
`uvx porttree 3000`
`uvx porttree free 3000 -y`

Code & GitHub Action: https://github.com/umutgungorr/porttree

I'd love feedback on port collision edge cases you run into in your workflows!
```

---

### Anticipated HN Skepticism & Answers Cheatsheet

- **"Why not just use `lsof -i :PORT` or `fuser -k PORT/tcp`?"**  
  *Answer*: `lsof` gives a flat process list without hierarchy. It doesn't tell you what Git repo or branch the process came from, doesn't unmask Docker containers from `docker-proxy`, and doesn't know about Windows Hyper-V dynamic port exclusions. `fuser -k` simply sends a signal to the listening PID without walking the worker tree or waiting for graceful exit.
- **"Why pure Python stdlib instead of `psutil`?"**  
  *Answer*: `psutil` requires compiling C extensions or downloading platform wheels. By using pure standard library (`/proc/net/tcp` procfs parsing on Linux, `lsof` on macOS, and structured `netstat`/WMI on Windows), PortTree starts in <15ms, has zero supply-chain baggage, and runs anywhere Python 3.9+ exists with `uvx porttree`.
- **"How does the pure-Python procfs scanner work?"**  
  *Answer*: On Linux, PortTree parses `/proc/net/tcp` and `/proc/net/tcp6` directly. It converts hex IP/ports into human-readable strings, matches state `0A` (`TCP_LISTEN`), and maps socket inodes to owning PIDs by reading `/proc/[pid]/fd/*` symlinks without spawning a single subshell.

---

## 2. 🔴 Reddit Launch Posts

### A. Subreddit: `r/Python`
**Title**: `I built PortTree: A zero-dependency CLI that maps open ports to process trees, Git branches, and Docker containers`  
**Flair**: `Project` / `Showcase`

**Body**:
```markdown
Hi r/Python!

Every developer has run into `Error: listen EADDRINUSE: address already in use :::3000`.

The standard solutions (`lsof -i :3000` or `netstat -ano`) are frustratingly opaque:
- They say `node (PID 48291)` without telling you which project, repo, or branch it belongs to.
- For Docker, they only say `docker-proxy (PID 19284)` with zero clue which container is mapped to it.
- On Windows, Hyper-V dynamic port exclusions can reserve ports without any visible PID in netstat.
- `kill -9` leaves orphaned worker processes listening on the port.

I built **PortTree** (https://github.com/umutgungorr/porttree) as an open-source, zero-dependency CLI to fix this permanently.

### Key Highlights:
- **Zero Dependencies**: Pure Python 3.9+ stdlib. No psutil, no click, instant sub-15ms cold start.
- **Hierarchical Process Trees**: Displays `npm run dev └─ nodemon └─ node server ├─ worker 1 └─ worker 2`.
- **Git Branch Detection**: Walks up the CWD to `.git/HEAD` and badges the active branch (`git: feat/auth (frontend)`).
- **Docker Unmasker**: Maps `docker-proxy` to container names, images, and Compose project/service labels.
- **Windows NAT Detector**: Diagnoses invisible Hyper-V/WinNAT port exclusions with 1-click fix commands.
- **Tree Killer**: `porttree free 3000` terminates the parent and all child workers cleanly.
- **Pre-Flight Checker**: `porttree check` scans `docker-compose.yml`, `package.json`, and `.env` before server startup to prevent port conflicts in CI.

Try it without installing:
```bash
uvx porttree
uvx porttree 3000
uvx porttree free 3000 -y
```

GitHub: https://github.com/umutgungorr/porttree

Feedback and feature ideas are warmly welcomed!
```

---

### B. Subreddit: `r/devops`
**Title**: `PortTree: Stop debugging mysterious EADDRINUSE in CI and local Docker stacks`  
**Flair**: `Tool` / `Open Source`

**Body**:
```markdown
Hey everyone,

Port conflicts during local multi-service development and CI test runners are a constant headache:
- Opaque `docker-proxy` PIDs holding ports without identifying the service.
- Orphaned worker processes surviving test runner crashes.
- Windows CI runners failing socket binds due to dynamic NAT port exclusions.

We built **PortTree** (https://github.com/umutgungorr/porttree) to automate port diagnostics:

1. **Pre-Flight Stack Check**: `porttree check docker-compose.yml package.json --fail` scans declared ports and exits with code 1 if a collision exists before boot.
2. **GitHub Action (`uses: umutgungorr/porttree@v1`)**: Automatically checks open ports on your CI runner and posts an inspection table straight to `$GITHUB_STEP_SUMMARY`.
3. **Docker Container Unmasking**: Transparently maps host ports to container names, Compose projects, and images.
4. **Clean Tree Termination**: `porttree free <PORT> -y` kills parent and all child workers with graceful timeout and force escalation.
5. **Zero Dependencies**: Pure Python stdlib, instant execution, cross-platform (Linux, macOS, Windows).

Available now on GitHub and PyPI:
https://github.com/umutgungorr/porttree
```

---

## 3. 🐦 X / Twitter Thread

**Tweet 1 (Hook + Visual)**:
```text
Tired of "Error: listen EADDRINUSE: address already in use :::3000"?

lsof says: "node 48291" (which repo? which branch?)
netstat on docker says: "docker-proxy 19284" (which container?)

I built PortTree: A zero-dependency CLI that sees through every port in a single ANSI tree 🌲👇
```

**Tweet 2 (Before & After)**:
```text
Traditional lsof gives you flat, opaque PIDs.

PortTree shows the entire hierarchy:
PORT 3000 (TCP) [LISTEN]
 └─ npm run dev (PID 48280) [git: feat/auth (frontend)]
    └─ nodemon (PID 48285)
       └─ node server.js (PID 48291)
          ├─ node worker.js (PID 48295)
          └─ node worker.js (PID 48296)
```

**Tweet 3 (Docker Unmasking)**:
```text
Port 5432 or 8080 held by Docker?

Standard tools just say `docker-proxy`.

PortTree inspects container runtimes and unmasks the real container name, compose project, and service:
PORT 5432 (TCP) [LISTEN]
 ├─ 🐳 Docker: postgres-db-1 (postgres:16-alpine) [db @ ecommerce-app]
 └─ docker-proxy (PID 19284)
```

**Tweet 4 (The Windows NAT Mystery)**:
```text
On Windows, ever had a port fail with EADDRINUSE but netstat shows NOTHING?

Hyper-V / WSL2 dynamic port exclusions silently reserve kernel port ranges.

PortTree diagnoses the range and prints copy-paste remediation commands (`net stop winnat`) 🪄
```

**Tweet 5 (One-Command Tree Kill & CI)**:
```text
Need to free the port?
`porttree free 3000 -y` kills the parent AND all child workers so you never leave zombie processes.

And in CI:
`porttree check --fail` stops collisions before your test suite runs.
GitHub Action: `uses: umutgungorr/porttree@v1`
```

**Tweet 6 (Call to Action)**:
```text
Zero external dependencies. Sub-15ms startup. Pure Python 3.9+ stdlib.

Run it right now without installing:
`uvx porttree`

⭐ Star on GitHub: https://github.com/umutgungorr/porttree
RTs appreciated! 🔁
```

---

## 4. 💼 LinkedIn Post

```markdown
Every developer has lost time to this error:
"Error: listen EADDRINUSE: address already in use :::3000"

You run `lsof -i :3000` or `netstat -ano`. What do you get?
- An opaque PID like `node 48291` — no clue which repository, branch, or project it came from.
- Or `docker-proxy 19284` — zero indication of which container or compose service is holding it.
- Or on Windows, `netstat` returns empty because Hyper-V dynamic kernel exclusions silently reserved the port.

To solve this once and for all, I created **PortTree** — an open-source, zero-dependency developer tool.

🌲 What PortTree delivers:
1. **Full Process Hierarchy**: Connects listening sockets to parent orchestrators (npm, nodemon, cargo) and child worker pools.
2. **Git Context**: Automatically links the active Git branch and repository name to the listening process.
3. **Docker Container Unmasking**: Resolves opaque docker-proxy PIDs into real container names, images, and compose services.
4. **Windows NAT Diagnoser**: Detects kernel-level dynamic port exclusions and provides instant fix commands.
5. **1-Command Tree Killer**: Gracefully terminates parent and all child workers, eliminating zombie processes.
6. **Pre-Flight CI Checker**: Prevents CI test runner port collisions before server boot.

It is 100% pure Python standard library with zero external dependencies and a sub-15ms startup time.

Run it instantly with uvx:
`uvx porttree`

Explore the repository and GitHub Action here:
https://github.com/umutgungorr/porttree

#OpenSource #DevOps #Python #DeveloperTools #SoftwareEngineering #Docker #Terminal #CLI
```
