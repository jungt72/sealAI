# MIGRATION: Phase-2 - Resolver deterministisch

from ..state import SealAIState, MetaInfo
from ..nodes.resolver import resolver

def test_resolver_determinism():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    state = SealAIState(meta=meta, routing={"domains": ["material"], "confidence": 0.8})
    
    result1 = resolver(state)
    result2 = resolver(state)
    # Assert same output
    assert result1 == result2