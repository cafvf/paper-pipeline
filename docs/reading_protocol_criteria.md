# Reading Protocol Criteria

This document converts `docs/Research Reading Protocol.md` into one local user's operational criteria for stage recommendations. Treat this protocol as a configurable local profile and example, not as a universal rule set. Future users or future versions may provide a different protocol profile with the same kind of criteria.

The protocol is secondary evidence for Zotero reading-stage movement. It complements project-paper utility; it does not replace project-by-project human decisions.

## Stage Vocabulary

The repository uses the current operational collection names:

- `.ToLook`: initial screening;
- `.To Revise`: deeper review and layer 2/3 extraction;
- `.ToDig`: deep reading, formulation, implementation, insight, and application work;
- `Expendable`: discard policy for items not useful after completed human review. If a matching Zotero collection does not exist, the sync plan may recommend creating it at the Zotero library root before moving items.

The protocol document uses equivalent conceptual labels:

- `TO LOOK` -> `.ToLook`;
- `TO REVIEW` -> `.To Revise`;
- `TO DIG` -> `.ToDig`.

## Gate 1: Keep For Review Consideration

This gate answers whether a captured paper has any screening trigger.

Trigger criteria:

- `active_keyword_in_title`: title contains an active keyword from current work;
- `problem_domain_aligned`: problem domain matches current study context;
- `monitored_author_or_venue`: author or journal/venue is monitored;
- `cited_by_deep_reference`: cited by a reference already studied deeply;
- `monitored_search_term`: found through a search term intentionally monitored;
- `review_reference_mining`: review paper likely provides filtered references.

Gate result: pass if at least one trigger is true.

Monitored authors, journals, and venues should come from a local configuration file, suggested as `configs/monitored_sources.yaml`.

## Gate 2: Move From `.ToLook` To `.To Revise`

This gate answers whether the paper deserves deeper review and literature-note-level treatment.

Original-paper criteria:

- `direct_relevance`: direct relevance to active/current work;
- `comparable_methodology`: identifiable and comparable methodology;
- `recent_or_seminal`: recent enough, or seminal/classic;
- `author_or_venue_credibility`: credible authors or venue;
- `explorable_gap`: signals a gap the user can explore;
- `citation_sentence_ready`: user can write the sentence for how the paper would be cited.

Review-paper substitutions:

- `comparable_methodology` becomes `explicit_review_strategy`: search strategy and inclusion/exclusion criteria are explicit;
- `citation_sentence_ready` can be satisfied by `background_citation_ready` or `reference_mining_use`.

Gate result:

- score each criterion as 1 for yes and 0 for no;
- pass if score is at least `3/6`.

The `author_or_venue_credibility` criterion should be human-fillable in review. If h-index or equivalent credibility evidence is unknown, the field should remain `unknown` rather than being guessed as true.

Stage recommendation:

- if current stage is `.ToLook` and at least one eligible project decision is or is likely to be approved, recommend `.To Revise`;
- if current stage is `.ToLook` and Gate 2 passes, recommend `.To Revise`;
- if current stage is `.To Revise` or `.ToDig`, Gate 2 is historical/context evidence and should not force demotion.

## Gate 3: Move To `.ToDig`

This gate answers whether the paper deserves deep study.

Original-paper criteria, all required:

- `new_method_for_toolkit`: method is new to the user's toolkit;
- `reproducible_equations_and_parameters`: equations, parameters, and conditions are explicit enough to reproduce;
- `validated_results`: results are validated against analytical solution, experiment, or field data;
- `domain_applicability`: applicable to the user's domain without major conceptual readaptation;
- `paper_section_value`: implementing or critiquing the work can generate a paper section.

Review-paper criteria, all required:

- `defines_state_of_art`: defines state of the art for an active subtopic;
- `identifies_actionable_gaps`: identifies explicit actionable gaps;
- `selective_and_transparent_review`: paper selection is careful and transparent, with bias risk addressed when relevant;
- `reference_mining_value`: references can feed `.ToLook`;
- `positions_extension_or_rebuttal`: positions the user for extension, narrowing, or rebuttal.

Gate result:

- pass for original papers only if all five original-paper criteria are true;
- pass for review papers only if all five review-paper criteria are true.

Additional high-adherence rule:

- recommend `.ToDig` if the maximum project-paper adherence score is at least `0.80`, even if Gate 3 is not fully confirmed yet;
- this threshold is initial and may be tuned later.

## Expendable Recommendation

Recommend `Expendable` only when:

- all project-level decisions for the paper are complete;
- all project-level decisions are `rejected`;
- no project-level decision is `approved`;
- no explicit human override keeps the item;
- protocol gates do not justify continued review.

The final move to `Expendable` is always human-approved. The system recommends; it does not discard automatically. When approved, the Zotero plan should add `!discarded`, remove mutually exclusive stage tags such as `@look`, `@review`, and `@dig`, remove the item from stage/triage collections such as `.ToLook`, `.To Revise`, and `.ToDig`, and move it to the root-level `Expendable` collection.

Local products for `Expendable` papers are preserved and may still contribute to future reference mining.

If any project-level decision is `pending`, the paper review remains incomplete. If any project-level decision is `deferred`, the paper is not automatically expendable; it should normally remain in the current stage or be handled manually.

## Tag Evidence From Protocol

The protocol's tag taxonomy can inform recommendations:

- `@look`, `@review`, `@dig` align with reading stages;
- `#topic` tags provide domain evidence;
- `%method` tags provide methodological evidence;
- `$use-tags` provide paper-writing use evidence;
- `!quality` tags provide caution or priority evidence.

These tags are evidence for review and stage recommendation. They are not a replacement for human approval.

Operational meaning:

- `@` tags indicate the current reading-stage position and must remain coherent with Zotero collection movement;
- official stage mapping is `.ToLook` -> `@look`, `.To Revise` -> `@review`, `.ToDig` -> `@dig`, and `Expendable` -> `!discarded`;
- approved stage changes should add the new `@` stage tag and remove the old mutually exclusive `@` stage tag;
- `$` tags indicate paper-use highlights such as background, gap signal, methods citation, discussion use, extension value, or manuscript-specific use. They are suggested at paper level in Zotero as the union of approved project-level uses;
- `#` and `%` tags are also keyword sources for matching and protocol evidence.

Tags should come from the reading protocol taxonomy. The system should not invent new `@`, `#`, `%`, `$`, or `!` tags without a deliberate taxonomy update.
