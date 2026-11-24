---
source: reference/questions.md
source_hash: ddeb23ad257a
---
# Domande

Le domande poste da Copier, con il valore predefinito. Le risposte sono registrate in
`.copier-answers.yml`.

| Domanda | Predefinito | Valori |
| --- | --- | --- |
| `project_name` | `my_project` | snake_case: nome del pacchetto Python e della CLI |
| `project_description` | `An enterprise FastAPI service` | Una riga |
| `author_name`, `author_email` | `Your Name`, `you@example.com` | |
| `timezone` | `UTC` | Fuso orario IANA per scheduler e log |
| `brand_name` | da `project_name` | Nome del prodotto nell'interfaccia e nella documentazione delle API |
| `brand_primary_color` | `#1F3A5F` | Colore esadecimale a sei cifre |
| `web_frontend` | `react` | `react`, `none` |
| `task_backend` | `taskiq` | `taskiq`, `celery`, `arq` |
| `ai_framework` | `pydantic_ai` | `pydantic_ai`, `langgraph`, `langchain`, `deepagents`, `pydantic_deep` |
| `llm_provider` | `openai` | `openai`, `anthropic`, `google`, `openrouter`, `openai_compatible`, `all` |
| `vector_database` | `qdrant` | `none`, `qdrant`, `pgvector` |
| `ci_provider` | `gitlab` | `gitlab`, `github` |
| `kubernetes` | `true` | Manifest Kubernetes |
| `logfire` | `false` | Pydantic Logfire |

`openrouter` e `openai_compatible` richiedono `pydantic_ai` o `pydantic_deep`; Copier rifiuta
le altre combinazioni. `openai_compatible` copre server on-premise come Ollama e vLLM.

`langchain`, `deepagents` e `pydantic_deep` vengono generati e sono coperti dai test di
generazione, ma il test end-to-end gira solo sui valori predefiniti.

## Scelte fisse

Alcune scelte non sono domande, perché Keelson è costruito intorno a esse: PostgreSQL con
SQLAlchemy, Redis con cache e rate limiting, organizzazioni con ruoli (multi-tenant), email via
SMTP, streaming via WebSocket, metriche Prometheus, Traefik con HTTPS, Python 3.13.
