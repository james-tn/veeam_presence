"""Veeam Presence — data query tools.

Lazy package — does NOT import submodules at package level to avoid
pulling in pandas/numpy on every import. Callers should import directly:
    from tools.query_office_intel import query_office_intel
    from tools.query_person import query_person
"""
