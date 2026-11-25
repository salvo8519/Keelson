<!-- i18n source: concepts/sign-in-and-workload-identity.md source_hash: 23dfade918a5 -->
# Accesso e identità dei workload

Le persone accedono con una password o tramite il provider di identità della propria azienda.
I job di CI e gli altri sistemi si autenticano con una API key oppure, senza alcun segreto
salvato, con l'identità che la loro piattaforma fornisce. Ogni percorso arriva allo stesso
punto: un principal a cui si applica la segregazione del database (vedi
[Tenancy e API key](tenancy-and-api-keys.md)).

## Password

Le password sono salvate come hash Argon2id. Gli hash delle versioni precedenti (bcrypt)
vengono verificati e sostituiti al login successivo. Un login con un indirizzo sconosciuto
esegue lo stesso lavoro di hashing, così i tempi di risposta non rivelano quali indirizzi sono
registrati.

Neanche la registrazione li rivela: risponde `202 Accepted` con lo stesso messaggio per un
indirizzo nuovo e per uno che ha già un account. Per un indirizzo noto non viene creato nulla,
e il suo titolare riceve un'e-mail con i link per accedere e per reimpostare la password. Un
accesso successivo con la password appena scelta distingue ancora un indirizzo noto da uno
nuovo: per chiudere anche questo serve la verifica dell'e-mail prima del primo accesso.

## Indirizzi e-mail

Un account registra se il suo utente ha dimostrato di controllare il proprio indirizzo
(`email_verified`): seguendo un link inviato a quell'indirizzo (una conferma, un reset della
password, un link di accesso) oppure accedendo con un provider che lo ha verificato. Un utente
cambia l'indirizzo in due passi: `POST /api/v1/users/me/email` invia un link di conferma al
nuovo indirizzo, e l'indirizzo cambia solo quando il link viene seguito
(`POST /api/v1/auth/email/confirm`). `PATCH /api/v1/users/me` non lo cambia, e rifiuta (422)
qualsiasi campo estraneo al profilo. Il link vale un'ora e una sola volta: indica l'indirizzo che
sostituisce e l'epoch dei link di accesso dell'account, che ogni cambio confermato alza, quindi
smette di funzionare quando l'indirizzo cambia, anche se poi torna quello di prima. Anche un
link di accesso usato nel frattempo alza l'epoch e quindi annulla un link di cambio in sospeso:
l'utente ne chiede uno nuovo. Il link decade anche dopo un cambio di password o un'uscita da
tutti i dispositivi. Un indirizzo impostato da un amministratore della
piattaforma non è confermato.

Una richiesta risponde `202 Accepted` con lo stesso messaggio per ogni indirizzo, quindi non
rivela quali indirizzi hanno un account in qualsiasi organizzazione. Un indirizzo già usato da
un altro account non riceve nulla, e il cambio viene rifiutato se il suo link viene comunque
seguito. L'indirizzo in vigore viene avvisato per e-mail di ogni richiesta (senza il link, che
va solo al nuovo indirizzo) e del cambio confermato, con le indicazioni su cosa fare se non è
stato il suo titolare. Le richieste sono limitate per utente (3 all'ora, categoria
`email_change`), oltre ai limiti della nuova autenticazione descritti sotto.

Una richiesta richiede inoltre che l'utente dimostri di nuovo la propria identità, così che una
sessione da sola (un cookie rubato, un computer lasciato sbloccato) non possa spostare l'account.
L'eliminazione dell'account, `DELETE /api/v1/users/me`, richiede la stessa prova. Un account con
una password la invia (`current_password`; se manca o è errata la risposta è `400`). Un account
senza password, che accede solo tramite single sign-on, ha bisogno di una sessione iniziata
negli ultimi 5 minuti: i token portano l'ora dell'accesso (`auth_time`), che il rinnovo della
sessione non cambia, e una sessione più vecchia viene rifiutata con `403` e il motivo
`recent_sign_in_required` (accedere di nuovo). Un'impersonificazione non conta mai come accesso
recente. `GET /api/v1/users/me` indica se l'account ha una password (`has_password`), così il
modulo del profilo e la finestra di eliminazione la chiedono oppure spiegano che serve un nuovo
accesso.

