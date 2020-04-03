import shutil


def ensure_command_exists(command: str):
    """Raise a RuntimeError if `command` is not executable on the system."""
    if shutil.which(command) is None:
        raise RuntimeError(f"The command `{command}` must be installed on your "
                          "machine. Please consult the vaws requirements.")
