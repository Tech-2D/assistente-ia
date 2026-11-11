# Assistente de IA da Agenda Tech-2D

Serviço FastAPI para consultar atividades da Agenda por conversa, usando LangChain, LangGraph e Groq (`openai/gpt-oss-20b`). A primeira e única ferramenta disponível é `consultar_atividades`, que lê o catálogo e não grava nele.

## Como funciona

1. O usuário entra com Firebase Authentication. A API verifica o Firebase ID token em cada rota protegida.
2. O modelo classifica a mensagem em um schema fechado: consultar, esclarecer ou recusar. Ele não tem campo para escrever uma resposta livre.
3. O LangGraph valida e executa `consultar_atividades` quando a intenção é uma consulta da Agenda.
4. A consulta usa TLS com verificação de certificado e hostname, e o PostgreSQL inicia cada sessão em modo somente leitura.
5. O modelo não recebe linhas da Agenda. O servidor monta a resposta e os cards, trata datas, matérias, turmas e avisos de recorrência sem pedir ao modelo para interpretar conteúdo cadastrado.

O prompt e os exemplos de fuga de escopo ficam em `prompts/`. O bloqueio de insultos também é aplicado no servidor. O prompt ajuda a classificar a intenção; as regras decisivas são validadas por código.

## Regras implementadas

- Uma turma por consulta. A preferência pessoal vem do localStorage da Agenda; o seletor desta tela altera apenas o filtro temporário.
- Matérias aproximadas são resolvidas pelo catálogo e pelos codinomes confirmados. Uma correspondência ambígua gera uma pergunta com opções; o servidor informa a matéria escolhida quando consulta.
- Tipos aceitos: tarefa, lição, trabalho, prova e evento. Eventos gerais entram por padrão.
- No esquema atual, cada atividade tem uma única coluna `date`; não existe campo de data final ou duração. A consulta usa essa data e não inventa intervalos para uma atividade.
- Períodos inclusivos no fuso `America/Sao_Paulo`: hoje e os seis dias seguintes por padrão; sete dias quando só há data inicial; limite máximo de um ano; segunda-feira ambígua pede confirmação.
- Recorrências são descritas somente com dados do modelo ativo e suas ocorrências cadastradas. Cada ocorrência continua em um card individual. A API avisa se faltarem ocorrências esperadas ou se a consulta ultrapassar o horizonte conhecido de 56 dias.
- Conversas ficam apenas na memória do processo, vinculadas ao UID e removidas após 30 minutos sem atividade, ao sair ou iniciar outra conversa. O texto do chat não é gravado em arquivo nem no banco da Agenda.
- Limite padrão de 50 mensagens por usuário por dia. O SQLite local guarda somente o hash do UID, a data e a contagem, com limpeza de registros antigos.

## Requisitos e configuração local

Requer Python 3.12.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

Configure no `.env`:

- `GROQ_API_KEY`: chave da API Groq. Não está incluída no ZIP de credenciais fornecido.
- `DATABASE_URL` e `DB_SSLROOTCERT`: conexão PostgreSQL e certificado aprovados para leitura. A aplicação força TLS verificado e transações somente leitura.
- Firebase Web config: `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID` e `VITE_FIREBASE_APP_ID`. A API key Web é configuração pública do Firebase; nunca coloque uma chave de service account no navegador.
- `FIREBASE_PROJECT_ID`: projeto cuja identidade a API verifica.
- `LLM_TIMEOUT_SECONDS` limita a espera do Groq; `DATABASE_STATEMENT_TIMEOUT_MS` limita cada consulta ao PostgreSQL. O cliente Groq tenta novamente no máximo uma vez.

O `.env` local deve permanecer fora do Git. Os valores já configurados localmente não devem ser copiados para este README nem para commits.

## Rodar

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000`. A conta precisa existir no Firebase Authentication com login por e-mail e senha habilitado.

- `GET /health` confirma apenas que o processo está ativo.
- `GET /ready` informa quais dependências ainda faltam sem expor credenciais ou dados do banco; retorna HTTP 503 enquanto alguma dependência estiver indisponível.
- `GET /api/classes` lista turmas depois de autenticar.
- `POST /api/chat` recebe `Authorization: Bearer <Firebase ID token>` e JSON `{"message":"Quais provas temos esta semana?","preferred_class":"2° TECH D"}`.
- `DELETE /api/session/{session_id}` descarta o contexto temporário ao iniciar um chat novo ou sair.

## Verificações

```powershell
python -m pytest -q
ruff check app tests
```

Os testes unitários e de API não fazem chamadas ao Groq nem gravam no banco real. A integração de leitura com PostgreSQL pode ser verificada localmente depois de configurar o `.env`.

## Operação e limites conhecidos

- O `.env` de desenvolvimento atual não tem `GROQ_API_KEY`; por isso o processo e as rotas sem modelo sobem, mas a consulta conversacional real ao Groq não está pronta para validação até essa chave ser adicionada.
- Sessões e contador SQLite são adequados para desenvolvimento com um processo. Uma implantação com várias instâncias requer armazenamento compartilhado para sessões e limites, além de infraestrutura própria para essa finalidade. O app não grava esses dados no banco real da Agenda.
- O modelo de recorrência informa o que está cadastrado, não cria datas por conta própria. Jobs atrasados podem deixar ocorrências ausentes; nesses casos o assistente mostra o aviso definido pelo produto.
