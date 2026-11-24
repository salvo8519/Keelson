<!-- i18n source: reference/api.md source_hash: d4b7e57aedd7 -->
# API

Tutti gli endpoint delle API, raggruppati per tag, generati dal codice a ogni build di questo
sito. Il riferimento interattivo, con gli schemi e le richieste da inviare, è su `/docs` di
un'istanza avviata (ambienti local, development e staging). Gli errori seguono il
[formato Problem Details](../concepts/languages.md#errori).

## Il contratto

Il documento OpenAPI è conservato nel repository, in `openapi/openapi.json`, e pubblicato con
questo sito in `/openapi.json`. È il contratto delle API:

| Passo | Cosa succede |
| --- | --- |
| Esportazione | `cd backend && uv run python ../scripts/openapi.py export` lo scrive dal codice, con le impostazioni predefinite, così è uguale su ogni macchina |
| Revisione | Una modifica alle API compare nella pull request come modifica di questo file |
| Disallineamento | La pipeline fallisce quando il file non corrisponde al codice (`openapi.py check`) |
| Modifiche incompatibili | La pipeline lo confronta con il branch di destinazione tramite oasdiff e fallisce su una modifica incompatibile |
| Client | Il client del frontend è generato da questo file (`scripts/generate-client.sh`), e la pipeline fallisce quando il client nel repository non è aggiornato |
| Versione | `info.version` è la versione del pacchetto backend in `backend/pyproject.toml` |

Una modifica incompatibile (un endpoint o un campo rimosso, un nuovo parametro obbligatorio, un
tipo più ristretto) va in una nuova versione delle API con un nuovo prefisso, come `/api/v2`,
mentre `/api/v1` continua a funzionare finché i suoi client non sono passati alla nuova.

--8<-- ".generated/docs/it/reference/api.md"
