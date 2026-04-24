# Pixi Dependency Management Notes

Last updated: 2026-04-24

This document captures the dependency-management lessons from stabilizing the
WhisperX transcription stack. It is intended to be the first place to check
before changing `pixi.toml` or `pixi.lock`.

## Mental Model

Pixi solves Conda and PyPI dependencies in two stages:

1. Conda packages from `[dependencies]` are resolved first.
2. PyPI packages from `[pypi-dependencies]` are resolved by uv after that.

The important detail is that Pixi passes already resolved Conda packages to uv
as locked packages. That prevents uv from installing its own copy of the same
package and makes the environment more coherent, but it also means broad Conda
requirements can accidentally force the PyPI solver into an older or awkward
package set.

In this project, broad Conda constraints allowed `pytorch` and `torchaudio` to
resolve to `2.10.0`. uv then had to resolve `whisperx` and `pyannote.audio`
around those locked Conda versions. That is why the correct fix was not a
post-install dedupe. It was to declare a compatible version window in the
manifest and let Pixi re-solve the lockfile.

References:

- Pixi PyPI integration says Conda packages are passed to uv as locked:
  https://pixi.prefix.dev/dev/reference/pixi_manifest/#pypi-dependencies
- Pixi PyTorch guidance warns about mixing incompatible package sources:
  https://pixi.prefix.dev/latest/python/pytorch/
- Pixi dependency overrides are a last resort because they ignore dependency
  constraints from upstream packages:
  https://pixi.prefix.dev/latest/advanced/override/

## Tools To Use Before Editing

Use these commands to understand the graph before changing constraints:

```bash
pixi tree whisperx
pixi tree pyannote-audio
pixi tree pytorch
pixi tree torchaudio
pixi tree --invert pytorch
pixi tree --invert torchaudio
pixi update --dry-run pytorch torchaudio whisperx pyannote-audio
```

Use a scratch manifest when testing a proposed solve:

```bash
mkdir -p /tmp/kaz-video-dub-pixi-solve
cp pixi.toml /tmp/kaz-video-dub-pixi-solve/pixi.toml
pixi add --manifest-path /tmp/kaz-video-dub-pixi-solve/pixi.toml --no-install \
  "pytorch>=2.5.1,<2.6" "torchaudio>=2.5.1,<2.6"
pixi add --manifest-path /tmp/kaz-video-dub-pixi-solve/pixi.toml --no-install --pypi \
  "whisperx>=3.4.5,<3.5" "pyannote-audio>=3.3.2,<4"
pixi lock --manifest-path /tmp/kaz-video-dub-pixi-solve/pixi.toml --dry-run
```

Use `pixi.lock` as generated output. Do not edit it by hand. Commit it after
`pixi lock` or a lock-updating Pixi command.

## Direct Dependencies, Constraints, And Overrides

Prefer direct dependency ranges when the package is a real runtime dependency of
this project. That is why `pytorch`, `torchaudio`, `whisperx`, and
`pyannote-audio` are declared directly in `pixi.toml`.

Use `[constraints]` when a Conda package may be pulled in transitively and we
only want to restrict it if it appears. Constraints do not install the package.

Use `[pypi-options.dependency-overrides]` only when an upstream PyPI dependency
has an incorrect or too-tight transitive requirement and we intentionally want to
override it. This is risky because uv will ignore the upstream package's own
version constraints for the overridden package.

There is no useful `dedupe` move for this class of issue. Pixi's model is a
single solved environment, not an npm-style nested dependency tree that can be
cleaned up afterward.

## Current WhisperX Stack

Current manifest windows:

```toml
[dependencies]
pytorch = ">=2.5.1,<2.6"
torchaudio = ">=2.5.1,<2.6"

[pypi-dependencies]
whisperx = ">=3.4.5,<3.5"
pyannote-audio = ">=3.3.2,<4"
```

Current resolved versions:

```text
whisperx       3.4.5
pyannote.audio 3.4.0
pytorch        2.5.1
torchaudio     2.5.1
```

These are range constraints, not exact pins. The ranges express a compatibility
generation. Pixi then selects the highest compatible versions inside that
generation.

## Why Not Latest WhisperX And pyannote.audio

As of 2026-04-24:

- Latest `whisperx` is `3.8.5`.
- Latest `pyannote.audio` is `4.0.4`.

They are not used because they are a different compatibility stack, not a drop-in
upgrade for the current project.

Local metadata for `whisperx 3.4.5` says:

```text
pyannote-audio >=3.3.2,<4.0.0
torch          >=2.5.1
torchaudio     >=2.5.1
```

