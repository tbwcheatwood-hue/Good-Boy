"""Good Boy — a voice-driven, cross-platform meta-orchestrator.

``__version__`` is the Good Boy release. ``ENGINE_LINEAGE`` is the upstream
engine this tree was cut from. Install paths and the keyring name stay on
the older identity so an existing data directory is not orphaned.
"""

__version__ = "1.2.0"
ENGINE_LINEAGE = "3.1.1"

# Every httpx client in the process shares one parsed CA bundle instead of
# re-parsing it (~200 ms of CPU) per client. Patches httpx lazily, the moment
# it is first imported; importing ``jarvis`` itself still loads nothing heavy.
from jarvis.core.shared_tls import install_when_imported as _install_shared_tls

_install_shared_tls()
del _install_shared_tls
