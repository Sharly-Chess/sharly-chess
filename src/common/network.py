"""Common network code"""

import socket
import random
from logging import Logger
import time
from threading import Thread

from common.i18n import _
from common.logger import get_logger

logger: Logger = get_logger()

SLEEP_TIME = 15


class NetworkMonitor:
    """Class for monitoring internet connectivity"""

    # We assume we're connected to the internet on startup
    connected_status = True

    @staticmethod
    def _test_dns_server(ip: str) -> bool:
        """Tries to connect to a given DNS over TCP server (port 53).
        Returns True if it connected, False otherwise"""
        # https://stackoverflow.com/questions/3764291/how-can-i-see-if-theres-an-available-and-active-network-connection-in-python
        try:
            socket.setdefaulttimeout(3)
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((ip, 53))
            return True
        except socket.error:
            return False

    @classmethod
    def _test_for_internet_connection(cls):
        from web.server_engine import ServerEngine

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

        # NOTE(Amaras): if you need to prioritize servers, use the `counts`
        # keyword argument to specify integer weights for each server.
        selected_servers: list[str] = random.sample(root_dns_servers, 2)
        if any(cls._test_dns_server(server) for server in selected_servers):
            if not cls.connected_status:
                logger.info(_('Internet connection established'))
                if ServerEngine.app:
                    ServerEngine.app.emit('connected')
            cls.connected_status = True
        else:
            if cls.connected_status:
                logger.info(_('Internet connection lost'))
                # NOTE(Molrn) 'disconnected' event not emitted as an event without listeners raises
            cls.connected_status = False

    # ---------------------------------------------------------------------------------
    # Main thread functions
    # ---------------------------------------------------------------------------------

    @classmethod
    def start_monitoring(cls):
        """Starts a thread to test for internet connectivity every few seconds"""
        # NOTE(Amaras): The entire Python program exits when only daemon threads
        # are left, and those threads will be stopped abruptly on program shutdown
        # See https://docs.python.org/3.12/library/threading.html#thread-objects
        # for more documentation
        #
        # By passing cls as an arg, we can share it with the main thread.

        def _check_connected(cls) -> None:
            """This function is supposed to be run in a thread or process, or it will
            hog all the caller's time.
            Tries to connect to root DNS servers, as shit has already hit the fan if
            they are not reachable"""

            while True:
                cls._test_for_internet_connection()
                time.sleep(SLEEP_TIME)

        connection_checker = Thread(target=_check_connected, args=(cls,), daemon=True)
        connection_checker.start()

    @classmethod
    def set_connected(cls, status: bool):
        """Sets the connected status from the main thread"""
        cls.connected_status = status

    @classmethod
    def connected(cls, use_cached=True) -> bool:
        """Checks if the program is connected to the internet.
        This relies on a background thread checking every few seconds,
        and so the returned value isn't 100% sure"""

        if not use_cached:
            cls._test_for_internet_connection()
        return cls.connected_status
