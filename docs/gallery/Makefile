# Gallery render pipeline (dev-only). Run from anywhere via:
#   make -C docs/gallery gallery              # all commands
#   make -C docs/gallery gallery CMD=picks2seg
#   make -C docs/gallery gallery GROUP=convert
#   make -C docs/gallery render               # print the ChimeraX command for master.cxc
#   make -C docs/gallery clean                # remove build/
#
# `gallery` builds inputs, runs each CLI command, verifies output and emits .cxc files.
# It does NOT launch ChimeraX — it prints the command for you to run (a GUI window opens).

DOCS := $(abspath ..)
PY ?= python
CHIMERAX ?= /Applications/ChimeraX.app/Contents/MacOS/ChimeraX
MASTER := build/cxc/master.cxc

# Build the selection flag from CMD / GROUP (default: --all).
ifdef CMD
SELECT := --only $(CMD)
else ifdef GROUP
SELECT := --group $(GROUP)
else
SELECT := --all
endif

.PHONY: gallery render clean help

gallery:
	cd $(DOCS) && $(PY) -m gallery.driver $(SELECT)

render:
	@if [ ! -f "$(MASTER)" ]; then echo "No $(MASTER); run 'make gallery' first."; exit 1; fi
	"$(CHIMERAX)" --exit "$(abspath $(MASTER))"

clean:
	rm -rf build

help:
	@echo "targets: gallery [CMD=<name> | GROUP=<convert|process|logical>], render, clean"
