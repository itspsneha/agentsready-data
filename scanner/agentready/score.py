"""Agent-Readiness Score (ARS) v1: 100 points across five pillars, plus levels L0-L4."""

# (check id, pillar, points, label, how to pass)
CHECKS = [
    # A. Access: can an agent read you at all?
    ("agent_not_blocked", "Access", 10, "Agents get the real page, not a bot wall",
     "Serve the homepage to AI user-agents (Claude-User, ChatGPT-User) without a challenge/403."),
    ("robots_allows_user_agents", "Access", 6, "robots.txt lets user-triggered agents in",
     "Do not Disallow ChatGPT-User / Claude-User / Perplexity-User; block training crawlers if you must."),
    ("home_ssr", "Access", 4, "Content is server-rendered",
     "Ship meaningful HTML (>1k chars of text) without requiring JavaScript."),
    # B. Context: can an agent understand you cheaply?
    ("llms_txt", "Context", 8, "llms.txt exists",
     "Publish /llms.txt (markdown index of your docs) at the root or docs host."),
    ("llms_full_txt", "Context", 3, "llms-full.txt exists",
     "Publish /llms-full.txt with the full docs corpus in one file."),
    ("markdown_docs", "Context", 6, "Docs available as markdown",
     "Serve every docs page as .md (append .md or honour Accept: text/markdown)."),
    ("sitemap", "Context", 2, "Sitemap", "Publish sitemap.xml and reference it from robots.txt."),
    ("structured_meta", "Context", 1, "Structured metadata", "Add JSON-LD + meta description."),
    # C. Interfaces: can an agent act through you?
    ("docs_found", "Interfaces", 4, "Public developer docs", "Link docs from the homepage; host at docs.<domain>."),
    ("openapi", "Interfaces", 8, "Machine-readable API spec",
     "Publish an OpenAPI spec at a stable URL (/openapi.json) and link it from llms.txt."),
    ("mcp_product", "Interfaces", 12, "Remote MCP server for the product",
     "Host a remote MCP server (e.g. mcp.<domain>/mcp, Streamable HTTP) exposing core actions."),
    ("mcp_docs", "Interfaces", 4, "Docs MCP / searchable docs for agents",
     "Expose a docs search MCP (Mintlify/Fern/GitBook do this out of the box)."),
    ("sdk_cli", "Interfaces", 4, "SDKs and a CLI", "Ship official SDKs and a CLI agents can install and script."),
    # D. Onboarding & auth: can an agent get credentials without a human babysitter?
    ("oauth_metadata", "Onboarding", 5, "OAuth discovery metadata",
     "Publish /.well-known/oauth-authorization-server (RFC 8414) and protected-resource metadata (RFC 9728)."),
    ("oauth_dcr", "Onboarding", 6, "Dynamic client registration",
     "Let agents self-register OAuth clients (RFC 7591) so MCP clients connect with one click."),
    ("self_serve_keys", "Onboarding", 5, "Self-serve API keys",
     "Document how to create an API key in the first screen of docs; no sales call."),
    ("free_tier", "Onboarding", 3, "Free tier / test mode",
     "Offer free credits or a sandbox so an agent can verify an integration before payment."),
    # E. Trust & protocols
    ("agent_manifests", "Trust", 4, "Agent manifests",
     "Publish an MCP server card (/.well-known/mcp.json) or A2A agent card (/.well-known/agent-card.json)."),
    ("security_txt", "Trust", 2, "security.txt", "Publish /.well-known/security.txt with a contact."),
    ("status_page", "Trust", 3, "Public status page", "Link a status page so agents can tell outages from bugs."),
]
PILLARS = ["Access", "Context", "Interfaces", "Onboarding", "Trust"]
LEVELS = [(80, "L4", "Agent-native"), (60, "L3", "Agent-operable"), (40, "L2", "Agent-documented"),
          (20, "L1", "Agent-readable"), (0, "L0", "Agent-invisible")]
assert sum(c[2] for c in CHECKS) == 100


def passes(r):
    if not r.get("reachable"):
        return {c[0]: False for c in CHECKS}
    return {
        "agent_not_blocked": not r.get("agent_blocked"),
        "robots_allows_user_agents": not r.get("robots_blocks_user_agents"),
        "home_ssr": bool(r.get("home_ssr")),
        "llms_txt": bool(r.get("llms_txt")),
        "llms_full_txt": bool(r.get("llms_full_txt")),
        "markdown_docs": bool(r.get("markdown_docs")),
        "sitemap": bool(r.get("sitemap")),
        "structured_meta": bool(r.get("has_jsonld") or r.get("has_meta_description")),
        "docs_found": bool(r.get("docs_url")),
        "openapi": bool(r.get("openapi_url")) or bool(r.get("in_apis_guru")),
        "mcp_product": bool(r.get("mcp_product_server")),
        "mcp_docs": bool(r.get("mcp_docs_server")) or bool(r.get("mcp_product_server")),
        "sdk_cli": bool(r.get("kw_sdk") or r.get("kw_cli")),
        "oauth_metadata": bool(r.get("oauth_metadata") or r.get("oauth_protected_resource")),
        "oauth_dcr": bool(r.get("oauth_dcr")),
        "self_serve_keys": bool(r.get("kw_api_key") and r.get("docs_url")),
        "free_tier": bool(r.get("kw_free_tier")),
        "agent_manifests": bool(r.get("mcp_server_card") or r.get("a2a_agent_card") or r.get("ai_plugin") or r.get("agents_json")),
        "security_txt": bool(r.get("security_txt")),
        "status_page": bool(r.get("link_status") or r.get("kw_status")),
    }


def score(r):
    p = passes(r)
    total = sum(pts for cid, _, pts, *_ in CHECKS if p[cid])
    pillars = {pl: [0, 0] for pl in PILLARS}
    for cid, pl, pts, *_ in CHECKS:
        pillars[pl][1] += pts
        if p[cid]:
            pillars[pl][0] += pts
    lvl = next((l, n) for t, l, n in LEVELS if total >= t)
    fixes = sorted(((pts, label, how) for cid, _, pts, label, how in CHECKS if not p[cid]), reverse=True)
    return {"score": total, "level": lvl[0], "level_name": lvl[1],
            "pillars": {k: v[0] for k, v in pillars.items()},
            "pillar_max": {k: v[1] for k, v in pillars.items()},
            "passes": p, "top_fixes": [{"points": a, "check": b, "fix": c} for a, b, c in fixes[:5]]}
