---
source: concepts/api-reference-and-observability.md
source_hash: dac1c1b4cb87
---
# Riferimento API e osservabilità

## Riferimento API

`/docs` serve il riferimento delle API con [Scalar](https://scalar.com), personalizzato con le
risposte di Copier `brand_name` e `brand_primary_color`: titolo della pagina, favicon (lo
stesso marchio del frontend), colore di accento, nessun link al fornitore. Swagger UI e ReDoc
sono disattivati. Il riferimento e `openapi.json` esistono in `local`, `development` e
`staging`, non in `production`.

La pagina non fa chiamate a terzi. Telemetria, agente AI, font ospitati, proxy delle richieste
e pulsante che apre il client di Scalar sono disattivati, e la pagina ha una propria Content
Security Policy, costruita dall'HTML generato: script solo dal bundle di Scalar fissato e dallo
script inline della pagina (tramite hash), connessioni solo verso l'API stessa.

Il bundle arriva da jsDelivr, fissato a una versione esatta in `API_DOCS_SCALAR_JS_URL`. Per le
installazioni senza accesso a internet si serve una copia di
`@scalar/api-reference/dist/browser/standalone.js` dalla propria infrastruttura e si punta lì
l'impostazione: la policy la segue.

## Log

I log sono righe JSON sullo standard output, pronte per Loki, Elasticsearch o CloudWatch
(`LOG_FORMAT=text` per il terminale). Ogni record riporta `timestamp`, `level`, `logger`,
`message`, gli eventuali campi passati con `extra=`, il `request_id` della richiesta HTTP e,
con il tracing attivo, `trace_id` e `span_id`. Indirizzi email, token e password vengono
oscurati per ogni logger.

Il `request_id` è l'header di risposta `X-Request-ID` e il campo `request_id` degli errori
Problem Details: un errore segnalato da un client porta alle sue righe di log. Un request id
inviato dal client viene mantenuto solo se è un identificatore semplice (lettere, cifre,
`._:-`, al massimo 128 caratteri).

## Tracce

Con `OTEL_EXPORTER_OTLP_ENDPOINT` impostato (per esempio `http://otel-collector:4318`) le
tracce vengono esportate via OTLP/HTTP verso qualsiasi backend OpenTelemetry: richieste in
arrivo (esclusi health check e metriche), query SQL, chiamate httpx in uscita e comandi Redis.
`OTEL_TRACES_SAMPLE_RATIO` campiona una quota delle tracce, seguendo la decisione del
chiamante quando la richiesta ne porta una. Senza endpoint non viene strumentato nulla.

I progetti generati con `logfire` usano invece Logfire per il tracing, anch'esso basato su
OpenTelemetry.

## Metriche

`/metrics` espone metriche Prometheus: numero e latenza delle richieste per route, più le
metriche standard del processo. Con `PROMETHEUS_AUTH_TOKEN` l'endpoint richiede un bearer
token, utile quando è raggiungibile dall'esterno.

## Header di sicurezza

Ogni risposta riporta una Content Security Policy, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy` e `Permissions-Policy`.
