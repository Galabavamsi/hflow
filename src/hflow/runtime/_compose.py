"""Docker Compose invocation for a rendered bundle (the single subprocess seam).

Everything the SDK does to the runtime is a plain ``docker compose`` command a
user could type themselves -- the bundle stays inspectable and hand-runnable.
This module is the one place that shells out, so tests monkeypatch exactly one
function (:func:`run_compose_command`) to keep Docker out of unit tests.
"""

import subprocess
from pathlib import Path


class ComposeError(RuntimeError):
    """A ``docker compose`` invocation failed; ``stderr`` carries the reason."""

    def __init__(self, command: list[str], returncode: int, stderr: str) -> None:
        super().__init__(
            f"{' '.join(command)} failed with exit code {returncode}: {stderr.strip()}"
        )
        self.command = command
        self.returncode = returncode
        self.stderr = stderr


def compose_base_command(compose_file: Path, project_name: str | None = None) -> list[str]:
    """The ``docker compose`` prefix targeting one bundle's compose file."""
    command = ["docker", "compose", "--file", str(compose_file)]
    if project_name is not None:
        command.extend(["--project-name", project_name])
    return command


def run_compose_command(
    compose_file: Path,
    *arguments: str,
    project_name: str | None = None,
    timeout_s: float = 600.0,
) -> str:
    """Run one compose subcommand and return its stdout (the monkeypatch seam)."""
    command = [*compose_base_command(compose_file, project_name), *arguments]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as error:
        raise ComposeError(command, -1, "docker not found on PATH -- install Docker") from error
    except subprocess.TimeoutExpired as error:
        raise ComposeError(command, -1, f"timed out after {timeout_s:.0f}s") from error
    if completed.returncode != 0:
        raise ComposeError(command, completed.returncode, completed.stderr)
    return completed.stdout


def compose_up_detached(
    compose_file: Path,
    *,
    project_name: str | None = None,
    timeout_s: float = 600.0,
) -> None:
    """``docker compose up --detach`` (image pulls make the first call slow)."""
    run_compose_command(
        compose_file, "up", "--detach", project_name=project_name, timeout_s=timeout_s
    )


def compose_down(
    compose_file: Path,
    *,
    project_name: str | None = None,
    remove_volumes: bool = False,
    timeout_s: float = 300.0,
) -> None:
    """``docker compose down``; ``remove_volumes`` also drops the DB and venv."""
    arguments = ["down"]
    if remove_volumes:
        arguments.append("--volumes")
    run_compose_command(compose_file, *arguments, project_name=project_name, timeout_s=timeout_s)


def compose_ps(compose_file: Path, *, project_name: str | None = None) -> str:
    """``docker compose ps`` output (human-readable service table)."""
    return run_compose_command(compose_file, "ps", project_name=project_name, timeout_s=60.0)


def compose_logs(
    compose_file: Path,
    *services: str,
    project_name: str | None = None,
    timeout_s: float = 120.0,
) -> str:
    """``docker compose logs --no-color`` for diagnosis (all services by default)."""
    return run_compose_command(
        compose_file,
        "logs",
        "--no-color",
        *services,
        project_name=project_name,
        timeout_s=timeout_s,
    )
