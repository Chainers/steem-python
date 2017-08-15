# coding=utf-8
import logging
import socket
import time
from functools import partial
from http.client import RemoteDisconnected
from itertools import cycle

import certifi
import urllib3
from urllib3.connection import HTTPConnection
from urllib3.exceptions import MaxRetryError, ReadTimeoutError, ProtocolError

from steepbase.base_client import BaseClient

logger = logging.getLogger(__name__)


class HttpClient(BaseClient):
    """ Simple Steem JSON-HTTP-RPC API

    This class serves as an abstraction layer for easy use of the Steem API.

    Args:
      nodes (list): A list of Steem HTTP RPC nodes to connect to.

    .. code-block:: python

       from steem.http_client import HttpClient
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

    def __init__(self, nodes, **kwargs):
        super().__init__()

        self.return_with_args = kwargs.get('return_with_args', False)
        self.re_raise = kwargs.get('re_raise', True)
        self.max_workers = kwargs.get('max_workers', None)

        num_pools = kwargs.get('num_pools', 10)
        maxsize = kwargs.get('maxsize', 10)
        timeout = kwargs.get('timeout', 60)
        retries = kwargs.get('retries', 20)
        pool_block = kwargs.get('pool_block', False)
        tcp_keepalive = kwargs.get('tcp_keepalive', True)

        if tcp_keepalive:
            socket_options = HTTPConnection.default_socket_options + \
                             [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1), ]
        else:
            socket_options = HTTPConnection.default_socket_options

        self.http = urllib3.poolmanager.PoolManager(
            num_pools=num_pools,
            maxsize=maxsize,
            block=pool_block,
            timeout=timeout,
            retries=retries,
            socket_options=socket_options,
            headers={'Content-Type': 'application/json'},
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where())
        '''
            urlopen(method, url, body=None, headers=None, retries=None,
            redirect=True, assert_same_host=True, timeout=<object object>,
            pool_timeout=None, release_conn=None, chunked=False, body_pos=None,
            **response_kw)
        '''

        self.nodes = cycle(nodes)
        self.request = None
        self.next_node()

        log_level = kwargs.get('log_level', logging.INFO)
        logger.setLevel(log_level)

    def next_node(self):
        """ Switch to the next available node.

        This method will change base URL of our requests.
        Use it when the current node goes down to change to a fallback node. """
        self.set_node(next(self.nodes))

    def set_node(self, node_url):
        """ Change current node to provided node URL. """
        self.url = node_url
        self.request = partial(self.http.urlopen, 'POST', self.url)

    def exec(self, name, *args, api=None, return_with_args=None, _ret_cnt=0):
        """ Execute a method against steemd RPC.

        Warnings:
            This command will auto-retry in case of node failure, as well as handle
            node fail-over, unless we are broadcasting a transaction.
            In latter case, the exception is **re-raised**.
        """
        body = HttpClient.json_rpc_body(name, *args, api=api)
        response = None
        try:
            response = self.request(body=body)
        except (MaxRetryError,
                ConnectionResetError,
                ReadTimeoutError,
                RemoteDisconnected,
                ProtocolError) as e:
            # if we broadcasted a transaction, always raise
            # this is to prevent potential for double spend scenario
            if api == 'network_broadcast_api':
                raise e

            # try switching nodes before giving up
            if _ret_cnt > 2:
                time.sleep(5 * _ret_cnt)
            elif _ret_cnt > 10:
                raise e
            self.next_node()
            logging.debug('Switched node to %s due to exception: %s' %
                          (self.hostname, e.__class__.__name__))
            return self.exec(name, *args,
                             return_with_args=return_with_args,
                             _ret_cnt=_ret_cnt + 1)
        except Exception as e:
            if self.re_raise:
                raise e
            else:
                extra = dict(err=e, request=self.request)
                logger.info('Request error', extra=extra)
                return self._return(
                    response=response,
                    args=args,
                    return_with_args=return_with_args)
        else:
            if response.status not in tuple(
                    [*response.REDIRECT_STATUSES, 200]):
                logger.info('non 200 response:%s', response.status)

            return self._return(
                response=response,
                args=args,
                return_with_args=return_with_args)
