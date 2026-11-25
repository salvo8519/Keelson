<!-- i18n source: concepts/tenancy-and-api-keys.md source_hash: b925412aac85 -->
# Tenancy e API key

I progetti Keelson servono più organizzazioni con un solo deploy. Questa pagina spiega come
i loro dati restano separati e come gli altri sistemi ottengono l'accesso.

## Organizzazioni e organizzazione attiva

Ogni utente ha un'organizzazione personale e può appartenere ad altre, con un ruolo: owner,
admin, member o viewer. Il frontend permette di scegliere l'organizzazione attiva; ogni
richiesta la porta nell'header `X-Organization-Id`, e il backend verifica l'appartenenza prima
di usarla.

Il database separa i tenant in base all'appartenenza: le richieste di un utente possono leggere
le righe di tutte le organizzazioni a cui appartiene, qualunque sia quella attiva.
L'organizzazione attiva decide dove vanno i nuovi dati dell'organizzazione e cosa elencano le
schermate; non è un secondo confine tra le organizzazioni dell'utente. Fanno eccezione le API
key: una chiave agisce solo per la sua organizzazione.

## Isolamento nel database

È il database stesso a imporre la separazione, così un filtro dimenticato nel codice non può
esporre le righe di un altro tenant.

**Due login.** `POSTGRES_USER` è proprietario delle tabelle ed esegue le migrazioni. Le
richieste usano un secondo login, `POSTGRES_APP_USER`, creato dalle migrazioni: non possiede le
tabelle, non può aggirare la row level security e agisce tramite un ruolo ristretto.

**Chi agisce, in ogni transazione.** L'autenticazione stabilisce il principal della richiesta,
e ogni transazione del login applicativo lo scrive in impostazioni locali alla transazione:

| Principal | Impostato da | Vede |
| --- | --- | --- |
| Utente | un JWT o una sessione | le proprie righe, quelle delle sue organizzazioni, le persone con cui condivide un'organizzazione |
| Organizzazione | l'organizzazione attiva, dopo la verifica dell'appartenenza | dove vengono scritti i nuovi dati dell'organizzazione; il confine nel database resta l'appartenenza dell'utente |
| Servizio | una API key | i dati della sua organizzazione, non le conversazioni private dei membri; non può gestire le chiavi |
| Nessuno | nessuna autenticazione | niente: le policy falliscono in modo chiuso |

**Policy per tabella e comando.** I punti principali:

- una conversazione è privata del suo autore, salvo condivisione; owner e admin di
  un'organizzazione vedono gli aggregati (uso dei tool, valutazioni), mai le chat dei membri;
- i ruoli sono verificati anche nel database: solo owner e admin gestiscono API key, membri e
  inviti; un admin gestisce solo membri e viewer, il ruolo owner lo assegna un owner, e chi
  crea un'organizzazione ne diventa owner una sola volta;
- i viewer leggono le knowledge base, i documenti e le sorgenti di sincronizzazione di
  un'organizzazione; owner, admin e membri li modificano. Un documento si scrive solo con una
  knowledge base che l'utente può modificare, nella collezione di quella knowledge base,
  qualunque organizzazione indichi la riga;
- i documenti e le sorgenti di sincronizzazione di una knowledge base si leggono con la
  knowledge base, non con l'organizzazione registrata sulla riga: quelli di una knowledge base
  personale restano al suo proprietario, anche se un caricamento registra l'organizzazione
  attiva. Una sorgente di sincronizzazione alimenta solo una knowledge base che il suo autore
  può modificare;
- ciò che una riga concede non può essere riscritto dal login applicativo: i privilegi di
  colonna mantengono come sono stati creati il ruolo e il flag di amministratore di un utente,
  l'autore, l'organizzazione e il flag di demo pubblica di una conversazione, e l'autore di una
  condivisione. Né una riga può essere creata con ciò che concede solo il sistema: una
  conversazione non nasce come demo pubblica, una knowledge base come predefinita, un oggetto
  archiviato come migrazione di storage in corso;
- le tabelle sono aperte al login applicativo una alla volta, con le loro policy: una tabella
  creata in seguito, da una migrazione o dallo store pgvector a run time, resta chiusa finché
  una migrazione non la segrega;
