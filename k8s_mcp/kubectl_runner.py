"""
Thin, safe wrapper around the kubectl CLI.

Design goals:
- Never shell out to an arbitrary string. Always pass an argv list to subprocess.
- Whitelist verbs. This is a read-mostly tool: get/describe/logs/top/explain/version
  are always allowed. Mutating verbs (delete/apply/edit/exec/scale/rollout/patch/cp/drain)
  are blocked by default and only allowed if KUBECTL_MCP_ALLOW_MUTATIONS=1 is set in the
  environment that launches this server.
- Always enforce a timeout so a hung API server can't hang Claude's tool call forever.
- Return structured results (stdout, stderr, exit code) rather than raising on non-zero
  exit, since a non-zero exit from kubectl (e.g. "not found") is often a meaningful
  answer, not a tool failure.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_TIMEOUT_SECONDS = 30

# Verbs that only read state. These are always permitted.
READ_ONLY_VERBS = {
    "get",
    "describe",
    "logs",
    "top",
    "explain",
    "version",
    "config",  # "config get-contexts" / "config current-context" — read-only subcommands
    "api-resources",
    "api-versions",
    "cluster-info",
    "events",
}

# Verbs that change cluster state. Blocked unless explicitly enabled.
MUTATING_VERBS = {
    "delete",
    "apply",
    "edit",
    "exec",
    "scale",
    "rollout",
    "patch",
    "cp",
    "drain",
    "cordon",
    "uncordon",
    "taint",
    "label",
    "annotate",
    "create",
    "replace",
    "set",
}

# "config" has read-only and mutating subcommands mixed together. We special-case it.
CONFIG_MUTATING_SUBCOMMANDS = {"use-context", "set-context", "set-cluster", "set-credentials", "delete-context", "rename-context", "unset"}


@dataclass
class KubectlResult:
    command: list[str]
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    blocked_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.blocked_reason is None


def _mutations_allowed() -> bool:
    return os.environ.get("KUBECTL_MCP_ALLOW_MUTATIONS", "").strip() == "1"


def _validate_verb(args: list[str]) -> str | None:
    """Return a blocked_reason string if this command should be rejected, else None."""
    if not args:
        return "Empty command."

    verb = args[0]

    if verb == "config":
        # e.g. ["config", "use-context", "prod"]
        subcommand = args[1] if len(args) > 1 else ""
        if subcommand in CONFIG_MUTATING_SUBCOMMANDS and not _mutations_allowed():
            return (
                f"'kubectl config {subcommand}' changes local kubeconfig state and is "
                "blocked. Set KUBECTL_MCP_ALLOW_MUTATIONS=1 in the server environment to allow it."
            )
        return None

    if verb in MUTATING_VERBS and not _mutations_allowed():
        return (
            f"'kubectl {verb}' is a mutating command and is blocked by default. "
            "Set KUBECTL_MCP_ALLOW_MUTATIONS=1 in the server environment to allow it."
        )

    if verb not in READ_ONLY_VERBS and verb not in MUTATING_VERBS:
        return (
            f"'kubectl {verb}' is not in the recognized verb list for this tool. "
            "If this is a valid read-only kubectl verb, it can be added to READ_ONLY_VERBS."
        )

    return None


def kubectl_available() -> bool:
    return shutil.which("kubectl") is not None


def run_kubectl(
    args: list[str],
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> KubectlResult:
    """
    Run `kubectl <args>` safely and return a structured result.

    `args` must be a list of tokens, e.g. ["get", "pods", "-n", "default"].
    Never pass a single shell string here.
    """
    if not kubectl_available():
        return KubectlResult(
            command=["kubectl", *args],
            stdout="",
            stderr="kubectl binary not found on PATH of the machine running this MCP server.",
            exit_code=127,
            blocked_reason="kubectl not installed or not on PATH",
        )

    blocked_reason = _validate_verb(args)
    if blocked_reason:
        return KubectlResult(
            command=["kubectl", *args],
            stdout="",
            stderr="",
            exit_code=-1,
            blocked_reason=blocked_reason,
        )

    full_command = ["kubectl", *args]
    try:
        proc = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return KubectlResult(
            command=full_command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired:
        return KubectlResult(
            command=full_command,
            stdout="",
            stderr=f"Command timed out after {timeout}s.",
            exit_code=-1,
            timed_out=True,
        )
    except FileNotFoundError:
        return KubectlResult(
            command=full_command,
            stdout="",
            stderr="kubectl binary not found.",
            exit_code=127,
        )
    