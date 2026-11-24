<!-- i18n source: concepts/sign-in-and-workload-identity.md source_hash: 699ed6188617 -->
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
| `trust_email` | `true` per una directory aziendale (Entra ID, Keycloak) che garantisce i propri indirizzi |
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
   "client_id": "...", "client_secret": "...", "trust_email": true}
]'
```

`GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` restano come scorciatoia per un provider Google.

Come funziona un accesso:

1. Il pulsante porta l'utente al provider (flusso authorization code con PKCE).
2. Il provider riporta indietro l'utente. L'ID token viene verificato: firma con le chiavi
   pubblicate dal provider, issuer, audience, scadenza e nonce.
3. L'utente viene trovato tramite l'identità del provider o, la prima volta, tramite
   l'indirizzo e-mail. Un indirizzo è accettato solo se il provider lo indica come verificato,
   o se il provider è una directory affidabile: altrimenti chiunque potrebbe aprire un account
   presso un provider con l'indirizzo di un altro e accedere al suo posto. Un nuovo utente
   riceve un'organizzazione personale.
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
| `claims` | Claim che devono corrispondere esattamente; almeno uno, come il repository |
| `organization_id` | L'organizzazione per cui il job agisce |
| `scopes` | Scope di API key della credenziale |
| `ttl_seconds` | Durata della credenziale, da 60 a 3600 (predefinito 900) |

```bash
WORKLOAD_IDENTITIES='[
  {"name": "deploy-main", "issuer": "https://token.actions.githubusercontent.com",
   "audience": "https://api.example.com",
   "claims": {"repository": "acme/service", "ref": "refs/heads/main"},
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

Per GitLab, i claim utili sono `project_path`, `ref`, `ref_protected` e `environment`.

Un token rifiutato riceve la stessa risposta qualunque sia il motivo; il motivo è nel log del
server. Rimuovere un trust blocca subito le nuove credenziali; quelle già emesse scadono alla
fine della loro durata.
