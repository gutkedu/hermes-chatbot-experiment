# Remove Knowledge Base and RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the Hermes experiment to direct Bedrock chat while retaining authenticated web chat, AgentCore Runtime, Memory, persistent skills, and generic Guardrails.

**Architecture:** Remove the dedicated Knowledge Base CDK stack and its runtime retrieval dependency. The Hermes entrypoint will assemble Memory and persisted-skill context, then stream a direct Bedrock response. The BFF and browser contract will carry only chat deltas and lifecycle/error events; source envelopes and citation rendering will disappear.

**Tech Stack:** Python, AWS CDK, Bedrock AgentCore Runtime, AgentCore Memory, Node.js Lambda BFF, browser ES modules, pytest, Node test runner.

---

### Task 1: Remove Knowledge Base infrastructure and deployment plumbing

**Files:**
- Delete: `stacks/knowledge_base_stack.py`
- Modify: `app.py`, `stacks/runtime_stack.py`, `scripts/deploy.sh`, `scripts/teardown.sh`
- Delete: `scripts/ingest_knowledge_base.sh`, `knowledge-base/lumen-desk-lamp.md`
- Test: `tests/test_serverless_deployment.py`
- Delete: `tests/test_knowledge_base_stack.py`

- [x] Remove the stack import, instantiation, dependency, runtime constructor arguments, retrieval IAM policy, Knowledge Base environment variable, and Knowledge Base deployment/teardown commands.
- [x] Update synthesis assertions to require only the active web/runtime stacks and assert no Knowledge Base/vector/retrieval configuration remains.
- [x] Run the focused CDK/deployment tests and synthesis.

### Task 2: Make the active Hermes runtime direct-chat only

**Files:**
- Modify: `app/hermes/main.py`, `app/hermes/Dockerfile`
- Delete: `app/hermes/retrieval.py`
- Test: `tests/test_runtime_persistence.py`
- Delete: `tests/test_retrieval.py`

- [x] Add a failing runtime test proving a chat request streams without `KNOWLEDGE_BASE_ID` or retrieval calls.
- [x] Remove retrieval imports, readiness gates, evidence-only prompts, source events, and retrieval-specific fallback text while preserving Memory, skills, workspace restore/save, and safe failure handling.
- [x] Remove retrieval from the Docker build context.
- [x] Run the focused runtime tests.

### Task 3: Remove RAG fields from the BFF and browser contract

**Files:**
- Modify: `lambda/web_chat/src/agentcore.mjs`, `lambda/web_chat/src/route.mjs`, `web/app.mjs`, `web/src/state.mjs`
- Test: `lambda/web_chat/test/agentcore.test.mjs`, `lambda/web_chat/test/route.test.mjs`, `web/tests/state.test.mjs`

- [x] Add failing tests showing source envelopes are ignored and the browser state has no source branch.
- [x] Keep delta parsing and lifecycle/error streaming, but stop translating source envelopes into SSE events or rendering citations.
- [x] Run BFF and browser tests.

### Task 4: Update active documentation and verify the simplified architecture

**Files:**
- Modify: `README.md`, `docs/authenticated-web-chat-runbook.md`

- [x] Describe direct Bedrock chat, Memory, and persistent skills as the active architecture.
- [x] Remove active ingestion, vector-store, Knowledge Base, citation, and retrieval-failure instructions while leaving upstream historical material untouched.
- [x] Run repository-wide searches for active RAG references, all Python/Node tests, and CDK synthesis.
