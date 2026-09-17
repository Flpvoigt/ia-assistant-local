# Organização do projeto

| Pasta | Responsabilidade |
| --- | --- |
| `src/ia_assistant_local/ai` | Integração com IA e adaptação ao usuário |
| `src/ia_assistant_local/core` | Dados, memória, voz, segurança e recursos locais |
| `src/ia_assistant_local/integrations` | Ferramentas e serviços externos |
| `src/ia_assistant_local/web` | Interface do aplicativo e servidor HTTP local |
| `scripts/windows` | Build e publicação das versões Windows |
| `packaging/windows` | Instalador Inno Setup e entrypoints do executável |
| `tools` | Utilitários auxiliares de desenvolvimento |
| `download-site` | Site de apresentação, download e manifesto público |
| `browser-extension` | Extensão de navegador |
| `tests` | Testes automatizados |
| `docs` | Arquitetura e guias |
| `build` e `dist` | Artefatos gerados; não entram no Git |
| `data` | Dados locais do desenvolvimento; não entram no Git |

Os scripts de instalação e início (`install.*` e `start.*`) ficam na raiz como
atalhos de desenvolvimento. Os arquivos `.env` e o banco de dados nunca devem ser
movidos para pastas publicadas ou versionadas.

## Comandos Windows

```powershell
.\scripts\windows\build.ps1
.\scripts\windows\publish-release.ps1
# Republicar um instalador já compilado:
.\scripts\windows\publish-release.ps1 -SkipBuild
```

O build gera os arquivos `.spec` dentro de `build/windows/specs`, a pasta do
aplicativo em `dist/Oraculo` e o instalador em `dist/installer`. O manifesto e a
cópia versionada para download são preparados automaticamente.
