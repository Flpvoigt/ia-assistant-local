# Seguranca

## Principios

- negar por padrao;
- expor somente aplicativos, entidades e acoes explicitamente permitidos;
- confirmar toda operacao com efeito colateral;
- nunca entregar um shell, token ou segredo ao modelo;
- manter Home Assistant e Ollama restritos a rede local.

Nao habilite fechaduras, alarmes, cameras, compras, exclusao de arquivos ou
comandos administrativos durante o MVP.

Use `.env` somente no computador local. Se um token for publicado, revogue-o
imediatamente e gere outro.