Ogni tentativo di dimostrare di nuovo l'identità, sul cambio di indirizzo, sul cambio password
(`PATCH /api/v1/users/me/password`) o sull'eliminazione, conta in un unico budget per utente (5
ogni 15 minuti) e in uno per IP del client (20 ogni 15 minuti), entrambi nella categoria
`reauth`: i tentativi su una route consumano quelli delle altre. Il budget dell'utente viene
verificato per primo, e l'indirizzo conta solo i tentativi che il suo utente poteva fare. Un
tentativo poi rifiutato dal limite dell'indirizzo conta comunque nel budget dell'utente: chi ha
in mano la sessione (un cookie rubato) può esaurirne i 5 tentativi e impedire al suo utente
queste modifiche per 15 minuti. È accettato, perché la sessione gli consente già
altrettanto. Queste route non contano nel limite delle route di accesso, così dietro uno stesso
indirizzo di rete gli errori di un utente non impediscono ai colleghi di accedere.

Anche i link di reset della password e i link di accesso indicano l'indirizzo a cui sono stati
inviati: quando l'indirizzo dell'account cambia, un link inviato al precedente non funziona più,
e un cambio confermato annulla anche tutti i link di accesso in sospeso. Un link vale una sola
volta anche quando viene usato due volte nello stesso momento: il secondo utilizzo attende il
primo e trova il link annullato.

Il token di un link inviato per e-mail viaggia nel frammento dell'URL
(`/reset-password#token=...`), che il browser non invia mai a un server, quindi resta fuori dai
log del web server e dalle intestazioni Referer. Le pagine del frontend lo tolgono dalla barra
degli indirizzi e dalla cronologia appena lo hanno letto, e leggono ancora la query string dei
link inviati in precedenza. Il frontend non ha una pagina per i link di accesso
(`/auth/magic-link`): un progetto che li offre costruisce quella pagina, che legge il frammento.

Le e-mail dell'account (benvenuto, avviso di una registrazione con un indirizzo già noto, link
di conferma, avvisi, link di reset e di accesso) partono dopo la richiesta, una volta confermata
la sua transazione e inviata la risposta (background task di FastAPI). Una richiesta che
fallisce non invia nulla, nessuna riga resta bloccata mentre un provider risponde, e il tempo
della risposta non dipende da quante e-mail la richiesta invia.

Il single sign-on si basa su questo: un account non resta mai su un indirizzo che il suo utente
non controlla, in attesa che il titolare di quell'indirizzo lo usi. Per gli account il cui
indirizzo non è mai stato confermato, un reset della password o un link di accesso inviato
all'indirizzo rimuove anche l'identità esterna dell'account, così chi la possiede non può più
accedervi. Gli account creati prima di questo controllo partono non confermati: un utente che
accede tramite un provider e reimposta la password accede poi con la password.

## La sessione nel browser

Nel browser, i token di accesso e di refresh sono cookie HttpOnly impostati dalle API: nessuno
script della pagina può leggerli, quindi uno script iniettato nella pagina non può rubare la
sessione.

| Cookie | Inviato a | Durata |
| --- | --- | --- |
| `access_token` | ogni richiesta alle API | quella del token di accesso (`ACCESS_TOKEN_EXPIRE_MINUTES`) |
| `refresh_token` | solo `/api/v1/auth/session` | quella del token di refresh (`REFRESH_TOKEN_EXPIRE_MINUTES`) |

Entrambi sono `SameSite=Lax`, e `Secure` fuori dallo sviluppo locale. Quando il token di
accesso scade, il frontend rinnova la sessione una volta dal cookie di refresh e ripete la
richiesta; i nuovi token sono impostati come cookie, mai restituiti alla pagina. L'uscita
rimuove i cookie e chiude la sessione (vedi sotto).

Poiché un browser allega i cookie da solo, una richiesta autenticata da un cookie che modifica
qualcosa (qualsiasi metodo tranne GET, HEAD e OPTIONS), e una WebSocket aperta con un cookie,
deve provenire da un'origine elencata in `CORS_ORIGINS`; altrimenti viene rifiutata (cross-site
request forgery). I programmi (script, servizi, CI) inviano `Authorization: Bearer` o una API
key, che un browser non allega mai da solo, e non sono interessati.

