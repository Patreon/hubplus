# HubPlus

A command line tool to manage our pull request flow.


# Installation

1. Install and set up [`hub`](https://github.com/github/hub#installation), and run it once

        $ brew install hub
        $ hub

2. Install [`pipsi`](https://github.com/mitsuhiko/pipsi#readme).

        $ curl https://raw.githubusercontent.com/mitsuhiko/pipsi/master/get-pipsi.py | python

3. Install `hubplus`:

        $ pipsi install .


# Usage

To assign [21echoes](https://github.com/21echoes/) to a PR opened by your current branch:

    $ hubplus -a 21echoes
    
To learn more:

    $ hubplus --help
