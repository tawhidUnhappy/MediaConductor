"""Public product identity and backwards-compatibility names."""

PRODUCT_NAME = "mangaEasy"
PACKAGE_NAME = "mangaeasy"
CLI_NAME = "mangaeasy"
LEGACY_CLI_NAME = "mediaconductor"
MCP_SERVER_NAME = "mangaeasy"

# Environment variables: MANGAEASY_* is the documented prefix; the
# MEDIACONDUCTOR_* spelling keeps working via mirror_legacy_environment().
ENV_PREFIX = "MANGAEASY_"
LEGACY_ENV_PREFIX = "MEDIACONDUCTOR_"

# Machine-parsable stdout/log markers. Emit the first spelling; scanners must
# accept every spelling because tool scripts copied into existing external
# envs (`<data>/tools/<name>/`) still print the legacy one.
RESULT_MARKERS = ("MANGAEASY_RESULT ", "MEDIACONDUCTOR_RESULT ")
PROGRESS_MARKERS = ("MANGAEASY_PROGRESS ", "MEDIACONDUCTOR_PROGRESS ")


def mirror_legacy_environment() -> None:
    """Honor MEDIACONDUCTOR_* configuration under the new MANGAEASY_* names.

    Runs once at CLI startup, before any module reads configuration. An
    explicitly set MANGAEASY_* value always wins; mirrored values are
    inherited by child processes, so external tool envs see both spellings.
    """
    import os

    for name, value in list(os.environ.items()):
        if name.startswith(LEGACY_ENV_PREFIX):
            os.environ.setdefault(ENV_PREFIX + name[len(LEGACY_ENV_PREFIX):], value)
