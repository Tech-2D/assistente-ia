# Contexto para desenvolver o assistente Tech-2D

## Comece aqui

Este arquivo reúne as instruções, decisões, estado verificado e pendências do projeto. Este repositório é o serviço independente `Tech-2D/assistente-ia`, não o frontend `Tech-2D/Agenda`. A `main` contém o serviço e um chat de testes; não há integração nem implantação do chat no site da Agenda. A cópia anterior na branch `codex/agenda-ai-assistant` de `Tech-2D/Agenda` não é a fonte principal.

`docs/memorial-original.txt` é o texto original fornecido pelo usuário, preservado como histórico. Ele descreve planos futuros e fatos que eram desconhecidos quando foi escrito; não é um retrato atual nem uma ordem para implementar tudo. Em caso de divergência, siga as decisões mais recentes do usuário e verifique o código.

## Manutenção obrigatória deste arquivo

Ao realizar mudanças significativas, atualize o `AGENTS.md` na mesma entrega, antes do commit ou da conclusão do trabalho. Isso inclui mudanças de arquitetura, serviços e integrações, modelo ou ferramentas, regras de produto, configuração e execução, segurança, validações, implantação e pendências. Atualize ou remova informações superadas, registre o que foi efetivamente validado e o que continua pendente, e mantenha os exemplos e caminhos coerentes com o código. Não registre segredos. Mudanças pequenas que não alterem essas informações não exigem edição do documento.

## Objetivo e escopo

O objetivo maior é um assistente para o ecossistema Tech-2D, acessado futuramente por um botão flutuante e uma janela de chat. O usuário quer uma arquitetura organizada, segura e de baixo custo. A versão atual se restringe a consultar atividades da Agenda: tarefa, lição, trabalho, prova e evento. Outras tools, Kanban, avisos, professores e anotações são ideias futuras, não capacidades implementadas. Não afirme que uma escrita ocorreu sem confirmação real nem invente status de conclusão de atividades.

O usuário prefere explicações simples em português e decisões autônomas dentro do escopo autorizado. Não prometa que uma integração funciona sem validação. A Agenda já recebeu uma mudança anterior: “Sua turma” em Mais Opções salva a preferência no navegador; o dropdown da Agenda só filtra. Essa alteração pertence ao repositório Agenda, commit `fe5dd06`.

## Fluxo e arquivos

- `app/main.py`: rotas `/`, `/api/config`, `/health`, `/ready`, `/api/classes`, `/api/chat` e `DELETE /api/session/{session_id}`; valida token, limita uso e administra sessões. `ChatRequest` recebe `message`, `session_id` opcional e `preferred_class` opcional.
- `app/assistant.py`: LangGraph, schema `RequestIntent`, validações, continuação de conversa, chamada da tool e montagem da resposta. Modelo Groq `openai/gpt-oss-20b`, temperatura 0,7 e top_p 0,95. A saída do modelo é estruturada; o servidor formata o resultado. Modelo não recebe linhas das atividades.
- `app/activity_tool.py`, `app/types.py`, `app/dates.py`, `app/subjects.py` e `app/recurrence_check.py`: consulta, validação, datas, resolução de matérias e recorrência. `app/classes.py` consulta turmas e combina com `app/agenda_classes.py`.
- `app/db.py` abre conexões `asyncpg` com CA e hostname verificados, `default_transaction_read_only=on`, confirmação com `SHOW transaction_read_only` e timeout. `app/config.py` centraliza configurações.
- `app/security.py` verifica ID token Firebase e termos bloqueados; `app/limits.py` usa SQLite local para contador diário por hash de UID; `static/` é o chat simples; `prompts/system/`, `prompts/examples/` e `prompts/guardrails/` guardam instruções e exemplos. `tests/` contém testes unitários e de API.

## Regras do primeiro recurso

- Uma turma por consulta. Todas as turmas são visíveis e podem ser filtradas; se forem pedidas várias, perguntar qual. Usar a preferência pessoal como padrão quando disponível. Não confundir com o filtro temporário.
- Datas inclusivas em `America/Sao_Paulo`; sem datas, hoje e seis dias seguintes; apenas data inicial, sete dias; apenas data final, perguntar a inicial. Sem data final/duração no esquema de atividade inspecionado. Limite de um ano; a mensagem escolhida é: “Eita, pera ai, A agenda não é uma máquina do tempo! Escolha um período de até um ano para eu procurar as atividades.”
- O usuário escolheu a próxima segunda quando disser “segunda”, inclusive quando hoje é segunda. O prompt e os exemplos instruem o modelo a aplicar a regra; a interpretação com Groq real ainda precisa ser validada.
- Matérias: identificar aproximações entre nomes existentes, avisar a escolha e perguntar em caso de ambiguidade. Apelidos aprovados estão no dicionário `ALIASES` em `app/subjects.py` e no prompt; `mobile` é Aplicativo Móvel, `DAD` é Aplicação Dinâmica, e “desenvolvimento do app” pede esclarecimento. Prefixos numerados não devem induzir matérias como Chefia quando a pessoa quis Português; veja a pendência abaixo.
- Ocorrências são cards individuais, com resumo da recorrência quando sustentado pelo modelo cadastrado; não inventar ocorrências. O aviso escolhido para recorrências potencialmente incompletas é: “Estas são as atividades cadastradas até agora. Algumas atividades recorrentes desse período ainda podem não ter sido registradas!”
- Em erro, dizer que não foi possível consultar e orientar tentativa manual na Agenda; não confundir falha com ausência de resultados. Os cards são simples e apontam para a atividade; não há necessidade de expor anexos ou descrição no chat.

