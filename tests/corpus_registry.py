"""Single source of truth for the immutable test-corpus archive."""

import os

ARCHIVE_NAME = "sample_project.zip"
CORPUS_DOI = os.environ.get("COPICK_TEST_DATA_DOI", "10.5281/zenodo.21939821")
CORPUS_DIGEST = os.environ.get("COPICK_TEST_DATA_DIGEST", "md5:05b1582e675719d3f1bb23349c20b86c")
