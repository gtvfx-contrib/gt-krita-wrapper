"""Entry point for the Krita Wrapper.

This module serves as the main entry point for the Krita wrapper package.
It orchestrates the initialization sequence and launches Krita with the
properly configured environment.

Initialization Sequence:
    1. Preserve PYINIT_STARTUP paths before environment resolution changes them
    2. Establish Python environment (KRITA_PYTHONPATH)
    3. Manage plugin deployment to pykrita directory
    4. Ensure plugins are enabled in kritarc configuration
    5. Spawn Krita process with configured environment

The wrapper is invoked via: 'envoy krita'

"""

import sys
from pathlib import Path
import logging

import envoy

from . import _initialize as krita


log = logging.getLogger(__name__)


def main() -> None:
    """Execute the Krita wrapper initialization and launch sequence."""
    # Resolve the executable path
    krita_exe = (
        Path(krita.KRITA_ENV.get("ENVOY_KRITA_BIN", ""))
    )

    if not krita_exe.is_file():
        log.error("Unable to find executable for Krita at: %s", krita_exe)
        raise RuntimeError("Unable to find application...")
    
    # Preserve PYINIT_STARTUP early, before environment resolution changes it
    krita.preservePyinitStartup()

    # Manage Krita plugins
    krita.manageKritaPlugins()

    # Ensure T2 plugins are enabled in kritarc
    krita.ensurePluginsEnabled()

    # Launch Krita inside the krita envoy environment, streaming its
    # stdout and stderr to the terminal in real-time.
    import threading

    proc = envoy.proc.spawn(
        [str(krita_exe)],
        env_override='krita',
        stdout=envoy.proc.PIPE,
        stderr=envoy.proc.PIPE,
        creationflags=0,  # override envoy's CREATE_NO_WINDOW so output flows through
    )

    def _stream(stream, dest):
        for line in iter(stream.readline, b''):
            dest.write(line.decode(errors='replace'))
            dest.flush()
        stream.close()

    stdout_thread = threading.Thread(target=_stream, args=(proc.stdout, sys.stdout), daemon=True)
    stderr_thread = threading.Thread(target=_stream, args=(proc.stderr, sys.stderr), daemon=True)
    stdout_thread.start()
    stderr_thread.start()

    proc.wait()
    stdout_thread.join()
    stderr_thread.join()

    if proc.returncode:
        log.error("Krita exited with error code: %d", proc.returncode)
        sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