- l'audit log è in sola aggiunta per l'applicazione: una voce indica il proprio autore e
  l'applicazione non può leggerla, modificarla o cancellarla.

**Sessioni di sistema.** Il lavoro che non ha ancora un utente o attraversa più tenant usa il
login proprietario tramite `system_session(reason)`, e ogni uso è registrato con la sua
motivazione sul logger `app.db.system`: accesso, registrazione e ricerche per token,
l'amministrazione della piattaforma (dopo la verifica dell'admin, con il suo nome), la riga di
comando e i worker in background. I worker agiscono su più organizzazioni per costruzione,
quindi il loro codice filtra in modo esplicito.

**Test.** Le policy sono elencate in `app/db/tenancy.py`. Un test fallisce quando una tabella non
è coperta da una policy né chiusa con una motivazione, così una nuova tabella non può essere
dimenticata. I test di attacco girano su un PostgreSQL reale con il login applicativo: nessun
principal, un altro utente, un'altra organizzazione, un membro contro i dati di un owner,
scritture falsificate e una API key.

**Limiti.** Il principal è impostato dall'applicazione sulla propria connessione. Un'SQL
injection nel login applicativo potrebbe cambiare quelle impostazioni e agire come qualcun
altro; la difesa è quella che il codice già segue (SQLAlchemy con parametri vincolati, nessuna
SQL costruita dall'input). Un contesto firmato dall'applicazione e verificato nel database
eliminerebbe questo limite ed è un possibile passo futuro.

## Knowledge base e vettori

Una knowledge base è personale (solo il proprietario), di un'organizzazione (i suoi membri) o
dell'applicazione (tutti gli utenti). Chi legge una knowledge base non è chi la modifica: una
personale la modifica il proprietario, una di un'organizzazione i suoi owner, admin e membri,
e quelle dell'applicazione solo gli amministratori della piattaforma, attraverso la sessione di
sistema, perché ogni tenant le legge. Una collezione appartiene a una sola knowledge base (un
indice univoco), e le colonne che ne decidono il tenant (scope, organizzazione, proprietario,
collezione) non possono essere modificate dal login applicativo.

La vector store non ha una propria row level security, quindi ha due barriere:

1. **Quali collezioni.** Una ricerca raggiunge solo le collezioni delle knowledge base che
   l'utente vede nell'organizzazione attiva; a qualsiasi altro nome risponde che non esiste.
   L'agente risolve le sue collezioni sul server a partire dalla conversazione, mai dal modello
   o dal client, e scarta un'organizzazione di cui l'utente non è più membro.
2. **Quali vettori.** Ogni vettore porta il tenant della sua knowledge base (`user:<id>`,
   `org:<id>` o `app`) e ogni ricerca dichiara i tenant del suo lettore: un filtro in Qdrant
   (un indice di tenant, il pattern di multitenancy di Qdrant), una clausola `WHERE` in
   pgvector. Una ricerca senza lettore non restituisce nulla. Solo la riga di comando, per
   l'amministrazione, può cercare in tutti i tenant.

Eliminare un documento ne elimina i vettori, ed eliminare una knowledge base ne elimina i
documenti e la collezione: il contenuto eliminato non è più recuperabile. Un documento
eliminato mentre è in ingestione non ha ancora vettori; il worker rimuove i vettori che ha
scritto quando trova il documento eliminato. La sincronizzazione
locale (`POST /rag/sync/local`) legge solo dentro `RAG_LOCAL_SYNC_ROOT` e alimenta solo le
knowledge base dell'applicazione; senza questa impostazione è rifiutata in staging e
produzione.

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

Una richiesta autenticata da una chiave agisce come principal di servizio dell'organizzazione
della chiave (vedi la tabella sopra), sotto row level security come una richiesta di un utente. Per proteggere una route con una chiave:

```python
from fastapi import Depends

from app.api.deps import CurrentApiKey, require_api_scopes


@router.post("/agent/run", dependencies=[Depends(require_api_scopes("agent:run"))])
async def run(principal: CurrentApiKey) -> ...:
    ...
```

I nuovi scope si aggiungono a `SCOPES` in `app/core/api_keys.py`, con una descrizione mostrata
nell'interfaccia.
