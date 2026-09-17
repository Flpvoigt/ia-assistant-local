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

- Python 3.11, 3.12 ou 3.13;
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

## Aplicativo instalável para Windows

O Oráculo também pode ser distribuído como aplicativo de desktop. Quem instalar não precisa ter Python, Codex ou acesso ao código-fonte. Na primeira abertura, cada pessoa deve informar a própria chave da Groq; nenhuma chave pessoal é incluída no instalador.

Depois de informar a chave, o aplicativo abre diretamente no perfil local. Login
é solicitado somente quando alguém escolhe **Acesso da equipe** para usar uma das
contas administrativas autorizadas.

Para gerar o aplicativo e o instalador, execute `.\scripts\windows\build.ps1`. O arquivo final será criado em `dist\installer\Oraculo-Setup.exe`. As configurações, o banco local e os modelos de voz ficam em `%LOCALAPPDATA%\Oraculo`.

Para gerar somente a pasta executável, use `.\scripts\windows\build.ps1 -SkipInstaller`.

### Atualizações automáticas do aplicativo

A partir da versão 0.2.0, o instalador registra o `OraculoUpdater.exe` para
verificar novas versões quando o usuário entra no Windows. O Oráculo também
dispara uma verificação ao abrir. O atualizador consulta o manifesto HTTPS
`https://oraculo-desktop.vercel.app/update.json`, baixa o novo instalador e
confere tamanho e SHA-256 antes de executá-lo.

Se o Oráculo estiver aberto, a atualização fica preparada em
`%LOCALAPPDATA%\Oraculo\updates` e é instalada silenciosamente depois que o
aplicativo fechar. Conversas, memórias, modelos de voz e a chave Groq ficam fora
da pasta de instalação e são preservados.

Para gerar o instalador, atualizar o manifesto e publicar tudo na Vercel:

```powershell
.\scripts\windows\publish-release.ps1
```

Quem já possui uma versão anterior à 0.2.0 precisa instalar esta versão uma vez
pelo site. As versões seguintes poderão ser recebidas pelo atualizador.

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

### macOS

No Terminal, entre na pasta do projeto e execute:

```bash
bash install.sh
```

Abra o arquivo `.env`, preencha `GROQ_API_KEY` com a chave pessoal e inicie:

```bash
bash start.sh
```

O Oráculo exige Python 3.11, 3.12 ou 3.13. No macOS, o ambiente virtual usa
`.venv/bin`; caminhos `.venv\Scripts` e arquivos `.ps1` são exclusivos do Windows.
Se o Terminal estiver fora da pasta do projeto, use `cd` até a pasta
`ia-assistant-local` antes dos comandos.

O aplicativo entra automaticamente no perfil local `oraculo`, sem cadastro ou
senha. O histórico e as memórias desse perfil ficam no banco local
`data/oraculo.db`, que não é enviado ao Git. Cada instalação possui seus próprios
dados e cada entrada abre uma conversa nova e limpa.

As contas administrativas `will`, `gustavo` e `felipe` continuam disponíveis no
menu **Acesso da equipe**. Na primeira inicialização, suas senhas temporárias são
mostradas uma única vez. Elas usam hashes `scrypt` e precisam ser trocadas no
primeiro acesso. O perfil local nunca recebe acesso à central administrativa.

A interface possui seletor de modelo salvo por usuario, chat temporario que nao
grava historico nem memorias, uma sala compartilhada entre os tres criadores,
pesquisa global, painel de saude do sistema e paineis de artefatos para blocos de
codigo, tabelas e checklists. A lista permitida de modelos pode ser ajustada em
`GROQ_MODELS`; somente modelos incluidos nela sao aceitos pelo servidor.

O botao de microfone abre a conversa por voz em portugues: o navegador escuta a
frase, envia ao Oraculo e le a resposta em voz alta. Nao exige outra chave paga,
pois usa reconhecimento e sintese oferecidos pelo navegador. Fora de `localhost`,
o navegador pode exigir HTTPS para liberar o microfone.

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

Felipe, Will e Gustavo possuem acesso ao painel Atualizacao segura. Nos perfis de
Will e Gustavo, a entrada administrativa permanece oculta e o painel e aberto
somente pelo comando `/adm`. A verificacao remota e manual; o sistema recusa atualizacoes quando existem
mudancas locais e cria uma aprovacao separada antes de executar `git pull --ff-only`,
com backup consistente do banco. Depois de aplicar uma versao nova, reinicie o
Oraculo quando o painel solicitar.

O projeto inclui manifesto e service worker de PWA. Em `localhost`, navegadores
compativeis podem oferecer a instalacao no computador. Instalar no celular fora da
rede local continua dependendo de HTTPS/hospedagem, que nao e configurada aqui.

