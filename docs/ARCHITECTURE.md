# Arquitetura

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

