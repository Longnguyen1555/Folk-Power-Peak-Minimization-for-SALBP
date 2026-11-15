"""Captured subprocesses with descendant cleanup on timeout/interruption."""

import os
import signal
import subprocess


def run_command(command, *, timeout=None, cwd=None):
    options = (
        {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        }
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **options
    ) as process:

        def stop_tree():
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    check=False,
                    timeout=5,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.poll() is None:
                process.kill()

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(
                command, timeout, output=stdout, stderr=stderr
            )
        except BaseException:
            stop_tree()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
