# Mark II multiline capture

Hold the scan button while moving across several printed lines. This experimental patch detects line changes and runs the pen's ordinary finish/start sequence automatically. The standard Mark app receives the resulting scans through its existing processing path and combines them as usual.

This repository preserves the source and exact application payload that the device owner reported working. It patches the existing ARM Linux program; the factory camera SDK, text recognition pipeline, and phone app are unchanged.

## Start here

- [How it works](docs/HOW_IT_WORKS.md): simple explanation and exact detection rules.
- [Development process](docs/PROCESS.md): reverse engineering, failed attempts, diagnostics, and the final correction.
- [Build and checks](docs/BUILD.md): reproduce the payload and run the checks offline.
- [OTA installation](docs/INSTALL.md): macOS uploader, compatibility requirements, and verification.
- [Device interface](docs/DEVICE.md): resolved addresses and diagnostic formats.
- [Evidence and limitations](docs/VALIDATION.md): what was verified and what remains uncertain.

## Files

| File | Purpose |
| --- | --- |
| `capture.c` | Button lifecycle, focus/lift detection, startup buffer, and diagnostics |
| `motion.c` | Small gradient-based image movement estimator |
| `build.py` | Hash-pinned ELF patch builder; never contacts hardware |
| `check_*.py`, `verify.py` | ARM emulation, buffer ownership, capture preservation, and synthetic font checks |
| `ota_client.swift` | Bluetooth updater; defaults to read-only preflight |
| `read_camera.py`, `read_queue.py`, `replay_camera.py` | Decode and replay locally supplied diagnostics |
| `ai-pen.capture-rewrite.experimental.bin` | Exact installed application payload |
| `vendor/ai-pen.hotupdate.recovered.bin` | Exact recovered base application needed to reproduce the payload |
| `evidence/` | Historical software results and installation summary; no camera pixels or scanned text |

## Exact working snapshot

```text
Payload SHA256: 8bfce6857fd2c6e17aa30a94990660190d6dce53668df3b576ea22b76acc323c
Payload bytes:  332782
OTA CRC32:      32d3e656
Base SHA256:    d4919df3e0a72cd8cb9dcd57e6c2e75d7e03391c0e655286a015bc6532111d44
Camera tag:    CQB2
Queue format:  version 2
```

The transfer checksum, scheduled replacement/reboot, and subsequent read-only reconnect were verified. The owner then reported: “great it works.” Fresh raw buffer counters and the complete final saved text were not independently inspected after that report. Repeated capture consistency is unmeasured.

The startup buffer does **not** eliminate the native camera pause during line completion. Exact base compatibility must be established before using another pen; the displayed version `7.6.2.2` alone is insufficient.

Private scans, page photos, Bluetooth device identifiers, raw camera recordings, and local tool installations are excluded. The bundled base/patched executables contain manufacturer code; this snapshot does not assign that code an open-source license. See [NOTICE](NOTICE.md).
