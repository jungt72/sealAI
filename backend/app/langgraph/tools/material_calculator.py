# MIGRATION: Phase-1/Phase-2 - Reine Tool-Signaturen + Validierung, mit Cache

from typing import Dict, Any
from pydantic import BaseModel
import hashlib
import json
import os
import redis

class MaterialCalculatorInput(BaseModel):
    material: str
    pressure: float
    temperature: float

class MaterialCalculatorOutput(BaseModel):
    result: float
    units: str

REDIS_URL = os.getenv("REDIS_URL")
CACHE_TTL = 3600

def _get_cache_key(input_data: dict) -> str:
    data_str = json.dumps(input_data, sort_keys=True)
    return f"tool:material_calculator:{hashlib.md5(data_str.encode()).hexdigest()}"

def material_calculator(input: MaterialCalculatorInput) -> MaterialCalculatorOutput:
    cache_key = _get_cache_key(input.dict())
    if REDIS_URL:
        r = redis.Redis.from_url(REDIS_URL)
        cached = r.get(cache_key)
        if cached:
            return MaterialCalculatorOutput.parse_raw(cached)
    # Dummy calculation
    result = input.pressure * input.temperature / 100
    output = MaterialCalculatorOutput(result=result, units="MPa")
    # Cache
    if REDIS_URL:
        r.setex(cache_key, CACHE_TTL, output.json())
    return output