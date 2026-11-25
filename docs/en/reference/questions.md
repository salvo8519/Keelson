# Questions

The questions Copier asks, with their default. Answers are recorded in `.copier-answers.yml`.

| Question | Default | Values |
| --- | --- | --- |
| `project_name` | `my_project` | snake_case: Python package and CLI name |
| `project_description` | `An enterprise FastAPI service` | One line |
| `author_name`, `author_email` | `Your Name`, `you@example.com` | |
| `security_contact` | `author_email`, empty while it is an `example.com` address | Address for vulnerability reports in `SECURITY.md`; empty: private security advisories only |
| `timezone` | `UTC` | IANA timezone for schedulers and logs |
| `repository_url` | `https://github.com/your-org/<project>` | HTTPS URL of the repository: documentation site and edit links |
| `brand_name` | from `project_name` | Product name in the UI and the API reference |
| `brand_primary_color` | `#1F3A5F` | Six-digit hex color |
| `languages` | `en`, `it` | Languages of the API, emails and interface; `en` is required |
| `web_frontend` | `react` | `react`, `none` |
| `task_backend` | `taskiq` | `taskiq`, `celery`, `arq` |
| `ai_framework` | `pydantic_ai` | `pydantic_ai`, `langgraph`, `langchain`, `deepagents`, `pydantic_deep` |
| `llm_provider` | `openai` | `openai`, `anthropic`, `google`, `openrouter`, `openai_compatible`, `all` |
| `vector_database` | `qdrant` | `none`, `qdrant`, `pgvector` |
| `ci_provider` | `github` | `github`, `gitlab` |
| `kubernetes` | `true` | Kubernetes manifests |
| `logfire` | `false` | Pydantic Logfire |

`openrouter` and `openai_compatible` require `pydantic_ai` or `pydantic_deep`; Copier refuses
other combinations. `openai_compatible` covers on-premise servers such as Ollama and vLLM.

`langchain`, `deepagents` and `pydantic_deep` render and are covered by the render tests, but
the end-to-end test runs on the defaults only.

## Fixed choices

Some choices are not questions, because Keelson is built around them: PostgreSQL with
SQLAlchemy, Redis with caching and rate limiting, organizations with roles (multi-tenant),
email over SMTP, WebSocket streaming, Prometheus metrics, Traefik with HTTPS, Python 3.13.
