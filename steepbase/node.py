from datetime import timedelta, datetime
from itertools import cycle
from typing import List, Iterator, Generator
from urllib.parse import urlparse


class Node:
    """Class which allows us to interact with blockchain nodes."""

    def __init__(
        self,
        url: str,
        ban_timeout: int = 2,  # in minutes
        unavailable_timeout: int = 20,  # in minutes
    ):
        """Providing interface for working with node."""
        self._url = url
        self._hostname = urlparse(url).hostname
        self._available = True
        self._banned = False
        self._use_condenser_api = True

        self._ban_timestamp = None  # when node was banned
        self._unavailable_timestamp = None  # when we marked node as unavailable

        self._ban_timeout = timedelta(minutes=ban_timeout)
        self._unavailable_timeout = timedelta(minutes=unavailable_timeout)


    @property
    def url(self) -> str:
        """Returns node's url."""
        return self._url

    @property
    def hostname(self) -> str:
        """Returns node's hostname."""
        return self._hostname

    @property
    def is_available(self) -> bool:
        """Is node available or no."""
        if not self._available:
            if datetime.now() >= self._unavailable_timestamp + self._unavailable_timeout:
                self._available = True

        return self._available

    @property
    def is_banned(self) -> bool:
        """Is we banned on this node or no."""
        if self._banned:
            if datetime.now() >= self._ban_timestamp + self._ban_timeout:
                self._banned = False

        return self._banned

    @property
    def is_working(self) -> bool:
        """Returns true if node is available and not banned."""
        return self.is_available and not self.is_banned

    @property
    def use_condenser_api(self) -> bool:
        """Is we use only condenser API for node."""
        return self._use_condenser_api

    @use_condenser_api.setter
    def use_condenser_api(self, value: bool):
        """Set use_condenser_api."""
        self._use_condenser_api = value

    def set_unavailable(self):
        """Set node unavailable during unavailable_timeout."""
        self._unavailable_timestamp = datetime.now()
        self._available = False

    def set_banned(self):
        """Set node banned during ban_timeout."""
        self._ban_timestamp = datetime.now()
        self._banned = True

    def reset(self):
        """Makes node available and not banned."""
        self._banned = False
        self._available = True

    def __repr__(self):
        """Returns hostname."""
        return self._hostname


class NodesContainer:
    """Class for working with list of nodes."""

    def __init__(self, nodes_urls: List[str]):
        """Method gets list of nodes urls."""
        self._nodes: List[Node] = [Node(url) for url in nodes_urls]
        self._nodes_cycle: Iterator[Node] = cycle(self._nodes)
        self._nodes_amount: int = len(nodes_urls)
        self._current_node: Node = next(self._nodes_cycle)

    @property
    def cur_node(self) -> Node:
        """Returns current node."""
        return self._current_node

    def lap(self) -> Generator:
        """Returns generator from all working nodes."""
        if not self._working_nodes_exist():
            self._reset_nodes()

        for _ in range(self._nodes_amount):
            if self._current_node.is_working:
                yield self._current_node

            self._current_node = next(self._nodes_cycle)

    def _working_nodes_exist(self) -> bool:
        """Do we have available and not banned nodes?

        Used for avoid situations when we don't have working nodes in list.
        """
        for node in self._nodes:
            if node.is_working:
                return True

        return False

    def _reset_nodes(self):
        """Make all nodes available and not banned.

        Used when we have no working nodes in list.
        """
        for node in self._nodes:
            node.reset()
