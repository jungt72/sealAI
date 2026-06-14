"""security — Tenant-Scoping (P0), unvertraute Inhalte, Injection-Guards (build-spec §3/§12).

Tenant-scoping is non-negotiable (build-spec §12): this stub must never become a
tenant-bypass. Vector-store filters are server-side only; tenant scope is a
mandatory repository-layer parameter.
"""
