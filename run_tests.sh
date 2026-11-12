#!/usr/bin/env bash
set -e
export PYTHONPATH=.
echo "== offline tests"
python test_memory.py && python test_guards.py && python test_extractor.py
echo "== needs Ollama"
python eval_extractor.py
python eval_e2e.py
python test_router.py
python test_battery_guards.py
python eval_router.py
