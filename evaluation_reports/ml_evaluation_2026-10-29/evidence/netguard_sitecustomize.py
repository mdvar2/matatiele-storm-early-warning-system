# Test-process network guard: blocks and records every non-local socket connection.
import socket, os, datetime
_LOG = os.environ.get("NETGUARD_LOG")
_orig_connect = socket.socket.connect
_orig_getaddrinfo = socket.getaddrinfo
def _record(kind, target):
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().isoformat()} BLOCKED {kind} {target!r}\n")
def _local(host):
    return str(host) in {"127.0.0.1", "::1", "localhost", ""}
def guarded_connect(self, address):
    host = address[0] if isinstance(address, tuple) else address
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _local(host):
        _record("connect", address)
        raise ConnectionRefusedError("netguard: external connection blocked")
    return _orig_connect(self, address)
def guarded_getaddrinfo(host, *a, **k):
    if host is not None and not _local(host):
        _record("dns", host)
        raise socket.gaierror("netguard: DNS lookup blocked")
    return _orig_getaddrinfo(host, *a, **k)
socket.socket.connect = guarded_connect
socket.getaddrinfo = guarded_getaddrinfo
