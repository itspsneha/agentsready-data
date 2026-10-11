"""Score every scanned domain and print the aggregates used in the PRD."""
import collections, csv, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agentready.score import CHECKS, LEVELS, score

ROOT = os.path.join(os.path.dirname(__file__), "..")
rows = {}
for l in open(os.path.join(ROOT, "results", "scan.jsonl")):
    if l.strip():
        r = json.loads(l); rows[r["domain"]] = r
guru = {r["domain"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "companies.csv"))) if r["source"] == "apis_guru"}

GROUP = {"ai_models": "AI & ML", "devtools_infra": "Devtools & infra", "payments_fintech": "Payments & fintech",
         "comms_saas": "Comms & SaaS", "ecommerce_consumer": "Consumer & commerce", "maps_data_misc": "Data, security & logistics",
         "enterprise_bigco": "Enterprise & big co", "healthcare_edu_hr": "Health, edu & HR", "apis_guru": "API-first (APIs.guru)"}
def group(r):
    return GROUP.get(r["category"], "YC startups" if r["source"] == "yc" else r["category"])

scored = []
for d, r in rows.items():
    r["in_apis_guru"] = d in guru
    s = score(r)
    scored.append({**{k: r.get(k) for k in ("domain", "name", "category", "source")}, "group": group(r),
                   "reachable": r.get("reachable"), "score": s["score"], "level": s["level"], **s["pillars"],
                   **{f"c_{k}": v for k, v in s["passes"].items()},
                   "llms_txt": r.get("llms_txt"), "mcp_endpoints": " ".join(r.get("mcp_endpoints") or []),
                   "openapi_url": r.get("openapi_url"), "docs_url": r.get("docs_url"), "docs_platform": r.get("docs_platform"),
                   "agent_blocked": r.get("agent_blocked"), "robots_blocked_bots": " ".join(r.get("robots_blocked_bots") or []),
                   "robots_blocks_training": r.get("robots_blocks_training"), "oauth_dcr": r.get("oauth_dcr")})
with open(os.path.join(ROOT, "results", "scored.jsonl"), "w") as f:
    for s in scored:
        f.write(json.dumps(s) + "\n")
with open(os.path.join(ROOT, "results", "scored.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(scored[0].keys())); w.writeheader(); w.writerows(scored)

live = [s for s in scored if s["reachable"]]
N = len(live)
pct = lambda xs: round(100 * sum(1 for x in xs if x) / max(1, len(xs)), 1)
print(f"scanned {len(scored)}, reachable {N}")
print("mean score", round(sum(s["score"] for s in live) / N, 1), "median", sorted(s["score"] for s in live)[N // 2])
print("levels", collections.Counter(s["level"] for s in live).most_common())
print("\nAdoption (% of reachable):")
for cid, *_ in CHECKS:
    print(f"  {cid:<28} {pct([s['c_'+cid] for s in live])}")
print("  agent_blocked              ", pct([s["agent_blocked"] for s in live]))
print("  robots blocks >=1 training ", pct([(s["robots_blocks_training"] or 0) > 0 for s in live]))
print("  robots blocks GPTBot       ", pct(["GPTBot" in (s["robots_blocked_bots"] or "") for s in live]))
print("  robots blocks ClaudeBot    ", pct(["ClaudeBot" in (s["robots_blocked_bots"] or "") for s in live]))
print("  any mcp endpoint           ", pct([bool(s["mcp_endpoints"]) for s in live]))

print("\nBy group: n, mean, llms, md, openapi, mcp_product, mcp_any, dcr, blocked, L3+")
for g in sorted({s["group"] for s in live}):
    G = [s for s in live if s["group"] == g]
    print(f"  {g:<28} {len(G):>4} {sum(s['score'] for s in G)/len(G):5.1f} {pct([s['c_llms_txt'] for s in G]):5} "
          f"{pct([s['c_markdown_docs'] for s in G]):5} {pct([s['c_openapi'] for s in G]):5} {pct([s['c_mcp_product'] for s in G]):5} "
          f"{pct([bool(s['mcp_endpoints']) for s in G]):5} {pct([s['c_oauth_dcr'] for s in G]):5} {pct([s['agent_blocked'] for s in G]):5} "
          f"{pct([s['level'] in ('L3','L4') for s in G]):5}")

print("\nDocs platform -> llms.txt rate")
for p, n in collections.Counter(s["docs_platform"] for s in live if s["docs_url"]).most_common(12):
    G = [s for s in live if s["docs_platform"] == p and s["docs_url"]]
    print(f"  {str(p):<12} {n:>4}  llms {pct([s['c_llms_txt'] for s in G])}  mcp {pct([bool(s['mcp_endpoints']) for s in G])}")

print("\nTop 30")
for s in sorted(live, key=lambda s: -s["score"])[:30]:
    print(f"  {s['score']:>3} {s['level']} {s['domain']:<24} {s['group']}")
print("\nScore histogram (10-pt bins)")
h = collections.Counter(min(s["score"] // 10, 9) for s in live)
for b in range(10):
    print(f"  {b*10:>2}-{b*10+9:<3} {h[b]}")
