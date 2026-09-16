# Site de download do Oráculo

Landing page estática. A Vercel publica somente `public`; nenhuma configuração ou chave do aplicativo é enviada.

Copie `../dist/installer/Oraculo-Setup.exe` para `public/downloads/Oraculo-Setup.exe` antes de publicar. Ao trocar a versão, atualize tamanho, versão e SHA-256 na página.

Preview: `python -m http.server 4173 --directory public`.
Publicação: `vercel deploy --prod`.
