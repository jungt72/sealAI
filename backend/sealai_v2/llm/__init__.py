"""llm — the thin LLM I/O adapter (build-spec §12: dünne Adapter).

The ONLY place that touches a provider SDK. ``openai`` is imported lazily inside the
factory so importing the rest of ``sealai_v2`` (and the offline test/CI path) never needs
the SDK. The pure generator (``core``) depends only on the ``LlmClient`` Protocol.
"""
