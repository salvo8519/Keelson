---
source: concepts/document-storage.md
source_hash: 156ccb113cb1
---
# Archiviazione dei documenti

I documenti delle knowledge base e i file allegati in chat sono oggetti archiviati. Il
database registra di chi è ogni oggetto, dove si trovano i suoi byte e quale hash devono
avere; i byte risiedono in un backend di archiviazione. Documenti e file della chat fanno
riferimento a un oggetto tramite il suo id, mai tramite un percorso.

## Backend

Un unico punto di accesso (`app/services/file_storage.py`) offre due backend intercambiabili:

| Backend | Dove vanno i byte | Uso |
| --- | --- | --- |
| `local` | Sotto `MEDIA_DIR`, sul disco del server | Sviluppo, un solo server |
| `s3` | Un bucket di qualsiasi servizio compatibile S3: Garage, AWS S3, Cloudflare R2, Ceph, MinIO | Produzione, più server, Kubernetes |

`STORAGE_BACKEND` sceglie il backend dei nuovi oggetti. Se non è impostato, il backend è `s3`
quando è impostato `S3_ENDPOINT` o `S3_ACCESS_KEY`, altrimenti `local`. Ogni oggetto registra
il proprio backend, quindi gli oggetti scritti prima di un cambio restano leggibili dove sono
finché non vengono migrati.

| Impostazione | Predefinito | Significato |
| --- | --- | --- |
| `S3_ENDPOINT` | AWS | Endpoint del servizio S3 |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | vuoto | Credenziali, solo dall'ambiente; mai scritte nei log |
| `S3_BUCKET` | il nome del progetto con i trattini | Bucket degli oggetti |
| `S3_REGION` | `us-east-1` | Regione (`garage` per Garage) |
| `S3_ADDRESSING_STYLE` | `auto` | `path` per Garage, MinIO e Ceph senza DNS wildcard |

Gli avatar di utenti e organizzazioni non sono oggetti archiviati: restano sul disco locale.

## Chiavi e proprietà

Ogni oggetto ha esattamente un proprietario, un'organizzazione o un utente, e la sua chiave
ne deriva:

- `org/<organization_id>/<object_id>` per un oggetto di un'organizzazione: documenti delle
  knowledge base dell'organizzazione e documenti caricati da un amministratore;
- `user/<user_id>/<object_id>` per un oggetto personale: file della chat e documenti delle
  knowledge base personali.

La chiave non deriva mai dal contenuto. Due tenant che caricano lo stesso file ottengono due
oggetti: un archivio condiviso per contenuto rivelerebbe a un tenant che un altro possiede un
file, e legherebbe la cancellazione dei dati di un tenant a quelli degli altri. Il prefisso
del proprietario rende semplice anche la cancellazione: il contenuto di un utente o di
un'organizzazione eliminati è tutto ciò che sta sotto il suo prefisso.

Gli id degli oggetti sono UUID casuali di versione 4.

## Chi può leggere un oggetto

La tabella `stored_objects` è sotto row level security come ogni altra tabella (vedi
[Tenancy e API key](tenancy-and-api-keys.md)). Un oggetto personale è visibile solo al suo
utente; un oggetto di un'organizzazione ai membri dell'organizzazione e alle sue API key.
Un altro utente o un'altra organizzazione non può leggerlo, elencarlo, modificarlo o
eliminarlo, né creare un oggetto a nome di altri: la riga viene scritta prima dei byte, quindi
il database rifiuta il caricamento prima che qualcosa venga archiviato.

I download passano dall'API. La route trova il documento o il file della chat, poi legge
l'oggetto attraverso la sessione della richiesta: un oggetto che il principal non può vedere
risulta inesistente. Il contenuto viene poi trasmesso in streaming dal backend. Con
`S3_PRESIGNED_DOWNLOADS=true`, a un oggetto su S3 si risponde invece con un redirect a un URL
prefirmato valido per `S3_PRESIGN_TTL_SECONDS` (cinque minuti per impostazione predefinita),
emesso solo dopo lo stesso controllo; `S3_ENDPOINT` deve allora essere raggiungibile dal
browser.

## Integrità

Lo SHA-256 di un oggetto viene calcolato durante la scrittura, a blocchi: nessun backend
legge un file intero in memoria, e il limite di dimensione viene applicato strada facendo,
quindi un caricamento troppo grande non lascia nulla. Gli oggetti più grandi di una parte
(8 MiB) vengono inviati a S3 come upload multipart; un upload che fallisce viene annullato.

L'hash serve all'integrità, non alla deduplicazione: una migrazione verifica ogni copia
rispetto a esso.

