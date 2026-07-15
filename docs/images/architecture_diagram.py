# IRIS architecture — Amazon Bedrock AgentCore Runtime (serverless).
# Source of truth for docs/images/architecture.png, rendered with standard AWS icons.
# Render with (from this directory):
#   ../../../.venv/bin/python3 architecture_diagram.py
# Requires: pip install diagrams  +  graphviz `dot` on PATH.
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.security import Cognito
from diagrams.aws.network import CloudFront
from diagrams.aws.storage import SimpleStorageServiceS3
from diagrams.aws.ml import Bedrock
from diagrams.aws.general import Users
from diagrams.custom import Custom

# Strands Agents logo (composed in strands.png) — used for the IRIS agent node.
STRANDS_ICON = "strands.png"

graph_attr = {
    "fontsize": "20",
    "fontname": "Helvetica",
    "labelloc": "t",
    "pad": "0.6",
    "nodesep": "0.9",
    "ranksep": "1.6",
    "splines": "spline",
    "bgcolor": "white",
}
node_attr = {"fontsize": "13", "fontname": "Helvetica"}
edge_attr = {"fontsize": "12", "fontname": "Helvetica", "color": "#5a6b7b"}

with Diagram(
    "IRIS Architecture",
    filename="architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    user = Users("User / Web Browser")

    with Cluster("Customer AWS account"):
        cognito = Cognito("Amazon Cognito\n(User Pool + Client)")

        with Cluster("Static frontend (Amazon CloudFront + Amazon S3)"):
            cf = CloudFront("Amazon CloudFront\n(OAC, HTTPS, SPA routing)")
            s3site = SimpleStorageServiceS3("Frontend S3 bucket\n(private, static React app)")

        with Cluster("Amazon Bedrock AgentCore Runtime (serverless)"):
            authz = Cognito("Managed Cognito\nJWT authorizer")
            agent = Custom("IRIS agent\n(Strands, per-session microVM)", STRANDS_ICON)

        bedrock = Bedrock("Amazon Bedrock\n(Claude models)")
        s3data = SimpleStorageServiceS3("Codebase S3 bucket\n(external, read-only)")

    # Frontend delivery
    user >> Edge(label="1 . load app (HTTPS)") >> cf
    cf >> Edge(label="serve static assets via OAC") >> s3site

    # Auth
    user >> Edge(label="2 . authenticate, get access token") >> cognito

    # Chat: browser invokes the Runtime data-plane endpoint directly
    user >> Edge(label="3 . POST /invocations (HTTPS, SSE)\nAuthorization: Bearer access token") >> authz
    authz >> Edge(label="4 . validate token, then forward") >> agent
    cognito >> Edge(label="OIDC discovery / JWKS", style="dashed") >> authz

    # Backend work
    agent >> Edge(label="5 . invoke models (HTTPS)") >> bedrock
    agent >> Edge(label="6 . read codebase + index") >> s3data
