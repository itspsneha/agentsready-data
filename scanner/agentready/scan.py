"""Agent-readiness scanner: probes a domain the way an AI agent would."""
import asyncio, json, re, socket, time
from urllib.parse import urljoin, urlparse

import httpx

AGENT_UA = "Mozilla/5.0 (compatible; Claude-User/1.0; +https://agentsready.dev/bot)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

# AI user agents we evaluate in robots.txt. "user" = fetches on behalf of a person in real time.
AI_BOTS = {
    "GPTBot": "training", "ClaudeBot": "training", "anthropic-ai": "training", "CCBot": "training",
    "Google-Extended": "training", "Applebot-Extended": "training", "meta-externalagent": "training",
    "Bytespider": "training",
    "OAI-SearchBot": "search", "Claude-SearchBot": "search", "PerplexityBot": "search",
    "ChatGPT-User": "user", "Claude-User": "user", "Perplexity-User": "user",
}
CHALLENGE_RE = re.compile(r"just a moment|attention required|cf-browser-verification|captcha|"
                          r"verify you are human|access denied|request blocked|px-captcha|_incapsula_", re.I)
DOC_HOSTS = ("docs", "developer", "developers", "dev", "api-docs", "platform")
MCP_HOSTS = ("mcp", "api", "docs", "")
MCP_PATHS = ("/mcp", "/sse", "/mcp/sse", "/")
OPENAPI_PATHS = ("/openapi.json", "/openapi.yaml", "/swagger.json", "/api/openapi.json",
                 "/v1/openapi.json", "/api-docs/openapi.json", "/swagger/v1/swagger.json")
KEYWORDS = {
    "kw_api_key": r"api[ -]?keys?\b|api[ -]?tokens?\b|access tokens?\b|secret keys?\b|personal access token",
    "kw_mcp": r"\bmcp\b|model context protocol",
    "kw_llms_txt": r"llms\.txt",
    "kw_openapi": r"openapi|swagger",
    "kw_sdk": r"\bsdks?\b|npm (i|install)|pip install|go get |gem install",
    "kw_cli": r"\bcli\b|command[- ]line|brew install",
    "kw_free_tier": r"free (tier|plan|trial|credits|forever)|(start|started|try|sign up) (for )?free|no credit card|\$0\b|\bfree\b\s*(/|per)\s*month|free usage",
    "kw_agent": r"\bai agents?\b|for agents|agentic",
    "kw_github_login": r"(sign|log) ?(up|in) with github|continue with github",
    "kw_google_login": r"(sign|log) ?(up|in) with google|continue with google",
    "kw_status": r"status\.[a-z0-9-]+\.[a-z]+|statuspage|/status\b",
}
MCP_INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "agentready-scanner", "version": "1.0"}}}


def _visible_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def _robots_blocks(robots, agent):
    """True if `agent` is disallowed from '/' (most specific group wins, else '*')."""
    groups, cur, last_ua = [], None, False
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (s.strip() for s in line.split(":", 1))
        k = k.lower()
        if k == "user-agent":
            if not last_ua:
                cur = {"agents": [], "rules": []}; groups.append(cur)
            cur["agents"].append(v.lower()); last_ua = True
        elif k in ("allow", "disallow") and cur is not None:
            cur["rules"].append((k, v)); last_ua = False
        else:
            last_ua = False
    def verdict(g):
        dis = any(k == "disallow" and v == "/" for k, v in g["rules"])
        allow_root = any(k == "allow" and v in ("/", "/*") for k, v in g["rules"])
        return dis and not allow_root
    specific = [g for g in groups if agent.lower() in g["agents"]]
    if specific:
        return any(verdict(g) for g in specific), "specific"
    star = [g for g in groups if "*" in g["agents"]]
    return (any(verdict(g) for g in star), "wildcard") if star else (False, "none")


