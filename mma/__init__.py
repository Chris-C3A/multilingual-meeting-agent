"""multilingual-meeting-agent: from voice to action, beyond English."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("multilingual-meeting-agent")
except PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
