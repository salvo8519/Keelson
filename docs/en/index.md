---
hide:
  - navigation
  - toc
---

<div class="kl-hero" markdown>

![Keelson](assets/brand/mark.svg){ width="96" }

# Keelson

<p class="kl-tagline">Enterprise FastAPI template with an agent layer.</p>

<p class="kl-promise">Assembled from two proven open source templates, and improved where they stop.</p>

Keelson generates a FastAPI service ready for companies: organizations as tenants, users who
belong to several of them, asynchronous and scheduled work, an agent layer with retrieval,
deployment on Docker and Kubernetes, and a development process for coding agents.

[Generate a project](getting-started/index.md){ .md-button .md-button--primary }
[How Keelson is assembled](concepts/assembly.md){ .md-button }

</div>

!!! note "Status"
    Pre-release. The template renders and the generated backend passes its test suite. The
    pages state what exists today; the release notes list what changes.

<div class="grid cards kl-features" markdown>

-   __Assembled, not rewritten__

    ---

    The backend, workers and agent layer come from the Full-Stack AI Agent Template by
    Vstorm; the React frontend from the official Full Stack FastAPI Template. Every import and
    every change is recorded.

    [Assembly](concepts/assembly.md)

-   __One template, several stacks__

    ---

    Choose the task queue (Taskiq, Celery, ARQ), the agent framework (Pydantic AI, LangGraph
    and others), the LLM provider, the vector database and the CI system. The answers stay in
    the project, so `copier update` brings later template versions.

    [Questions](reference/questions.md)

-   __Ready for operations__

    ---

    PostgreSQL with migrations, Redis, rate limiting, Prometheus metrics, Traefik with HTTPS,
    Kubernetes manifests, and a GitHub or GitLab pipeline.

    [Architecture](concepts/architecture.md)

-   __Built for coding agents__

    ---

    Instructions for agents, roles, process skills, and the official skills of FastAPI,
    Pydantic, LangChain, Qdrant and the React stack, pinned and installed with one command.

    [Agent skills](concepts/agent-skills.md)

</div>
