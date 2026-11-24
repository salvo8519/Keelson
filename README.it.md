<!-- i18n source: README.md source_hash: 23acece8e1d3 -->
<p align="center">
  <img src="docs/_shared/assets/brand/mark.svg" alt="Keelson" width="96">
</p>

<h1 align="center">Keelson</h1>

<p align="center"><strong>Template FastAPI enterprise con livello agentico.</strong><br>
Assemblato da due template open source collaudati, e migliorato dove si fermano.</p>

<p align="center">
  <img alt="Stato: pre-release" src="https://img.shields.io/badge/status-pre--release-0B1F3A">
  <img alt="Licenza: Apache-2.0" src="https://img.shields.io/badge/licence-Apache--2.0-0B1F3A">
  <img alt="Copier" src="https://img.shields.io/badge/generator-Copier-C8A24A">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-0B1F3A">
  <img alt="Documentazione: inglese e italiano" src="https://img.shields.io/badge/docs-EN%20%7C%20IT-0B1F3A">
</p>

[English](README.md) | Italiano

Keelson genera un servizio FastAPI pronto per le aziende: organizzazioni come tenant, utenti
che appartengono a più organizzazioni, lavoro asincrono e schedulato, un livello agentico con
retrieval, deploy su Docker e Kubernetes, e un processo di sviluppo pensato per gli agenti di
programmazione.

## Perché Keelson

- **Assemblato, non riscritto.** Backend, worker e livello agentico vengono dal
  [Full-Stack AI Agent Template](https://github.com/vstorm-co/full-stack-ai-agent-template)
  di Vstorm; il frontend React dal
  [Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template)
  ufficiale. [PROVENANCE.md](PROVENANCE.md) registra ogni import, commit e modifica.
- **Conversione verificata.** Il template cookiecutter upstream gira con Copier senza essere
  riscritto: il suo stesso generatore deriva le variabili di ogni combinazione valida di
  risposte, e il progetto generato viene confrontato file per file con quello upstream.
- **Difetti corretti all'import.** L'audit del codice importato ha trovato e corretto un import
  circolare che bloccava all'avvio i progetti con Taskiq e uno scheduler mancante su
  Kubernetes, ciascuno con un test di regressione.
- **Pensato per gli agenti.** Istruzioni, ruoli e skill di processo, più le skill ufficiali di
  FastAPI, Pydantic, LangChain, Qdrant e dello stack React, scelte in base alle risposte e
  fissate a una versione.

## Avvio rapido

```bash
uvx copier copy --trust https://gitlab.com/salvo8519/keelson my_service
cd my_service
cp backend/.env.example backend/.env
make dev
```

Le domande e i valori predefiniti sono nel
[riferimento](docs/it/reference/questions.md). Le versioni successive del template si portano
nel progetto con `uvx copier update --trust`.

## Cosa scegli

| Domanda | Opzioni |
| --- | --- |
| Frontend | React (Vite, TanStack, shadcn/ui), nessuno |
| Coda dei task | Taskiq, Celery, ARQ |
| Framework agentico | Pydantic AI, LangGraph, LangChain, Deep Agents, Pydantic Deep |
| Provider LLM | OpenAI, Anthropic, Google, OpenRouter, compatibile OpenAI (on-premise), tutti |
| Database vettoriale | Qdrant, pgvector, nessuno |
| CI | GitLab CI, GitHub Actions |
| Kubernetes | sì, no |

## Documentazione

Il sito della documentazione è costruito con Zensical, in inglese e in italiano: primi passi,
architettura di un progetto generato, come è assemblato Keelson, skill per gli agenti.

## Sviluppo del template

```bash
uv sync --all-groups
uv run just check            # stile, YAML, strumenti, traduzioni, test di generazione
uv run just test-generated   # genera il progetto predefinito ed esegue la suite del backend
uv run just skills           # installa le skill ufficiali dei componenti per gli agenti
```

Vedi [AGENTS.md](AGENTS.md) e [CONTRIBUTING.md](CONTRIBUTING.md).

## Licenza

Apache License 2.0 (vedi [LICENSE](LICENSE) e [NOTICE](NOTICE)). Keelson include codice da due
template con licenza MIT; le loro note sono in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
e vengono riportate in ogni progetto generato. La licenza non concede diritti sull'uso del nome
o del logo Keelson.
