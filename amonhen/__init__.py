"""Personal finance monitoring: unified ledger, ingest and metrics.

Replaces the Actual Budget connector. The package owns its ledger (SQLite,
double-entry postings), its ingest pipeline (PSD2 sync plus manual export
import) and, in later phases, its own API and UI.
"""
