# Build and checks

## Environment

The snapshot was built on macOS with Apple clang 17 (`clang-1700.6.3.2`). The uploader was compiled with Swift 6.2.3. Python checks use pyelftools, Unicorn, and Pillow. The synthetic font check uses the system Helvetica, Times, and Courier fonts on macOS.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python build.py
.venv/bin/python verify.py
```

`build.py` compiles `capture.c`, which includes `motion.c`, for Cortex-A7 ARMv7-A Thumb. It checks the base executable's SHA256 and original hook bytes, relocates the new functions, expands writable state, and adds a separate read/execute ELF mapping. It keeps original imports and virtual addresses. It does not contact the pen.

Outputs are `capture.o`, `build.json`, and `ai-pen.capture-rewrite.experimental.bin`. The latter two are tracked to preserve the exact installed payload and its layout. A different compiler can produce a different hash; never treat it as the accepted payload automatically.

The optional `build.py --monitor` changes the controller's behavior for diagnostics and overwrites those outputs. It is not the accepted active build. Rebuild normally before running the standard checks.

## Checks

`verify.py` runs the six existing offline check scripts sequentially and validates their output counts and the pinned application hash. It writes `verification-local.json` and leaves the historical results in `evidence/` unchanged.

| Check | Cases | Coverage |
| --- | ---: | --- |
| `check_arm.py` | 17 | Full key cycle, asynchronous completion, cancellation, failure handling, layout passthrough |
| `check_preservation.py` | 5 | Whitespace, mild focus changes, transient blur, and preservation before confirmed lift |
| `check_camera.py` | 8 | Real callback integration, diagnostics, release bookkeeping, bounded storage |
| `check_queue.py` | 11 | Real native buffer lifetime, FIFO ordering, capacity fallback, late/large/small pools |
| `check_motion.py` | 15 | Gradient matching with movement, exposure changes, borders, faint detail, unrelated images |
| `check_fonts.py` | 54 | Synthetic sharp/blurred text across three fonts, sizes, and ink levels |

These checks execute ARM instructions in Unicorn. SDK, OS, and timing behavior are simulated. The six-pass fixture contains only scalar measurements and is translated into synthetic focus states by one historical regression. Neither it nor the font suite proves real capture reliability.

## Recorded replay

Four historical camera recordings were replayed successfully; summary results are in `evidence/replay-results.json`. Raw recordings are excluded because they contain scan imagery. To replay your own locally retained recordings:

```sh
.venv/bin/python replay_camera.py /path/to/camera-2.bin /path/to/camera-3.bin
```

The replay expands recorded thumbnails to synthetic full-size frames and mocks the SDK. It checks decisions and buffer ownership, not real OCR, acquisition timing, or words recovered.

## Uploader

```sh
swiftc -module-cache-path .swift-module-cache ota_client.swift -o ota_client
./ota_client --help
```

Compiling does not contact hardware. Read [INSTALL.md](INSTALL.md) before running it with a device argument. The shared uploader requires a device UUID instead of embedding the original owner's identifier; that host-side argument change does not alter the firmware payload.