L'accesso e l'uscita impostano o rimuovono cookie prima che qualcuno sia autenticato, quindi
vengono rifiutati quando il browser indica un altro sito in `Origin` o `Referer`: una pagina
altrove non può far accedere il browser a un account scelto da lei (login CSRF). I programmi
non inviano nessuna delle due intestazioni.

## Chiusura delle sessioni

Ogni token di accesso e di refresh porta la versione di sessione del suo utente (`ver`, la
colonna `token_epoch`). Una richiesta, un refresh e l'apertura di una WebSocket vengono
rifiutati quando la versione del token non è quella corrente dell'utente. La versione viene
incrementata, chiudendo ogni sessione emessa prima, da:

- un cambio di password (il browser che lo ha fatto riceve nuovi cookie e resta collegato);
- un reset della password, e una password impostata da un amministratore della piattaforma;
- una disattivazione (un account riattivato non riottiene le vecchie sessioni);
- `POST /api/v1/auth/logout-all`, l'uscita da tutti i dispositivi.

Un accesso apre una sessione, con un id (`sid`) che ogni token di refresh della sessione porta
con sé. Un refresh ruota il token: il client riceve un nuovo token di refresh, e quello
presentato viene registrato in Redis come già scambiato. Un token scambiato una volta e
presentato di nuovo significa che qualcun altro ne ha una copia, quindi l'intera sessione si
chiude (rilevamento del riuso, RFC 9700, sezione 4.14.2) e ogni suo token viene rifiutato,
compreso l'ultimo. Le schede di uno stesso browser condividono il cookie di refresh e possono
rinnovare insieme: un token presentato di nuovo entro 10 secondi dal suo scambio
(`REUSE_GRACE`) viene rinnovato ancora una volta, nella stessa sessione. Il primo scambio viene
registrato in Redis in modo atomico e la finestra si misura con l'orologio di Redis, quindi
repliche delle API con orologi non allineati concordano, e due scambi nello stesso momento non
possono contare entrambi come primo. La scadenza di un token è fissata dall'orologio della
replica che lo ha emesso: un token scaduto secondo l'orologio di Redis viene rifiutato, e le
chiavi di un token gli sopravvivono di 5 minuti (`MAX_CLOCK_SKEW`). I token di refresh emessi
prima che le sessioni avessero un id vengono rifiutati: i loro utenti accedono di nuovo una
volta.

L'uscita (`POST /api/v1/auth/session/logout` nel browser, `POST /api/v1/auth/logout` con il
token di refresh per i programmi) chiude solo quella sessione, con tutti i token di refresh per
cui è passata con le rotazioni: l'id della sessione resta in Redis per la durata di un token di
refresh, e un refresh in quella sessione viene rifiutato. Un token copiato prima di una
rotazione si chiude quindi con la sessione. I token di accesso della sessione non sono
confrontati con l'elenco: scadono da soli, ed è per questo che `ACCESS_TOKEN_EXPIRE_MINUTES` non
può superare 60 in staging e in produzione. Quando Redis non risponde, un refresh fallisce
invece di rinnovare una sessione che potrebbe essere chiusa (vedi il guasto più sotto).

Una WebSocket verifica di nuovo la sua sessione prima di ogni turno di una chat: una connessione
la cui versione di sessione è cambiata dall'apertura, o il cui utente è stato disattivato, viene
chiusa (codice 4001).

La versione di sessione cresce soltanto: il database rifiuta un aggiornamento che abbassa
`token_epoch` (un trigger, `app/db/tenancy.py`), così nessuna scrittura può riportare in vita le
sessioni che ha chiuso. Lo stesso vale per `magic_link_epoch`, che annulla i link di
accesso e di cambio indirizzo.

Il rinnovo di una sessione è limitato per utente (20 ogni 15 minuti per impostazione
predefinita, categoria `refresh`), non per indirizzo: gli utenti dietro uno stesso indirizzo di
rete non condividono un limite tra loro né con gli accessi falliti. Un token di refresh non
valido conta nel limite per indirizzo delle route di accesso.

