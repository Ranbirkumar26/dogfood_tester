"""Evaluation harness: dev tooling that scores agent runs against labeled ground truth.

Not shipped in the wheel (design D14, D9). Imports the installed website_agent package and
drives the same AgentRunner the CLI and API use, so measurements reflect shipping behavior.
"""
