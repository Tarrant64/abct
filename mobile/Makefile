# ABCT Mobile — device deploy helpers.
# These wrap scripts/build_device.sh; they do not replace it and do not call
# `flutter run`/`flutter build` directly, so SHA stamping, the dirty-tree
# guard, and framework re-signing all still apply. See that script and the
# README's "Installing on a Physical iPhone" section for what it does.

BUILD_SCRIPT := scripts/build_device.sh

# Device UDID, in priority order:
#   1. `make deploy DEVICE=<udid>`      (command line — always wins)
#   2. ABCT_DEVICE_ID in your shell env (no file edit needed)
#   3. the default below (this user's iPhone)
ifeq ($(origin DEVICE),undefined)
  ifneq ($(ABCT_DEVICE_ID),)
    DEVICE := $(ABCT_DEVICE_ID)
  else
    DEVICE := 00008150-001A62AE0C20401C
  endif
endif

.DEFAULT_GOAL := help

.PHONY: help deploy iphone build-only verify _check-script

help:
	@echo "ABCT Mobile — device deploy targets:"
	@echo "  make deploy       Build, re-sign, and install release build on the iPhone"
	@echo "  make iphone       Alias for 'make deploy'"
	@echo "  make build-only   Build + re-sign only, skip install (compile-error check)"
	@echo "  make verify       Print what to check on-device after an install"
	@echo "  make help         Show this menu (default target — bare 'make' is safe)"
	@echo ""
	@echo "Current default device: $(DEVICE)"
	@echo "Override:  make deploy DEVICE=<udid>   or   export ABCT_DEVICE_ID=<udid>"

deploy iphone: _check-script
	@if ! xcrun devicectl list devices 2>/dev/null | grep -q "$(DEVICE)"; then \
		echo "ERROR: device $(DEVICE) was not found by devicectl."; \
		echo "  - Plug in the iPhone, unlock it, and tap Trust if prompted."; \
		echo "  - List connected devices: xcrun devicectl list devices"; \
		echo "  - Wrong phone? Override: make deploy DEVICE=<correct-udid>"; \
		exit 1; \
	fi
	./$(BUILD_SCRIPT) --device $(DEVICE)
	@echo ""
	@echo "Installed. Run 'make verify' for what to check on the phone."

build-only: _check-script
	./$(BUILD_SCRIPT) --no-install

verify:
	@echo "On the phone, confirm the fix actually landed:"
	@echo "  1. Settings tab -> About -> Build should show:"
	@echo "       $$(git rev-parse --short HEAD 2>/dev/null || echo '<run this from dashboard/mobile>') (dirty: false)"
	@echo "     If it says 'unknown', the install didn't go through build_device.sh."
	@echo "  2. Pull down past ~140px on the Dashboard tab (hard refresh, amber indicator)."
	@echo "  3. Force-quit the app (swipe up in the app switcher) and reopen it."
	@echo "  4. Confirm the timestamp/values do NOT roll back to older data on reopen."

_check-script:
	@if [ ! -f "$(BUILD_SCRIPT)" ]; then \
		echo "ERROR: $(BUILD_SCRIPT) not found."; \
		echo "  Run make from dashboard/mobile/ (this Makefile's own directory)."; \
		exit 1; \
	fi
	@if [ ! -x "$(BUILD_SCRIPT)" ]; then \
		echo "ERROR: $(BUILD_SCRIPT) exists but isn't executable."; \
		echo "  Fix with: chmod +x $(BUILD_SCRIPT)"; \
		exit 1; \
	fi
