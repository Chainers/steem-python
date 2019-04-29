import logging
from datetime import timedelta, datetime
from itertools import cycle
from typing import List, Iterator, Generator
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class Node:
    """Class which allows us to interact with blockchain nodes."""

    def __init__(
        self,
        url: str,
        ban_timeout: timedelta = timedelta(minutes=2),
        unavailable_timeout: timedelta = timedelta(minutes=30),
    ):
        """Providing interface for working with node."""
        self._url = url
        self._hostname = urlparse(url).hostname
        self._available = True
        self._banned = False
        self._use_condenser_api = True

        self._ban_timeout = ban_timeout
        self._ban_timestamp = None

        self._unavailable_timeout = unavailable_timeout
        self._unavailable_timestamp = None

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


class NodesContainer:
    """Class for working with list of nodes."""

    def __init__(self, nodes_urls: List[str]):
        """Method gets list of nodes urls."""
        self._nodes: Iterator[Node] = cycle([Node(url) for url in nodes_urls])
        self._nodes_amount: int = len(nodes_urls)
        self._current_node: Node = self.next_node()

    @property
    def cur_node(self) -> Node:
        """Returns current node."""
        return self._current_node

    def lap(self) -> Generator:
        """Returns generator from all working nodes."""
        yield self._current_node

        for _ in range(self._nodes_amount):
            self._current_node = next(self._nodes)

            if self._current_node.is_available and not self._current_node.is_banned:
                yield self._current_node

    def next_node(self) -> Node:
        """Use moves_amount to avoid cycling by unavailable nodes (if each node is unavailable)."""
        moves_amount = 0

        while moves_amount < self._nodes_amount:
            node = next(self._nodes)
            if not node.is_available or node.is_banned:
                moves_amount += 1
                continue

            self._current_node = node
            return self._current_node

        self._reset_nodes()
        return self.next_node()

    def _reset_nodes(self):
        """Make all nodes available and not banned."""
        for _ in range(self._nodes_amount):
            node = next(self._nodes)
            node.reset()
