# Hermes AgentCore Product Support Chatbot

## Objetivo

Construir um chatbot web autenticado para atendimento de um produto. O agente será executado com Hermes Agent no Amazon Bedrock AgentCore Runtime, usará modelos do Amazon Bedrock e, em uma evolução posterior, responderá com base na documentação oficial do produto por meio de Amazon Bedrock Knowledge Bases e Amazon S3 Vectors.

O desenvolvimento começa a partir de um snapshot completo e rastreável do sample oficial [`aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore`](https://github.com/aws-samples/sample-host-hermesagent-on-amazon-bedrock-agentcore), preservando licença e atribuição. A revisão de referência aprovada para o bootstrap é `b9988e3ceaacf57da4305c7f8f32cedc3e3d80ce`, obtida da branch `main` em 15 de agosto de 2026.

## Escopo e estratégia

O trabalho será entregue em fatias verticais pequenas. O primeiro incremento apenas importa e valida o sample completo, inclusive a Fase 4 opcional, sem criar recursos na AWS. O canal-alvo do produto será o navegador; Telegram, Slack, Discord, Feishu e WeChat permanecem inicialmente como parte do baseline importado, não como requisitos do MVP.

As adaptações para web, autenticação e RAG serão feitas em incrementos separados. Essa ordem permite distinguir problemas herdados do sample de problemas introduzidos pelo produto.

## Arquitetura-alvo

```text
Browser
  -> Amazon Cognito
  -> Amazon API Gateway
  -> Backend for Frontend (BFF)
  -> Hermes Agent no Amazon Bedrock AgentCore Runtime
       -> modelo no Amazon Bedrock
       -> Amazon Bedrock Knowledge Base
            -> bucket S3 de documentos
            -> índice no Amazon S3 Vectors
```

O navegador autentica o usuário no Cognito e envia o token ao BFF. O BFF valida a identidade, aplica limites de uso, deriva uma sessão AgentCore isolada por usuário e transmite a resposta ao navegador. Credenciais AWS nunca são enviadas ao cliente.

O BFF é a fronteira estável do produto. Ele evita acoplamento do frontend aos contratos internos do AgentCore e concentra autenticação, autorização, rate limiting, tradução de erros e observabilidade.

## Componentes

### Aplicação web

Oferece login via Cognito e uma interface de chat com resposta progressiva, estado de carregamento, fontes consultadas e mensagens de erro recuperáveis. O primeiro MVP é voltado a clientes autenticados; não haverá acesso anônimo.

### BFF de conversação

Valida tokens Cognito, relaciona a identidade do usuário a uma sessão do AgentCore, encaminha mensagens e normaliza eventos de streaming. Também impede acesso cruzado ao histórico de outros usuários e registra métricas sem persistir conteúdo sensível desnecessariamente.

### Hermes no AgentCore

Executa o agente e usa os modelos Bedrock por credenciais IAM. O baseline mantém a ponte e a infraestrutura do sample. As adaptações futuras devem preservar a separação entre o runtime do agente e os canais de entrada.

### Knowledge Base e armazenamento vetorial

A documentação bruta do produto fica em um bucket S3 de propósito geral. O Bedrock Knowledge Bases realiza parsing, chunking e geração de embeddings. Os vetores ficam em um bucket e índice do S3 Vectors. A primeira versão usa busca semântica e retorna citações para os documentos de origem.

### Pipeline de conteúdo

No MVP, um administrador envia arquivos PDF ou Markdown pelo Console da AWS ou CLI. A sincronização da fonte S3 com a Knowledge Base é iniciada explicitamente e seu status pode ser inspecionado. Uma interface administrativa e automação baseada em eventos ficam fora do escopo inicial.

## Fluxos principais

### Conversa sem RAG

1. O cliente autentica no Cognito.
2. A aplicação envia a mensagem e o token ao BFF.
3. O BFF valida a identidade e invoca a sessão correta no AgentCore.
4. O Hermes produz uma resposta pelo modelo Bedrock.
5. O BFF transmite os eventos normalizados ao navegador.

### Conversa fundamentada em RAG

1. O Hermes consulta a Knowledge Base com a pergunta e o contexto permitido.
2. A Knowledge Base recupera chunks semanticamente próximos no S3 Vectors.
3. O agente formula a resposta usando os chunks recuperados.
4. A aplicação exibe a resposta e as citações retornadas.
5. Quando não há evidência suficiente, o agente informa a limitação em vez de inventar informação do produto.

### Publicação de documentos

1. Um administrador envia um documento válido ao bucket S3 de origem.
2. O administrador inicia a sincronização da data source.
3. O Bedrock processa o documento e atualiza o índice no S3 Vectors.
4. O estado da ingestão e eventuais falhas ficam disponíveis para diagnóstico.

## Segurança e isolamento

- O Cognito é obrigatório para acessar o chat.
- Cada identidade possui sessão isolada; um usuário não pode ler ou continuar a sessão de outro.
- IAM segue privilégio mínimo entre BFF, AgentCore, Knowledge Base, buckets e índice vetorial.
- Buckets bloqueiam acesso público e usam criptografia em repouso.
- Segredos, IDs pessoais de conta e credenciais não entram no repositório.
- Logs evitam tokens, credenciais e conteúdo sensível; identificadores são correlacionáveis sem expor dados pessoais desnecessários.
- Limites de requisições, tokens e custo são aplicados antes de abrir o serviço a usuários reais.

## Tratamento de erros

- Token ausente, inválido ou expirado produz `401`; falta de autorização produz `403`.
- Indisponibilidade do AgentCore ou Bedrock gera uma mensagem recuperável e um identificador de correlação.
- Falha ou timeout na recuperação não deve ser mascarado como uma resposta fundamentada.
- Ausência de resultados relevantes produz uma resposta explícita de insuficiência de evidência.
- Falhas de ingestão permanecem observáveis e não substituem silenciosamente a versão anteriormente indexada.
- O frontend permite nova tentativa sem duplicar mensagens ou criar sessões inconsistentes.

## Estratégia de testes

O bootstrap executa os testes existentes do sample e `cdk synth` sem deploy. As fatias seguintes adicionam testes unitários e de contrato para autenticação, autorização, mapeamento de sessão e eventos de streaming. Testes de integração verificam invocação do AgentCore, recuperação com e sem resultados, citações e falhas de ingestão. Testes end-to-end em ambiente AWS validam login, conversa e isolamento entre dois usuários antes da liberação do MVP.

## Entregas planejadas

1. Importar e validar o sample completo como baseline reproduzível.
2. Entregar um chat web autenticado que percorra Cognito, BFF e AgentCore de ponta a ponta.
3. Provisionar uma Knowledge Base com fonte S3 e armazenamento no S3 Vectors.
4. Entregar o fluxo manual de publicação e sincronização de documentos com estado observável.
5. Integrar o Hermes à recuperação e exibir respostas com citações e fallback seguro.
6. Adicionar avaliação do RAG, isolamento, limites de custo e observabilidade operacional.

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
- Tela administrativa para upload de documentos.
- Ingestão automática baseada em eventos.
- Busca híbrida; S3 Vectors será usado inicialmente para busca semântica.
- Voz, canais de mensageria e automação do navegador pelo agente.
