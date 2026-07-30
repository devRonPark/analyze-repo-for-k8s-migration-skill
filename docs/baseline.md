# Executable Baseline

Date: 2026-07-29

The original VS-001 baseline on the clean source revision was:

```text
python3 scripts/validate_skill.py .
python3 -m unittest discover -s tests -p 'test_*.py' -v
# VS-008에서 폐기된 static regression wrapper
```

Observed result before the vertical-slice changes:

- package validator: PASS;
- unit tests: 31 tests PASS;
- static regression fixture: 8 cases PASS.

The static fixture compared prewritten JSON objects and was not agent
end-to-end coverage. VS-008 retired it as a source of truth. The current gate
uses the executable scenario evaluator:

```text
python3 scripts/evaluate_scenarios.py --cases tests/evaluation/cases.json --actual-dir tests/evaluation/golden-actual
```

It evaluates eight external report artifacts, expected core facts, forbidden
behavior, repeated-run core fields, and repository immutability.
