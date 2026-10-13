# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-10-14

### Added
- **Cross-Platform Socket Scanner (`scanner.py`)**:
  - Pure-Python Linux `/proc/net/tcp` and `/proc/net/tcp6` parsing with socket inode-to-PID mapping without spawning subshells.
  - Native fallbacks to `ss -tulpn` and `lsof -iTCP -sTCP:LISTEN -P -n`.
  - macOS Darwin `lsof` scanner for listening IPv4/IPv6 TCP and UDP sockets.
  - Windows `netstat -ano -p tcp` / `-p udp` parsing supporting both IPv4 dotted-quad and IPv6 brackets.
- **Process Tree Resolver (`tree.py`)**:
  - Resolves process names, full command-line arguments, CWD, and owner users.
  - Identifies parent orchestrators (`npm`, `yarn`, `nodemon`, `pnpm`, `cargo`) to root trees at the true launcher.
  - Hierarchically attaches child worker processes recursively.
  - Pure-Python Git branch detector (`find_git_info`): traverses directory hierarchy, parses `.git/HEAD`, handles standard repos, detached commits (SHA-1/SHA-256), and Git worktrees/submodules (`gitdir:`).
- **Docker Container Unmasker (`docker.py`)**:
  - Maps opaque `docker-proxy` PIDs on host ports to actual container names, images, Docker Compose projects, and service labels.
  - Supports container port ranges (`8000-8005->8000-8005/tcp`).
  - Graceful fallback when Docker daemon or Podman runtime is offline.
- **Windows NAT / Hyper-V Port Exclusion Detector (`winnat.py`)**:
  - Detects kernel-level dynamic port exclusions via `netsh int ipv4/ipv6 show excludedportrange`.
  - Diagnoses silent `EADDRINUSE` / `WSAEACCES` socket collisions where no user-space PID exists in netstat.
  - Provides instant copy-paste remediation commands (`net stop winnat && net start winnat`, `netsh dynamicport`).
- **Graceful Tree Killer (`killer.py`)**:
  - `porttree free <PORT>` and `porttree kill <PORT>` commands.
  - Bottom-up termination sequence (child workers first, then parent) to eliminate orphaned zombie processes.
  - Graceful `SIGTERM` with configurable timeout (`-t 3.0`), followed by automatic escalation to `SIGKILL` (`taskkill /F /T` on Windows).
  - Safety `--dry-run` preview mode and interactive confirmation prompt (skippable via `-y`/`--yes`).
  - Automatic post-kill port verification re-scan.
- **Pre-Flight Stack Checker (`checker.py`)**:
  - `porttree check [FILES...]` command for stack configuration files.
  - Pure-Python parser for `docker-compose.yml` / `compose.yaml` (handles IP bindings, port mappings, and ranges without PyYAML).
  - Scans `package.json` scripts for `--port`, `-p`, and `PORT=` flags.
  - Scans `.env`, `.env.local`, and `.env.development` files for port definitions.
  - Cross-checks declared ports against currently active sockets and Windows kernel exclusions.
  - `--fail` flag for CI pipelines and pre-commit hooks.
- **Output Renderers & CLI (`formatter.py`, `cli.py`)**:
  - Rich ANSI tree view with Unicode branch glyphs (`├─`, `└─`, `│`).
  - `--ascii` flag for legacy terminal compatibility (`|--`, `\--`).
  - `--compact` tabular view for quick terminal inspection.
  - `--json` machine-readable output for programmatic pipelines.
  - Automatic `NO_COLOR` and non-TTY detection.
- **GitHub Action (`action.yml`, `action.py`)**:
  - Official GitHub composite action for pre-flight collision checking in CI.
  - Formatted Markdown summaries written straight to `$GITHUB_STEP_SUMMARY`.
  - Step outputs for `open-ports`, `conflict-count`, and `conflicts`.
