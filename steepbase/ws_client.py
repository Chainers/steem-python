import logging
import ssl
import time
from itertools import cycle

import websocket

from steepbase.base_client import BaseClient
from steepbase.exceptions import NumRetriesReached

logger = logging.getLogger(__name__)


class WsClient(BaseClient):
    """ Simple Steem JSON-WebSocket-RPC API

        This class serves as an abstraction layer for easy use of the Steem API.

        Args:
          nodes (list): A list of Steem WebSocket RPC nodes to connect to.

        .. code-block:: python

           from golosbase.http_client import HttpClient
           rpc = HttpClient(['https://steemd-node1.com', 'https://steemd-node2.com'])

        any call available to that port can be issued using the instance
        via the syntax ``rpc.exec('command', *parameters)``.

        Example:

        .. code-block:: python

           rpc.exec(
               'get_followers',
               'furion', 'abit', 'blog', 10,
               api='follow_api'
           )

        """

    def __init__(self, nodes: list, **kwargs):
        super().__init__()

        self.return_with_args = kwargs.get('return_with_args', False)

        self.num_retries = kwargs.get("num_retries", 20)
        self.nodes = cycle(nodes)
        self.url = ''
        self.ws = None

        log_level = kwargs.get('log_level', logging.INFO)
        logger.setLevel(log_level)
        self.ws_connect()

    def ws_connect(self):
        cnt = 0
        while True:
            cnt += 1
            self.url = next(self.nodes)
            logger.debug("Trying to connect to node %s" % self.url)
            if self.url[:3] == "wss":
                sslopt_ca_certs = {'cert_reqs': ssl.CERT_NONE}
                self.ws = websocket.WebSocket(sslopt=sslopt_ca_certs)
            else:
                self.ws = websocket.WebSocket()

            try:
                self.ws.connect(self.url)
                break
            except KeyboardInterrupt:
                raise
            except:
                if self.num_retries >= 0 and cnt > self.num_retries:
                    raise NumRetriesReached()

                sleeptime = (cnt - 1) * 2 if cnt < 10 else 10
                if sleeptime:
                    logger.warning(
                        "Lost connection to node during wsconnect(): %s (%d/%d) "
                        % (self.url, cnt, self.num_retries) +
                        "Retrying in %d seconds" % sleeptime
                    )
                    time.sleep(sleeptime)

    def exec(self, name, *args, api=None, return_with_args=None, _ret_cnt=0):
        body = WsClient.json_rpc_body(name, *args, api=api)

        response = None

        cnt = 0
        while True:
            cnt += 1

            try:
                self.ws.send(body)
                response = self.ws.recv()
                break
            except KeyboardInterrupt:
                raise
            except:
                if self.num_retries > -1 and cnt > self.num_retries:
                    raise NumRetriesReached()
                sleeptime = (cnt - 1) * 2 if cnt < 10 else 10
                if sleeptime:
                    logger.warning(
                        "Lost connection to node during exec(): %s (%d/%d) "
                        % (self.url, cnt, self.num_retries) +
                        "Retrying in %d seconds" % sleeptime
                    )
                    time.sleep(sleeptime)

                # retry
                try:
                    self.ws.close()
                    time.sleep(sleeptime)
                    self.ws_connect()
                except:
                    pass

        return self._return(
            response=response,
            args=args,
            return_with_args=return_with_args)
