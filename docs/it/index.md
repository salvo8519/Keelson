---
hide:
- navigation
- toc
source: index.md
source_hash: 0aa3498365f2
---
<div class="kl-hero" markdown>

![Keelson](assets/brand/mark.svg){ width="96" }

# Keelson

<p class="kl-tagline">Template FastAPI enterprise con livello agentico.</p>

<p class="kl-promise">Assemblato da due template open source collaudati, e migliorato dove si fermano.</p>

Keelson genera un servizio FastAPI pronto per le aziende: organizzazioni come tenant, utenti
che appartengono a più organizzazioni, lavoro asincrono e schedulato, un livello agentico con
retrieval, deploy su Docker e Kubernetes, e un processo di sviluppo pensato per gli agenti di
programmazione.

[Genera un progetto](getting-started/index.md){ .md-button .md-button--primary }
[Come è assemblato Keelson](concepts/assembly.md){ .md-button }

</div>

!!! note "Stato"
    Pre-release. Il template viene generato correttamente e il backend generato supera la sua
    suite di test. Le pagine descrivono ciò che esiste oggi; le note di rilascio elencano cosa
    cambia.

<div class="grid cards kl-features" markdown>

-   __Assemblato, non riscritto__

    ---

    Backend, worker e livello agentico vengono dal Full-Stack AI Agent Template di Vstorm; il
    frontend React dal Full Stack FastAPI Template ufficiale. Ogni import e ogni modifica sono
    registrati.

    [Assemblaggio](concepts/assembly.md)

-   __Un template, più stack__

    ---

    Scegli la coda dei task (Taskiq, Celery, ARQ), il framework agentico (Pydantic AI,
    LangGraph e altri), il provider LLM, il database vettoriale e il sistema di CI. Le risposte
    restano nel progetto, quindi `copier update` porta le versioni successive del template.

    [Domande](reference/questions.md)

-   __Pronto per l'esercizio__

    ---

    PostgreSQL con migrazioni, Redis, rate limiting, metriche Prometheus, Traefik con HTTPS,
    manifest Kubernetes e una pipeline GitLab o GitHub.

    [Architettura](concepts/architecture.md)

-   __Pensato per gli agenti__

    ---

    Istruzioni per gli agenti, ruoli, skill di processo e le skill ufficiali di FastAPI,
    Pydantic, LangChain, Qdrant e dello stack React, fissate a una versione e installate con un
    solo comando.

    [Skill per gli agenti](concepts/agent-skills.md)

</div>
