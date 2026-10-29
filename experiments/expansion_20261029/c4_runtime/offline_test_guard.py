"""Test-only: forbid non-loopback IP endpoints, including DNS/DDS/robot."""
import sys
import ipaddress

def local(address):
    if isinstance(address, str):
        return address.startswith('/') or address.startswith('\x00')
    if isinstance(address, tuple) and address:
        host = address[0]
        if host in ('localhost', None):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    return False

def audit(event, args):
    if event in ('socket.connect','socket.bind','socket.sendto'):
        if not local(args[-1]):
            raise PermissionError('C4_OFFLINE_TEST_GUARD_NONLOOPBACK')
    if event == 'socket.getaddrinfo' and args[0] not in ('localhost','127.0.0.1','::1',None):
        raise PermissionError('C4_OFFLINE_TEST_GUARD_DNS')

sys.addaudithook(audit)
