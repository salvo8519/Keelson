<!-- i18n source: getting-started.md source_hash: 7eddfa2b3d51 -->
# Per iniziare

## Requisiti

- Docker, per avviare lo stack
- Python 3.13 e [uv](https://docs.astral.sh/uv/), per lavorare sul backend
- [Bun](https://bun.sh/), quando il progetto ha il frontend React

## Avviare lo stack

```bash
cp backend/.env.example backend/.env
make dev
```

`make dev` costruisce l'immagine del backend e avvia i servizi con Docker Compose. `make help`
elenca tutti i comandi.

## Lavorare sul backend

```bash
make install   # dipendenze del backend e hook di pre-commit
make test      # suite di test del backend
make lint      # lint e controllo dei tipi
```

I test che richiedono PostgreSQL (row level security, API key, migrazioni) usano il database
di `backend/.env` e si saltano da soli quando non è raggiungibile.

## Traduzioni

API, email e interfaccia seguono le [lingue](concepts/languages.md) del progetto.
`make i18n-check` fallisce su qualsiasi messaggio del backend senza traduzione; nel frontend fa
lo stesso `bun run i18n:check`.

## Documentazione

Questo sito è costruito con [Zensical](https://zensical.org) a partire da `docs/`: pagine
inglesi in `docs/en`, traduzioni in `docs/<lingua>`.

```bash
make docs          # tutte le edizioni, in modalità strict, con il riferimento di API e impostazioni
make docs-serve    # anteprima dal vivo; DOCS_LANG=it make docs-serve per l'edizione italiana
make docs-check    # traduzioni mancanti o non aggiornate
```

Le pagine di riferimento delle [API](reference/api.md) e delle
[impostazioni](reference/settings.md) vengono generate dal codice a ogni build, quindi non
possono restare indietro. Una pagina tradotta registra la versione della pagina inglese da cui è
stata tradotta: dopo aver tradotto si esegue
`python scripts/i18n.py stamp docs/<lingua>/<pagina>.md`. La CI costruisce il sito, fallisce su
link rotti e traduzioni non aggiornate e lo pubblica dal ramo principale.
