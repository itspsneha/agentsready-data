# Contributing

Thanks for helping keep the benchmark honest.

## Rules

- **Evidence or it didn't happen.** Link the official doc, changelog or a screen recording that shows the gate (or its removal).
- **Never include credentials**, API keys, OTPs, or personal data, even redacted screenshots of dashboards with keys.
- **One platform per pull request**, so reviews stay quick.
- Platform owners are welcome. Please say so in the PR; it helps us prioritise.

## Deep-dive schema (`deepdives/companies/<domain>.json`)

| Field | Meaning |
| --- | --- |
| `company`, `domain` | Name and primary domain |
| `key_path` | Ordered steps from "no account" to a working credential |
| `human_gates` | Gates an agent can't clear alone (see below), with notes |
| `agent_native_auth` | CLI login, OAuth self-registration (DCR/CIMD), key API, scoped keys, sandbox/test keys, free credits, claimable no-account sandbox, `auth.md` |
| `mcp` | Official MCP server: remote URL, transport, auth, product vs docs |
| `docs_for_agents` | llms.txt, llms-full.txt, markdown pages, OpenAPI |
| `time_to_first_call_minutes` | Minutes for an agent doing every step, with a human clearing only the gates |
| `fully_autonomous_possible` | `true` if an agent can reach a working (test) credential with no human |
| `agent_friendliness_score` | 1-10 with a one-line reason |
| `sources` | URLs actually opened |

## Gates

`email_verification`, `phone_otp`, `captcha`, `credit_card_required`, `kyc_business_verification`, `domain_verification`, `sales_contact`, `waitlist`, `manual_approval`, `admin_approval`, `partner_application`, `mandatory_2fa`.

A gate counts only if it sits on the **fastest** path to a first working credential. A gate that applies only to live or production use goes in the notes, not the list.