Depois de cada mensagem, o Oraculo identifica automaticamente fatos e preferencias
duradouras que possam ajudar no futuro. Pedidos momentaneos e informacoes sensiveis,
como senhas, tokens, documentos e dados financeiros, nao devem virar memoria.
Memorias automaticas podem ser revisadas e excluidas nas configuracoes.

O Oraculo tambem adapta o jeito de conversar a cada conta. Desde a primeira
mensagem, ele pode aprender formalidade, ritmo, objetividade, humor, girias e
bordoes, salvando apenas um resumo do estilo e refinando-o ao longo da conversa.
A adaptacao deve ser natural, sem caricatura e sem copiar erros ou linguagem
ofensiva. O usuario pode dizer "pare de imitar meu jeito" para desativar a funcao
de forma persistente e "pode voltar a adaptar seu jeito" para reativa-la.

Ao responder perguntas sobre si mesmo, o Oraculo pode explicar suas funcoes
publicas, incluindo voz, mascote, memorias, projetos, anexos, tarefas, cofre,
extensoes e configuracoes. Ele explica como usar os recursos, mas nao revela
codigo, arquitetura, detalhes internos nem recursos administrativos.

As memorias sao organizadas como informacoes pessoais, preferencias, projetos e
objetivos. Cada fato recebe uma chave estavel: quando o usuario corrige uma
informacao, a versao anterior e atualizada em vez de gerar uma duplicata. Pedidos
explicitos para esquecer um fato removem a memoria correspondente.

Felipe, com papel `owner`, exibe o painel administrativo no perfil. Will e Gustavo
conservam o papel `admin`, nao veem essa entrada no perfil e abrem o mesmo painel
somente com `/adm`. Os tres acessos sao validados pelo backend e podem auditar as conversas dos
demais usuarios durante validacoes e diagnosticos. Os membros da equipe devem estar
cientes dessa auditoria.

Felipe, Will e Gustavo sempre conservam acesso total, e suas permissoes nao podem
ser reduzidas pelo painel ou pela API.

O `.env` nunca deve ser enviado ao Git. Sem os dados do Home Assistant, as
ferramentas da casa permanecem indisponiveis.

## Menu do perfil e mascote

Clique no nome da conta no rodape da barra lateral para abrir consumo individual,
mascote, convite, configuracoes e sair. Configuracoes inclui troca de senha,
acesso a memorias (conforme permissao) e integracoes.

O mascote vive dentro da janela do Oraculo, inclusive na versao instalada pelo
navegador. Ele caminha, escala as laterais, se pendura, acena, se alonga e cochila
sentado na barra de mensagem. Arraste para reposicionar ou clique para focar o
chat. Durante a digitacao ele fica sentado; janelas de configuracao pausam os
movimentos. Alt+Shift+M mostra/oculta o mascote e Ctrl+, abre configuracoes.
As preferencias ficam separadas por conta neste navegador. Movimento reduzido
e respeitado; sair encerra a exibicao do mascote.

O consumo mostra solicitacoes e falhas da conta nas ultimas 24 horas, incluindo
novas tentativas. A cota restante da Groq nao e calculada por esses contadores.
Na instalacao local, o convite compartilha orientacoes para pedir acesso ao
responsavel; nao cria contas nem torna localhost acessivel por outro computador.

## Desenvolvimento

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
```

Leia `CONTRIBUTING.md`, `docs/ARCHITECTURE.md` e `SECURITY.md` antes de
adicionar ferramentas.

## Voz profissional local

O Oráculo usa o Kokoro ONNX com uma voz masculina própria para responder em
português brasileiro. O perfil combina uma base brasileira grave com uma camada
britânica discreta e usa cadência mais calma, buscando o estilo de um assistente
cinematográfico sem imitar a voz de uma pessoa real. A síntese roda no próprio
computador, sem chave de API e sem cobrança por fala. Se o mecanismo ou o modelo
estiver indisponível, a interface troca automaticamente para a voz instalada no
navegador.

`install.ps1` no Windows e `bash install.sh` no macOS/Linux instalam a biblioteca
e baixam uma vez os arquivos do modelo para `data/kokoro/`. O modelo INT8 ocupa
cerca de 88 MB e não entra no Git. Quando o F32 já existe, o modo automático o
prefere porque ele pode ser mais rápido em algumas CPUs; o INT8 continua como
alternativa leve. Defina `ORACULO_VOICE_MODEL=int8` no `.env` para forçar o modelo
menor ou `ORACULO_VOICE_MODEL=f32` para forçar o modelo completo. Quem já possui o
projeto pode atualizar apenas a voz:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m ia_assistant_local.core.voice --install
```

