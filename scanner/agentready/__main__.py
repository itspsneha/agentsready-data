"""agentready CLI.

  python -m agentready check stripe.com [--agent] [--json]
  python -m agentready serve [--port 8787]
"""
import argparse, asyncio, json, os, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .scan import scan_one
from .score import CHECKS, PILLARS, score

HERE = os.path.dirname(__file__)
BENCH = os.path.join(HERE, "..", "results", "scored.jsonl")
DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})+$")


def clean_domain(raw):
    d = raw.strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].removeprefix("www.")
    if not DOMAIN_RE.match(d):
        raise ValueError(f"not a domain: {raw!r}")
    return d


def benchmark_scores():
    if not os.path.exists(BENCH):
        return []
    return sorted(json.loads(l)["score"] for l in open(BENCH) if l.strip())


def check(domain, agent=False):
    d = clean_domain(domain)
    r = asyncio.run(scan_one(d))
    s = score(r)
    bench = benchmark_scores()
    if bench:
        s["percentile"] = round(100 * sum(x < s["score"] for x in bench) / len(bench))
        s["benchmark_n"] = len(bench)
    out = {"domain": d, "scan": r, "result": s}
    if agent:
        from .audit import run_audit
        out["audit"] = run_audit(d, r)
    return out


def print_report(out):
    s, r = out["result"], out["scan"]
    print(f"\n  {out['domain']}  ARS {s['score']}/100  {s['level']} {s['level_name']}", end="")
    if "percentile" in s:
        print(f"  (beats {s['percentile']}% of {s['benchmark_n']} benchmarked companies)", end="")
    print("\n")
    for pl in PILLARS:
        print(f"  {pl:<11} {s['pillars'][pl]:>3}/{s['pillar_max'][pl]}")
    print()
    for cid, pl, pts, label, _ in CHECKS:
        mark = "PASS" if s["passes"][cid] else "fail"
        print(f"  [{mark}] {pts:>2}  {label}")
    print("\n  Top fixes:")
    for f in s["top_fixes"]:
        print(f"   +{f['points']:>2}  {f['check']}: {f['fix']}")
    if r.get("mcp_endpoints"):
        print("\n  MCP endpoints found:", ", ".join(r["mcp_endpoints"]))
    if out.get("audit"):
        a = out["audit"]
        print("\n  Agent audit:", json.dumps(a, indent=2)[:3000])
    print()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, open(os.path.join(HERE, "web.html")).read(), "text/html; charset=utf-8")
        if u.path == "/api/rubric":
            return self._send(200, json.dumps([dict(zip(["id", "pillar", "points", "label", "fix"], c)) for c in CHECKS]),
                              "application/json")
        if u.path == "/api/check":
            q = parse_qs(u.query)
            try:
                out = check(q.get("domain", [""])[0], agent=q.get("agent", ["0"])[0] == "1")
            except ValueError as e:
                return self._send(400, json.dumps({"error": str(e)}), "application/json")
            except Exception as e:  # noqa: BLE001
                return self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}), "application/json")
            return self._send(200, json.dumps(out), "application/json")
        self._send(404, "not found", "text/plain")

    def log_message(self, fmt, *args):
        sys.stderr.write("  " + fmt % args + "\n")


def main():
    p = argparse.ArgumentParser(prog="agentready")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("domain"); c.add_argument("--agent", action="store_true")
    c.add_argument("--json", action="store_true")
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=8787)
    a = p.parse_args()
    if a.cmd == "check":
        out = check(a.domain, a.agent)
        print(json.dumps(out, indent=2)) if a.json else print_report(out)
    else:
        print(f"Agent-readiness checker on http://localhost:{a.port}")
        ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


main()