Therefore `pyannote.audio 4.x` is not compatible with `whisperx 3.4.5` by the
package's own metadata. There is also a known upstream breaking-change thread
around `pyannote.audio 4.0` and WhisperX's `use_auth_token` call path:
https://github.com/m-bain/whisperX/issues/1241

Latest `whisperx 3.8.5` moved to a newer stack:

```text
pyannote-audio >=4.0.0
torch          ~=2.8.0
torchaudio     ~=2.8.0
torchcodec     >=0.6.0,<0.8.0
```

Reference:
https://github.com/m-bain/whisperX/blob/main/pyproject.toml

That means upgrading to latest WhisperX should be treated as a coordinated
stack migration:

```toml
whisperx = ">=3.8.5,<3.9"
pyannote-audio = ">=4,<5"
pytorch = "~=2.8.0"
torchaudio = "~=2.8.0"
```

It should not be mixed with `pytorch/torchaudio 2.10`, and it should be tested
against the real transcription sample before landing.

## Why Not Latest PyTorch And TorchAudio

The earlier broad ranges were:

```toml
pytorch = ">=2.4,<3"
torchaudio = ">=2.4,<3"
```

On 2026-04-24 those resolved to `pytorch 2.10.0` and `torchaudio 2.10.0`. That
pair is metadata-compatible with `whisperx 3.4.5` because WhisperX only declares
lower bounds. It is not runtime-compatible with the older WhisperX/pyannote VAD
stack.

Known break points:

- `torch >=2.6` changed the default `torch.load` behavior toward
  `weights_only=True`. The legacy pyannote/Lightning VAD checkpoint used by
  `whisperx 3.4.5` expects the older behavior unless an explicit workaround is
  applied.
- `torchaudio >=2.9` removed APIs deprecated in 2.8, including
  `torchaudio.info` and `torchaudio.AudioMetaData`. The pyannote/SpeechBrain
  side of the current stack can still touch those APIs.

References:

- PyTorch serialization behavior:
  https://docs.pytorch.org/docs/stable/notes/serialization.html
- TorchAudio 2.8 deprecation and 2.9 removal:
  https://docs.pytorch.org/audio/main/generated/torchaudio.info.html

The selected `>=2.5.1,<2.6` window is based on the oldest version WhisperX
requires (`>=2.5.1`) and the first known PyTorch break point (`2.6`). Keeping
`pytorch` and `torchaudio` on the same `2.5.x` family also avoids the
TorchAudio 2.9 API-removal break point.

## Compatibility Matrix

| Package family | Avoid with current stack | Reason |
| --- | --- | --- |
| `pyannote.audio >=4` | `whisperx 3.4.x` | `whisperx 3.4.5` requires `<4`; pyannote 4 has breaking API changes. |
| `pytorch >=2.6` | `whisperx 3.4.x` VAD checkpoint | `torch.load` default behavior changed, causing legacy checkpoint load failures without a workaround. |
| `torchaudio >=2.9` | `pyannote.audio 3.x` / SpeechBrain path | Deprecated audio metadata APIs were removed. |
| `pytorch/torchaudio 2.10` | `whisperx 3.4.x + pyannote 3.x` | Metadata may allow it, but runtime VAD load path breaks on the changes above. |
| `whisperx >=3.8.5` | `pytorch/torchaudio 2.10` | Latest WhisperX declares `torch~=2.8.0` and `torchaudio~=2.8.0`. |

## Upgrade Checklist

Before changing this stack:

1. Read package metadata for the installed and target versions:

   ```bash
   pixi run python - <<'PY'
   from importlib.metadata import metadata, version
   for pkg in ["whisperx", "pyannote.audio"]:
       print(pkg, version(pkg))
       for req in metadata(pkg).get_all("Requires-Dist") or []:
           if any(name in req.lower() for name in ["torch", "torchaudio", "pyannote", "torchcodec"]):
               print(" ", req)
   PY
   ```

2. Dry-run the solve in `/tmp`.
3. Check the inverse tree for `pytorch` and `torchaudio`.
4. Run `pixi lock`.
5. Confirm versions:

   ```bash
   pixi run python -c "import torch, torchaudio, importlib.metadata as md; print(torch.__version__, torchaudio.__version__, md.version('whisperx'), md.version('pyannote.audio'))"
   ```

6. Run:

   ```bash
   pixi run test
   pixi run typecheck
   pixi run pyright
   pixi run ruff check src/video_dub/providers/whisperx_provider.py tests/test_whisperx_provider.py
   ```

7. Smoke-test real WhisperX VAD loading and one short transcription sample.

