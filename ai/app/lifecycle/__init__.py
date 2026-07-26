"""Process lifecycle core shared by CLI and Electron."""

from .manifest import ServiceManifest
from .orchestrator import LifecycleOrchestrator

__all__ = ["ServiceManifest", "LifecycleOrchestrator"]
