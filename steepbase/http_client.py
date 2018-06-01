import json
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

from steep.consts import CONDENSER_API
from steepbase.base_client import BaseClient
from steepbase.exceptions import RPCError, RPCErrorRecoverable

logger = logging.getLogger(__name__)


class HttpClient(BaseClient):
    """ Simple Steem JSON-HTTP-RPC API

    This class serves as an abstraction layer for easy use of the Steem API.

    Args:
      nodes (list): A list of Steem HTTP RPC nodes to connect to.

    .. code-block:: python

       from steem.http_client import HttpClient

       rpc = HttpClient(['https://steemd-node1.com',
       'https://steemd-node2.com'])

    any call available to that port can be issued using the instance
    via the syntax ``rpc.call('command', *parameters)``.

    Example:

    .. code-block:: python

       rpc.call(
           'get_followers',
           'furion', 'abit', 'blog', 10,
           api='follow_api'
       )

    """

    # set of endpoints which were detected to not support condenser_api
    non_appbase_nodes = set()

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
        self.url = ''
        self.request = None
        self.next_node()

        log_level = kwargs.get('log_level', logging.INFO)
        logger.setLevel(log_level)

    def _curr_node_downgraded(self):
        return self.url in HttpClient.non_appbase_nodes

    def _downgrade_curr_node(self):
        HttpClient.non_appbase_nodes.add(self.url)

    def _is_error_recoverable(self, error):
        assert 'message' in error, "missing error msg key: {}".format(error)
        assert 'code' in error, "missing error code key: {}".format(error)
        message = error['message']
        code = error['code']

        # common steemd error
        # {"code"=>-32003, "message"=>"Unable to acquire database lock"}
        if message == 'Unable to acquire database lock':
            return True

        # rare steemd error
        # {"code"=>-32000, "message"=>"Unknown exception", "data"=>"0 exception: unspecified\nUnknown Exception\n[...]"}
        if message == 'Unknown exception':
            return True

        # generic jussi error
        # {'code': -32603, 'message': 'Internal Error', 'data': {'error_id': 'c7a15140-f306-4727-acbd-b5e8f3717e9b',
        #         'request': {'amzn_trace_id': 'Root=1-5ad4cb9f-9bc86fbca98d9a180850fb80', 'jussi_request_id': None}}}
        if message == 'Internal Error' and code == -32603:
            return True

        return False

    def next_node(self):
        """ Switch to the next available node.

        This method will change base URL of our requests.
        Use it when the current node goes down to change to a fallback node. """
        self.set_node(next(self.nodes))

    def set_node(self, node_url):
        """ Change current node to provided node URL. """
        self.url = node_url
        self.request = partial(self.http.urlopen, 'POST', self.url)

    def call(self, name, *args, **kwargs):
        """ Call a remote procedure in steemd.

        Warnings:
            This command will auto-retry in case of node failure, as well as handle
            node fail-over, unless we are broadcasting a transaction.
            In latter case, the exception is **re-raised**.
        """

        retry_exceptions = (
            MaxRetryError,
            ConnectionResetError,
            ReadTimeoutError,
            RemoteDisconnected,
            ProtocolError,
            RPCErrorRecoverable,
            json.decoder.JSONDecodeError,
        )

        tries = 0
        while True:
            try:
                body_kwargs = kwargs.copy()
                if not self._curr_node_downgraded():
                    body_kwargs['api'] = CONDENSER_API

                body = HttpClient.json_rpc_body(name, *args, **body_kwargs)
                response = self.request(body=body)

                success_codes = {*response.REDIRECT_STATUSES, 200}
                if response.status not in success_codes:
                    raise RPCErrorRecoverable('non-200 response: %s from %s' % (response.status, self.hostname))

                result = json.loads(response.data.decode('utf-8'))
                assert result, 'result entirely blank'

                if 'error' in result:
                    # legacy (pre-appbase) nodes always return err code 1
                    legacy = result['error']['code'] == 1
                    detail = result['error']['message']

                    # some errors have no data key (db lock error)
                    if 'data' not in result['error']:
                        error = 'error'
                    # some errors have no name key (jussi errors)
                    elif 'name' not in result['error']['data']:
                        error = 'unspecified error'
                    else:
                        error = result['error']['data']['name']

                    if legacy:
                        detail = ":".join(detail.split("\n")[0:2])
                        if not self._curr_node_downgraded():
                            self._downgrade_curr_node()
                            logging.error('Downgrade-retry %s', self.hostname)
                            continue

                    detail = ('%s from %s (%s) in %s' % (
                        error, self.hostname, detail, name))

                    if self._is_error_recoverable(result['error']):
                        raise RPCErrorRecoverable(detail)
                    else:
                        raise RPCError(detail)

                return result['result']

            except retry_exceptions as e:
                if tries >= 10:
                    logger.error('Failed to call Steem API after %d atempts - %s: %s', tries, e.__class__.__name__, e)
                tries += 1
                logger.warning('Retry in %ds - %s: %s', tries, e.__class__.__name__, e)
                time.sleep(tries)
                self.next_node()
                continue

            except Exception as e:
                logger.error('Unexpected exception - %s: %s', e.__class__.__name__, e, extra={
                    'err': e,
                    'request': self.request
                })
                raise e
