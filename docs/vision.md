# Vision

`paper-pipeline` is a local research-assistant pipeline for triaging academic papers with Zotero, LM Studio, runtime artifacts, and Obsidian handoff notes.

The next target is to evolve it from a paper-centered reading pipeline into an Obsidian + Zotero research assistant. In that target shape, Obsidian is the intention layer and Zotero is the evidence layer.

## Problem

Academic work is rarely a flat reading queue. A paper can be essential for one project, useful only as background for another, and irrelevant for a third. The system should therefore classify the relationship:

```text
project/objective <-> paper
```

The project or objective gives the question, scope, methods, gaps, and expected outputs. The paper gives bibliographic evidence, methods, claims, limitations, and possible implementation material.

## Why Obsidian Is Intention

Obsidian contains the user's evolving research context:

- active projects and objectives;
- study trails and learning goals;
- implementation plans;
- knowledge gaps;
- existing notes and links;
- human curation decisions.

The system should initially read this layer only. It should identify project profiles from explicit markers such as `#projeto` or frontmatter like `type: project` and `status: active`.

## Why Zotero Is Evidence

Zotero contains the bibliography:

- papers, books, theses, and PDFs;
- titles, abstracts, authors, years, DOI, collections, and tags;
- Better BibTeX citekeys from `Extra`;
- annotations and local PDF attachment paths when available.

The system should first export structured paper profiles without changing the library. Writing Zotero tags is a later, approval-gated step.

## Human Review Is Mandatory

LLMs can recommend, rank, summarize, and explain. They must not become the source of truth for library curation. The intended workflow is:

```text
system recommends -> user reviews -> user approves/rejects -> system applies approved decisions
```

This repository already has a human decision-note pattern in `paper_pipeline/decision_notes.py` and `paper_pipeline/decision_applier.py`. The future project-paper workflow should preserve that approval boundary.

## Risks To Avoid

- leaking Zotero API keys, user IDs, local paths, request payloads, or private note text;
- modifying a real Zotero library during exploratory runs;
- writing permanent Obsidian notes before the user approves;
- treating a paper-level score as project-specific utility;
- trusting malformed or unconstrained LLM JSON;
- reprocessing unchanged project-paper pairs without cache/history;
- inventing equations or conclusions during PDF analysis.

## MVP 0.1

The first project-specific MVP should be "triage without writing":

- read 3 to 5 project notes from a safe Obsidian fixture or explicit vault path;
- read metadata for 100 to 300 Zotero items through a mockable adapter/export;
- generate candidates by lexical or embedding similarity;
- classify top 10 papers per project using title, abstract, tags, and collections;
- export a Markdown review report;
- avoid Zotero writes, permanent Obsidian notes, and full PDF analysis.

