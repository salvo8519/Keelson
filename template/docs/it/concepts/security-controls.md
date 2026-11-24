<!-- i18n source: concepts/security-controls.md source_hash: 4945958a00a6 -->
# Controlli di sicurezza e conformità

Questa pagina collega i controlli della ISO/IEC 27001:2022 (Annex A) e i Trust Services
Criteria di SOC 2 a ciò che un progetto generato implementa, e al file o al test che lo
dimostra. È materiale per un audit, non una certificazione: la ISO 27001 certifica il sistema
di gestione di un'organizzazione e SOC 2 riferisce sui controlli di un'organizzazione. Il
software supporta i controlli elencati; l'organizzazione che lo esegue resta responsabile del
resto (ultima sezione).

Ogni riga indica la sua evidenza. I test girano nella pipeline del progetto, quindi l'evidenza
è verificata a ogni modifica, non scritta una volta sola.

## Controllo degli accessi e identità

| Controllo | ISO 27001 | SOC 2 | Cosa fa il progetto | Evidenza |
| --- | --- | --- | --- | --- |
| Segregazione dei tenant | A.8.3 | CC6.1, C1.1 | Row level security di PostgreSQL su ogni tabella, per un login applicativo che non possiede nulla e non può aggirarla; senza un principal nessuna riga è visibile | `app/db/tenancy.py`, `tests/test_segregation_postgres.py` |
| Privilegio minimo | A.5.15, A.8.2 | CC6.3 | Ruoli dell'organizzazione verificati nel database oltre che nel codice; API key limitate agli scope; conversazioni dei membri private anche per gli amministratori | `app/db/tenancy.py`, `tests/test_rbac_teams.py`, `tests/test_api_keys_postgres.py` |
| Accessi privilegiati | A.8.2 | CC6.1 | Il lavoro fuori dalla row level security passa da `system_session(reason)` sul login proprietario, e ogni uso è registrato con la sua motivazione | `app/db/session.py` (logger `app.db.system`) |
| Tenancy del retrieval | A.8.3 | C1.1 | Ogni vettore porta il proprio tenant; una ricerca senza lettore non restituisce nulla | `app/services/rag/tenancy.py`, `tests/test_rag_tenancy.py`, `tests/test_rag_search_scope.py` |
| Autenticazione | A.8.5 | CC6.1, CC6.2 | Single sign-on con OpenID Connect (flusso authorization code con PKCE, ID token verificato, account abbinati solo tramite indirizzi verificati); nessun token negli URL | `app/core/oidc.py`, `tests/test_sso.py` |
| Informazioni di autenticazione | A.5.17 | CC6.1 | Password salvate come hash Argon2id, hash precedenti aggiornati all'accesso; il tempo di accesso non rivela gli indirizzi registrati; segreti delle API key salvati come hash con chiave | `app/core/security.py`, `app/core/api_keys.py`, `tests/test_security.py`, `tests/test_services.py` |
| Identità delle macchine | A.5.16, A.8.5 | CC6.2 | I job di CI si autenticano con il token OpenID Connect della loro piattaforma rispetto a un trust configurato (issuer, audience, repository, branch); le credenziali scadono entro un'ora | `app/core/workload_identity.py`, `tests/test_workload_identity.py` |
| Ciclo di vita delle API key | A.5.18 | CC6.2 | Per organizzazione, con scope, scadenza, rotazione con periodo di tolleranza, revoca e limiti di frequenza | `app/services/api_key.py`, `tests/test_api_keys.py` |

## Crittografia e protezione dei dati

