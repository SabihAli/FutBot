# Snapshot Context Management for Cold-Context RAG Chatbots

A snapshot is a structured machine-readable state used to resume
conversations after old context is dropped.

## Principles

-   Store structured state, not prose.
-   Store references to retrieved knowledge, not documents.
-   Never store chain-of-thought.
-   Update only after meaningful state changes.

## Recommended JSON Schema

``` json
{
  "schema_version":1,
  "conversation_id":"...",
  "primary_goal":"",
  "current_intent":"",
  "conversation_stage":"",
  "facts":{},
  "filled_slots":{},
  "missing_slots":[],
  "constraints":[],
  "completed_actions":[],
  "pending_actions":[],
  "retrieval":{"topics":[],"document_ids":[]},
  "tools":{"last_tool":"","status":"","outputs":{}},
  "next_action":""
}
```

## Cold Context Recovery

1.  Load snapshot.
2.  Retrieve referenced knowledge.
3.  Add recent messages.
4.  Build prompt.

## Snapshot vs Summary

  Snapshot                   Summary
  -------------------------- -----------------------------
  Structured JSON            Natural-language prose
  Explicit state             Implicit state
  Deterministic              Requires LLM interpretation
  Best for agent execution   Best for continuity
