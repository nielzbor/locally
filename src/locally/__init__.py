from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("locally")
except PackageNotFoundError:
    __version__ = "unknown"
