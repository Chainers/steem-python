import concurrent.futures
import json
import logging
import re
from urllib.parse import urlparse

from steepbase.exceptions import RPCError, decodeRPCErrorMsg, AlreadyTransactedThisBlock, \
    MissingRequiredPostingAuthority, VoteWeightTooSmall, OnlyVoteOnceEvery3Seconds, AlreadyVotedSimilarily, \
    PostOnlyEvery5Min, DuplicateTransaction, ExceededAllowedBandwidth, NoMethodWithName, UnhandledRPCError

logger = logging.getLogger(__name__)


class BaseClient(object):
    """
    This class provides general methods to process requests and responses from blockchain nodes
    """

    def __init__(self):
        self.return_with_args = False
        self.re_raise = True
        self.max_workers = None
        self.url = ''

    @property
    def hostname(self):
        return urlparse(self.url).hostname

    @staticmethod
    def json_rpc_body(name, *args, api=None, as_json=True, _id=0):
        """ Build request body for steemd RPC requests.

        Args:
            name (str): Name of a method we are trying to call. (ie: `get_accounts`)
            args: A list of arguments belonging to the calling method.
            api (None, str): If api is provided (ie: `follow_api`),
             we generate a body that uses `call` method appropriately.
            as_json (bool): Should this function return json as dictionary or string.
            _id (int): This is an arbitrary number that can be used for request/response tracking in multi-threaded
             scenarios.

        Returns:
            (dict,str): If `as_json` is set to `True`, we get json formatted as a string.
            Otherwise, a Python dictionary is returned.
        """
        headers = {"jsonrpc": "2.0", "id": _id}
        if api:
            body_dict = {**headers, "method": "call", "params": [api, name, args]}
        else:
            body_dict = {**headers, "method": name, "params": args}
        if as_json:
            return json.dumps(body_dict, ensure_ascii=False).encode('utf8')
        else:
            return body_dict

    def exec(self, name, *args, api=None, return_with_args=None, _ret_cnt=0):
        pass

    def _return(self, response=None, args=None, return_with_args=None):
        return_with_args = return_with_args or self.return_with_args
        result = None

        if response:
            try:
                if hasattr(response, 'data'):
                    data = response.data.decode('utf-8')
                else:
                    data = response if isinstance(response, str) else response.decode('utf-8')
                response_json = json.loads(data)
            except Exception as e:
                extra = dict(response=response, request_args=args, err=e)
                logger.info('failed to load response', extra=extra)
                result = None
            else:
                if 'error' in response_json:
                    error = response_json['error']

                    if self.re_raise:
                        error_message = error.get(
                            'detail', response_json['error']['message'])
                        e = RPCError(error_message)
                        msg = decodeRPCErrorMsg(e).strip()
                        if msg == "Account already transacted this block.":
                            raise AlreadyTransactedThisBlock(msg)
                        elif msg == "missing required posting authority":
                            raise MissingRequiredPostingAuthority
                        elif msg == "Voting weight is too small, please accumulate more voting power or steem power.":
                            raise VoteWeightTooSmall(msg)
                        elif msg == "Can only vote once every 3 seconds.":
                            raise OnlyVoteOnceEvery3Seconds(msg)
                        elif msg == "You have already voted in a similar way.":
                            raise AlreadyVotedSimilarily(msg)
                        elif msg == "You may only post once every 5 minutes.":
                            raise PostOnlyEvery5Min(msg)
                        elif msg == "Duplicate transaction check failed":
                            raise DuplicateTransaction(msg)
                        elif msg == "Account exceeded maximum allowed bandwidth per vesting share.":
                            raise ExceededAllowedBandwidth(msg)
                        elif re.match("^no method with name.*", msg):
                            raise NoMethodWithName(msg)
                        elif msg:
                            raise UnhandledRPCError(msg)
                        else:
                            raise e

                    result = response_json['error']
                else:
                    result = response_json.get('result', None)
        if return_with_args:
            return result, args
        else:
            return result

    def exec_multi_with_futures(self, name, params, api=None, max_workers=None):
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers) as executor:
            # Start the load operations and mark each future with its URL
            def ensure_list(parameter):
                return parameter if type(parameter) in (list, tuple, set) else [parameter]

            futures = (executor.submit(self.exec, name, *ensure_list(param), api=api)
                       for param in params)
            for future in concurrent.futures.as_completed(futures):
                yield future.result()
