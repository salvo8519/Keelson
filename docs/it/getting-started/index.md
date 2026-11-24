---
source: getting-started/index.md
source_hash: 64645fe930e4
---
# Generare un progetto

## Requisiti

- Python 3.12 o successivo, e [uv](https://docs.astral.sh/uv/)
- Git
- Docker, per avviare lo stack generato
- [Bun](https://bun.sh/), quando il progetto ha il frontend React

## Generare

Copier pone le domande elencate nel [riferimento](../reference/questions.md). L'opzione
`--trust` consente a Copier di eseguire il task finale che rimuove i file esclusi dalle tue
risposte e formatta il codice.

```bash
uvx copier copy --trust https://gitlab.com/salvo8519/keelson my_service
```

Per accettare tutti i valori predefiniti aggiungi `--defaults`. Per fornire le risposte senza
domande aggiungi `--data chiave=valore` per ciascuna, per esempio `--data task_backend=celery`.

## Avviare

```bash
cd my_service
cp backend/.env.example backend/.env
make dev
```

`make dev` costruisce le immagini, avvia i servizi e applica le migrazioni del database. La
documentazione delle API è poi su `http://localhost:8000/docs`. `make help` elenca tutti i
comandi.

## Installare le skill per gli agenti

```bash
cd backend && uv sync && cd ..
python scripts/agent_skills.py install
```

Le skill dei componenti scelti vengono installate per Claude Code, Codex e gli altri agenti
che leggono `.agents/skills/`. Vedi [Skill per gli agenti](../concepts/agent-skills.md).

## Aggiornare da una versione più recente di Keelson

Il file `.copier-answers.yml` registra la versione del template e le tue risposte. Per portare
nel progetto una versione più recente del template:

```bash
uvx copier update --trust
```

Copier applica le modifiche del template con un merge a tre vie insieme alle tue modifiche.
