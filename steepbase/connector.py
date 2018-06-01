from urllib.parse import urlparse

from steepbase.exceptions import InvalidNodeSchemes
from steepbase.http_client import HttpClient
from steepbase.ws_client import WsClient


class Connector(object):
    def __init__(self, nodes, **kwargs):
        scheme = self.get_scheme(nodes)

        if scheme == 'http':
            self.client = HttpClient(nodes, **kwargs)
        elif scheme == 'ws':
            self.client = WsClient(nodes, **kwargs)
        else:
            raise InvalidNodeSchemes('Unsupported node scheme.')

    @staticmethod
    def get_scheme(nodes):
        ws_schemas = ['ws', 'wss']
        http_schemas = ['', 'http', 'https']

        is_ws = False
        is_http = False

        for node in nodes:
            schema = urlparse(node).scheme
            if schema in ws_schemas:
                is_ws = True
            if schema in http_schemas:
                is_http = True

        if (is_ws and is_http) or (not is_ws and not is_http):
            raise InvalidNodeSchemes('Invalid node schemas. All schemas should be of one type: http(s) or ws(s).')

        return 'ws' * is_ws + 'http' * is_http

    @property
    def hostname(self):
        return self.client.hostname

    def call(self, name, *args, **kwargs):
        """ Execute a method against steemd RPC.

        Warnings:
            This command will auto-retry in case of node failure, as well as handle
            node fail-over, unless we are broadcasting a transaction.
            In latter case, the exception is **re-raised**.
        """
        return self.client.call(name, *args, **kwargs)

    def call_multi_with_futures(self, name, params, api=None, max_workers=None):
        return self.client.call_multi_with_futures(name, params, api=api, max_workers=max_workers)
