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
   Perfil local automatico
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

O aplicativo cria o perfil `oraculo` e o utiliza automaticamente para o uso
comum. Como o servidor escuta somente em `127.0.0.1`, esse perfil representa a
pessoa que usa a instalação local. As contas `will`, `gustavo` e `felipe`
continuam disponíveis apenas para a área administrativa opcional. Suas senhas
usam `scrypt`, e as sessões administrativas usam cookies `HttpOnly` com tokens
armazenados no banco somente como hashes.

`felipe` possui o papel `owner`; `will` e `gustavo` permanecem `admin`, mas integram
a lista explicita de contas autorizadas para a central administrativa. O servidor
valida essa autorizacao em todas as rotas privilegiadas. A entrada visual aparece
no perfil das três contas autorizadas, que também acessam a central com `/adm`.
Ocultar a entrada nao e considerado uma barreira de seguranca por si so.
