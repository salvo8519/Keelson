<!-- i18n source: README.md source_hash: da9123ea94c0 -->
<p align="center">
  <img src="docs/_shared/assets/brand/mark.svg" alt="Keelson" width="96">
</p>

<h1 align="center">Keelson</h1>

<p align="center"><strong>Un servizio FastAPI per le aziende, pronto dal primo giorno.</strong><br>
Tenant separati dal database, single sign-on, un contratto API e un livello agentico,
ognuno presidiato da test.</p>

<p align="center">
  <img alt="Stato: pre-release" src="https://img.shields.io/badge/status-pre--release-0B1F3A">
  <img alt="Licenza: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-0B1F3A">
  <img alt="Copier" src="https://img.shields.io/badge/generator-Copier-C8A24A">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-0B1F3A">
  <img alt="Documentazione: inglese e italiano" src="https://img.shields.io/badge/docs-EN%20%7C%20IT-0B1F3A">
</p>

[English](README.md) | Italiano

Avviare un servizio per le aziende significa risolvere gli stessi problemi prima della prima
funzionalità: tenere separati i dati di ogni cliente, far accedere gli utenti con il loro
provider di identità, dare agli altri sistemi un accesso controllato, pubblicare API che non
rompono i client e superare una revisione di sicurezza. Keelson genera un progetto FastAPI in
cui tutto questo è già fatto, verificato da test che girano nella sua pipeline, e lascia al
vostro team la parte che è solo vostra.

Un solo comando produce un backend, un frontend React, worker per il lavoro asincrono e
schedulato, un livello agentico con retrieval, il deploy su Docker e Kubernetes, e la
documentazione in inglese e italiano.

## Cosa è già fatto

