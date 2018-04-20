# -*- coding: utf-8 -*-
import os
import sys
sys.path.insert(0, os.path.abspath('..'))

from steep import *  # noqa
from steepbase import *  # noqa


# pylint: disable=unused-import,unused-variable
def test_import():
    _ = Steem()
    _ = account.PasswordKey
