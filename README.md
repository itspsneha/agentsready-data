# AgentsReady data

**Can an AI agent get your API key?** This repo is the open dataset behind [agentsready.dev](https://agentsready.dev), the agent onboarding benchmark.

Most "agent readiness" checkers ask whether agents can *read* your site. This dataset asks whether an agent can *sign up*: how long it takes an AI agent to go from nothing to a working API key, and which human gates (email verification, phone OTP, card, KYC, sales) get in the way.

## What's here

| Path | What it is |
| --- | --- |
| `data/onboarding_benchmark.csv` | 64 platforms, traced by hand: time to key, no-human path, gates, main blocker, onboarding score /10 |
| `deepdives/companies/*.json` | One file per platform: the step-by-step key path, gates, agent-native auth options, MCP details, sources |
| `data/readiness_index.csv` | Automated readiness score (ARS v1, 0-100) and 20 pass/fail checks for 2,000 companies |
| `data/companies.csv` | The study set: 861 hand-picked, 700 YC, 439 API-first companies from APIs.guru |
| `scanner/` | The Python scanner and scorer used to build the index |

Snapshot: **11 October 2026**.

## Headline numbers

- **9 of 64** platforms let an agent reach a working key with no human at all. All 9 do it the same way: a sandbox or test key without an account, claimed by a human later.
- **56 of 64** stop the agent at email verification. Phone OTP (18), manual review (19), KYC (16) and a card before the first call (13) follow.
- Across 1,846 reachable companies, the average readiness score is **41/100**. 50% publish llms.txt, 20% run a product MCP server, and **14%** let agents self-register an OAuth client.
- Sites on hosted docs platforms (Mintlify, Fern, GitBook) have llms.txt **97%** of the time, against 56% for custom docs.

## Contribute

Gates change fast. If a platform added a sandbox, dropped phone verification or launched an MCP server, the benchmark should know.

1. Open an issue or a pull request that edits `deepdives/companies/<domain>.json`.
2. Include **evidence**: a link to official docs, or a short screen recording of the signup path. No credentials, ever.
3. A maintainer re-checks the path and updates `data/onboarding_benchmark.csv`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the schema and the gate definitions.

## Method, in short

- **Readiness index:** about 60 read-only HTTP requests per domain as a Claude-User agent: bot walls, robots.txt rules for 14 AI user-agents, llms.txt, markdown docs, OpenAPI, a live MCP `initialize` handshake, and OAuth discovery down to dynamic client registration. Scored on [ARS v1](https://agentsready.dev/standard).
- **Onboarding benchmark:** research agents read each platform's official docs and mapped the shortest path to a credential. Nobody signed up, so gates are as documented on the snapshot date.
- **Validation:** the index ranks the 64 hand-graded platforms with a Spearman correlation of 0.65. The scan undercounts MCP servers: it found 30 of the 53 the deep dives confirmed.

## License

Data: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Please cite "AgentsReady, agentsready.dev". Scanner code: MIT.
