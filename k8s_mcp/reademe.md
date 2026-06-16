# k8s-mcp-tool

A Model Context Protocol (MCP) server that gives Claude safe, structured access to Kubernetes clusters through `kubectl`.

Instead of allowing arbitrary shell execution, this tool exposes a curated set of Kubernetes operations as MCP tools. It is designed to be safe by default, read-focused, and suitable for local use with Claude Desktop.

---

# Features

## Kubernetes Context Management

* List available kubeconfig contexts
* View the currently active context
* Switch contexts (optional, requires explicit permission)

## Kubernetes Resource Inspection

* Get resources (pods, deployments, services, nodes, etc.)
* Describe resources
* View logs
* View cluster events
* View resource utilization with `kubectl top`

## Safe by Default

* Uses `subprocess.run()` with argument lists (no shell execution)
* Blocks dangerous or mutating commands by default
* Enforces command timeouts
* Returns structured output for better Claude responses

---

# Exposed MCP Tools

| Tool                  | Description                                        |
| --------------------- | -------------------------------------------------- |
| `k8s_list_contexts`   | List all kubeconfig contexts                       |
| `k8s_current_context` | Show current Kubernetes context                    |
| `k8s_switch_context`  | Change active context (requires mutations enabled) |
| `k8s_get`             | Run kubectl get                                    |
| `k8s_describe`        | Run kubectl describe                               |
| `k8s_logs`            | Fetch pod logs                                     |
| `k8s_top`             | Show CPU and memory usage                          |
| `k8s_events`          | Show recent cluster events                         |
| `k8s_raw`             | Execute any whitelisted kubectl command            |

---

# Project Structure

```text
mcp_tools/
├── k8s_mcp/
│   ├── __init__.py
│   ├── server.py
│   └── kubectl_runner.py
├── requirements.txt
└── README.md
```

---

# Requirements

* Python 3.10+
* kubectl
* Access to a Kubernetes cluster
* Claude Desktop (or another MCP-compatible client)

Verify kubectl:

```bash
kubectl version --client
```

Verify cluster access:

```bash
kubectl config current-context
kubectl get pods -A
```

---

# Installation

## Clone Repository

```bash
git clone <repository-url>
cd mcp_tools
```

## Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

# Running the MCP Server

From the project root:

```bash
source .venv/bin/activate

python -m k8s_mcp.server
```

Expected behavior:

* No output
* Terminal remains active
* Process waits for MCP requests

This indicates the server is running correctly.

Stop with:

```bash
Ctrl + C
```

---

# Claude Desktop Configuration

Create or edit:

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

Example configuration:

```json
{
  "mcpServers": {
    "k8s": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": [
        "-m",
        "k8s_mcp.server"
      ],
      "env": {
        "PYTHONPATH": "/absolute/path/to/project/root"
      }
    }
  }
}
```

Example:

```json
{
  "mcpServers": {
    "k8s": {
      "command": "/Users/example/mcp_tools/.venv/bin/python",
      "args": [
        "-m",
        "k8s_mcp.server"
      ],
      "env": {
        "PYTHONPATH": "/Users/example/mcp_tools"
      }
    }
  }
}
```

After updating the configuration:

1. Quit Claude Desktop completely.
2. Restart Claude Desktop.
3. Verify the MCP server appears in Claude.

---

# Enabling Mutating Commands

By default, mutating commands are blocked.

Blocked examples:

```bash
kubectl delete
kubectl apply
kubectl patch
kubectl scale
kubectl exec
kubectl config use-context
```

To enable them:

```bash
export KUBECTL_MCP_ALLOW_MUTATIONS=1
```

Or in Claude Desktop:

```json
{
  "mcpServers": {
    "k8s": {
      "command": "/path/to/python",
      "args": [
        "-m",
        "k8s_mcp.server"
      ],
      "env": {
        "PYTHONPATH": "/path/to/project",
        "KUBECTL_MCP_ALLOW_MUTATIONS": "1"
      }
    }
  }
}
```

---

# Example Claude Prompts

## Context Inspection

```text
List all Kubernetes contexts.
```

```text
What cluster am I currently connected to?
```

## Resource Discovery

```text
Show all pods in the default namespace.
```

```text
List deployments across all namespaces.
```

## Troubleshooting

```text
Describe pod payment-service-abc123.
```

```text
Show logs for pod checkout-service.
```

```text
Show cluster events.
```

## Resource Usage

```text
Show CPU and memory usage for all pods.
```

```text
Show node resource utilization.
```

---

# Security Model

The server intentionally avoids arbitrary command execution.

## Allowed Verbs

```text
get
describe
logs
top
explain
version
config
api-resources
api-versions
cluster-info
events
```

## Blocked by Default

```text
delete
apply
edit
exec
scale
rollout
patch
cp
drain
cordon
uncordon
taint
label
annotate
create
replace
set
```

Mutations require:

```bash
KUBECTL_MCP_ALLOW_MUTATIONS=1
```

---

# Troubleshooting

## ModuleNotFoundError: No module named 'k8s_mcp'

Ensure:

```json
{
  "env": {
    "PYTHONPATH": "/path/to/project/root"
  }
}
```

is configured correctly.

---

## kubectl Connection Refused

Example:

```text
The connection to the server 127.0.0.1:xxxxx was refused
```

Verify:

```bash
kubectl get nodes
kubectl get pods -A
```

The Kubernetes cluster must be running before the MCP server can access it.

---

## MCP Server Not Appearing in Claude

1. Validate JSON configuration.
2. Restart Claude Desktop.
3. Confirm the server runs manually:

```bash
python -m k8s_mcp.server
```

4. Check Claude Desktop logs for startup errors.

---

# License

MIT License
