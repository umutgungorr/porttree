# Contributing to PortTree

Thank you for your interest in contributing to **PortTree**! We welcome bug reports, feature proposals, documentation improvements, and pull requests.

---

## 🧭 Core Principles

1. **Zero External Dependencies**: Runtime code (`src/porttree/`) MUST rely strictly on Python 3.9+ standard library modules (`sys`, `os`, `re`, `subprocess`, `socket`, `dataclasses`, `pathlib`, `json`, `argparse`). No third-party runtime dependencies are permitted.
2. **Sub-15ms Startup**: CLI startup time is paramount. Avoid heavy module imports at top level if only needed conditionally.
3. **Cross-Platform Parity**: Features should work seamlessly across Linux, macOS, and Windows. When an OS-specific nuance exists (e.g. Windows Hyper-V dynamic port exclusions), handle it gracefully with dedicated diagnostic reporting.
4. **Resilience Over Crashes**: Never crash on unexpected system outputs or permission denied errors. Fall back gracefully to alternative scan methods.

---

## 🛠️ Local Development Setup

We recommend using [`uv`](https://github.com/astral-sh/uv) or standard Python `venv`:

```bash
# Clone the repository
git clone https://github.com/umutgungorr/porttree.git
cd porttree

# Install in editable mode with development dependencies
uv pip install -e ".[dev]"
# Or with standard pip:
pip install -e ".[dev]"
```

---

## 🧪 Running the Test Suite

Our test suite uses `pytest`:

```bash
# Run tests with uv
uv run --with pytest --with pytest-cov pytest

# Or with activated virtual environment
pytest --cov=src/porttree --cov-report=term-missing
```

Ensure all tests pass and coverage remains above 90% before submitting a PR.

---

## 🎨 Code Style and Linting

We enforce formatting and linting rules using [`ruff`](https://github.com/astral-sh/ruff):

```bash
# Check code for lint errors
uv run --with ruff ruff check .

# Format code
uv run --with ruff ruff format .
```

---

## 📦 Pull Request Process

1. Fork the repo and create a new feature branch (`git checkout -b feat/my-new-feature`).
2. Add comprehensive unit tests in `tests/` covering both happy paths and edge cases (boundary values, malformed inputs, permission errors).
3. Ensure `ruff check .` and `pytest` both pass cleanly.
4. Commit your changes with clear semantic messages (`feat: ...`, `fix: ...`, `docs: ...`).
5. Open a Pull Request on GitHub and provide a concise summary of the changes and motivation.
