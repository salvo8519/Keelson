<!-- i18n source: concepts/sign-in-and-workload-identity.md source_hash: b6018599880d -->
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
rimuove i cookie.

Poiché un browser allega i cookie da solo, una richiesta autenticata da un cookie che modifica
qualcosa (qualsiasi metodo tranne GET, HEAD e OPTIONS), e una WebSocket aperta con un cookie,
deve provenire da un'origine elencata in `CORS_ORIGINS`; altrimenti viene rifiutata (cross-site
request forgery). I programmi (script, servizi, CI) inviano `Authorization: Bearer` o una API
key, che un browser non allega mai da solo, e non sono interessati.

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
   un URL, dove la cronologia del browser, i proxy e i log del server li conserverebbero.

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
momento: rimuovere un trust, spostarlo su un'altra organizzazione o togliergli degli scope vale
subito anche per le credenziali già emesse.