**I dati di ogni azienda restano suoi, e lo impone il database.**
La row level security di PostgreSQL copre ogni tabella, per un login applicativo che non può
aggirarla. Ogni transazione dichiara chi agisce (un utente, un'organizzazione, una API key);
senza, nessuna riga è visibile. Le conversazioni dei membri restano private anche per gli
amministratori della loro organizzazione, e i ruoli sono verificati nel database oltre che nel
codice. Test di attacco su un PostgreSQL reale provano a superare ogni confine. Il database
vettoriale ha un proprio filtro per tenant, così il retrieval non restituisce mai documenti di
un altro tenant.

**Persone e sistemi accedono come le aziende si aspettano.**
Single sign-on con qualsiasi provider OpenID Connect (Microsoft Entra ID, Google, Keycloak,
Okta), configurato a runtime, senza un secondo login. Password salvate come hash Argon2id. API
key per organizzazione, con scope, scadenza, rotazione e audit. I job di CI su GitHub Actions
o GitLab CI chiamano le API con la propria identità, senza segreti salvati nella CI.

**Un contratto API che non rompe i client.**
Il documento OpenAPI è versionato con il codice. La pipeline fallisce quando si discosta dal
codice, quando una pull request contiene una modifica incompatibile, o quando il client del
frontend non è rigenerato da esso. Su `/docs` c'è un riferimento white label (Scalar), e gli
errori seguono la RFC 9457 nella lingua dell'utente.

**Pronto per una revisione di sicurezza.**
I segreti non arrivano mai nei log, e un test fa passare segreti noti in ogni percorso di
logging per dimostrarlo. I segreti salvati nel database usano chiavi proprie e ruotabili. La
pipeline cerca segreti nella storia del repository, verifica le dipendenze di backend e
frontend, scansiona l'immagine del container, esegue regole di lint di sicurezza e produce una
distinta dei componenti software (SBOM). Le skill date agli agenti di programmazione sono
vincolate al digest del loro contenuto e scansionate prima dell'installazione.

**Osservabile e pronto al deploy.**
Log JSON con request id e trace id, trace OpenTelemetry, metriche Prometheus, sonde di salute,
lavoro in background con Taskiq, Celery o ARQ e uno scheduler, Docker Compose e manifest
Kubernetes.

**Pensato per essere mantenuto con gli agenti di programmazione.**
Istruzioni, ruoli e skill di processo per Claude Code, Codex, Copilot e Cursor, più le skill
ufficiali di FastAPI, Pydantic, LangChain, Qdrant e dello stack React, scelte in base alle
vostre risposte.

## In sintesi

| Area | Cosa ha un progetto generato | Verificato da |
| --- | --- | --- |
| Tenancy | Row level security su ogni tabella; login applicativo separato; tenancy dei vettori | test di copertura delle tabelle e di attacco su PostgreSQL, test di tenancy del retrieval |
| Identità | Single sign-on OpenID Connect, Argon2id, API key con scope, identità dei workload di CI | test di accesso, API key e identità dei workload |
| API | Contratto OpenAPI versionato, controllo delle modifiche incompatibili, client generato, riferimento Scalar, errori RFC 9457 | controlli di disallineamento del contratto e del client nella pipeline |
| Sicurezza | Oscuramento dei log, chiavi dei dati ruotabili, traccia di audit, gitleaks, scansioni di dipendenze e immagini, SBOM | test-trappola sui log, test delle impostazioni di produzione, controlli della pipeline |
| Operatività | Log JSON, OpenTelemetry, Prometheus, sonde di salute, `make prod-local`, Compose con Traefik, Kubernetes | stack Compose risolti nei test |
| Lingue | Inglese e italiano in errori delle API, e-mail, interfaccia e documentazione | controlli dei cataloghi nella pipeline |

| Livello | Stack |
| --- | --- |
| Backend | Python 3.13, FastAPI, Pydantic 2, SQLAlchemy 2 (async), Alembic, PostgreSQL 16 |
| Lavoro in background | Taskiq, Celery o ARQ, con uno scheduler; Redis (Valkey) |
| Agenti e retrieval | Pydantic AI, LangGraph, LangChain, Deep Agents o Pydantic Deep; Qdrant o pgvector |
| Frontend | React, TypeScript, Vite, TanStack Router e Query, Tailwind CSS, shadcn/ui |
| Rilascio | Docker Compose, Traefik con Let's Encrypt, manifest Kubernetes, GitHub Actions o GitLab CI |
| Documentazione | Zensical, inglese e italiano, riferimento di API e impostazioni generato dal codice |

## Controlli di sicurezza

Un progetto generato implementa controlli richiesti da ISO/IEC 27001:2022 e SOC 2, ognuno
supportato da un file o da un test. Supporta un audit; non sostituisce i controlli
dell'organizzazione. La [mappa completa](docs/it/concepts/security-controls.md) elenca ogni
controllo, la sua evidenza e ciò che resta all'organizzazione.

| Controllo | ISO 27001 | SOC 2 | Evidenza |
| --- | --- | --- | --- |
| Segregazione dei tenant | A.8.3 | CC6.1, C1.1 | `tests/test_segregation_postgres.py` |
| Privilegio minimo | A.5.15, A.8.2 | CC6.3 | `tests/test_rbac_teams.py` |
| Autenticazione sicura | A.8.5, A.5.17 | CC6.1, CC6.2 | `tests/test_sso.py`, `tests/test_security.py` |
| Crittografia | A.8.24 | CC6.1, CC6.7 | `tests/test_data_encryption.py` |
| Prevenzione della fuga di dati | A.8.12 | CC6.7 | `tests/test_log_trap.py` |
| Log e traccia di audit | A.8.15 | CC7.2 | `app/core/audit.py`, `tests/test_observability.py` |
| Configurazione sicura | A.8.9 | CC7.1 | `tests/test_production_settings.py` |
| Gestione delle modifiche | A.8.32 | CC8.1 | controlli del contratto API e delle migrazioni |
| Gestione delle vulnerabilità | A.8.8 | CC7.1 | scansioni di dipendenze e immagini |
| Catena di fornitura | A.5.21 | CC6.8, CC9.2 | SBOM, skill degli agenti vincolate e scansionate |

## Avvio rapido

```bash
uvx copier copy --trust https://github.com/salvo8519/keelson my_service
cd my_service
cp backend/.env.example backend/.env
make dev
```

Keelson usa [Copier](https://copier.readthedocs.io): pone alcune domande, genera il progetto e
registra le risposte. Quando Keelson migliora, `uvx copier update --trust` porta le modifiche
nel vostro progetto e le unisce alle vostre, così un progetto non resta fermo alla versione da
cui è stato generato. Le domande e i loro valori predefiniti sono nel
[riferimento](docs/it/reference/questions.md).

## Cosa si sceglie

| Domanda | Opzioni |
| --- | --- |
| Frontend | React (Vite, TanStack, shadcn/ui), nessuno |
| Coda dei task | Taskiq, Celery, ARQ |
| Framework agentico | Pydantic AI, LangGraph, LangChain, Deep Agents, Pydantic Deep |
| Provider LLM | OpenAI, Anthropic, Google, OpenRouter, compatibile OpenAI (on-premise), tutti |
| Database vettoriale | Qdrant, pgvector, nessuno |
| CI | GitHub Actions, GitLab CI |
| Kubernetes | sì, no |

## Come è verificato

Ogni modifica al template genera progetti ed esegue i loro controlli: la suite del backend su
un PostgreSQL reale (segregazione del database e migrazioni incluse, dove un test saltato conta
come un fallimento), la build e le traduzioni del frontend, la build della documentazione, il
contratto API e il client generato. La revisione del codice su cui Keelson si basa ha trovato
difetti, tutti corretti con un test di regressione. Tra questi: commit falliti che arrivavano
al client come successi, token di accesso negli URL di reindirizzamento, un filtro dei log che
poteva stampare password, account collegati tramite indirizzi e-mail non verificati, e una
ricerca che restituiva documenti di un'altra organizzazione. [PROVENANCE.md](PROVENANCE.md)
elenca ogni modifica.

## Documentazione

Il sito della documentazione è costruito con Zensical in inglese e italiano: primi passi,
concetti (tenancy, accesso, API key, lingue, osservabilità), il riferimento di API e
impostazioni generato dal codice, e come Keelson è assemblato.

## Sviluppo del template

```bash
uv sync --all-groups
uv run just check            # stile, YAML, strumenti, traduzioni, test di rendering
uv run just test-generated   # genera i default ed esegue i controlli del progetto generato
uv run just skills           # installa le skill ufficiali dei componenti per gli agenti
```

Vedi [AGENTS.md](AGENTS.md) e [CONTRIBUTING.md](CONTRIBUTING.md).

## Basato su

Keelson poggia su due template open source e ne mantiene visibile il lavoro. Backend, worker e
livello agentico vengono dal
[Full-Stack AI Agent Template](https://github.com/vstorm-co/full-stack-ai-agent-template) di
Vstorm; il frontend React dal
[Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template)
ufficiale. Entrambi hanno licenza MIT. Keelson li importa a commit registrati, converte il
primo a Copier senza riscriverlo, e aggiunge i livelli di segregazione, identità, contratto,
sicurezza e lingue descritti sopra. [Come è assemblato Keelson](docs/it/concepts/assembly.md)
spiega il metodo.

## Licenza

Apache License 2.0 (vedi [LICENSE](LICENSE) e [NOTICE](NOTICE)). Gli avvisi dei due template
con licenza MIT sono in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) e vengono riportati in
ogni progetto generato. La licenza non concede alcun diritto di usare il nome o il logo di
Keelson.
