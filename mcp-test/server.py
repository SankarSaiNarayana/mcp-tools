from fastmcp import FastMCP

mcp = FastMCP("KubeAtlas-Test")


from kubernetes import client, config

@mcp.tool
def get_namespaces():
    config.load_kube_config()

    v1 = client.CoreV1Api()

    namespaces = v1.list_namespace()

    return [n.metadata.name for n in namespaces.items]

if __name__ == "__main__":
    mcp.run()