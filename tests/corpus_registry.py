"""Single source of truth for the immutable test-corpus archive."""

import os

ARCHIVE_NAME = "sample_project.zip"
CORPUS_DOI = os.environ.get("COPICK_TEST_DATA_DOI", "10.5281/zenodo.23171726")
CORPUS_DIGEST = os.environ.get("COPICK_TEST_DATA_DIGEST", "md5:fd2be0b41c2d82f0cddcbe693d9858d4")
