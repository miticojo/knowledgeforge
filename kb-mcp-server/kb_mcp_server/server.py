"""MCP stdio server for the ArchiMate Knowledge Base.

Exposes graph query tools to MCP-compatible AI agents (Codex, Cursor, etc.)
via the Model Context Protocol. Runs locally as a lightweight proxy,
calling the KB backend on Cloud Run via HTTP.

Usage:
    kb-mcp serve --backend-url https://kb-agent-XXXX.run.app

Or configure in your MCP client's settings file:
    {
        "mcpServers": {
            "kb": {
                "command": "kb-mcp",
                "args": ["serve", "--backend-url", "https://..."]
            }
        }
    }
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys

import httpx


# Lazy-loaded auth token
_cached_token: str | None = None


def _get_auth_headers(backend_url: str) -> dict[str, str]:
    """Get Google IAP auth headers for Cloud Run backend."""
    global _cached_token
    if "localhost" in backend_url or "127.0.0.1" in backend_url:
        return {}
    try:
        import google.auth
        import google.auth.transport.requests
        credentials, _ = google.auth.default()
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        _cached_token = credentials.token
        return {"Authorization": f"Bearer {_cached_token}"}
    except Exception:
        return {}


async def _call_backend(client: httpx.AsyncClient, backend_url: str,
                         method: str, path: str, json_body: dict | None = None) -> dict:
    """Call the KB backend and return JSON response."""
    url = f"{backend_url.rstrip('/')}{path}"
    headers = _get_auth_headers(backend_url)
    if method == "GET":
        resp = await client.get(url, headers=headers, timeout=30)
    else:
        resp = await client.post(url, json=json_body, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def serve(backend_url: str, tenant_id: str = "") -> None:
    """Start the MCP server with KB tools."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    server = Server("kb")
    default_headers = {"X-Tenant-Id": tenant_id} if tenant_id else {}
    client = httpx.AsyncClient(headers=default_headers)

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="get_brief",
                description="Get a structured Knowledge Base brief — overview of entities, relationships, confidence levels, gaps, and source documents. Use this first to orient yourself.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="query",
                description="Query the Knowledge Base with a natural language question. Returns relevant text chunks, graph connections, and source citations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question about the architecture"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_entity",
                description="Look up a specific entity by type and name. Returns entity details, layer, and source document.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "description": "ArchiMate type (e.g. ApplicationComponent, BusinessProcess, SystemSoftware)"},
                        "entity_name": {"type": "string", "description": "Entity name to look up"},
                    },
                    "required": ["entity_type", "entity_name"],
                },
            ),
            types.Tool(
                name="get_connections",
                description="Get all direct connections (1-hop) for an entity by its ID. Returns incoming and outgoing relationships with confidence levels.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_id": {"type": "string", "description": "Entity UUID"},
                    },
                    "required": ["entity_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected entities in the knowledge graph — the architectural hubs.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "top_n": {"type": "integer", "default": 10, "description": "Number of top entities to return"},
                    },
                },
            ),
            types.Tool(
                name="graph_stats",
                description="Return aggregate statistics: entity counts by type, edge counts, confidence distribution, document count.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="check_conformance",
                description="Validate the knowledge graph against architecture and data governance rules. Returns pass/warning/error for each rule with violation details.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="impact_analysis",
                description="Calculate blast radius from an entity through all relationship layers. Uses BFS with confidence decay. Essential for change impact and decommission analysis.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_type": {"type": "string", "description": "ArchiMate type (e.g. SystemSoftware, ApplicationComponent)"},
                        "entity_name": {"type": "string", "description": "Entity name to analyze"},
                        "max_hops": {"type": "integer", "default": 4, "description": "Max traversal depth (1-6)"},
                    },
                    "required": ["entity_type", "entity_name"],
                },
            ),
        ]

    async def _handle_get_brief(_: dict) -> str:
        result = await _call_backend(client, backend_url, "GET", "/graph/brief")
        return result.get("brief", "No brief available")

    async def _handle_query(args: dict) -> str:
        question = args["question"]
        # Use the CopilotKit/ADK endpoint for full pipeline query
        # For now, use a simplified approach via the search tool directly
        result = await _call_backend(client, backend_url, "POST", "/copilotkit", {
            "messages": [{"role": "user", "content": question}],
        })
        # Extract the assistant response
        if isinstance(result, dict):
            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)

    async def _handle_get_entity(args: dict) -> str:
        etype = args["entity_type"]
        ename = args["entity_name"]
        result = await _call_backend(client, backend_url, "GET", f"/graph/entity/{etype}/{ename}")
        return json.dumps(result, indent=2)

    async def _handle_get_connections(args: dict) -> str:
        eid = args["entity_id"]
        result = await _call_backend(client, backend_url, "GET", f"/graph/connections/{eid}")
        conns = result.get("connections", [])
        lines = [f"Connections for entity {eid} ({result.get('total', 0)} total):"]
        for c in conns:
            direction = c.get("direction", "?")
            rel = c.get("relationship", "?")
            conf = c.get("confidence", "EXTRACTED")
            if direction == "outgoing":
                lines.append(f"  --> {c.get('target_type', '?')} [{rel}, {conf}]")
            else:
                lines.append(f"  <-- {c.get('source_type', '?')} [{rel}, {conf}]")
        return "\n".join(lines)

    async def _handle_god_nodes(args: dict) -> str:
        top_n = args.get("top_n", 10)
        result = await _call_backend(client, backend_url, "GET", f"/graph/god-nodes?top_n={top_n}")
        lines = ["Most connected entities (architectural hubs):"]
        for i, node in enumerate(result, 1):
            lines.append(f"  {i}. {node['name']} ({node['type']}) — {node['degree']} connections")
        return "\n".join(lines)

    async def _handle_graph_stats(_: dict) -> str:
        result = await _call_backend(client, backend_url, "GET", "/graph/stats")
        conf = result.get("confidence_distribution", {})
        lines = [
            f"Entities: {result.get('total_entities', 0)}",
            f"Edges: {result.get('total_edges', 0)}",
            f"Documents: {result.get('documents', 0)}",
            f"Chunks: {result.get('chunks', 0)}",
            f"Confidence: EXTRACTED={conf.get('EXTRACTED', 0)}, INFERRED={conf.get('INFERRED', 0)}, AMBIGUOUS={conf.get('AMBIGUOUS', 0)}",
        ]
        return "\n".join(lines)

    async def _handle_check_conformance(_: dict) -> str:
        result = await _call_backend(client, backend_url, "GET", "/graph/conformance")
        lines = [f"Conformance Report: {result['passed']}/{result['total_rules']} passed, "
                 f"{result['warnings']} warnings, {result['errors']} errors", ""]
        for r in result.get("results", []):
            icon = "PASS" if r["status"] == "passed" else r["severity"].upper()
            lines.append(f"[{icon}] {r['rule_id']}: {r['description']}")
            if r["status"] != "passed":
                for v in r.get("violations", [])[:5]:
                    lines.append(f"      - {v}")
                if r["violation_count"] > 5:
                    lines.append(f"      ... and {r['violation_count'] - 5} more")
        return "\n".join(lines)

    async def _handle_impact_analysis(args: dict) -> str:
        etype = args["entity_type"]
        ename = args["entity_name"]
        max_hops = args.get("max_hops", 4)
        result = await _call_backend(client, backend_url, "GET",
                                      f"/graph/impact/{etype}/{ename}?max_hops={max_hops}")
        if "error" in result:
            return f"Error: {result['error']}"

        src = result.get("source", {})
        lines = [
            f"Impact Analysis: {src.get('name', '?')} ({src.get('type', '?')})",
            f"Blast radius: {result.get('total_blast_radius', 0)} entities "
            f"(confidence-weighted: {result.get('confidence_weighted_radius', 0)})",
            f"Layers: {result.get('layer_summary', {})}",
            f"Max hops reached: {result.get('max_hops_reached', 0)}",
            "",
        ]
        current_hop = 0
        for e in result.get("impacted_entities", []):
            if e["hops"] != current_hop:
                current_hop = e["hops"]
                lines.append(f"Hop {current_hop}:")
            lines.append(f"  {e['name']} ({e['type']}) [{e['layer']}] conf={e['confidence']}")
        return "\n".join(lines)

    _handlers = {
        "get_brief": _handle_get_brief,
        "query": _handle_query,
        "get_entity": _handle_get_entity,
        "get_connections": _handle_get_connections,
        "god_nodes": _handle_god_nodes,
        "graph_stats": _handle_graph_stats,
        "check_conformance": _handle_check_conformance,
        "impact_analysis": _handle_impact_analysis,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            result = await handler(arguments)
            return [types.TextContent(type="text", text=result)]
        except httpx.HTTPStatusError as exc:
            return [types.TextContent(type="text", text=f"Backend error {exc.response.status_code}: {exc.response.text[:500]}")]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error: {exc}")]

    async def run_server() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(run_server())


def main():
    parser = argparse.ArgumentParser(description="KB MCP Server")
    sub = parser.add_subparsers(dest="command")
    serve_cmd = sub.add_parser("serve", help="Start MCP stdio server")
    serve_cmd.add_argument("--backend-url", required=True, help="KB backend URL (e.g. https://kb-agent-XXX.run.app)")
    serve_cmd.add_argument("--tenant", default="", help="Tenant ID (email) for data isolation")
    args = parser.parse_args()

    if args.command == "serve":
        serve(args.backend_url, tenant_id=args.tenant)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
