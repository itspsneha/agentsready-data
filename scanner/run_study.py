"""Scan the whole company set. Resumable: appends JSONL, skips domains already done."""
import asyncio, csv, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from agentready.scan import scan_one

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "results", "scan.jsonl")
CONCURRENCY = int(os.environ.get("CONC", 60))
RETRY = os.environ.get("RETRY") == "1"  # rescan rows that came back unreachable
PER_DOMAIN_TIMEOUT = 120


async def main():
    companies = list(csv.DictReader(open(os.path.join(ROOT, "data", "companies.csv"))))
    done, prior = set(), []
    if os.path.exists(OUT):
        prior = [json.loads(l) for l in open(OUT) if l.strip()]
        done = {r["domain"] for r in prior if r.get("reachable") or not RETRY}
        if RETRY:  # rewrite without the unreachable rows; they get rescanned
            with open(OUT, "w") as f:
                for r in prior:
                    if r["domain"] in done:
                        f.write(json.dumps(r) + "\n")
    todo = [c for c in companies if c["domain"] not in done]
    print(f"{len(todo)} to scan ({len(done)} done)", flush=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    t0, n = time.time(), 0
    with open(OUT, "a") as out:

        async def one(c):
            nonlocal n
            async with sem:
                try:
                    r = await asyncio.wait_for(scan_one(c["domain"]), PER_DOMAIN_TIMEOUT)
                except Exception as e:  # noqa: BLE001
                    r = {"domain": c["domain"], "reachable": False, "errors": [f"scan failed: {type(e).__name__}"]}
                r.update({"name": c["name"], "category": c["category"], "source": c["source"]})
                out.write(json.dumps(r) + "\n"); out.flush()
                n += 1
                if n % 50 == 0:
                    print(f"{n}/{len(todo)} in {time.time()-t0:.0f}s", flush=True)

        await asyncio.gather(*(one(c) for c in todo))
    print("done", time.time() - t0)


asyncio.run(main())
