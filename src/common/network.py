import socket
import random
from logging import Logger

from common import get_logger

logger: Logger = get_logger()


def test_dns_server(ip: str) -> bool:
    # https://stackoverflow.com/questions/3764291/how-can-i-see-if-theres-an-available-and-active-network-connection-in-python
    try:
        socket.setdefaulttimeout(3)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 53))
        return True
    except socket.error as e:
        return False

def connected() -> bool:
    # https://www.iana.org/domains/root/servers
    root_dns_servers: list[str] = [
        '198.41.0.4',
        '170.247.170.2',
        '192.33.4.12',
        '199.7.91.13',
        '192.203.230.10',
        '192.5.5.241',
        '192.112.36.4',
        '198.97.190.53',
        '192.36.148.17',
        '192.58.128.30',
        '193.0.14.129',
        '199.7.83.42',
        '202.12.27.33',
    ]
    dns_server: str = random.choice(root_dns_servers)
    if test_dns_server(dns_server):
        return True
    elif test_dns_server('8.8.8.8'):
        logger.warning(f'DNS server {dns_server} did not respond while connected.')
        return True
    else:
        return False
