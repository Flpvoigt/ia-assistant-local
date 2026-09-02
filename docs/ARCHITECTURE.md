# Arquitetura

```text
Usuario (terminal; voz no futuro)
              |
              v
        LocalAgent / Ollama
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

