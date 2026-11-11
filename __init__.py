"""Hermes loads this directory as the JobApps plugin."""

from .hermes_jobapps.plugin import register

__all__ = ["register"]
