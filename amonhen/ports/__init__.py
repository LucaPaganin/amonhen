"""Ports: what the application needs from the outside, in its own words.

A port is written by the side that uses it. It names the operations the
application calls and the types and errors they speak, and it imports nothing
from the libraries or the providers that implement it: those are adapters, and
the composition root (`amonhen.composition`) picks one. See
`docs/architettura.md`, section 5.1.
"""
