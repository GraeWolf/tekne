"""Shared helpers for the QEMU smoke tests: drive a VM over its serial console."""
import functools
import glob
import http.server
import os
import select
import shutil
import socket
import socketserver
import subprocess
import threading
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "out")
OVMF_CODE = "/usr/share/OVMF/OVMF_CODE_4M.fd"
OVMF_VARS = "/usr/share/OVMF/OVMF_VARS_4M.fd"

# GRUB entry in live-build/config/bootloaders/grub-pc/grub.cfg that sends
# output to the serial port and starts a serial login prompt.
SERIAL_ENTRY_TITLE = "serial console"
SERIAL_ENTRY_HOTKEY = "s"


class Serial:
    """The VM's serial console, with everything it prints copied to a log file."""

    def __init__(self, proc, log):
        self.proc, self.log, self.buf = proc, log, ""

    def expect(self, needle, timeout):
        """Wait for needle; return the output before it and consume both."""
        found = self.expect_any([needle], timeout)
        before, _, self.buf = self.buf.partition(found)
        return before

    def expect_any(self, needles, timeout):
        """Wait for the first of several strings; return which one appeared (not consumed)."""
        deadline = time.monotonic() + timeout
        while True:
            hits = [(self.buf.find(n), n) for n in needles if n in self.buf]
            if hits:
                return min(hits)[1]
            if self.proc.poll() is not None:
                raise RuntimeError(f"QEMU exited while waiting for {needles!r}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out after {timeout}s waiting for {needles!r}")
            ready, _, _ = select.select([self.proc.stdout], [], [], min(remaining, 1.0))
            if ready:
                chunk = os.read(self.proc.stdout.fileno(), 4096).decode("utf-8", "replace")
                self.buf += chunk
                self.log.write(chunk)
                self.log.flush()

    def send(self, text):
        self.proc.stdin.write(text.encode())
        self.proc.stdin.flush()


def newest_iso():
    isos = sorted(glob.glob(os.path.join(OUT, "tekne-*-amd64.iso")), key=os.path.getmtime)
    return isos[-1] if isos else None


def uefi_vars(path):
    """A fresh, writable copy of the OVMF variable store."""
    shutil.copy(OVMF_VARS, path)
    return path


def qemu_command(mode, vars_path=None, memory=2048, cpus=2, monitor=None):
    """Base QEMU command: headless, serial console on stdio, KVM if available.
    With monitor (a socket path), QEMU's human monitor listens there, for
    sendkeys()."""
    cmd = [
        "qemu-system-x86_64", "-m", str(memory), "-smp", str(cpus),
        "-display", "none", "-serial", "stdio",
        "-monitor", f"unix:{monitor},server=on,wait=off" if monitor else "none", "-no-reboot",
    ]
    if os.access("/dev/kvm", os.R_OK | os.W_OK):
        cmd += ["-enable-kvm", "-cpu", "host"]
    if mode == "uefi":
        cmd += [
            "-machine", "q35",
            "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
            "-drive", f"if=pflash,format=raw,file={vars_path}",
        ]
    return cmd


# QEMU key names for the characters sendkeys() can type (US layout; letters,
# digits and "-" are the same keys on GB).
_KEYS = {"-": "minus", "\n": "ret", " ": "spc", ".": "dot"}


def sendkeys(monitor, text):
    """Type text on the VM's keyboard (not the serial console), through QEMU's
    monitor socket, for programs that read the keyboard, like a screen locker."""
    keys = []
    for ch in text:
        if not ((ch.isascii() and ch.isalnum()) or ch in _KEYS):
            raise ValueError(f"sendkeys can't type {ch!r}")
        keys.append("shift-" + ch.lower() if ch.isupper() else _KEYS.get(ch, ch))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(monitor)
        sock.settimeout(1)
        for key in keys:
            sock.sendall(f"sendkey {key}\n".encode())
            time.sleep(0.15)
            try:
                sock.recv(65536)   # the monitor's echo; keeps its buffer from filling
            except socket.timeout:
                pass


def start(cmd):
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)


def stop(proc, timeout=60):
    """Wait for a VM that was asked to power off; kill it if it doesn't."""
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(root):
    """Serve root over HTTP on a free loopback port, in a background thread.
    A VM on QEMU's user network reaches it at http://10.0.2.2:<port>/.
    Call .shutdown() on the result when done."""
    handler = functools.partial(_QuietHandler, directory=root)
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
