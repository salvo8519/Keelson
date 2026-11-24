---
source: concepts/assembly.md
source_hash: 1e8d8dd43735
---
# Come è assemblato Keelson

Keelson non riscrive ciò che due template open source maturi fanno già bene. Li importa,
registra cosa ha importato e aggiunge ciò che serve a un progetto enterprise e che loro non
coprono.

## Fonti

| Fonte | Licenza | Cosa prende Keelson |
| --- | --- | --- |
| Full-Stack AI Agent Template (Vstorm) | MIT | Backend, organizzazioni e ruoli, worker e scheduler, framework agentici, retrieval, Docker, Kubernetes, CI, strumenti di progetto |
| Full Stack FastAPI Template (FastAPI) | MIT | Frontend React |

I commit, la procedura di import e ogni modifica che Keelson aggiunge sono registrati in
[Provenance](https://salvo8519.gitlab.io/keelson/project/provenance/) (in inglese).

## Da cookiecutter a Copier

Il template del backend upstream è un template cookiecutter con circa duecento variabili,
derivate dal suo generatore a partire da poche scelte. Keelson mantiene quei file così come
sono e li esegue con Copier, che registra le risposte nel progetto e può aggiornarlo in
seguito.

Neanche la derivazione viene riscritta. Uno script esegue il generatore upstream su ogni
combinazione valida delle domande di Keelson, più di tremila, e scrive ogni variabile upstream
come costante o come tabella sulle poche domande che la determinano. Con le risposte
predefinite, il progetto generato da Copier viene confrontato file per file con quello del
generatore upstream: le uniche differenze sono quelle volute.

## Cosa aggiunge Keelson

- I difetti trovati nell'audit del codice importato sono corretti e coperti da test; l'elenco
  è in [Provenance](https://salvo8519.gitlab.io/keelson/project/provenance/).
- Una traccia delle licenze: i progetti generati contengono `NOTICE` e
  `THIRD_PARTY_NOTICES.md`.
- Stile della casa: niente emoji né icone nei file generati.
- Le skill ufficiali dei componenti, scelte in base alle risposte
  ([Skill per gli agenti](agent-skills.md)).
- Test di generazione su una matrice di risposte, e un test end-to-end che esegue la suite del
  backend generato.