## Spostare gli oggetti su un altro backend

Per passare dal disco locale a S3 (o viceversa):

1. Configurare la destinazione e impostare `STORAGE_BACKEND` su di essa, così i nuovi
   caricamenti vanno lì.
2. Eseguire `uv run <project> cmd migrate-storage --from local --to s3`. Il comando scorre gli
   oggetti dell'origine a lotti (`--batch-size`, `--limit`) e accoda un task per oggetto sui
   worker; `--inline` copia invece nel processo del comando.
3. Ogni task segna l'oggetto come in migrazione, lo copia in streaming, rilegge la copia e ne
   confronta lo SHA-256 con quello registrato, poi fa puntare l'oggetto alla copia in una sola
   transazione. I lettori non vengono mai bloccati: fino al cambio leggono l'originale.
4. Eseguire `uv run <project> cmd storage-cleanup` (gira anche ogni giorno sui worker) per
   rimuovere le copie rimaste sull'origine.

Una copia che non corrisponde all'hash viene eliminata e l'oggetto resta dov'era. Gli oggetti
registrati prima che esistessero gli oggetti archiviati non hanno ancora un hash: la
migrazione lo calcola.

La pulizia rimuove anche gli oggetti a cui nessun documento o file della chat fa più
riferimento e, con la riconciliazione (predefinita), il contenuto sotto `org/` e `user/` che
nessun oggetto registra: byte di un caricamento la cui transazione è stata annullata, e il
contenuto di utenti e organizzazioni eliminati. Il contenuto più recente di 24 ore non viene
toccato, perché un caricamento potrebbe essere ancora in corso.

## Garage in Docker Compose

Gli stack Compose di sviluppo e di produzione eseguono [Garage](https://garagehq.deuxfleurs.fr),
un archivio di oggetti compatibile S3 di Deuxfleurs, in un container proprio, fissato a una
release:

- `garage/garage.toml` configura un nodo con una copia di ogni oggetto. Non contiene segreti:
  Garage legge `GARAGE_RPC_SECRET` e `GARAGE_ADMIN_TOKEN` dal proprio ambiente.
- `garage-init` esegue `cmd garage-bootstrap` a ogni avvio: tramite l'API di amministrazione
  di Garage assegna al nodo un ruolo nel layout, importa la chiave dell'applicazione, crea il
  bucket e concede alla chiave l'accesso. Ogni passo già fatto viene saltato. L'API attende
  che finisca.
- `garage/storage.env` indirizza l'API e i worker verso Garage. Le chiavi vengono da
  `garage/development.env` in sviluppo (valori pubblicati, solo per la macchina di uno
  sviluppatore), da `.env.prod-local` con `make prod-local` (generate a caso), e da
  `backend/.env` in produzione, dove `GARAGE_RPC_SECRET`, `GARAGE_ADMIN_TOKEN`,
  `S3_ACCESS_KEY` e `S3_SECRET_KEY` sono obbligatori. Garage importa le chiavi nel proprio
  formato: `GK` seguito da 24 cifre esadecimali, e un segreto di 64 cifre esadecimali.

I manifest Kubernetes non installano alcun archivio di oggetti: si aspettano un servizio
esterno compatibile S3, configurato nella ConfigMap e nel Secret.

### Licenza di Garage

Garage è distribuito con la GNU Affero General Public License versione 3. Il progetto lo
esegue come servizio separato, senza modifiche, e comunica con esso tramite il protocollo S3;
non collega né include il codice di Garage, quindi la licenza del progetto non ne è toccata.
Gli obblighi dell'AGPL, cioè offrire il codice sorgente agli utenti del servizio, valgono per
chi modifica Garage e ne fa usare la versione modificata ad altri attraverso una rete.
Qualsiasi altro servizio compatibile S3 può prenderne il posto senza modifiche al codice.

## Limiti

- Una copia interrotta non viene ripresa: l'upload multipart parziale viene annullato e
  l'esecuzione successiva copia di nuovo l'oggetto dall'inizio. Una migrazione interrotta da
  un crash viene ripresa dopo un'ora. Sui bucket S3 è consigliata una regola di lifecycle che
  rimuova gli upload multipart incompleti.
- L'originale di un documento in una knowledge base condivisa con tutta l'applicazione
  appartiene all'organizzazione che l'ha caricato: gli utenti di altre organizzazioni possono
  cercare nel documento ma non scaricarne l'originale.
- Riportare il database a prima della migrazione che ha introdotto gli oggetti archiviati
  richiede che ogni oggetto sia sul disco locale.
