# Site de download do Oráculo

Landing page estática. A Vercel publica somente `public`; nenhuma configuração ou chave do aplicativo é enviada.

O script `../scripts/windows/build.ps1` copia o instalador para `public/downloads` e
gera `public/update.json` com versão, tamanho e SHA-256. O site lê esses dados
automaticamente.

Preview: `python -m http.server 4173 --directory public`.
Publicação completa: `../scripts/windows/publish-release.ps1`.
