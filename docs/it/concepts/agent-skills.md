---
source: concepts/agent-skills.md
source_hash: 75b10dcaac08
---
# Skill per gli agenti

Gli agenti di programmazione lavorano meglio su una libreria quando leggono indicazioni scritte
da chi la mantiene. Keelson installa quelle skill, e solo quelle, per i componenti usati dal
progetto.

## Cosa viene installato

Il file `skills.lock.toml` elenca le skill del progetto generato. Viene generato dalle tue
risposte: un progetto con Qdrant riceve le skill di Qdrant, un progetto senza frontend non
riceve skill React.

| Componente | Skill | Manutentore |
| --- | --- | --- |
| FastAPI | `fastapi` | FastAPI |
| Pydantic | `pydantic` | Pydantic |
| Pydantic AI | `building-pydantic-ai-agents` | Pydantic |
| LangChain, LangGraph, Deep Agents | `langchain-build-agent` | LangChain |
| Logfire | `logfire-instrumentation` | Pydantic |
| Qdrant | `qdrant-clients-sdk`, `qdrant-multitenancy`, `qdrant-search-quality` | Qdrant |
| React | `vercel-react-best-practices`, `vercel-composition-patterns` | Vercel |
| shadcn/ui | `shadcn` | shadcn |

## Due tipi di fonte

- **Pacchetto**: la skill è distribuita dentro il pacchetto Python installato (la convenzione
  [Library Skills](https://library-skills.io) usata da FastAPI e Pydantic AI). Corrisponde
  sempre alla versione installata.
- **Git**: la skill si trova nel repository del manutentore ed è fissata a un commit.

Ogni skill viene letta prima di essere aggiunta al lock. La skill `shadcn` esegue
`npx shadcn@latest info --json` quando viene caricata: un comando in sola lettura che descrive
il progetto.

## Comandi

```bash
python scripts/agent_skills.py install   # installa o aggiorna
python scripts/agent_skills.py check     # fallisce se un'installazione manca o è cambiata
python scripts/agent_skills.py list      # cosa dichiara il lock
```

Le skill installate finiscono in `.agents/skills/` e `.claude/skills/` e si escludono da sole
da git: quello che si committa è il lock.
