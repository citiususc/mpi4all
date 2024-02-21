import importlib.metadata

try:
    __version__ = importlib.metadata.version('MPI4All')
except:
    __version__ = "dev"
