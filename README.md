# Assistente de IA da Tech-2D

Serviço em desenvolvimento para consultar, por conversa, as atividades da Agenda. A primeira ferramenta busca atividades de uma turma e retorna cards com links para a Agenda. O projeto também contém uma tela simples de chat para testes.

O chat ainda é independente: ele não foi integrado ao site da Agenda. A validação de uma conversa real com o Groq e um login Firebase real ainda está pendente.

## Arquitetura

O navegador envia a mensagem para a API **FastAPI**, que valida o usuário com **Firebase Authentication**. O **LangGraph/LangChain** usa o modelo Groq para interpretar o pedido; o servidor valida os filtros, consulta o **PostgreSQL em modo somente leitura** e monta a resposta e os cards. A Agenda continua em um [repositório próprio](https://github.com/Tech-2D/Agenda).

## Executar localmente

Requer Python 3.12. No PowerShell, na pasta deste projeto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e ".[test]"
Copy-Item .env.example .env
```

O arquivo `requirements.lock` registra as versões testadas no Windows com Python 3.12, incluindo dependências de teste.

Preencha o `.env` com a chave Groq, os dados do PostgreSQL e a configuração Web do Firebase. Chaves Groq adicionais são opcionais em `GROQ_API_KEYS`, separadas por vírgula. Providencie o certificado CA do banco no caminho indicado por `DB_SSLROOTCERT`. Esses arquivos e credenciais não vêm no Git e devem ser obtidos por um meio seguro.

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra `http://127.0.0.1:8000`. Consulte `/health` para saber se o processo está no ar e `/ready` para verificar dependências configuradas. Uma resposta positiva de `/ready` não substitui um teste real de conversa e login.

O usuário de teste precisa existir no Firebase Authentication. A verificação do ID token usa certificados públicos do Google e precisa de acesso à internet; não é necessário colocar uma chave de conta de serviço no navegador.

Para continuar o desenvolvimento, leia [AGENTS.md](AGENTS.md), que reúne o contexto, o estado atual e as pendências. O [memorial original](docs/memorial-original.txt) preserva o planejamento histórico.
