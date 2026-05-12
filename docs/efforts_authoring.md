# Efforts Authoring Guide

This guide explains how to structure notes under `Efforts/` so the Obsidian
inventory can extract better `ProjectProfile` rows with less ambiguity.

Concrete rewrite examples based on real notes are collected in
`docs/efforts_rewrite_examples.md`.

## Principle

The scanner works best when each effort note separates:

- what this effort is trying to achieve;
- how it is being approached;
- what is still unknown or blocked;
- what concrete outputs it should produce.

If those signals are implicit, spread across long prose, or mixed with logs and
checklists, recall drops quickly.

## Best-Recognized Signals

Use a real note title and one or more of the sections below.

Recommended sections:

- `## 🎯 Objetivo`
- `## Methods` or `## Como fazer`
- `## Knowledge Gaps` or `## Lacunas`
- `## 📤 Entregas / Outputs`

Also recognized in some note families:

- `## Outcome` or `## Outcome macro`
- `## Finalidade do documento`
- `## Pergunta central`
- `## Eixos metodológicos recorrentes`
- `## Sinais de alerta`
- `## Bloqueios / Dependências`

## Frontmatter

Helpful frontmatter fields:

```yaml
type: effort
effort_kind: project_hub
state: ongoing
priority: high
project_id: caracterizacao_probabilistica_de_solos
tags:
  - efforts
  - type/effort
  - efforts/ongoing
  - state/ongoing
```

Recommendations:

- Prefer `priority: high|medium|low`.
- Numeric priorities like `1|2|3` are supported.
- Letter priorities like `A|B|C` are supported.
- If you already know a stable machine id, set `project_id`.

## Writing Style

To improve extraction quality:

- Prefer one bullet per objective/output/method/gap.
- Keep bullets concise and self-contained.
- Put long explanation after the bullets, not instead of them.
- Keep logs in `## Log` or `## 📝 Log de progresso`, separate from semantic sections.
- Avoid using generic H1 titles like `# Objetivo` or `# Outcome` as the main
  note title.

Good:

```md
# Caracterização Probabilística de Solos

## 🎯 Objetivo
- Desenvolver uma linha de caracterização probabilística de solos a partir de CPTu.

## Como fazer
- Consolidar benchmark de Robertson.
- Comparar com krigagem e baseline determinístico.

## Lacunas
- Falta validar a integração com evidência geológica.
- Ainda não há baseline reproduzível para comparação regional.

## 📤 Entregas / Outputs
- Benchmark classificatório documentado.
- Benchmark espacial documentado.
- Draft de artigo metodológico.
```

Weak for extraction:

```md
# Objetivo

Texto longo misturando motivação, tarefas, histórico, riscos e entregas.
```

## Recommended Patterns By Note Type

### Active project or research effort

Use:

- `# <real project title>`
- `## 🎯 Objetivo`
- `## Como fazer`
- `## Lacunas`
- `## 📤 Entregas / Outputs`

### Operational or implementation effort

Use:

- `# <real effort title>`
- `## Outcome`
- `## Bloqueios / Dependências`
- `## Próxima ação`

If there is no separate objective section, make the `Outcome` bullet explicit
and concrete.

### Roadmap or portfolio hub

Use:

- `# <real roadmap title>`
- `## Finalidade do documento`
- `## Pergunta central`
- `## Eixos metodológicos recorrentes`
- `## Sinais de alerta`
- `## Outcome`

This gives the scanner a usable objective, method family, risk/gap list, and
expected outputs without having to infer them from long narrative sections.

## Common Problems

These patterns reduce recall or create noisy fields:

- using `# Objetivo` as the note title instead of the real effort name;
- placing objectives only inside long paragraphs with no semantic heading;
- using `## Horizonte e limites` as the only place where constraints appear;
- mixing outputs into logs or task lists;
- leaving placeholder bullets such as `-` under dependency or blocker sections;
- relying on `Definition of Done` alone without a separate outcome or objective.

## Minimal Template

```md
---
type: effort
effort_kind: project_hub
state: ongoing
priority: high
tags:
  - efforts
  - type/effort
  - efforts/ongoing
  - state/ongoing
---
# Real Project Title

## 🎯 Objetivo
- One clear purpose statement.

## Como fazer
- Main method or approach 1.
- Main method or approach 2.

## Lacunas
- Main uncertainty, blocker, or unresolved gap.

## 📤 Entregas / Outputs
- Concrete output 1.
- Concrete output 2.

## Próxima ação
- Immediate next step.

## 📝 Log de progresso
- Date-stamped work log.
```
