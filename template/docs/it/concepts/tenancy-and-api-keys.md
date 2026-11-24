<!-- i18n source: concepts/tenancy-and-api-keys.md source_hash: 287ba2a53d73 -->
# Tenancy e API key

I progetti Keelson servono più organizzazioni con un solo deploy. Questa pagina spiega come
i loro dati restano separati e come gli altri sistemi ottengono l'accesso.

## Organizzazioni e organizzazione attiva

Ogni utente ha un'organizzazione personale e può appartenere ad altre, con un ruolo: owner,
admin, member o viewer. Il frontend permette di scegliere l'organizzazione attiva; ogni
richiesta la porta nell'header `X-Organization-Id`, e il backend verifica l'appartenenza prima
di usarla.

## Isolamento nel database

I repository filtrano le query per organizzazione. La row level security di PostgreSQL aggiunge
una seconda barriera, indipendente:

- quando una richiesta ha risolto la sua organizzazione attiva, la sua sessione del database
  viene legata a quell'organizzazione;
- ogni transazione di una sessione legata gira con un ruolo ristretto, le cui policy mostrano e
  accettano solo le righe di quell'organizzazione;
- una query che dimentica il filtro non restituisce nulla delle altre organizzazioni, e un
  inserimento per un'altra organizzazione viene rifiutato dal database.

Le tabelle isolate sono elencate in `app/db/tenancy.py`. Un test fallisce quando una tabella con
una colonna `organization_id` non è né isolata né esentata con una motivazione, così una nuova
tabella non può essere dimenticata.

## Knowledge base e vettori

Una knowledge base è personale (solo il proprietario), di un'organizzazione (i suoi membri) o
dell'applicazione (tutti gli utenti). La vector store non ha una propria row level security,
quindi ha due barriere:

1. **Quali collezioni.** Una ricerca raggiunge solo le collezioni delle knowledge base che
   l'utente vede nell'organizzazione attiva; a qualsiasi altro nome risponde che non esiste.
   L'agente risolve le sue collezioni sul server a partire dalla conversazione, mai dal modello
   o dal client, e scarta un'organizzazione di cui l'utente non è più membro.
2. **Quali vettori.** Ogni vettore porta il tenant della sua knowledge base (`user:<id>`,
   `org:<id>` o `app`) e ogni ricerca dichiara i tenant del suo lettore: un filtro in Qdrant
   (un indice di tenant, il pattern di multitenancy di Qdrant), una clausola `WHERE` in
   pgvector. Una ricerca senza lettore non restituisce nulla. Solo la riga di comando, per
   l'amministrazione, può cercare in tutti i tenant.

## API key

Un'organizzazione può creare chiavi per altri sistemi. Owner e amministratori le gestiscono
nella pagina API keys o su `/api/v1/api-keys`.

| Proprietà | Come funziona |
| --- | --- |
| Formato | `key_` e 12 caratteri (il prefisso, mostrato nell'interfaccia) seguiti da un segreto |
| Conservazione | Solo un HMAC del segreto con la `SECRET_KEY` del server; il token è mostrato una volta |
| Scope | Ogni chiave ha un insieme di scope; le route li richiedono con `require_api_scopes` |
| Scadenza | Data facoltativa dopo la quale la chiave smette di funzionare |
| Rotazione | Una chiave sostitutiva con gli stessi scope; la vecchia funziona per un periodo di grazia |
| Revoca | Immediata |
| Limiti | Le richieste sono limitate per chiave e per organizzazione |
| Audit | Creazione, rotazione, revoca e usi rifiutati sono registrati nell'audit log |

Una richiesta autenticata da una chiave agisce sull'organizzazione della chiave, con la stessa
row level security di una richiesta di un utente. Per proteggere una route con una chiave:

```python
from fastapi import Depends

from app.api.deps import CurrentApiKey, require_api_scopes


@router.post("/agent/run", dependencies=[Depends(require_api_scopes("agent:run"))])
async def run(principal: CurrentApiKey) -> ...:
    ...
```

I nuovi scope si aggiungono a `SCOPES` in `app/core/api_keys.py`, con una descrizione mostrata
nell'interfaccia.
