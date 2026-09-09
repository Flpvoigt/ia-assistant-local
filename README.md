# IA Assistant Local

Assistente pessoal para controlar, com seguranca, o computador e uma casa conectada.
As conversas usam a API do Groq; toda acao passa por uma lista explicita de
ferramentas, validacao de argumentos e confirmacao humana.

> Projeto inicial. Nao use para fechaduras, alarmes, cameras, compras ou operacoes criticas.

## Objetivos do MVP

- conversar por uma interface web usando o Groq;
- consultar informacoes basicas do computador;
- abrir somente aplicativos previamente permitidos;
- consultar e controlar somente entidades permitidas do Home Assistant;
- pedir confirmacao antes de qualquer acao que altere o ambiente;
- testar automaticamente as regras de seguranca.

## Requisitos

- Python 3.11 ou superior;
- uma chave de API do Groq;
- Home Assistant e token de longa duracao somente para integrar a casa.

## Instalacao no Windows

`requirements.txt` contem todas as dependencias de execucao, instalacao, testes
e formatacao. A forma recomendada e:

```powershell
git clone https://github.com/Flpvoigt/ia-assistant-local.git
cd ia-assistant-local
.\install.ps1
```

Crie uma chave individual em https://console.groq.com/keys. Abra o arquivo `.env`
criado pelo instalador e preencha somente a linha:

```env
GROQ_API_KEY=gsk_sua_chave_aqui
```

Nunca envie a chave em mensagens, capturas de tela ou commits. Depois, execute:

```powershell
.\start.ps1
```

O servidor abre automaticamente `http://127.0.0.1:8765` no navegador.
Cada colaborador deve usar sua propria chave no arquivo `.env`; esse arquivo nao
deve ser enviado ao Git. Para encerrar, pressione `Ctrl+C` no terminal.

Instalacao manual, caso scripts PowerShell estejam bloqueados:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -e .
Copy-Item .env.example .env
# Preencha GROQ_API_KEY no .env e depois execute:
.\.venv\Scripts\ia-assistant.exe
```

Na primeira inicializacao, o terminal mostra senhas temporarias para as tres contas
administrativas: `will`, `gustavo` e `felipe`. Cada pessoa deve entrar com a
propria conta e trocar a senha temporaria. As senhas sao armazenadas como hashes
`scrypt`, nunca em texto puro.

O historico e as memorias ficam separados por conta no banco local
`data/oraculo.db`, que tambem nao e enviado ao Git. Cada entrada abre uma conversa
nova e limpa; conversas anteriores aparecem na barra lateral e podem ser reabertas
ou excluidas.

A interface possui seletor de modelo salvo por usuario, chat temporario que nao
grava historico nem memorias, uma sala compartilhada entre os tres criadores,
pesquisa global, painel de saude do sistema e paineis de artefatos para blocos de
codigo, tabelas e checklists. A lista permitida de modelos pode ser ajustada em
`GROQ_MODELS`; somente modelos incluidos nela sao aceitos pelo servidor.

Respostas do Oraculo sao exibidas com Markdown seguro: titulos, listas, tabelas,
links, checklists e blocos de codigo com botao para copiar. O conteudo gerado nao
e inserido como HTML executavel no navegador.

Arquivos de texto, codigo e PDFs podem ser arrastados ou escolhidos pelo botao de
anexo. O conteudo e extraido localmente e aparece em uma tela editavel de revisao;
somente depois da confirmacao ele entra no proximo pedido. PNG, JPG e WebP tambem
exigem previa e confirmacao e usam o modelo visual `qwen/qwen3.6-27b`. Anexos nao
sao gravados no historico, e o limite atual e de 5 MB por arquivo e uma imagem por
pedido.

O painel Extensoes mostra as integracoes implementadas: nucleo local e Home Assistant.
O Home Assistant permite consultar estados e controlar luzes e tomadas autorizadas;
aparece como "configuracao necessaria" enquanto faltar sua configuracao.

Felipe tambem possui o painel Atualizacao segura. A verificacao remota e manual; o
sistema recusa atualizacoes quando existem mudancas locais e cria uma aprovacao
separada antes de executar `git pull --ff-only`, com backup consistente do banco.
Depois de aplicar uma versao nova, reinicie o Oraculo quando o painel solicitar.

O projeto inclui manifesto e service worker de PWA. Em `localhost`, navegadores
compativeis podem oferecer a instalacao no computador. Instalar no celular fora da
rede local continua dependendo de HTTPS/hospedagem, que nao e configurada aqui.

Depois de cada mensagem, o Oraculo identifica automaticamente fatos e preferencias
duradouras que possam ajudar no futuro. Pedidos momentaneos e informacoes sensiveis,
como senhas, tokens, documentos e dados financeiros, nao devem virar memoria.
Memorias automaticas podem ser revisadas e excluidas nas configuracoes.

As memorias sao organizadas como informacoes pessoais, preferencias, projetos e
objetivos. Cada fato recebe uma chave estavel: quando o usuario corrige uma
informacao, a versao anterior e atualizada em vez de gerar uma duplicata. Pedidos
explicitos para esquecer um fato removem a memoria correspondente.

A conta `felipe` tem o papel `owner` e exibe um painel exclusivo para auditar as
conversas de `will` e `gustavo` durante validacoes e diagnosticos. Essa permissao
tambem e validada pelo backend; esconder ou chamar a rota diretamente nao concede
acesso aos demais usuarios. Os membros da equipe devem estar cientes dessa auditoria.

No mesmo painel, Felipe pode liberar ou bloquear por usuario o acesso a memorias,
ao painel de contexto, a informacoes do computador, a abertura de aplicativos e
as funcoes do Home Assistant. As escolhas ficam salvas no banco local e sao
validadas pelo servidor antes de cada uso. A conta `felipe` sempre conserva acesso
total e suas permissoes nao podem ser reduzidas pelo painel ou pela API.

O `.env` nunca deve ser enviado ao Git. Sem os dados do Home Assistant, as
ferramentas da casa permanecem indisponiveis.

## Desenvolvimento

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Leia `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` e `SECURITY.md` antes de
adicionar ferramentas.