I limiti di frequenza sono contati in Redis. Quando Redis non risponde, le route che verificano
una password o una credenziale si chiudono: le route di accesso (categoria `auth`: accesso,
registrazione, richieste di link di reset e di accesso, conferma dell'indirizzo, token dei
workload, token di refresh non validi) e le route che chiedono la password attuale (categoria
`reauth`) rispondono `503` con il codice `RATE_LIMIT_UNAVAILABLE` e un'intestazione
`Retry-After`, e non verificano alcuna password, così che durante il guasto le password non
possano essere indovinate senza limiti. Le altre categorie restano aperte: le loro richieste
sono servite senza limite. Entrambi i casi sono registrati nel log come
`rate_limit_storage_unavailable`. I rifiuti di una API key restano registrati nel registro di
audit al massimo una volta al minuto per chiave, contati in ogni replica delle API finché Redis
non risponde.

Anche i registri dei token di refresh e i codici monouso del single sign-on sono in Redis,
quindi durante il guasto le sessioni non si rinnovano, le uscite non vengono registrate e il
single sign-on non si completa: un refresh e lo scambio di un codice di single sign-on
rispondono `503` con il codice `SESSION_STORE_UNAVAILABLE` e un'intestazione `Retry-After`.
Entrambe le route di uscita rispondono `503` con `revocation_recorded` a false: il token di
refresh resta valido fino alla scadenza. `POST /api/v1/auth/session/logout` rimuove comunque i
cookie del browser, che esce. I token di accesso continuano a funzionare fino alla scadenza (al
massimo 60 minuti in staging e in produzione), dopo di che i loro utenti accedono di nuovo
quando Redis risponde.

Un token di accesso emesso da un amministratore della piattaforma per agire come un utente
(impersonazione) indica l'amministratore e la sua versione di sessione nel claim `act`. Mentre
viene usato, ogni record di log riporta `acting_admin_id` e ogni voce del registro di audit lo
registra nei dettagli. Ogni richiesta, ogni apertura di WebSocket e ogni turno di una chat
verificano anche l'amministratore: il token smette di funzionare quando l'amministratore perde
il ruolo di piattaforma, viene disattivato o esce da tutti i dispositivi.

Le richieste autenticate da un cookie sono accettate solo dalle origini in `CORS_ORIGINS`.
Quando il browser invia l'intestazione `Origin`, decide da sola: `Origin: null` (un frame in
sandbox, un redirect tra siti) e un valore vuoto vengono rifiutati, qualunque cosa dica il
`Referer`. Il `Referer` viene letto solo quando non è stata inviata alcuna `Origin`.

## Single sign-on

Nella pagina di accesso si può offrire qualsiasi provider OpenID Connect: Google, Microsoft
Entra ID, Keycloak, Okta, Auth0 o un issuer aziendale. I provider si configurano a runtime,
come lista JSON in `OIDC_PROVIDERS`; una lista vuota disattiva il single sign-on. I progetti
generati senza frontend non lo includono.

| Campo | Significato |
| --- | --- |
| `name` | Identificativo negli URL e nell'identità dell'utente; non rinominare un provider in uso |
| `label` | Testo del pulsante nella pagina di accesso |
| `issuer` | URL dell'issuer del provider; i metadati sono letti da `/.well-known/openid-configuration` |
| `client_id`, `client_secret` | L'applicazione registrata presso il provider |
| `scopes` | Predefinito `openid email profile` |
| `trust_email` | `true` per una directory aziendale (Entra ID, Keycloak) che garantisce i propri indirizzi; richiede `email_domains` |
| `email_domains` | Facoltativo: solo questi domini possono accedere con questo provider |

Registrare presso il provider `<PUBLIC_API_URL>/api/v1/oauth/<name>/callback` come URI di
reindirizzamento.

```bash
OIDC_PROVIDERS='[
  {"name": "entra", "label": "Microsoft",
   "issuer": "https://login.microsoftonline.com/<tenant-id>/v2.0",
   "client_id": "...", "client_secret": "...", "trust_email": true,
   "email_domains": ["example.com"]},
  {"name": "keycloak", "label": "Account aziendale",
   "issuer": "https://sso.example.com/realms/<realm>",
   "client_id": "...", "client_secret": "...", "trust_email": true,
   "email_domains": ["example.com"]}
]'
```

`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` restano come scorciatoia per un provider Google.

Come funziona un accesso:

