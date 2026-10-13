"""Docker container unmasker for PortTree.

Resolves opaque docker-proxy and container runtime PIDs to real container names,
Docker Compose project names, service names, and container images.
"""

from __future__ import annotations

import re
import subprocess

from porttree.config import DockerContainerInfo


class DockerUnmasker:
    """Discovers and maps exposed host ports to running Docker and Podman containers."""

    def __init__(self, timeout_sec: float = 2.0):
        self.timeout_sec = timeout_sec
        self._port_to_container: dict[int, DockerContainerInfo] = {}
        self._inspected = False

    def is_docker_process(self, process_name: str) -> bool:
        """Check if a process name indicates a container runtime proxy or daemon."""
        if not process_name:
            return False
        p = process_name.lower()
        return any(
            token in p
            for token in (
                "docker-proxy",
                "com.docker.backend",
                "dockerd",
                "podman",
                "conmon",
                "containerd",
            )
        )

    def get_container_for_port(
        self, port: int, protocol: str = "tcp"
    ) -> DockerContainerInfo | None:
        """Look up container information mapped to a host port."""
        if not self._inspected:
            self._inspect_containers()

        return self._port_to_container.get(port)

    def _inspect_containers(self) -> None:
        """Query Docker or Podman CLI for running container port mappings."""
        self._inspected = True

        # Try docker first, then podman
        for cli in ("docker", "podman"):
            if self._query_cli(cli):
                return

    def _query_cli(self, cli_bin: str) -> bool:
        """Run docker/podman ps with structured tab-separated format."""
        cmd = [
            cli_bin,
            "ps",
            "--format",
            "{{.ID}}\t{{.Names}}\t{{.Ports}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}",
            "--no-trunc",
        ]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=self.timeout_sec,
            )
            if proc.returncode != 0 or not proc.stdout:
                return False
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return False

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) < 4:
                continue

            cid = parts[0][:12]
            name = parts[1]
            ports_raw = parts[2]
            image = parts[3]
            status = parts[4] if len(parts) > 4 else ""
            labels_raw = parts[5] if len(parts) > 5 else ""

            # Parse compose labels
            labels = self._parse_labels(labels_raw)
            compose_project = labels.get("com.docker.compose.project")
            compose_service = labels.get("com.docker.compose.service")
            compose_workdir = labels.get("com.docker.compose.project.working_dir")

            # Parse port mappings
            # Example: 0.0.0.0:5432->5432/tcp, :::5432->5432/tcp, 0.0.0.0:8080-8082->80-82/tcp
            host_ports = self._parse_ports(ports_raw)

            container_info = DockerContainerInfo(
                container_id=cid,
                name=name,
                image=image,
                compose_project=compose_project,
                compose_service=compose_service,
                compose_workdir=compose_workdir,
                ports=[ports_raw] if ports_raw else [],
                status=status,
            )

            for port in host_ports:
                self._port_to_container[port] = container_info

        return True

    @staticmethod
    def _parse_labels(labels_str: str) -> dict[str, str]:
        """Parse comma-separated KEY=VALUE labels string."""
        labels: dict[str, str] = {}
        if not labels_str:
            return labels

        # Match comma separated key=val, guarding escaped characters
        for item in labels_str.split(","):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                labels[k.strip()] = v.strip()
        return labels

    @staticmethod
    def _parse_ports(ports_str: str) -> list[int]:
        """Extract all mapped host ports from docker ps port output."""
        ports: list[int] = []
        if not ports_str:
            return ports

        # Regex for host port mappings:
        # e.g., "0.0.0.0:5432->5432/tcp" or "[::]:8080->80/tcp" or "::1:3000->3000/tcp"
        # or "localhost:4000->4000/tcp" or port ranges "0.0.0.0:8000-8002->8000-8002/tcp"
        pattern = re.compile(r"(?:^|[\s,])(?:\[?[a-zA-Z0-9._%*:-]*\]?):(\d+)(?:-(\d+))?->")

        for match in pattern.finditer(ports_str):
            start_port = int(match.group(1))
            end_port_str = match.group(2)
            if end_port_str:
                end_port = int(end_port_str)
                ports.extend(range(start_port, end_port + 1))
            else:
                ports.append(start_port)

        return ports
