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

Depois de cada mensagem, o Oraculo identifica automaticamente fatos e preferencias
duradouras que possam ajudar no futuro. Pedidos momentaneos e informacoes sensiveis,
como senhas, tokens, documentos e dados financeiros, nao devem virar memoria.
Memorias automaticas podem ser revisadas e excluidas nas configuracoes.

A conta `felipe` tem o papel `owner` e exibe um painel exclusivo para auditar as
conversas de `will` e `gustavo` durante validacoes e diagnosticos. Essa permissao
tambem e validada pelo backend; esconder ou chamar a rota diretamente nao concede
acesso aos demais usuarios. Os membros da equipe devem estar cientes dessa auditoria.

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
