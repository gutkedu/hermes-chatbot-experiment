# Hermes AgentCore Product Support Chatbot

## Objetivo

Construir um chatbot web autenticado para atendimento de um produto. O agente será executado com Hermes Agent no Amazon Bedrock AgentCore Runtime, usará modelos do Amazon Bedrock e responderá diretamente às mensagens. AgentCore Memory e skills persistentes fornecem personalização e estado entre sessões; este experimento não provisiona ou consulta uma base de conhecimento.

O desenvolvimento começa a partir de um snapshot completo e rastreável do sample oficial [`aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore`](https://github.com/aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore), preservando licença e atribuição. A revisão de referência aprovada para o bootstrap é `b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce`, obtida da branch `main` em 15 de agosto de 2026.

## Escopo e estratégia

O trabalho será entregue em fatias verticais pequenas. O primeiro incremento apenas importa e valida o sample completo, inclusive a Fase 4 opcional, sem criar recursos na AWS. O canal-alvo do produto será o navegador; Telegram, Slack, Discord, Feishu e WeChat permanecem inicialmente como parte do baseline importado, não como requisitos do MVP.

As adaptações para web, autenticação, Memory e skills persistentes são entregues em incrementos separados. A arquitetura de conversa permanece direta para manter o experimento pequeno e distinguir problemas herdados do sample dos problemas introduzidos pelo produto.

## Arquitetura-alvo

```text
Browser
  -> Amazon Cognito
  -> Amazon API Gateway
  -> Backend for Frontend (BFF)
  -> Hermes Agent no Amazon Bedrock AgentCore Runtime
       -> modelo no Amazon Bedrock
       -> AgentCore Memory
       -> workspace persistente e skills
```

O navegador autentica o usuário no Cognito e envia o token ao BFF. O BFF valida a identidade, aplica limites de uso, deriva uma sessão AgentCore isolada por usuário e transmite a resposta ao navegador. Credenciais AWS nunca são enviadas ao cliente.

O BFF é a fronteira estável do produto. Ele evita acoplamento do frontend aos contratos internos do AgentCore e concentra autenticação, autorização, rate limiting, tradução de erros e observabilidade.

## Componentes

### Aplicação web

Oferece login via Cognito e uma interface de chat com resposta progressiva, estado de carregamento e mensagens de erro recuperáveis. O primeiro MVP é voltado a clientes autenticados; não haverá acesso anônimo.

### BFF de conversação

Valida tokens Cognito, relaciona a identidade do usuário a uma sessão do AgentCore, encaminha mensagens e normaliza eventos de streaming. Também impede acesso cruzado ao histórico de outros usuários e registra métricas sem persistir conteúdo sensível desnecessariamente.

### Hermes no AgentCore

Executa o agente e usa os modelos Bedrock por credenciais IAM. O baseline mantém a ponte e a infraestrutura do sample. As adaptações futuras devem preservar a separação entre o runtime do agente e os canais de entrada.

### Estado e personalização

O AgentCore Memory mantém eventos conversacionais e extrai preferências do
usuário e resumos de sessão. O workspace persistente mantém arquivos de estado
do Hermes e skills em Markdown delimitado; esses arquivos são instruções não
confiáveis e nunca são importados ou executados como código.

## Fluxos principais

### Conversa direta

1. O cliente autentica no Cognito.
2. A aplicação envia a mensagem e o token ao BFF.
3. O BFF valida a identidade e invoca a sessão correta no AgentCore.
4. O Hermes recupera, quando disponível, contexto explicitamente não confiável do
   Memory e das skills persistentes.
5. O Hermes produz uma resposta pelo modelo Bedrock.
6. O BFF transmite apenas os eventos normalizados de ciclo de vida, erro e delta
   ao navegador.

## Segurança e isolamento

- O Cognito é obrigatório para acessar o chat.
- Cada identidade possui sessão isolada; um usuário não pode ler ou continuar a sessão de outro.
- IAM segue privilégio mínimo entre BFF, AgentCore, Memory e workspace bucket.
- Buckets bloqueiam acesso público e usam criptografia em repouso.
- Segredos, IDs pessoais de conta e credenciais não entram no repositório.
- Logs evitam tokens, credenciais e conteúdo sensível; identificadores são correlacionáveis sem expor dados pessoais desnecessários.
- Limites de requisições, tokens e custo são aplicados antes de abrir o serviço a usuários reais.

## Tratamento de erros

- Token ausente, inválido ou expirado produz `401`; falta de autorização produz `403`.
- Indisponibilidade do AgentCore ou Bedrock gera uma mensagem recuperável e um identificador de correlação.
- Falhas ou timeout de Memory não interrompem a resposta direta; o runtime registra
  apenas detalhes seguros e pode tentar novamente em uma invocação posterior.
- O frontend permite nova tentativa sem duplicar mensagens ou criar sessões inconsistentes.

## Estratégia de testes

O bootstrap executa os testes existentes do sample e `cdk synth` sem deploy. As fatias seguintes adicionam testes unitários e de contrato para autenticação, autorização, mapeamento de sessão, Memory, skills e eventos de streaming. Testes de integração verificam invocação direta do AgentCore sem configuração de base de conhecimento. Testes end-to-end em ambiente AWS validam login, conversa e isolamento entre dois usuários antes da liberação do MVP.

## Entregas planejadas

1. Importar e validar o sample completo como baseline reproduzível.
2. Entregar um chat web autenticado que percorra Cognito, BFF e AgentCore de ponta a ponta.
3. Provisionar AgentCore Memory e workspace persistente com skills seguras.
4. Integrar o Hermes à personalização e ao estado persistente sem interromper o chat direto.
5. Adicionar isolamento, limites de custo e observabilidade operacional.

## Primeiro incremento: baseline reproduzível

O primeiro incremento importa o snapshot completo do sample, preserva sua licença e registra a revisão upstream. Ele documenta instalação e verificações locais, fixa ou restringe versões de dependências e não exige credenciais AWS para testes e síntese da infraestrutura. Nenhum deploy faz parte desse incremento.

Critérios de aceite:

- O snapshot completo, inclusive a Fase 4, está no repositório.
- A origem, revisão e data da importação estão registradas.
- Licença e atribuições do upstream estão preservadas.
- Dependências Python e Node possuem versões reproduzíveis ou restrições explícitas.
- O setup local e os pré-requisitos estão documentados.
- Os testes existentes passam.
- `cdk synth` passa sem realizar deploy ou criar recursos AWS.
- Não há segredos, IDs pessoais de conta ou configuração local commitados.
- O README declara o navegador como canal-alvo e separa baseline de adaptações futuras.

## Fora do escopo inicial

- Deploy de produção no primeiro incremento.
- Acesso anônimo ao chatbot.
- Knowledge Bases, RAG, armazenamento vetorial e ingestão de documentos.
- Voz, canais de mensageria e automação do navegador pelo agente.
