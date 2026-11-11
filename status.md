# Status do assistente de IA da Agenda

Atualizado em 11/11/2026.

## Situação geral

O serviço FastAPI e sua primeira ferramenta, `consultar_atividades`, estão implementados para desenvolvimento local. A consulta real ao PostgreSQL foi exercitada em modo somente leitura e a aplicação passou pelos testes automatizados existentes. A validação de ponta a ponta com o Groq ainda depende de configurar `GROQ_API_KEY`.

## Implementado

- API FastAPI com `GET /health`, `GET /ready`, `GET /api/classes`, `POST /api/chat` e encerramento explícito de sessão.
- Interface web de login e chat com Firebase Authentication.
- Verificação de Firebase ID token nas rotas protegidas; sessões de conversa ficam em memória, vinculadas ao UID, com expiração após 30 minutos.
- Grafo LangGraph/LangChain usando Groq `openai/gpt-oss-20b`, temperatura `0.7` e `top_p=0.95`. A saída do modelo usa um schema restrito para classificar, pedir esclarecimento ou recusar; texto e cards finais são montados pelo servidor.
- Ferramenta `consultar_atividades`: lê atividades e turmas do PostgreSQL com TLS e verificação de certificado/hostname, transações somente leitura e limite de tempo por consulta. O modelo não recebe as linhas da Agenda.
- Filtro de uma turma por consulta, usando a turma preferida salva pela Agenda como padrão; a escolha na tela do assistente é temporária. A lista de turmas pode ser consultada e filtrada.
- Busca aproximada de matérias com os nomes e codinomes confirmados. Se houver mais de uma opção plausível, a IA pede esclarecimento; quando resolve, informa o nome escolhido.
- Filtro por tipos cadastrados: tarefa, lição, trabalho, prova e evento.
- Datas no fuso `America/Sao_Paulo`, período inclusivo, sete dias como padrão e limite de um ano. “Segunda” ambígua é resolvida para a próxima segunda-feira conforme a regra definida.
- Cards simples de atividades. O esquema atual tem uma única data por atividade, então o assistente não presume duração nem data final.
- Resumo de recorrência baseado nos dados cadastrados, ocorrências individuais em cards e aviso quando faltarem ocorrências esperadas ou a consulta passar do horizonte conhecido de 56 dias.
- Limite de 50 mensagens por usuário ao dia, com contador SQLite local que armazena hash do UID, data e contagem. Respostas de erro oferecem retorno manual à Agenda.
- Prompt, exemplos contra tentativas de fuga de escopo e bloqueio de termos ofensivos, além de validações determinísticas no servidor.

## Validações já feitas

- 38 testes automatizados passaram; Ruff check e formatação também passaram na última execução registrada.
- A rota de consulta percorreu a API, o grafo e a ferramenta usando uma identidade de teste, e consultou o PostgreSQL real em modo somente leitura. O resultado foi formatado pelo servidor em cards.
- A conexão confirmou `transaction_read_only = on`.
- A inicialização do cliente Groq e a construção da cadeia de saída estruturada foram verificadas sem fazer uma chamada ao modelo.

## Pendências para validar a experiência completa

1. Configurar uma `GROQ_API_KEY` válida fora do Git e validar uma conversa real com o modelo escolhido.
2. Fazer uma entrada real pelo Firebase Authentication configurado e exercitar uma chamada autenticada de ponta a ponta.
3. Repetir os cenários de conversa e de matérias ambíguas com Groq conectado; os testes automatizados atuais não substituem essa validação do modelo.
4. Antes de executar com múltiplas instâncias, substituir as sessões em memória e o contador SQLite local por armazenamento compartilhado apropriado.

## Limites conhecidos

- O assistente mostra o que está cadastrado. A recorrência não cria atividades no banco; ocorrências ausentes podem refletir atraso no processo que cadastra as atividades.
- O banco atual não fornece campo de data final/duração para atividades.
- As sessões e o controle de limite são locais a uma instância e não são gravados no banco da Agenda.
- Segredos, certificado de banco e banco SQLite de desenvolvimento são arquivos locais ignorados pelo Git; o repositório recebe somente `.env.example`.
