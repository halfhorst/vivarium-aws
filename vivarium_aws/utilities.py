import shutil

import boto3


def ensure_command_exists(command: str):
    """Raise a RuntimeError if `command` is not executable on the system."""
    if shutil.which(command) is None:
        raise RuntimeError(f"The command `{command}` must be installed on your "
                          "machine. Please consult the vaws requirements.")


def get_default_region():
    session = boto3.session.Session()
    return session.region_name
