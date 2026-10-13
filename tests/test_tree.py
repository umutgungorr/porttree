"""Tests for process tree resolver and Git branch resolution."""

from unittest.mock import MagicMock, patch

from porttree.config import ProcessNode
from porttree.tree import ProcessResolver, find_git_info


def test_find_git_info_standard_repo(tmp_path):
    repo_dir = tmp_path / "my-awesome-app"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)

    head_file = git_dir / "HEAD"
    head_file.write_text("ref: refs/heads/feature/oauth\n", encoding="utf-8")

    branch, repo = find_git_info(str(repo_dir / "src" / "controllers"))
    assert branch == "feature/oauth"
    assert repo == "my-awesome-app"


def test_find_git_info_detached_head(tmp_path):
    repo_dir = tmp_path / "detached-repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)

    head_file = git_dir / "HEAD"
    head_file.write_text(
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n", encoding="utf-8"
    )

    branch, repo = find_git_info(str(repo_dir))
    assert branch == "detached:e3b0c44"
    assert repo == "detached-repo"


def test_find_git_info_submodule_or_worktree(tmp_path):
    main_git = tmp_path / "main-git" / "worktrees" / "wt1"
    main_git.mkdir(parents=True)
    (main_git / "HEAD").write_text("ref: refs/heads/release/1.0\n", encoding="utf-8")

    worktree_dir = tmp_path / "my-worktree"
    worktree_dir.mkdir()
    (worktree_dir / ".git").write_text(f"gitdir: {main_git}\n", encoding="utf-8")

    branch, repo = find_git_info(str(worktree_dir))
    assert branch == "release/1.0"
    assert repo == "my-worktree"


def test_find_git_info_non_repo(tmp_path):
    branch, repo = find_git_info(str(tmp_path))
    assert branch is None
    assert repo is None


def test_process_resolver_load_windows_csv():
    resolver = ProcessResolver(resolve_git=False)

    sample_csv = (
        '"ProcessId","ParentProcessId","Name","CommandLine","ExecutablePath"\r\n'
        '"1000","1","node.exe","node server.js","C:\\node\\node.exe"\r\n'
        '"1001","1000","node.exe","node worker.js","C:\\node\\node.exe"\r\n'
    )

    with patch("sys.platform", "win32"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_csv)
        resolver._load_windows_processes()

        assert 1000 in resolver._cache
        assert 1001 in resolver._cache

        p1 = resolver._cache[1000]
        assert p1.name == "node.exe"
        assert p1.cmdline == "node server.js"

        p2 = resolver._cache[1001]
        assert p2.ppid == 1000


def test_process_resolver_build_tree():
    resolver = ProcessResolver(resolve_git=False)
    # Pre-populate cache
    parent = ProcessNode(pid=500, ppid=1, name="npm", cmdline="npm run dev")
    server = ProcessNode(pid=600, ppid=500, name="node", cmdline="node index.js")
    worker1 = ProcessNode(pid=601, ppid=600, name="node", cmdline="node worker1.js")
    worker2 = ProcessNode(pid=602, ppid=600, name="node", cmdline="node worker2.js")

    resolver._cache = {
        500: parent,
        600: server,
        601: worker1,
        602: worker2,
    }
    resolver._all_processes_loaded = True

    # Build tree for listening server PID 600
    tree = resolver.build_full_tree(600, include_ancestors=True)
    assert tree is not None
    # Because parent (npm) is a dev runner, tree is rooted at npm
    assert tree.pid == 500
    assert len(tree.children) == 1
    server_node = tree.children[0]
    assert server_node.pid == 600
    assert len(server_node.children) == 2
    assert {c.pid for c in server_node.children} == {601, 602}


def test_process_resolver_load_macos_ps():
    resolver = ProcessResolver(resolve_git=False)
    sample_ps = """  PID  PPID USER     COMM             ARGS
    1     0 root     launchd          /sbin/launchd
  100     1 user     node             node /app/server.js
  101   100 user     node             node /app/worker.js
"""
    with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=sample_ps)
        resolver._load_macos_ps()

        assert 100 in resolver._cache
        assert 101 in resolver._cache
        assert resolver._cache[101].ppid == 100
        assert resolver._cache[100].cmdline == "node /app/server.js"


def test_find_git_info_tag_and_remote(tmp_path):
    repo_dir = tmp_path / "tagged-repo"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)

    head_file = git_dir / "HEAD"
    # Tag
    head_file.write_text("ref: refs/tags/v1.2.3\n", encoding="utf-8")
    branch, repo = find_git_info(str(repo_dir))
    assert branch == "tag:v1.2.3"
    assert repo == "tagged-repo"

    # Remote branch
    head_file.write_text("ref: refs/remotes/origin/main\n", encoding="utf-8")
    branch, repo = find_git_info(str(repo_dir))
    assert branch == "remote:origin/main"
    assert repo == "tagged-repo"


def test_process_resolver_resolve_git_from_cmdline(tmp_path):
    repo_dir = tmp_path / "my-web-service"
    git_dir = repo_dir / ".git"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/feature/login\n", encoding="utf-8")

    server_script = repo_dir / "src" / "server.py"
    server_script.parent.mkdir(parents=True)
    server_script.write_text("# server code", encoding="utf-8")

    resolver = ProcessResolver(resolve_git=True)
    # Process without cwd (e.g. system cwd), but with full script path in cmdline
    node = ProcessNode(
        pid=999,
        name="python",
        cmdline=f"python {server_script}",
        args=["python", str(server_script)],
        cwd="/usr/bin",
    )
    resolver._cache[999] = node
    resolver._all_processes_loaded = True

    resolved_node = resolver.get_process_node(999)
    assert resolved_node is not None
    assert resolved_node.git_branch == "feature/login"
    assert resolved_node.git_repo == "my-web-service"