No macOS/Linux, substitua o executável por `.venv/bin/python`. O estado e o teste
de reprodução aparecem em **Painel do dev-chefe → Testes**. Respostas maiores são
geradas e reproduzidas em partes, reduzindo a espera antes do início da fala.
# Anexos, pastas e PDF

- Use o botão + para escolher vários arquivos ou uma pasta com subpastas. Também é
  possível arrastar para qualquer ponto da página. Revise antes de enviar ao modelo.
- Limites: 50 arquivos, 5 MB por arquivo, 20 MB por lote; contexto de até 60.000
  caracteres, com até 12.000 por arquivo. Trechos limitados são indicados na revisão.
  Arquivos não incluídos são listados. .env, chaves, bancos, .git, ambientes virtuais
  e dependências não são importados. Revise também segredos em outros arquivos.
- Cole imagens com Ctrl+V na caixa de mensagem. Uma miniatura removível confirma
  o anexo; ele só será enviado à IA ao enviar a mensagem. Uma imagem por mensagem.
- Conversão local: /pdf nome-do-arquivo, /pdf todos ou
  “converta este arquivo para PDF”. Suporta texto/código, DOCX, PNG, JPG, WebP e PDF.
  DOCX exporta o texto, sem preservar tabelas, imagens ou diagramação original;
  HTML é convertido como código, não como página renderizada.
- A conversão usa o original, não o trecho resumido, com limite de 200.000 caracteres
  ou 20 megapixels. Originais e downloads ficam somente na sessão do navegador;
  ao trocar de conversa, sair ou recarregar, anexe novamente. Conversões locais
  não entram no histórico compartilhado nem são enviadas ao Groq.
- Após atualizar, execute python -m pip install -r requirements.txt no ambiente
  virtual, reinicie o servidor e atualize a página com Ctrl+F5.
# Lançamentos e boas-vindas

No painel do dev-chefe, **Lançar nova versão** está disponível para Felipe e Will,
desde que a conta tenha senha definitiva. Para Will, o painel é aberto com `/adm`;
a entrada continua oculta no perfil. O servidor também valida essa permissão.
O primeiro lançamento é 1.5, seguido de 2.0, 2.5 e assim por diante.

Informe as novidades, verifique a prévia e confirme para criar um commit e fazer
push para origin/main. Git precisa estar instalado, autenticado e com identidade
de commit configurada. A main deve estar sincronizada com o remoto, sem staging
pendente. Arquivos fora da lista permitida, arquivos privados e padrões comuns de
segredos bloqueiam o lançamento. Isso não substitui sua revisão do código.
Se o push falhar, o commit permanece local: confira o remoto e conclua esse push
antes de lançar outra versão. Não há force-push nem descarte automático de arquivos.

A equipe recebe o lançamento ao atualizar o projeto e reiniciar o servidor.
O filme de abertura termina com ORÁCULO e a versão; depois aparece o guia com as
novidades informadas no lançamento. Há botão para pular a animação e suporte a
movimento reduzido. A conclusão é lembrada por conta, versão e navegador; limpar
os dados do navegador ou entrar em outro dispositivo pode mostrar o guia novamente.
Nada é publicado apenas por instalar esta melhoria.

## Memória protegida, OCR e tarefas

- Se uma nova memória usar a mesma chave de uma informação diferente, o Oráculo
  mantém a versão atual e abre uma contradição em **Gerenciar memórias**. O usuário
  escolhe explicitamente qual versão permanece.
- **Cofre privado** usa AES-GCM e uma chave derivada da senha informada. A senha não
  é salva, apenas os nomes dos itens aparecem bloqueados e o texto descriptografado
  some da tela após 60 segundos. O cofre nunca é incluído automaticamente no
  contexto da IA. Perder a senha significa perder o acesso ao conteúdo.
- Documentos a partir de 750 KB são extraídos na fila. Abra **Tarefas** no perfil
  para acompanhar, cancelar ou revisar o resultado antes de anexá-lo ao chat.
- Em imagens anexadas, use **OCR** para extrair texto em segundo plano. A câmera do
  celular está disponível em **+ → Usar câmera**.
- A biblioteca Python de OCR é instalada pelo requirements.txt, mas o mecanismo
  Tesseract também precisa existir no computador. No macOS, use
  **brew install tesseract tesseract-lang**. Sem ele, imagens ainda podem ser
  anexadas normalmente e o painel mostra que o OCR local está indisponível.

## Web Clipper

A pasta **browser-extension** contém uma extensão local para Chrome e Edge. Abra a
página de extensões do navegador, ative o modo do desenvolvedor, escolha
**Carregar sem compactação** e selecione essa pasta. Ela captura seleção, texto
visível ou uma imagem da aba e abre uma revisão no Oráculo. O conteúdo só é
anexado depois da confirmação e nunca é enviado diretamente ao modelo.
