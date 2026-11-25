<!-- i18n source: concepts/languages.md source_hash: ffc317fc753b -->
# Lingue

I progetti Keelstone parlano le lingue scelte con la domanda di Copier `languages` (l'inglese è
sempre incluso, l'italiano è la seconda lingua predefinita). Questa pagina spiega da dove viene
ogni lingua e come aggiungere un testo.

## Quale lingua viene usata

Il backend sceglie la lingua di ogni richiesta in quest'ordine, e vince la prima disponibile:

1. la preferenza salvata dall'utente (`locale`, modificabile dal profilo);
2. la lingua predefinita dell'organizzazione attiva (`default_locale`);
3. l'header `Accept-Language`, che il frontend invia con la lingua dell'interfaccia;
4. l'inglese.

La lingua vale per i messaggi di errore e per le email. Le email partono nella lingua salvata
dal destinatario quando è nota, altrimenti nella lingua della richiesta; gli inviti usano la
lingua predefinita dell'organizzazione, perché chi viene invitato può non avere ancora un
account.

## Errori

Ogni errore è un documento Problem Details (RFC 9457), servito come `application/problem+json`:

```json
{
  "type": "about:blank",
  "title": "Non autorizzato",
  "status": 401,
  "detail": "Non autenticato",
  "code": "AUTHENTICATION_ERROR",
  "request_id": "0f6c..."
}
```

`title` e `detail` sono tradotti e la risposta porta l'header `Content-Language`. I client
devono decidere in base a `code`, che non cambia con la lingua.

## Aggiungere o modificare un testo

| Dove | Come |
| --- | --- |
| Errori del backend | Si solleva una sottoclasse di `AppException` con un messaggio in inglese; il messaggio è la chiave. Per i testi definiti lontano da dove vengono mostrati si usa `N_()` e li si traduce con `gettext()`. Poi si esegue `make i18n-extract` e si traducono le nuove voci in `backend/app/locales/<lingua>/LC_MESSAGES/messages.po`. |
| Email | Ogni email ha un template inglese in `backend/emails/compiled/` e una traduzione in `backend/emails/compiled/<lingua>/` con gli stessi `[[segnaposto]]`. Se la traduzione manca, si usa l'inglese. |
| Frontend | Si scrive il testo inglese dentro `t("...")` (oppure `N_("...")` dove il testo è solo definito) e si aggiunge la traduzione in `frontend/src/locales/<lingua>.json`. |

I controlli falliscono su qualsiasi testo non tradotto: `make i18n-check` per i cataloghi del
backend, un test per i template delle email e `bun run i18n:check` per il frontend. Tutti e
tre girano in CI.

## L'interfaccia

Il selettore di lingua nella barra laterale cambia la lingua dell'interfaccia e la salva nel
profilo dell'utente, così email ed errori delle API la seguono. Il cambio di lingua ricarica la
pagina. Dopo l'accesso, l'interfaccia adotta la lingua salvata nel profilo.
