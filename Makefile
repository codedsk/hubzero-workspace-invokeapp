PWD := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

test:
	docker run -i -t --rm \
	  -v ${PWD}:/opt/invokeapp \
	  --name invokeapp-test-container \
	  workspace \
	  /usr/local/bin/pytest /opt/invokeapp/test_container_invokeapp.py
