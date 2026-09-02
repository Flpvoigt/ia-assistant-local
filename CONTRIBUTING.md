# Como contribuir

1. Abra uma issue descrevendo a mudanca.
2. Crie uma branch: `git switch -c feat/nome-curto`.
3. Implemente a mudanca com testes.
4. Rode os testes e o linter.
5. Abra um pull request; nao envie diretamente para `main`.

Use commits pequenos: `feat: adiciona consulta de memoria` ou
`fix: bloqueia entidade nao permitida`.

Novas ferramentas devem restringir argumentos, testar recusas e exigir
confirmacao para efeitos colaterais. Nunca adicione execucao arbitraria de shell.

