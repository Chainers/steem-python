# Fork of official Python STEEM Library
`steep-steem` is the fork of official STEEM library for Python. It comes with a BIP38 encrypted wallet.

## Installation
You can install `steep-steem` with `pip`:

```
pip install -U steep-steem
```

## Homebrew Build Prereqs

If you're on a mac, you may need to do the following first:

```
brew install openssl
export CFLAGS="-I$(brew --prefix openssl)/include $CFLAGS"
export LDFLAGS="-L$(brew --prefix openssl)/lib $LDFLAGS"
```

# Tests

Some tests are included.  They can be run via:

* `python setup.py test`

## Notice
This library is *under development*. Use at own discretion.