| Controllo | ISO 27001 | SOC 2 | Cosa fa il progetto | Evidenza |
| --- | --- | --- | --- | --- |
| Segreti a riposo | A.8.24 | CC6.1, C1.1 | Credenziali dei connettori e token cifrati con chiavi dedicate e ruotabili (`DATA_ENCRYPTION_KEYS`), separate dalla chiave che firma i token | `app/core/crypto.py`, `tests/test_data_encryption.py` |
| Fuga di dati nei log | A.8.12 | CC6.7 | Messaggi, campi extra e testo delle eccezioni oscurati; campi con nomi da segreto scartati; parametri SQL nascosti fuori dalla modalità debug | `app/core/logging.py`, `tests/test_log_trap.py` |
| Fuga di dati nelle API | A.8.12 | CC6.7 | Note dei manutentori escluse dal riferimento API pubblicato | `tests/test_openapi_contract.py` |
| Trasporto | A.8.24 | CC6.7 | TLS terminato da Traefik con Let's Encrypt nello stack di produzione, con HSTS; Content Security Policy e gli altri header di sicurezza su API e frontend | `docker-compose.prod.yml`, `app/core/middleware.py`, `frontend/security-headers.conf` (con un frontend) |

## Log, monitoraggio e registrazioni

| Controllo | ISO 27001 | SOC 2 | Cosa fa il progetto | Evidenza |
| --- | --- | --- | --- | --- |
| Registrazione degli eventi | A.8.15 | CC7.2 | Log JSON con request id, trace id e span id | `app/core/logging.py`, `tests/test_observability.py` |
| Traccia di audit | A.8.15, A.5.33 | CC7.2 | Creazione, rotazione, revoca e usi rifiutati delle API key registrati; l'applicazione può aggiungere voci ma non leggerle, modificarle o cancellarle; un'azione che non si può registrare viene annullata | `app/core/audit.py`, `tests/test_segregation_postgres.py` |
| Monitoraggio | A.8.16 | CC7.2 | Metriche Prometheus, trace OpenTelemetry, sonde di liveness e readiness | `app/core/telemetry.py`, `app/api/routes/v1/health.py` |

## Sviluppo, modifiche e catena di fornitura

| Controllo | ISO 27001 | SOC 2 | Cosa fa il progetto | Evidenza |
| --- | --- | --- | --- | --- |
| Configurazione sicura | A.8.9 | CC7.1 | Un avvio in produzione rifiuta i valori di sviluppo dei segreti | `app/core/config.py`, `tests/test_production_settings.py` |
| Gestione delle modifiche | A.8.32 | CC8.1 | Il contratto API è versionato; disallineamenti e modifiche incompatibili fanno fallire la pipeline; migrazioni testate in avanti e indietro | `scripts/openapi.py`, `tests/test_migrations.py`, workflow di CI |
| Codice sicuro | A.8.28 | CC8.1 | Regole di lint di sicurezza (Ruff `S`, da Bandit) con eccezioni motivate | `backend/pyproject.toml` |
| Test di sicurezza | A.8.29 | CC7.1 | Test di attacco su un PostgreSQL reale, test-trappola sui log, test di autenticazione | i test citati sopra |
| Vulnerabilità tecniche | A.8.8 | CC7.1 | Verifica delle dipendenze (pip-audit, e bun audit con un frontend), scansione dell'immagine del container (Trivy); un fallimento ferma la pipeline | workflow di CI |
| Segreti nel repository | A.8.12 | CC6.1 | L'intera storia è scansionata alla ricerca di segreti (gitleaks) | workflow di CI |
| Catena di fornitura | A.5.21 | CC6.8, CC9.2 | Distinta dei componenti software (CycloneDX); skill degli agenti vincolate al digest del contenuto e scansionate prima dell'installazione | workflow di CI, `scripts/agent_skills.py`, `skills.lock.toml` |

## Cosa resta all'organizzazione

Il software non copre, e un auditor chiederà di:

- policy, valutazione dei rischi, ruoli e formazione (ISO 27001 clausole da 4 a 10, Annex A.5
  e A.6);
- revisioni degli accessi, ingressi e uscite del personale nel provider di identità,
  autenticazione a più fattori (configurata presso il provider usato per il single sign-on);
- conservazione e rotazione dei segreti in produzione (un secret manager invece di file),
  custodia delle chiavi `DATA_ENCRYPTION_KEYS`;
- backup, prove di ripristino e continuità operativa (A.8.13, A.5.30; disponibilità in SOC 2);
- conservazione dei log, allarmi e risposta agli incidenti (da A.5.24 a A.5.28; SOC 2 da CC7.3
  a CC7.5);
- penetration test e valutazione dei fornitori di modelli e di hosting.
