"""Agent mode: Claude researches the onboarding path (time to key, human gates, MCP) for a domain.

Passive scans can't see signup gates, so this layer reads the docs the way an agent would.
Requires Anthropic credentials (ANTHROPIC_API_KEY or an `ant auth login` profile).
"""
import json, re

import anthropic

MODEL = "claude-opus-5-5"
TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 15},
]

PROMPT = """You are auditing how agent-friendly {domain} is. Imagine you are an AI coding agent asked by a user
to integrate {domain}'s product. Research (official docs first) and do NOT sign up or submit any forms.

Automated scan results you can build on (verify anything surprising):
{scan}

Answer:
1. fastest_key_path: minimum ordered steps from nothing to a working API key/credential.
2. human_gates: subset of [email_verification, phone_otp, captcha, credit_card_required, kyc_business_verification,
   domain_verification, sales_contact, waitlist, manual_approval, admin_approval, partner_application, 2fa].
3. agent_native_auth: object with booleans cli_device_login, oauth_dcr_for_mcp, key_management_api, scoped_keys,
   test_or_sandbox_mode, free_credits, each with a short evidence string in agent_native_auth_evidence.
4. mcp: {{"official": bool, "remote_url": str|null, "auth": "oauth"|"api_key"|"none"|null, "local_package": str|null,
   "kind": "product"|"docs"|"both"|null}}.
5. time_to_first_call_minutes (human-assisted agent) and fully_autonomous_possible (bool).
6. onboarding_grade: A (agent can do it end to end), B (one human click/approval), C (several human gates),
   D (sales/partner approval or KYC before any call), F (no public API).
7. top_recommendations: 3 specific changes {domain} should make, most impactful first.
8. sources: URLs you actually opened.

Finish with ONLY a JSON object with exactly those keys (no prose after it)."""


def run_audit(domain, scan_result, client=None):
    client = client or anthropic.Anthropic()
    slim = {k: v for k, v in scan_result.items() if k not in ("title", "errors")}
    messages = [{"role": "user", "content": PROMPT.format(domain=domain, scan=json.dumps(slim, indent=1))}]
    final = None
    for _ in range(6):  # resume on pause_turn (long server-tool turns)
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            tools=TOOLS,
            messages=messages,
        ) as stream:
            final = stream.get_final_message()
        if final.stop_reason == "pause_turn":
            messages = messages[:1] + [{"role": "assistant", "content": final.content}]
            continue
        break
    if final.stop_reason == "refusal":
        return {"error": "audit declined by model"}
    text = "".join(b.text for b in final.content if b.type == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"error": "no JSON in audit", "raw": text[-2000:]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"error": "bad JSON in audit", "raw": m.group(0)[-2000:]}
