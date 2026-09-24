# Agent Boundaries

**Status: implemented (Phase 7).** [`app/agents/context_builder.py`](../app/agents/context_builder.py) +
[`app/agents/investigator.py`](../app/agents/investigator.py). Verified in
[`tests/test_agents/test_boundary_enforcement.py`](../tests/test_agents/test_boundary_enforcement.py)
and [`tests/test_agents/test_context_builder.py`](../tests/test_agents/test_context_builder.py),
against `FakeLLMClient` (zero real API calls) — see the scope note below
for what this proves today versus what a later phase still needs to
prove once real persisted state exists.

Agent independence is a technically enforced property, not an instruction
("Agent A is told not to see Agent B's output"). See
[ADR-007](decisions/ADR-007-agent-context-isolation.md) for the full
rationale.

## The invariant, as actually built

`build_context(documents, domain)` (`app/agents/context_builder.py`) is
the **entire** isolation mechanism — deliberately smaller than a
"restricted query surface with allowlists" implies. It's a single filter
over a plain list, with a signature that has no parameter for another
agent's output, another agent's run id, or any prior conclusion — not
because such data is access-controlled, but because it was never wired in
as an input to context construction at all. `run_investigator()`
(`app/agents/investigator.py`) calls this function and only this function
to obtain its documents; there is no second code path to a case's
documents anywhere else in the module.

**Verification:**
`test_investigator_context_has_no_cross_agent_data_even_when_available`
runs the security investigator first with a scripted response containing
a deliberately unique marker in its findings, confirms that marker is
genuinely present in the security result (so the test isn't trivially
passing for the wrong reason), then runs the privacy investigator against
the same document set and asserts the marker appears nowhere in its
prompt — system or user message. A companion test
(`test_run_investigator_signature_has_no_path_to_another_agents_output`)
asserts this structurally too: `run_investigator`'s parameters are
exactly `{client, model, agent_type, documents, max_tokens, max_attempts}`,
nothing else. A third test confirms the guarantee holds regardless of
which investigator runs first.

**Honest scope note:** this phase has no persisted `AgentRun`/`Finding`
data — both investigators are pure functions, same shape as the Phase 6
baseline, with no database wiring yet. What's proven above is that
(1) there is no code path from one agent's output to another's context,
and (2) even when one agent's real, distinctive output exists in the
same scope the other agent's context is being built in, it doesn't leak
in. When a real orchestrator later persists Finding rows to the database,
that boundary needs its own proof in that shape — a context builder
querying the DB with no join to another agent's rows, tested by seeding
that data first and confirming it's still unreachable, the same pattern
used for Phase 4's append-only trigger tests. This is the pattern to
follow then, not a substitute for doing it.

## Per-agent boundary specification

| Boundary | Security Investigator | Privacy/AI-Gov Investigator |
|---|---|---|
| Allowed documents | `domain="security"` or `"both"` only (`build_context`) | `domain="privacy_ai_governance"` or `"both"` only |
| Allowed DB records | None yet — no DB wiring this phase | Same |
| Tools/APIs | None (ADR-003) | None (ADR-003) |
| Output fields | Same shared schema as the baseline (`app/agents/schema.py`) | Same |
| Forbidden data | The other investigator's output — not reachable, not just disallowed (see invariant above) | Same |
| Execution identity | Own `AgentResult`, own token/cost accounting per call | Same |
| Persistence | None — returns structured output; a future orchestrator would write it | Same |
| Empty domain | Zero documents for this domain → returns immediately, no API call made (found while sizing the real Phase 7 evaluation run — 9 of 36 case/investigator pairs across the 18 real cases have no documents in scope) | Same |

Both agents are pure functions: context in, schema-validated JSON out. No
persistence or side effects in this phase — see the scope note above.

## Re-investigation preserves independence too (Phase 8, not yet built)

When a conflict triggers the bounded re-investigation round (max 1, decision
#13), the re-invoked agent is given a **neutral, domain-scoped follow-up** —
e.g. "re-examine the retention-period claim, with particular attention to
[document/section]" — never "Agent B concluded X, do you agree?" Exposing
the other agent's conclusion would reintroduce the anchoring risk that
independence exists to prevent. The orchestrator reformulates disagreements;
it never relays them verbatim.
