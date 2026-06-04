# Mutation Policy V7

MutationPolicy controls whether a turn may affect case state.

## Values

| Policy | Meaning |
|---|---|
| forbidden | No case mutation. Use for smalltalk, meta, pure side questions, and answer-only knowledge. |
| proposed | A possible technical fact exists. Store/propose as candidate or ask for confirmation. |
| allowed_by_validator | Backend validator may apply the value after deterministic validation. |
| correction | User corrects earlier information. Trigger conflict/stale/recompute handling. |

## Mapping

| User Turn | Policy |
|---|---|
| `Danke` | forbidden |
| `Warum fragst du das?` | forbidden |
| `Was ist FKM?` | forbidden |
| `Wasser` after medium question | allowed_by_validator |
| `Chlor` after medium question | proposed or allowed_by_validator with needs_clarification |
| `Bei uns ist die Welle geschliffen.` | proposed |
| `Eigentlich ist es statisch.` | correction |

## Rule

The router may suggest MutationPolicy, but backend policy validates it. No LLM directly confirms fields or final suitability.
