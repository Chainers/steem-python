#!/usr/bin/env python

import os
import sys

from setuptools import find_packages
from setuptools import setup
from setuptools.command.test import test as TestCommand

assert sys.version_info[0] == 3 and sys.version_info[1] >= 5, "steep-steem requires Python 3.5 or newer"

# Package meta-data.
NAME = 'steep-steem'
VERSION = '0.1.2'
DESCRIPTION = 'Fork of official python STEEM library.'
URL = 'https://github.com/Chainers/steep-steem'
EMAIL = 'steepshot.org@gmail.com'
AUTHOR = '@steepshot'


def readme_file():
    return 'README.rst' if os.path.exists('README.rst') else 'README.md'


def license_file():
    return 'LICENSE' if os.path.exists('LICENSE') else 'LICENSE.txt'


REQUIRED = [
    'appdirs',
    'certifi',
    'ecdsa>=0.13',
    'funcy',
    'futures ; python_version < "3.0.0"',
    'future',
    'langdetect',
    'prettytable',
    'pycrypto>=1.9.1',
    'pylibscrypt>=1.6.1',
    'scrypt>=0.8.0',
    'toolz',
    'ujson',
    'urllib3',
    'voluptuous',
    'w3lib'
]

TEST_REQUIRED = [
    'pep8',
    'pytest',
    'pytest-pylint',
    'pytest-xdist',
    'pytest-runner',
    'pytest-pep8',
    'pytest-cov',
    'yapf',
    'autopep8'
]

BUILD_REQUIRED = [
    'twine',
    'pypandoc',
    'recommonmark'
    'wheel',
    'setuptools',
    'sphinx',
    'sphinx_rtd_theme'
]

# The rest you shouldn't have to touch too much :)
# ------------------------------------------------
# Except, perhaps the License and Trove Classifiers!
# If you do change the License, remember to change the Trove Classifier for that!

here = os.path.abspath(os.path.dirname(__file__))


# Import the README and use it as the long-description.
# Note: this will only work if 'README.rst' is present in your MANIFEST.in file!
# with io.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
#     long_description = '\n' + f.read()


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass into py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        try:
            from multiprocessing import cpu_count
            self.pytest_args = ['-n', str(cpu_count()), '--boxed']
        except (ImportError, NotImplementedError):
            self.pytest_args = ['-n', '1', '--boxed']

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest

        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


# Where the magic happens:
setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    license=open(license_file()).read(),
    keywords=['steem' 'steep-steem', 'steemit', 'cryptocurrency', 'blockchain'],
    long_description=open(readme_file()).read(),
    author=AUTHOR,
    author_email=EMAIL,
    url=URL,
    packages=find_packages(exclude=('tests', 'scripts')),
    install_requires=REQUIRED,
    extras_require={
        'dev': TEST_REQUIRED + BUILD_REQUIRED,
        'build': BUILD_REQUIRED,
        'test': TEST_REQUIRED
    },
    tests_require=TEST_REQUIRED,
    include_package_data=True,

    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English', 'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Development Status :: 4 - Beta'
    ],
    # $ setup.py publish support.
    cmdclass={
        'test': PyTest
    },
)
