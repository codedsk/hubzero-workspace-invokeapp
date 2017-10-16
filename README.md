# hubzero-workspace-invokeapp
experimental upstream versions of invoke_app

# Test cases

## Prereqs

To run the test cases, you first need to have the ```workspace``` docker
container template built on your system. See the
[hubzero-workspace-testenv](https://github.com/codedsk/hubzero-workspace-testenv)
repository for instructions on how to build the container template.

## Running the test cases

The Makefile's *test* target can be used to run the test cases

```
make test
```
or, use the ```docker  run``` command to launch the container and run the test cases:

```
docker run -i -t --rm \
    -v `pwd`:/opt/invokeapp \
    --name invokeapp-test-container \
    workspace \
    /usr/local/bin/pytest -s /opt/invokeapp/test_container_invokeapp.py
```

Running the ```docker run``` command, you can add in flags, like ```-s``` to
show the debugging statement from stdout or select specific tests to run by
setting marks with the ```-m``` flag.

## Behind the scenes

```invoke_app``` relies on a few features of the workspace environment:
1. ```SESSIONDIR``` environment variable should be set.
2. toolparams needs an X11 server, we use X Virtual Frame Buffer (xvfb-run)

The ```workspace``` docker container addresses these requirements by:
1. Hard coding the SESSION, SESSIONDIR, and RESULTSDIR in [entry.sh](https://github.com/codedsk/hubzero-workspace-testenv)
2. Launching ```docker run``` commands through ```xvfb-run -s "-screen 0 800x600x24" ...```
