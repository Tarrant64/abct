"""
ABCT V2 Ingestion Engine

A staged pipeline for multi-chain transaction ingestion and portfolio reconstruction.

Architecture: 6-Stage Pipeline
    Wallet → [A] Expand → [B] Index (txids) → [C] Hydrate (full tx)
          → [D] Normalize (events) → [E] Enrich (prices) → [F] Positions (DeFi)

Each stage produces work units stored in the DB. Providers are interchangeable
per work unit. If Provider A rate-limits, remaining work units are reassigned
to Provider B — no restart.
"""
