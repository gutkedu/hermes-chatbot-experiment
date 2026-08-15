# Issue tracker: GitHub

Issues e PRDs vivem em GitHub Issues no repositório `gutkedu/hermes-chatbot-experiment`.

Use o `gh` para criar, consultar, comentar, rotular e fechar issues. O repositório pode ser inferido pelo remote quando o comando é executado dentro deste clone.

## Convenções

- Criar: `gh issue create --title "..." --body "..."`.
- Consultar com comentários: `gh issue view <number> --comments`.
- Listar: `gh issue list --state open` com os filtros necessários.
- Comentar: `gh issue comment <number> --body "..."`.
- Aplicar ou remover labels: `gh issue edit <number> --add-label "..."` ou `--remove-label "..."`.
- Fechar: `gh issue close <number> --comment "..."`.

Quando uma skill disser “publish to the issue tracker”, crie uma GitHub Issue. Quando disser “fetch the relevant ticket”, consulte a issue e seus comentários.