class Scanner:
    def __init__(self, client: httpx.AsyncClient, timeout=8.0):
        self.c, self.timeout = client, timeout

    async def get(self, url, ua=AGENT_UA, **kw):
        headers = {"User-Agent": ua, "Accept": kw.pop("accept", "*/*")}
        try:
            return await self.c.get(url, headers=headers, timeout=self.timeout, follow_redirects=True, **kw)
        except Exception as e:  # noqa: BLE001
            return e

    async def resolves(self, host):
        try:
            await asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return True
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def ok(r):
        return isinstance(r, httpx.Response) and r.status_code == 200

    @staticmethod
    def is_html(r):
        return "html" in r.headers.get("content-type", "") or r.text.lstrip()[:15].lower().startswith(("<!doctype", "<html"))

    async def scan(self, domain):
        t0 = time.time()
        d = domain.lower().removeprefix("https://").removeprefix("http://").strip("/").removeprefix("www.")
        res = {"domain": d, "errors": []}
        base = f"https://{d}"

        # 1. Homepage as an agent vs as a browser
        agent_r, browser_r = await asyncio.gather(self.get(base + "/"), self.get(base + "/", ua=BROWSER_UA))
        if not isinstance(browser_r, httpx.Response) and not isinstance(agent_r, httpx.Response):
            base = f"https://www.{d}"
            agent_r, browser_r = await asyncio.gather(self.get(base + "/"), self.get(base + "/", ua=BROWSER_UA))
        res["reachable"] = isinstance(browser_r, httpx.Response) or isinstance(agent_r, httpx.Response)
        if not res["reachable"]:
            res["errors"].append(f"unreachable: {type(agent_r).__name__}")
            res["scan_seconds"] = round(time.time() - t0, 1)
            return res
        ar = agent_r if isinstance(agent_r, httpx.Response) else None
        br = browser_r if isinstance(browser_r, httpx.Response) else None
        res["home_status_agent"] = ar.status_code if ar else None
        res["home_status_browser"] = br.status_code if br else None
        challenged = bool(ar and (ar.status_code in (403, 429, 503) or ar.headers.get("cf-mitigated") == "challenge"
                                  or (ar.status_code == 200 and CHALLENGE_RE.search(ar.text[:4000] or "")
                                      and len(_visible_text(ar.text)) < 800)))
        res["agent_blocked"] = (ar is None) or challenged
        res["browser_blocked"] = br is None or br.status_code >= 400
        home = ar if (ar and not challenged) else br
        html = home.text if home is not None else ""
        final = str(home.url) if home is not None else base + "/"
        origin = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
        res["final_url"] = final
        text = _visible_text(html)
        res["home_text_chars"] = len(text)
        res["home_html_kb"] = round(len(html) / 1024, 1)
        res["home_ssr"] = len(text) >= 1000
        res["has_jsonld"] = "application/ld+json" in html
        res["has_meta_description"] = bool(re.search(r'<meta[^>]+name=["\']description["\']', html, re.I))
        res["has_og"] = "og:title" in html
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        res["title"] = re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""

        # links on homepage → docs / pricing / status
        hrefs = re.findall(r'href=["\']([^"\'#]+)', html)
        abs_links = [urljoin(final, h) for h in hrefs]
        res["link_docs"] = next((u for u in abs_links if re.search(r"//(docs|developers?|dev)\.|/docs\b|/developers?\b|/api-reference|/reference\b", u)), None)
        res["link_pricing"] = next((u for u in abs_links if "/pricing" in u), None)
        res["link_status"] = next((u for u in abs_links if re.search(r"//status\.|statuspage", u)), None)
        res["link_github"] = next((u for u in abs_links if "github.com/" in u and "/sponsors" not in u), None)

        # 2. robots.txt, sitemap, security.txt, agent manifests on the root origin
        names = {"robots": "/robots.txt", "llms": "/llms.txt", "llms_full": "/llms-full.txt",
                 "sitemap": "/sitemap.xml", "security": "/.well-known/security.txt",
                 "ai_plugin": "/.well-known/ai-plugin.json", "agent_card": "/.well-known/agent-card.json",
                 "agent_json": "/.well-known/agent.json", "agents_json": "/.well-known/agents.json",
                 "mcp_card": "/.well-known/mcp.json", "mcp_card2": "/.well-known/mcp/server-card.json",
                 "oauth_as": "/.well-known/oauth-authorization-server",
                 "oidc": "/.well-known/openid-configuration",
                 "oauth_pr": "/.well-known/oauth-protected-resource"}
        rs = dict(zip(names, await asyncio.gather(*(self.get(origin + p) for p in names.values()))))

        robots = rs["robots"].text if self.ok(rs["robots"]) and not self.is_html(rs["robots"]) else ""
        res["robots_present"] = bool(robots)
        res["robots_content_signal"] = "content-signal" in robots.lower()
        blocked = {}
        for bot in AI_BOTS:
            b, how = _robots_blocks(robots, bot) if robots else (False, "none")
            blocked[bot] = b
        res["robots_blocked_bots"] = [b for b, v in blocked.items() if v]
        res["robots_blocks_user_agents"] = any(blocked[b] for b, k in AI_BOTS.items() if k == "user")
        res["robots_blocks_training"] = sum(blocked[b] for b, k in AI_BOTS.items() if k == "training")
        res["robots_names_ai_bots"] = sum(1 for b in AI_BOTS if b.lower() in robots.lower())
        res["sitemap"] = self.ok(rs["sitemap"]) and "<" in rs["sitemap"].text[:200] and not self.is_html(rs["sitemap"]) \
            or bool(re.search(r"(?im)^sitemap:", robots))
        res["security_txt"] = self.ok(rs["security"]) and "contact:" in rs["security"].text.lower()

        def json_ok(r, must=None):
            if not self.ok(r):
                return None
            try:
                j = r.json()
            except Exception:  # noqa: BLE001
                return None
            if must and not any(k in j for k in must):
                return None
            return j

        res["ai_plugin"] = json_ok(rs["ai_plugin"], ["api", "schema_version"]) is not None
        res["a2a_agent_card"] = any(json_ok(rs[k], ["skills", "capabilities", "url"]) is not None
                                    for k in ("agent_card", "agent_json"))
        res["agents_json"] = json_ok(rs["agents_json"]) is not None
        res["mcp_server_card"] = any(json_ok(rs[k]) is not None for k in ("mcp_card", "mcp_card2"))
        oauth = json_ok(rs["oauth_as"], ["issuer", "authorization_endpoint"]) or json_ok(rs["oidc"], ["issuer"])
        res["oauth_metadata"] = oauth is not None
        res["oauth_dcr"] = bool(oauth and oauth.get("registration_endpoint"))
        res["oauth_device_flow"] = bool(oauth and (oauth.get("device_authorization_endpoint")
                                                   or "urn:ietf:params:oauth:grant-type:device_code" in (oauth.get("grant_types_supported") or [])))
        res["oauth_protected_resource"] = json_ok(rs["oauth_pr"], ["resource", "authorization_servers"]) is not None

        # 3. Docs host discovery
        docs_candidates = []
        if res["link_docs"]:
            docs_candidates.append(res["link_docs"])
        resolving = await asyncio.gather(*(self.resolves(f"{h}.{d}") for h in DOC_HOSTS))
        docs_candidates += [f"https://{h}.{d}/" for h, ok in zip(DOC_HOSTS, resolving) if ok]
        docs_candidates.append(origin + "/docs")
        docs_url, docs_r = None, None
        for u in dict.fromkeys(docs_candidates):
            r = await self.get(u)
            # a "docs" link that just redirects to the homepage isn't docs (e.g. /docs -> /)
            fu, hu = urlparse(str(r.url)) if self.ok(r) else None, urlparse(final)
            same_as_home = fu is not None and fu.netloc.removeprefix("www.") == hu.netloc.removeprefix("www.") and fu.path.rstrip("/") == hu.path.rstrip("/")
            if self.ok(r) and urlparse(str(r.url)).netloc and not same_as_home:
                docs_url, docs_r = str(r.url), r
                break
        res["docs_url"] = docs_url
        docs_html = docs_r.text if docs_r is not None else ""
        docs_origin = f"{urlparse(docs_url).scheme}://{urlparse(docs_url).netloc}" if docs_url else None
        res["docs_platform"] = next((p for p, pat in {
            "mintlify": r"mintlify", "readme": r"readme\.io|readme\.com|rdmd", "gitbook": r"gitbook",
            "docusaurus": r"docusaurus", "fern": r"buildwithfern|fern-docs", "redocly": r"redoc",
            "nextra": r"nextra", "stoplight": r"stoplight", "swagger-ui": r"swagger-ui",
            "starlight": r"starlight", "vitepress": r"vitepress", "mkdocs": r"mkdocs"}.items()
            if re.search(pat, docs_html, re.I)), None)

        # 4. llms.txt on root and docs host
        async def llms(origin_):
            r = rs["llms"] if origin_ == origin else await self.get(origin_ + "/llms.txt")
            if self.ok(r) and not self.is_html(r) and r.text.strip()[:1] in ("#", "-", ">") or \
               (self.ok(r) and not self.is_html(r) and "](" in r.text[:5000]):
                return r
            return None
        llms_r = await llms(origin)
        llms_where = "root" if llms_r else None
        if not llms_r and docs_origin and docs_origin != origin:
            llms_r = await llms(docs_origin)
            llms_where = "docs" if llms_r else None
        if not llms_r and docs_url and urlparse(docs_url).path.strip("/"):
            r = await self.get(docs_url.rstrip("/") + "/llms.txt")
            if self.ok(r) and not self.is_html(r):
                llms_r, llms_where = r, "docs_path"
        res["llms_txt"] = llms_where
        res["llms_txt_kb"] = round(len(llms_r.text) / 1024, 1) if llms_r else 0
        res["llms_txt_links"] = len(re.findall(r"\]\((https?://[^)]+)\)", llms_r.text)) if llms_r else 0
        full_src = docs_origin if llms_where == "docs" else origin
        rf = rs["llms_full"] if full_src == origin else await self.get(full_src + "/llms-full.txt")
        res["llms_full_txt"] = bool(self.ok(rf) and not self.is_html(rf) and len(rf.text) > 2000)

        # 5. Markdown docs: .md links in llms.txt, Accept: text/markdown, or <page>.md
        md = False
        if llms_r:
            md_links = re.findall(r"\]\((https?://[^)]+\.md)\)", llms_r.text)
            if md_links:
                r = await self.get(md_links[0])
                md = self.ok(r) and not self.is_html(r)
        if not md and docs_url:
            r = await self.get(docs_url, accept="text/markdown")
            md = self.ok(r) and ("markdown" in r.headers.get("content-type", "") or
                                 (not self.is_html(r) and r.text.lstrip().startswith("#")))
            if not md and urlparse(docs_url).path.strip("/"):
                r = await self.get(docs_url.rstrip("/") + ".md")
                md = self.ok(r) and not self.is_html(r) and len(r.text) > 200
        res["markdown_docs"] = md

        # 6. OpenAPI spec
        spec_origins = list(dict.fromkeys(filter(None, [origin, docs_origin])))
        if await self.resolves(f"api.{d}"):
            spec_origins.append(f"https://api.{d}")
        spec_url = None
        llms_text = llms_r.text if llms_r else ""
        m = re.search(r"\((https?://[^)\s]+(?:openapi|swagger)[^)\s]*\.(?:json|ya?ml))\)", llms_text, re.I)
        cands = ([m.group(1)] if m else []) + [o + p for o in spec_origins for p in OPENAPI_PATHS]
        for i in range(0, len(cands), 8):
            rr = await asyncio.gather(*(self.get(u) for u in cands[i:i + 8]))
            for u, r in zip(cands[i:i + 8], rr):
                if self.ok(r) and not self.is_html(r) and re.search(r'["\']?(openapi|swagger)["\']?\s*:', r.text[:3000]):
                    spec_url = u; break
            if spec_url:
                break
        res["openapi_url"] = spec_url

        # 7. MCP endpoints: JSON-RPC initialize; accept 200 jsonrpc/SSE or 401 w/ OAuth resource metadata
        mcp_hits, probe_meta = [], {}
        hosts = []
        for h in MCP_HOSTS:
            host = f"{h}.{d}" if h else urlparse(origin).netloc
            if h and not await self.resolves(host):
                continue
            hosts.append(host)
        if docs_origin:
            hosts.append(urlparse(docs_origin).netloc)
        probes = [f"https://{h}{p}" for h in dict.fromkeys(hosts) for p in MCP_PATHS
                  if not (p == "/" and not h.startswith("mcp."))]
        # MCP URLs the company advertises (llms.txt, homepage, docs), e.g. api.githubcopilot.com/mcp
        advertised = re.findall(r"https://[a-z0-9.-]+(?:/[\w./-]*)?/(?:mcp|sse)\b/?|https://mcp\.[a-z0-9.-]+[\w./-]*",
                                llms_text[:50000] + " " + html + " " + docs_html)
        stem = d.split(".")[0]
        own = [u.rstrip(".") for u in dict.fromkeys(advertised)
               if (urlparse(u).hostname or "").endswith(d) or stem in (urlparse(u).hostname or "")]
        probes += own[:6]
        probes = list(dict.fromkeys(probes))
        async def probe(u):
            r = None
            for _ in range(2):
                try:
                    r = await self.c.post(u, json=MCP_INIT, timeout=self.timeout + 4, follow_redirects=True, headers={
                        "User-Agent": AGENT_UA, "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-06-18"})
                    break
                except Exception:  # noqa: BLE001
                    continue
            if r is None:
                return None
            if r.status_code == 401:
                m_ = re.search(r'resource_metadata="([^"]+)"', r.headers.get("www-authenticate", ""))
                if m_:
                    probe_meta[u] = m_.group(1)
            ct = r.headers.get("content-type", "")
            body = r.text[:2000] if "event-stream" not in ct else ""
            if r.status_code == 401 and "resource_metadata" in r.headers.get("www-authenticate", ""):
                return (u, "oauth")
            if r.status_code == 200 and ("event-stream" in ct or '"jsonrpc"' in body) and \
               ('"serverInfo"' in body or '"protocolVersion"' in body or "event-stream" in ct):
                return (u, "open")
            return None
        for hit in await asyncio.gather(*(probe(u) for u in probes)):
            if hit:
                mcp_hits.append(hit)
        # follow MCP OAuth: protected-resource metadata -> authorization server -> DCR?
        res["mcp_oauth_dcr"] = False
        for u, kind in mcp_hits:
            if kind != "oauth" or u not in probe_meta:
                continue
            prm = json_ok(await self.get(probe_meta[u]), ["authorization_servers", "resource"])
            servers = (prm or {}).get("authorization_servers") or []
            if prm:
                res["oauth_protected_resource"] = True
            for asu in servers[:1]:
                a = urlparse(asu)
                meta_urls = [f"{a.scheme}://{a.netloc}/.well-known/oauth-authorization-server{a.path.rstrip('/')}",
                             f"{a.scheme}://{a.netloc}/.well-known/oauth-authorization-server",
                             f"{a.scheme}://{a.netloc}/.well-known/openid-configuration"]
                for mu in meta_urls:
                    meta = json_ok(await self.get(mu), ["issuer", "authorization_endpoint"])
                    if meta:
                        res["oauth_metadata"] = True
                        if meta.get("registration_endpoint"):
                            res["mcp_oauth_dcr"] = res["oauth_dcr"] = True
                        break
            break
        res["mcp_endpoints"] = [u for u, _ in mcp_hits]
        res["mcp_auth"] = sorted({k for _, k in mcp_hits})
        res["mcp_docs_server"] = any(docs_origin and u.startswith(docs_origin) for u, _ in mcp_hits)
        res["mcp_product_server"] = any(not (docs_origin and u.startswith(docs_origin)) for u, _ in mcp_hits)

        # 8. Keyword signals across homepage + docs + llms.txt
        pricing_text = ""
        if res["link_pricing"]:
            pr = await self.get(res["link_pricing"], ua=BROWSER_UA)
            pricing_text = _visible_text(pr.text)[:30000] if self.ok(pr) else ""
        corpus = (text + " " + _visible_text(docs_html) + " " + llms_text[:20000] + " " + pricing_text).lower()
        for k, pat in KEYWORDS.items():
            res[k] = bool(re.search(pat, corpus))

        res["scan_seconds"] = round(time.time() - t0, 1)
        return res


def make_client(max_conn=24):
    # one client per domain, HTTP/1.1: a shared HTTP/2 pool fell over at high fan-out
    return httpx.AsyncClient(http2=False, verify=True, timeout=httpx.Timeout(8.0, pool=30.0),
                             limits=httpx.Limits(max_connections=max_conn, max_keepalive_connections=12))


async def scan_one(domain):
    async with make_client() as c:
        return await Scanner(c).scan(domain)


if __name__ == "__main__":
    import sys
    print(json.dumps(asyncio.run(scan_one(sys.argv[1])), indent=2))
