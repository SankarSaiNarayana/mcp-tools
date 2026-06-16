"""
k8s-mcp-tool — an MCP server giving Claude safe, structured access to kubectl.

Tools exposed:
  - k8s_list_contexts        list all kubeconfig contexts and which one is current
  - k8s_current_context      get just the current context name
  - k8s_switch_context       switch the active kubeconfig context
  - k8s_get                  run `kubectl get <resource>` with optional namespace/selector/output
  - k8s_describe             run `kubectl describe <resource> <name>`
  - k8s_logs                 fetch logs for a pod/container, with tail and previous support
  - k8s_top                  run `kubectl top nodes|pods` for resource usage
  - k8s_events               list recent cluster events, optionally filtered by namespace
  - k8s_raw                  escape hatch: run any whitelisted read-only kubectl command

Transport: stdio. This process is meant to be spawned locally by Claude Desktop / Claude
Code, one process per session. It reads the caller's local kubeconfig (~/.kube/config by
default, or $KUBECONFIG) — it never receives or stores credentials itself.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .kubectl_runner import KubectlResult, run_kubectl

mcp = FastMCP("k8s-mcp-tool")


def _result_to_text(result: KubectlResult) -> str:
    """Render a KubectlResult as a single text block for the MCP tool result."""
    if result.blocked_reason:
        return f"BLOCKED: {result.blocked_reason}"
    if result.timed_out:
        return f"TIMED OUT: {result.stderr}"
    if result.exit_code != 0:
        return (
            f"kubectl exited with code {result.exit_code}.\n"
            f"stderr:\n{result.stderr.strip()}\n"
            f"stdout:\n{result.stdout.strip()}"
        )
    return result.stdout.strip() or "(empty output)"


@mcp.tool()
def k8s_list_contexts() -> str:
    """
    List every context defined in the local kubeconfig, and mark which one is current.
    Use this before running other tools if you're unsure which cluster you're targeting.
    """
    result = run_kubectl(["config", "get-contexts"])
    return _result_to_text(result)


@mcp.tool()
def k8s_current_context() -> str:
    """Return just the name of the currently active kubeconfig context."""
    result = run_kubectl(["config", "current-context"])
    return _result_to_text(result)


@mcp.tool()
def k8s_switch_context(context_name: str) -> str:
    """
    Switch the active kubeconfig context to `context_name`.

    This mutates local kubeconfig state (which cluster subsequent commands target), so it
    requires the server to be launched with KUBECTL_MCP_ALLOW_MUTATIONS=1. Always confirm
    the new current context afterward with k8s_current_context.

    Args:
        context_name: Exact context name as shown by k8s_list_contexts.
    """
    result = run_kubectl(["config", "use-context", context_name])
    return _result_to_text(result)


@mcp.tool()
def k8s_get(
    resource: str,
    name: str = "",
    namespace: str = "",
    all_namespaces: bool = False,
    selector: str = "",
    output: str = "wide",
) -> str:
    """
    Run `kubectl get` for a resource type, with common filters.

    Args:
        resource: Resource type, e.g. "pods", "deployments", "nodes", "svc", "events".
        name: Specific resource name. Leave empty to list all of that type.
        namespace: Namespace to query. Leave empty to use the context's default namespace.
        all_namespaces: If True, query across all namespaces (overrides `namespace`).
        selector: Label selector, e.g. "app=payment-service".
        output: Output format: "wide" (default, most readable), "json", "yaml", or "name".
    """
    args = ["get", resource]
    if name:
        args.append(name)
    if all_namespaces:
        args.append("--all-namespaces")
    elif namespace:
        args.extend(["-n", namespace])
    if selector:
        args.extend(["-l", selector])
    if output:
        args.extend(["-o", output])

    result = run_kubectl(args)
    return _result_to_text(result)


@mcp.tool()
def k8s_describe(resource: str, name: str, namespace: str = "") -> str:
    """
    Run `kubectl describe` for a specific resource. Use this to see events, conditions,
    and config for one object — much more detail than k8s_get.

    Args:
        resource: Resource type, e.g. "pod", "deployment", "node".
        name: The specific resource name to describe.
        namespace: Namespace the resource lives in. Leave empty for the default namespace
            (ignored for cluster-scoped resources like nodes).
    """
    args = ["describe", resource, name]
    if namespace:
        args.extend(["-n", namespace])

    result = run_kubectl(args)
    return _result_to_text(result)


@mcp.tool()
def k8s_logs(
    pod_name: str,
    namespace: str = "",
    container: str = "",
    tail_lines: int = 200,
    previous: bool = False,
    since: str = "",
) -> str:
    """
    Fetch logs for a pod, optionally for a specific container.

    Args:
        pod_name: Name of the pod to fetch logs from.
        namespace: Namespace the pod lives in. Leave empty for the default namespace.
        container: Specific container name, required if the pod has multiple containers.
        tail_lines: Number of most recent lines to return. Defaults to 200 to avoid
            flooding context with an entire log history.
        previous: If True, fetch logs from the previous (crashed/restarted) container
            instance instead of the current one. Useful for diagnosing CrashLoopBackOff.
        since: Only return logs newer than this duration, e.g. "10m" or "1h".
    """
    args = ["logs", pod_name]
    if namespace:
        args.extend(["-n", namespace])
    if container:
        args.extend(["-c", container])
    if tail_lines:
        args.extend(["--tail", str(tail_lines)])
    if previous:
        args.append("--previous")
    if since:
        args.extend(["--since", since])

    result = run_kubectl(args)
    return _result_to_text(result)


@mcp.tool()
def k8s_top(target: str = "pods", namespace: str = "", all_namespaces: bool = False) -> str:
    """
    Run `kubectl top` to get live CPU/memory usage. Requires metrics-server to be
    installed in the cluster.

    Args:
        target: "pods" or "nodes".
        namespace: Namespace to scope to (ignored for "nodes").
        all_namespaces: If True and target is "pods", show usage across all namespaces.
    """
    if target not in ("pods", "nodes"):
        return 'BLOCKED: target must be "pods" or "nodes".'

    args = ["top", target]
    if target == "pods":
        if all_namespaces:
            args.append("--all-namespaces")
        elif namespace:
            args.extend(["-n", namespace])

    result = run_kubectl(args)
    return _result_to_text(result)


@mcp.tool()
def k8s_events(namespace: str = "", all_namespaces: bool = False) -> str:
    """
    List recent cluster events (warnings, scheduling failures, image pull errors, etc.),
    sorted by time. Use this first when investigating why something is unhealthy.

    Args:
        namespace: Namespace to scope to.
        all_namespaces: If True, list events across all namespaces.
    """
    args = ["get", "events", "--sort-by=.lastTimestamp"]
    if all_namespaces:
        args.append("--all-namespaces")
    elif namespace:
        args.extend(["-n", namespace])

    result = run_kubectl(args)
    return _result_to_text(result)


@mcp.tool()
def k8s_raw(args: list[str]) -> str:
    """
    Escape hatch: run any whitelisted read-only kubectl command not covered by the other
    tools, e.g. ["api-resources"] or ["explain", "pod.spec.containers"].

    Mutating verbs (delete, apply, scale, exec, patch, etc.) are blocked unless the server
    was started with KUBECTL_MCP_ALLOW_MUTATIONS=1.

    Args:
        args: The kubectl arguments as a list of tokens, NOT a single string.
            e.g. ["get", "pods", "-o", "json"] — never "get pods -o json" as one string.
    """
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return "BLOCKED: args must be a list of strings."

    result = run_kubectl(args)
    return _result_to_text(result)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()