import asyncio
import json
import logging
from asyncio import FIRST_COMPLETED
from typing import Iterable, Union
from urllib.parse import urlparse

import aiohttp
from aiohttp import ClientSession

from steep.consts import CONDENSER_API
from steepbase.base_client import BaseClient
from steepbase.exceptions import RPCError, RPCErrorRecoverable, NumRetriesReached

logger = logging.getLogger(__name__)


def get_hostname(url: str) -> str:
    """Getting hostname from url."""
    return urlparse(url).hostname


class HttpClient(BaseClient):
    """ Async HTTP client for steep-steem.

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
    success_response_codes = {200, 301, 302, 303, 307, 308}

    retry_exceptions = (
        aiohttp.ServerConnectionError,
        aiohttp.ServerTimeoutError,
        aiohttp.ServerDisconnectedError,
        json.decoder.JSONDecodeError,
        RPCErrorRecoverable,
    )

    def __init__(self, nodes: Iterable[str], **kwargs):
        super().__init__()

        # self.return_with_args = kwargs.get('return_with_args', False)
        # self.re_raise = kwargs.get('re_raise', True)
        # self.max_workers = kwargs.get('max_workers', None)
        #
        # num_pools = kwargs.get('num_pools', 10)
        # maxsize = kwargs.get('maxsize', 10)
        # timeout = kwargs.get('timeout', 60)
        # retries = kwargs.get('retries', 20)
        # pool_block = kwargs.get('pool_block', False)
        # tcp_keepalive = kwargs.get('tcp_keepalive', True)

        self.nodes = list(nodes)
        self.session = ClientSession(conn_timeout=5, read_timeout=15)
        self.loop = asyncio.get_event_loop()

        log_level = kwargs.get('log_level', logging.INFO)
        logger.setLevel(log_level)

    def __del__(self):
        self.loop.run_until_complete(self.session.close())
        self.loop.close()

    def _is_node_downgraded(self, node_url: str) -> bool:
        return node_url in self.__class__.non_appbase_nodes

    def _downgrade_node(self, node_url: str):
        self.__class__.non_appbase_nodes.add(node_url)

    def _is_error_recoverable(self, error: dict) -> bool:
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

    def _build_bodies_for_nodes(self, name, *args, **kwargs) -> dict:
        set_default_api = True
        if 'set_default_api' in kwargs:
            set_default_api = kwargs['set_default_api']
            kwargs.pop('set_default_api')

        kwargs_for_downgraded = kwargs.copy()
        kwargs['api'] = CONDENSER_API

        bodies = dict()
        for node in self.nodes:
            if set_default_api and not self._is_node_downgraded(node):
                body_kwargs = kwargs
            else:
                body_kwargs = kwargs_for_downgraded

            bodies[node] = self.__class__.json_rpc_body(name, *args, **body_kwargs)

        return bodies

    async def _request(self, node_url: str, data: Union[str, dict]):
        try:
            async with self.session.post(node_url, data=data) as response:
                node_hostname = get_hostname(node_url)

                if response.status not in self.success_response_codes:
                    message = '{status} status from {host}'.format(status=response.status, host=node_hostname)
                    logger.warning(message)
                    raise RPCErrorRecoverable(message)

                response_data = await response.json(encoding='utf-8')
                assert response_data, 'result entirely blank'

                if 'error' in response_data:
                    # legacy (pre-appbase) nodes always return err code 1
                    legacy = response_data['error']['code'] == 1
                    detail = response_data['error']['message']

                    # some errors have no data key (db lock error)
                    if 'data' not in response_data['error']:
                        error = 'error'
                    # some errors have no name key (jussi errors)
                    elif 'name' not in response_data['error']['data']:
                        error = 'unspecified error'
                    else:
                        error = response_data['error']['data']['name']

                    if legacy:
                        detail = ":".join(detail.split("\n")[0:2])
                        if not self._is_node_downgraded(node_url):
                            self._downgrade_node(node_url)
                            logger.error('Downgrade-retry %s', node_hostname)

                    detail = '{} from {} ({})'.format(error, node_hostname, detail)

                    if self._is_error_recoverable(response_data['error']):
                        raise RPCErrorRecoverable(detail)
                    else:
                        raise RPCError(detail)

                return response_data['result']
        except self.retry_exceptions as e:
            logger.warning('Retry exception - {}: {}'.format(e.__class__.__name__, e))
            await asyncio.sleep(5)
            return await self._request(node_url, data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                'Unexpected exception - {}: {}'.format(e.__class__.__name__, e),
                extra={'err': e}
            )

            await asyncio.sleep(60)

    async def _call(self, name, *args, **kwargs):
        bodies = self._build_bodies_for_nodes(name, *args, **kwargs)

        tasks = [
            asyncio.ensure_future(self._request(node_url, body)) for node_url, body in bodies.items()
        ]

        done, pending = await asyncio.wait(tasks, return_when=FIRST_COMPLETED, timeout=20)

        for task in pending:
            task.cancel()

        if done:
            return done.pop().result()
        else:
            raise NumRetriesReached

    def call(self, name, *args, **kwargs):
        future = asyncio.ensure_future(self._call(name, *args, **kwargs))
        self.loop.run_until_complete(future)
        return future.result()