1. Il pulsante porta l'utente al provider (flusso authorization code con PKCE).
2. Il provider riporta indietro l'utente. L'ID token viene verificato: firma con le chiavi
   pubblicate dal provider, issuer, audience, scadenza e nonce.
3. L'utente viene trovato tramite l'identità del provider. La prima volta, l'indirizzo deve
   essere verificato dal provider (o provenire da una directory affidabile, per i suoi domini).
   Se nessun account ha quell'indirizzo, ne viene creato uno con un'organizzazione personale.
   Un account esistente viene collegato solo se non ha password, né un'altra identità, né un
   ruolo di piattaforma, e il token dichiara l'indirizzo verificato; altrimenti l'accesso è
   rifiutato e l'utente accede con la propria password. Un account non viene mai preso tramite
   un indirizzo registrato da qualcun altro.
4. Il browser torna al frontend con un codice valido una sola volta, per un minuto, e salvato
   solo come hash. Il frontend lo scambia con i token di sessione. I token non compaiono mai in
   un URL, dove la cronologia del browser, i proxy e i log del server li conserverebbero. Il
   codice funziona solo nel browser tornato dal provider, che ha ricevuto anche un breve cookie
   HttpOnly: un codice inviato a qualcun altro non fa accedere nessuno (login CSRF).

L'utente accede una sola volta, presso il provider. Autenticazione a più fattori, policy delle
password e blocco degli account sono quelli del provider.

## Identità dei workload per la CI

GitHub Actions e GitLab CI forniscono a ogni job un token di breve durata, firmato dal loro
issuer, che indica repository, branch e workflow. Un trust in `WORKLOAD_IDENTITIES` stabilisce
quali di questi token possono agire per quale organizzazione, con quali scope di API key. Il
job scambia il proprio token con una credenziale di queste API, valida per pochi minuti, e la
invia come una API key. Nessun segreto è salvato nella CI.

| Campo | Significato |
| --- | --- |
| `name` | Identificativo del trust, nei log |
| `issuer` | `https://token.actions.githubusercontent.com` o `https://gitlab.com` (o il vostro GitLab) |
| `audience` | L'audience richiesta dal job; usare l'URL di queste API |
| `claims` | Claim che devono corrispondere esattamente; almeno uno, come il repository. Preferire identificativi immutabili (`repository_id`, `project_id`): il nome di un repository può essere preso da un altro account dopo una rinomina, un trasferimento o una cancellazione |
| `organization_id` | L'organizzazione per cui il job agisce |
| `scopes` | Scope di API key della credenziale |
| `ttl_seconds` | Durata della credenziale, da 60 a 3600 (predefinito 900) |

```bash
WORKLOAD_IDENTITIES='[
  {"name": "deploy-main", "issuer": "https://token.actions.githubusercontent.com",
   "audience": "https://api.example.com",
   "claims": {"repository_id": "123456789", "ref": "refs/heads/main"},
   "organization_id": "<uuid>", "scopes": ["agent:run"]}
]'
```

GitHub Actions:

```yaml
permissions:
  id-token: write
steps:
  - name: Call the API as this workflow
    run: |
      oidc=$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
        "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=https://api.example.com" | jq -r .value)
      credential=$(curl -sSf -X POST https://api.example.com/api/v1/auth/workload-token \
        -H "Content-Type: application/json" -d "{\"token\": \"$oidc\"}" | jq -r .credential)
      curl -sSf -H "X-API-Key: $credential" https://api.example.com/api/v1/api-keys/introspect
```

GitLab CI:

```yaml
call-api:
  id_tokens:
    API_TOKEN:
      aud: https://api.example.com
  script:
    - credential=$(curl -sSf -X POST https://api.example.com/api/v1/auth/workload-token
        -H "Content-Type: application/json" -d "{\"token\": \"$API_TOKEN\"}" | jq -r .credential)
```

Per GitLab, i claim utili sono `project_id`, `ref`, `ref_protected` e `environment`.

Un token rifiutato riceve la stessa risposta qualunque sia il motivo; il motivo è nel log del
server. Ogni richiesta verifica la sua credenziale rispetto ai trust configurati in quel
momento: rimuovere un trust, spostarlo su un'altra organizzazione, cambiarne issuer, audience o
claim, accorciarne `ttl_seconds` oppure togliergli degli scope vale subito anche per le
credenziali già emesse.
