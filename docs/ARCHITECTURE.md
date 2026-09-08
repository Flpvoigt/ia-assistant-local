# Arquitetura

## Estrutura do codigo

```text
src/ia_assistant_local/
|-- ai/
|   `-- agent.py              # prompts, Groq e raciocinio do assistente
|-- core/
|   |-- config.py             # leitura do .env e configuracoes
|   `-- memory.py             # usuarios, sessoes, chats e memorias
|-- integrations/
|   |-- home_assistant.py     # comunicacao com a casa conectada
|   `-- tools.py              # ferramentas permitidas e confirmacoes
|-- web/
|   |-- interface.html        # interface visual
|   `-- server.py             # rotas HTTP e autenticacao
|-- cli.py                    # ponto de entrada do programa
`-- __init__.py              # versao do pacote
```

Novos arquivos devem ser colocados na pasta da responsabilidade correspondente.
Os scripts `install.ps1` e `start.ps1` permanecem na raiz porque sao os
atalhos usados pela equipe.

```text
Usuario (interface web; voz no futuro)
              |
              v
   Sessao autenticada (admin)
              |
              v
 SQLite: chats + historico
 + memorias automaticas
   isolados por usuario
              |
              v
         Backend local
              |
              v
          Groq API
              |
       solicita uma ferramenta
              |
              v
   ToolRegistry: allowlist + confirmacao
          |                    |
          v                    v
 Aplicativos permitidos   Home Assistant
                          entidades permitidas
```

O modelo interpreta linguagem natural, mas nao executa comandos diretamente.
`ToolRegistry` e a fronteira de confianca: ferramentas desconhecidas,
aplicativos nao listados e entidades nao autorizadas sao recusados.

As contas `will`, `gustavo` e `felipe` sao criadas localmente no primeiro
inicio. Senhas usam `scrypt`, e sessoes sao identificadas por cookies
`HttpOnly` com tokens armazenados no banco somente como hashes.

`felipe` possui o papel `owner`. Rotas de auditoria verificam esse papel no
servidor antes de permitir a leitura das conversas de `will` e `gustavo`.
O painel visual exclusivo nao e considerado uma barreira de seguranca por si so.

