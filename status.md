# Status do assistente de IA da Tech-2D

Atualizado em 11/11/2026. Este documento é o ponto de partida para retomar o trabalho em outro computador. [AGENTS.md](AGENTS.md) descreve decisões, arquivos e cuidados para quem for desenvolver.

## Estado geral

O serviço FastAPI, uma interface separada de teste e a primeira ferramenta `consultar_atividades` estão implementados. O código está na `main` deste repositório privado, `Tech-2D/assistente-ia`. **Ainda não está integrado nem publicado no site da Agenda.** Há uma cópia anterior na branch `codex/agenda-ai-assistant` de `Tech-2D/Agenda`; a fonte deste serviço para continuar o trabalho é este repositório.

O serviço está em desenvolvimento: falta validar uma conversa real com Groq e autenticação real com Firebase. A configuração local usada neste computador não tinha `GROQ_API_KEY`. Não trate os testes locais nem `/ready` como prova de que a experiência completa funciona.

## O que existe

- `app/main.py`: API FastAPI e tela estática; autenticação Firebase ID token; sessões temporárias por UID, com expiração após 30 minutos; limite configurável de 50 mensagens por usuário por dia.
- `app/assistant.py`: LangGraph e LangChain com `openai/gpt-oss-20b`, temperatura `0.7` e `top_p=0.95`; classificação estruturada e montagem da resposta pelo servidor. O modelo não recebe as linhas das atividades.
- `app/activity_tool.py`: ferramenta de leitura de atividades por uma turma, período, matéria e tipos; inclui atividades gerais por padrão, ordena por data e horário e entrega cards simples com links para a Agenda.
- `app/db.py`: PostgreSQL com TLS, verificação do certificado e hostname, timeout e sessão configurada e verificada como somente leitura. Consulta o esquema `tech2d`; não cria nem altera atividades.
- `app/subjects.py`: resolução por nome cadastrado, apelido e aproximação; pede esclarecimento em caso de ambiguidade. O catálogo mistura nomes fixos e `DISTINCT subject` do banco.
- `app/recurrence_check.py`: usa os modelos de recorrência cadastrados, mostra cada ocorrência separadamente e apresenta resumo e aviso quando detecta ocorrências ausentes ou consulta além do horizonte de 56 dias.
- `static/`: chat básico com login Firebase, seletor temporário de turma e cards. `prompts/` contém o prompt principal, exemplos e termos bloqueados. As conversas não são persistidas; o contador SQLite local guarda hash do UID, data e contagem.

## Decisões de produto já tomadas

- Só uma turma por consulta; se pedirem duas, perguntar qual. Todas as turmas da Agenda podem ser selecionadas. Sem turma no contexto, perguntar. A turma pessoal configurada na Agenda deve ser o padrão; o dropdown da Agenda é apenas filtro.
- Nomes aproximados devem ser comparados com matérias reais; informar a matéria selecionada e perguntar quando houver dúvida. `mobile` significa Desenvolvimento de Aplicativo Móvel; `DAD` significa Desenvolvimento Aplicação Dinâmica; “desenvolvimento do app” deve gerar pergunta. Os demais apelidos confirmados estão em `app/subjects.py` e `prompts/system/assistant.md`.
- Período inclusivo, fuso `America/Sao_Paulo`, padrão de hoje mais seis dias, e máximo de um ano. A decisão do usuário para “segunda” foi assumir a próxima segunda-feira.
- Atividades recorrentes aparecem individualmente, com resumo como “toda segunda” e data final quando existir. O texto definido para situações de recorrência incompleta é: “Estas são as atividades cadastradas até agora. Algumas atividades recorrentes desse período ainda podem não ter sido registradas!”
- Se o período exceder o limite: “Eita, pera ai, A agenda não é uma máquina do tempo! Escolha um período de até um ano para eu procurar as atividades.” Em falhas, orientar a tentar novamente ou conferir manualmente na Agenda.
- Exibir cards simples que direcionem à atividade real, sem depender de descrição ou anexos. O esquema inspecionado tem uma data por atividade; não foi encontrado campo de duração/data final para atividades.

## Validações e o que ainda falta

Em 11/11/2026, `pytest -q` passou com **38 testes**, e `ruff check app tests` e `ruff format --check app tests` passaram. São testes locais; não fazem chamada real ao Groq.

Uma execução anterior percorreu a API, o grafo e a ferramenta usando identidade/classificador de teste e o PostgreSQL real. A sessão confirmou `transaction_read_only = on` e retornou cards. A construção do cliente Groq foi verificada sem chamada real. Isso não valida o login Firebase nem o comportamento real do modelo.

Próximos passos:

1. Configurar `GROQ_API_KEY`, banco, CA e Firebase no novo computador, sem enviar segredos ao Git. Testar login real, `/ready` e conversas completas com o modelo e a tool.
2. Corrigir a divergência de “segunda”: o código e prompt atuais perguntam quando o dia de hoje é segunda; a decisão do usuário foi assumir a próxima. Testar datas e ambiguidades de matérias com o modelo real.
3. Validar a integração futura com a Agenda: o `localStorage` pertence à origem do navegador. A tela separada só lê a preferência da Agenda se estiver na mesma origem; em origens diferentes será necessário passar o contexto de forma apropriada. O link dos cards também precisa de validação no site real.
4. Revisar a intenção sobre prefixos numéricos de matérias: o usuário disse para ignorar prefixos como “Matemática 10” ao interpretar o nome significativo, enquanto o resolvedor possui lógica específica para nomes numerados. Confirmar os casos com testes e preservar os apelidos aprovados.
5. Planejar a integração visual desejada: um botão flutuante e chat no sistema. A tela atual é apenas para testes. Conferir descarte da sessão ao fechar/recarregar: hoje o servidor também mantém sessões até exclusão explícita ou expiração.
6. Antes de múltiplas instâncias, substituir sessões em memória e contador SQLite por armazenamento compartilhado; revisar limites, logs, autenticação e operação. O memorial propõe fallback entre chaves Groq, mas o código atual usa uma chave e não implementa esse fallback.

## Limites e cuidados

- A consulta possui limite interno de 10.000 linhas antes de aplicar filtros de matéria/tipo em memória; o tratamento de grandes volumes precisa ser revisto. Recorrências são apresentadas a partir dos registros; a IA não cria ocorrências.
- `list_classes()` combina o catálogo consultado com uma lista fixa. Verifique a atualidade dessa lista ao evoluir o sistema.
- O Firebase verifica o token com `check_revoked=False`; a validação real da autenticação e da política de revogação está pendente.
- Não há dados individuais de conclusão no contrato atual: nunca afirmar que o aluno concluiu ou deixou de concluir uma atividade.
- `.env`, certificado, credenciais, banco SQLite, `.venv` e caches são locais e ignorados pelo Git. Ao trocar de computador é preciso configurá-los novamente.
