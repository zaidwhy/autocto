---
name: Bug report
about: Report incorrect or crashing analyzer behavior
title: "[bug] "
labels: bug
---

## What happened

A clear description of the incorrect behavior (wrong score, wrong ranking,
crash, etc).

## Which analyzer

- [ ] `src/autocto/hotspots.py` (`analyze_repo`, or one of the pure functions
      it wires together)
- [ ] `src/autocto/duplicates.py` (`analyze_repo`, or one of the pure
      functions it wires together)

## How to reproduce

The exact call that triggers it, plus any fixture data needed to reproduce
(a minimal `git log --numstat` snippet, or minimal file contents). Please do
not just describe the repo you ran it against - paste the smallest input
that still reproduces the bug.

```python
# minimal reproduction here
```

## Expected vs actual

What you expected the function to return, and what it actually returned.

## Environment

- Python version (`python --version`): 
- autocto version / commit hash: 
