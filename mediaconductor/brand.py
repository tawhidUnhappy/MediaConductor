"""Public product identity and backwards-compatibility names."""

PRODUCT_NAME = "MediaConductor"
PACKAGE_NAME = "media-conductor"
CLI_NAME = "mediaconductor"
LEGACY_CLI_NAME = "mangaeasy"
MCP_SERVER_NAME = "media-conductor"

# Environment variables: MEDIACONDUCTOR_* is the documented prefix; the
# pre-2.1 MANGAEASY_* spelling keeps working via mirror_legacy_environment().
ENV_PREFIX = "MEDIACONDUCTOR_"
LEGACY_ENV_PREFIX = "MANGAEASY_"

# Machine-parsable stdout/log markers. Emit the first spelling; scanners must
# accept every spelling because tool scripts copied into existing external
# envs (`<data>/tools/<name>/`) still print the legacy one.
RESULT_MARKERS = ("MEDIACONDUCTOR_RESULT ", "MANGAEASY_RESULT ")
PROGRESS_MARKERS = ("MEDIACONDUCTOR_PROGRESS ", "MANGAEASY_PROGRESS ")


def mirror_legacy_environment() -> None:
    """Honor MANGAEASY_* configuration under the new MEDIACONDUCTOR_* names.

    Runs once at CLI startup, before any module reads configuration. An
    explicitly set MEDIACONDUCTOR_* value always wins; mirrored values are
    inherited by child processes, so external tool envs see both spellings.
    """
    import os

    for name, value in list(os.environ.items()):
        if name.startswith(LEGACY_ENV_PREFIX):
            os.environ.setdefault(ENV_PREFIX + name[len(LEGACY_ENV_PREFIX):], value)
