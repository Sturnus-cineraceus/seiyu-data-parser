import bz2
from typing import IO

def open_bz2(path: str) -> IO[bytes]:
    """
    Open a .bz2 file and return a binary file-like object suitable for xml parsing.
    """
    return bz2.open(path, mode="rb")
