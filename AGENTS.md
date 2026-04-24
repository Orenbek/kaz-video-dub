# Agent Instructions

## Third-Party Package Failures

When a third-party package fails at runtime or import time, first investigate
dependency and version compatibility before adding local patches or monkeypatches.

Preferred order:

1. Inspect the installed package versions and package metadata.
2. Check the dependency tree and inverse dependency tree.
3. Search upstream documentation, release notes, and issue trackers for known
   compatibility ranges or breaking changes.
4. Express the correct compatible version window in `pixi.toml`, then re-solve
   `pixi.lock`.
5. Validate with the smallest real failing path and the normal test/typecheck
   commands.

Only add local compatibility patches when version alignment cannot reasonably
solve the problem, or when an upstream package has no released fix and the patch
is clearly documented as a temporary workaround.

