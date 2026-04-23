.PHONY: all bootstrap venv run test test-only test-sound clean

all: bootstrap venv

bootstrap: vendor/adarkroom/.git
vendor/adarkroom/.git:
	@echo "==> fetching doublespeakgames/adarkroom into vendor/ (~30 MB, one time)"
	@mkdir -p vendor
	git clone --depth=1 https://github.com/doublespeakgames/adarkroom.git vendor/adarkroom
	@echo "==> bootstrap complete"

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python dark_room.py

test: venv
	.venv/bin/python -m tests.qa

test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

test-sound: venv
	.venv/bin/python -m tests.sound_test

clean:
	rm -rf dark_room_tui/__pycache__ tests/__pycache__ tests/out/*.svg
