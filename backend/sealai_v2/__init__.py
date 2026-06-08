"""sealai_v2 — green-field V2.0 package (Option B coexistence; build-spec §3).

Phase-0 scaffold only: an additive, off-by-default sibling of ``app`` that holds
no behaviour yet. Modules fill in milestone order (M1..M6). Hard boundary: nothing
here may import ``app.*`` and nothing under ``app.*`` may import ``sealai_v2.*``
(enforced by backend/tests/architecture/test_v2_import_boundary.py).
"""
