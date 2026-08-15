## Agent skills

### Issue tracker

Tasks e PRDs são GitHub Issues em `gutkedu/hermes-chatbot-experiment`. Veja `docs/agents/issue-tracker.md`.

### Triage labels

O projeto usa `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` e `wontfix`. Veja `docs/agents/triage-labels.md`.

### Domain docs

Este é um repositório single-context, com `CONTEXT.md` na raiz e ADRs em `docs/adr/`. Veja `docs/agents/domain.md`.

### AWS Bedrock AgentCore skill

Use `.codex/skills/aws-bedrock-agentcore-skill/SKILL.md` sempre que uma tarefa envolver
construir, arquitetar, configurar, testar, publicar, proteger, monitorar ou depurar agentes
de IA na AWS, mesmo quando o usuário não mencionar explicitamente o serviço. Isso inclui,
em especial:

- Strands Agents e Amazon Bedrock (Converse, Guardrails e Knowledge Bases/RAG);
- Bedrock AgentCore Runtime, Memory, Gateway, Identity, Browser/Code Interpreter e
  Observability;
- IAM, custos, quotas, Terraform/CDK e deploy de agentes na AWS.

Comece pelo `SKILL.md` e abra somente as referências necessárias ao caso de uso. Para detalhes
que mudam com frequência, como modelos, preços, quotas e maturidade GA/Preview, revalide as
fontes oficiais indicadas pela própria skill antes de recomendar uma solução.
