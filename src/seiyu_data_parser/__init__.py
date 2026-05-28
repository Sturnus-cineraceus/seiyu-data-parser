__version__ = "0.1.0"

# re-export common submodules. expose both the wiki extractors and the template extractor.
from . import cli, io, wikistream, extract, template_extract

__all__ = ["cli", "io", "wikistream", "extract", "template_extract", "__main__"]
