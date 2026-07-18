# Context-bound follow-up resolution v1

## Trust invariant

A technical follow-up may reach retrieval or generation only when every
contextual reference needed by the request has been resolved to canonical,
user-authored domain entities.  Fluency is never evidence of a valid reference.

For comparisons this means:

1. exactly two same-type subjects are required;
2. subjects may come only from explicit user turns in the tenant/session-scoped
   working window;
3. assistant text is never an entity source;
4. the canonical request, not the ambiguous surface text, is supplied to
   retrieval, answer planning, generation, output guards and verification;
5. zero, one, more than two or mixed-type candidates produce a deterministic
   clarification without retrieval or an LLM call.

The canonical request retains the complete current user turn, including values,
application qualifiers and failure descriptions, and appends only the resolved
subject binding.  Reference resolution therefore cannot downgrade leakage,
RFQ, risk or engineering hard-gates.

## Supported subject namespaces

- sealing materials and compound families;
- seal types;
- media from the governed compatibility vocabulary.

The resolver reuses the same canonical vocabularies as answer planning.  No
parallel alias list is maintained in the conversation layer.

## Model boundary

The current high-confidence cases are resolved deterministically from typed
entities.  A future semantic reference parser may select only opaque candidate
IDs supplied by this layer.  It must use strict structured output, may not
invent entities, and cannot bypass the exact-two/same-type validation or the
clarification outcome.

## Rollback

The behavior ships with the backend image and remains bounded by the existing
execution-policy release profile.  Rolling back the backend image restores the
previous resolver.  No data migration is required.
