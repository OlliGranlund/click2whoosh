"""Windows DNS-SD registration through the installed Apple Bonjour daemon.

Independent ctypes binding to the public DNSServiceRegister API. No DLL is
redistributed; Bonjour remains a separately installed system prerequisite.
"""
import ctypes
import select
import socket
import threading


def encode_txt(properties):
    result = bytearray()
    for key, value in properties.items():
        segment = f"{key}={value}".encode("utf-8")
        if len(segment) > 255:
            raise ValueError("DNS-SD TXT entry exceeds 255 bytes")
        result.append(len(segment))
        result.extend(segment)
    return bytes(result)


class BonjourRegistration:
    def __init__(self, name, port, properties):
        self.ref = ctypes.c_void_p()
        self.stopping = threading.Event()
        self.ready = threading.Event()
        self.error = None
        self.thread = None
        try:
            self.dll = ctypes.WinDLL("dnssd.dll")
        except OSError as exc:
            raise RuntimeError("Network mode on Windows needs Apple Bonjour installed and running. Use Keyboard meanwhile.") from exc
        callback_type = ctypes.WINFUNCTYPE(None, ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.c_int32, ctypes.c_char_p, ctypes.c_char_p,
                                          ctypes.c_char_p, ctypes.c_void_p)

        def registered(ref, flags, error, name, regtype, domain, context):
            self.error = error or None
            self.ready.set()

        self.callback = callback_type(registered)
        register = self.dll.DNSServiceRegister
        register.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32, ctypes.c_uint32,
                             ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                             ctypes.c_uint16, ctypes.c_uint16, ctypes.c_void_p, callback_type, ctypes.c_void_p]
        register.restype = ctypes.c_int32
        self.dll.DNSServiceRefSockFD.argtypes = [ctypes.c_void_p]
        self.dll.DNSServiceRefSockFD.restype = ctypes.c_int
        self.dll.DNSServiceProcessResult.argtypes = [ctypes.c_void_p]
        self.dll.DNSServiceProcessResult.restype = ctypes.c_int32
        self.dll.DNSServiceRefDeallocate.argtypes = [ctypes.c_void_p]
        self.dll.DNSServiceRefDeallocate.restype = None
        txt = encode_txt(properties)
        error = register(ctypes.byref(self.ref), 0, 0, name.encode(), b"_openbikecontrol._tcp",
                         b"local.", None, socket.htons(port), len(txt), txt, self.callback, None)
        if error:
            raise RuntimeError(f"Bonjour registration failed ({error})")
        self.thread = threading.Thread(target=self._process, daemon=True)
        self.thread.start()

    def _process(self):
        try:
            fd = self.dll.DNSServiceRefSockFD(self.ref)
            while not self.stopping.is_set():
                if select.select([fd], [], [], .2)[0]:
                    error = self.dll.DNSServiceProcessResult(self.ref)
                    if error:
                        raise OSError(f"Bonjour processing failed ({error})")
        except Exception as exc:
            self.error = str(exc)
            self.ready.set()

    def wait_ready(self):
        if not self.ready.wait(5) or self.error:
            raise RuntimeError(f"Bonjour registration not confirmed: {self.error or 'timed out'}")

    def close(self):
        self.stopping.set()
        if self.thread:
            self.thread.join()
        if self.ref:
            self.dll.DNSServiceRefDeallocate(self.ref)
            self.ref = ctypes.c_void_p()
