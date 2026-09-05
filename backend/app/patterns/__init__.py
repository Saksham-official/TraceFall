"""Pattern detection.

Importing this package registers every detector. `base.REGISTRY` is populated by the
decorators in `detectors`, so a caller that imports only `base` gets an empty registry —
which is how the pipeline came to run the PATTERNS stage with no detectors at all and
report "0 findings" as though it had looked.
"""

from app.patterns import detectors as detectors  # noqa: F401  # registers the detectors