## Segurança, estado e limites

O usuário autorizou leitura do banco real. Preserve somente leitura e não execute migrações ou escritas nesse banco sem autorização específica. Valide filtros e identidade no servidor; não confie em texto ou dados cadastrados como instruções. Os dados de atividade não são enviados ao modelo para redigir a resposta.

Não versione `.env`, chaves, credenciais, CA local, SQLite ou `.venv`; não exiba valores de segredo em logs, respostas ou commits. O exemplo de configuração contém apenas campos de exemplo/públicos. Use credenciais do usuário obtidas por meio seguro e com acesso apropriado.

Conversas são em memória por UID e expiram; não existe histórico permanente. O contador local é separado do banco da Agenda e reinicia por dia em São Paulo; não é solução distribuída. O plano histórico menciona múltiplas chaves Groq e fallback, mas o serviço atual usa uma chave.

## Estado atual e validações

Em 11/11/2026, o serviço FastAPI, a tela de testes separada e a primeira ferramenta `consultar_atividades` estavam implementados. O serviço usa sessões em memória com expiração padrão de 30 minutos e limite configurável de 50 mensagens por usuário ao dia. O contador SQLite armazena hash do UID, data e contagem.

Em 11/11/2026, passaram 40 testes locais com `pytest -q`, além de `ruff check app tests` e `ruff format --check app tests`. Os testes não fazem chamada real ao Groq. Uma execução anterior percorreu API, grafo e ferramenta com identidade/classificador de teste e PostgreSQL real: a sessão confirmou `transaction_read_only = on` e retornou cards. Após mudar a consulta para aplicar filtros antes do limite, a nova SQL ainda não foi validada no banco real: as duas tentativas de conexão foram recusadas com `TooManyConnectionsError`. A migração documentada `sql/migrations/001_initial.sql` de `Tech-2D/modelagem-dados` define os campos usados como `text`. A construção do cliente Groq foi verificada sem chamada real. Login Firebase real e conversa completa com o modelo ainda não foram validados; a configuração local desse computador não tinha `GROQ_API_KEY`.

## Pendências e limitações conhecidas

1. No novo computador, configurar Groq, banco, CA e Firebase fora do Git; testar login real, `/ready` e conversas completas com modelo e ferramenta. `/ready` positivo não comprova essas integrações de ponta a ponta.
2. Testar a interpretação de “segunda”, outras datas e matérias ambíguas com o modelo Groq real.
3. Validar a integração com a Agenda. O `localStorage` pertence à origem do navegador: a tela separada só lê a preferência da Agenda se estiver na mesma origem. Em origens diferentes, será necessário passar o contexto adequadamente. Validar também o link dos cards no site real.
4. Revisar prefixos numéricos de matérias: o usuário disse para ignorar prefixos como “Matemática 10” ao interpretar o nome significativo, enquanto o resolvedor possui lógica específica para nomes numerados. Confirmar os casos com testes e preservar os apelidos aprovados.
5. Planejar o botão flutuante e o chat no sistema. A tela atual é de testes. Conferir descarte ao fechar ou recarregar: o servidor mantém sessões até exclusão explícita ou expiração.
6. Antes de múltiplas instâncias, substituir sessões em memória e contador SQLite por armazenamento compartilhado e revisar limites, logs, autenticação e operação. A alternância entre chaves Groq planejada no memorial não está implementada.
7. Validar a nova SQL no PostgreSQL real quando houver conexão disponível. Matéria e tipo são filtrados antes do limite de 10.000 resultados; uma consulta separada verifica a existência das ocorrências de recorrência mesmo quando foram alteradas e não coincidem com o filtro. Testar também grandes volumes. A lista de turmas combina catálogo e lista fixa, que precisa ser mantida atualizada. A verificação Firebase usa `check_revoked=False`; a política de revogação ainda precisa ser avaliada.

## Desenvolver em outro computador

Requer Python 3.12. Configure o ambiente conforme `README.md`, copie `.env.example` para `.env` e preencha `GROQ_API_KEY`, `DATABASE_URL`, `DB_SSLROOTCERT`, `FIREBASE_PROJECT_ID` e as variáveis `VITE_FIREBASE_*` necessárias. Obtenha o CA do banco e salve-o localmente no caminho configurado. A conta de teste precisa existir no Firebase e o login por e-mail e senha estar habilitado. Confirme o projeto Firebase e a configuração com o responsável; não presuma que os dados locais vieram no clone.

Execute `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`. `/health` só verifica o processo; `/ready` verifica configuração e acesso ao catálogo, não comprova uma chamada real ao Groq ou login Firebase. O navegador precisa acessar o SDK Firebase servido pelo Google. Os testes locais podem ser executados com `python -m pytest -q`; verificações: `ruff check app tests` e `ruff format --check app tests`.

Se este projeto ainda não existir na outra máquina, clone `https://github.com/Tech-2D/assistente-ia.git` com uma conta autorizada; se já existir, use `git pull`. Uma cópia dos documentos pode ser lida sem credenciais de banco/Groq, mas executar a experiência completa depende dessas configurações e de rede. Ao começar um novo chat, peça para ele ler `AGENTS.md` antes de continuar.
