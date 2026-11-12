# Resolved device interface

## Platform

- Retail Mark II; displayed application version `7.6.2.2`.
- Lombo Technology platform; executable targets Cortex-A7 / ARMv7-A Thumb.
- Linux with uClibc and POSIX threads, not an RTOS implementation.
- Exact physical SoC part, RAM capacity, clock, and camera sensor model were not established.
- Observed grayscale input: 96 × 108, in a 12288-byte native allocation. Observed frame rate was approximately 120 fps, not a guaranteed specification.

## Pinned functions and state

These addresses belong to the exact bundled base executable. Thumb function pointers have their low bit set.

| Address | Meaning |
| --- | --- |
| `0x4db7d` | Complete original key-up handler |
| `0x4df65` | Complete original key-down handler |
| `0x4c805` | Existing worker queue submission |
| `0x4cbe9` | Existing completion worker |
| `0x4c0ec` | Original camera callback entry |
| `0x209a8` | SDK frame-push PLT entry |
| `0x4c0bd` | Original frame-pop callback |
| `0x7c864` | Native key mutex |
| `0x7c660` | Native descriptor-list head |
| `0x7c668` | Native outstanding-frame count |
| `0x7c4b8` | SDK state |
| `0x7cd80` | Added controller state base |

The payload adds a read/execute mapping at `0x60000` and extends writable state separately. Controller state is 377744 bytes, mostly bounded diagnostic storage; appended code is 4814 bytes. There is no new DMA allocation or read/write/execute mapping.

## Bluetooth OTA

Service `EE01`, write characteristic `EE02`, notification characteristic `EE03`. Packets carry session information, offsets, and CRC32 checks. The shared uploader sends 180-byte data chunks on a 40 ms timer and limits outstanding unacknowledged packets. The accepted payload uses OTA CRC32 `32d3e656`.

## USB evidence

On the device, diagnostics are under `/media/Diagnostics/shadow/`. A macOS-mounted Mark drive exposed them under `/Volumes/Mark/Diagnostics/shadow/`.

There are bounded rings of `line-N.jpg`, `trace-N.bin`, `camera-N.bin`, and `queue-N.bin`, with N from 0 to 15. Files persist across sessions/reboots, so a matching filename alone does not prove fresh evidence. Camera/trace generation and tags matter.

Image metadata is in `System/database/gatt_image_db.db`, table `image_metadata`. Match JPEGs with byte length and CRC32. Transfer status 2 with all packets acknowledged establishes image delivery only.

### Queue format

Little-endian u32 fields; `read_queue.py` accepts old 64-byte version 1 and current 68-byte version 2 reports:

```text
magic QBF1, version, generation, capacity, peak, sent, released, errors,
fallbacks, direction (signed), reference_detail, current_detail,
moving_samples, low_detail_count, remaining_queue, pending_frame,
pool_nodes_observed_up_to_ten (version 2 only)
```

### Camera format

48-byte header (12 little-endian u32 values):

```text
magic CAM1, version 1, build_tag, generation, camera_frames, records,
stored, stride 704, pushes, rejections, last_push, controller_errors
```

Current tag: `CQB2` (`0x32425143`). Historical recognized tags are `CQD1` and `CQB1`. Each 704-byte record has 14 u32 values followed by 648 grayscale thumbnail pixels:

```text
serial, time, phase, sdk_before, sdk_after, pushes, rejections,
last_push, callback_result, width, height, edge, packedrange, generation
```

`packedrange` stores maximum brightness step in its high 16 bits and contrast in its low 16 bits. The ring holds 512 records. `read_camera.py` validates sizes, serial/ring placement, and generation before producing JSON/contact sheets. Its outputs contain scan imagery and stay local by default.

### Trace format

60-byte header (15 little-endian u32 values):

```text
generation, phase, observed_generation, seen, blank_frames, frames,
sample_count, rotations, width, height, physical_address, bytes,
errors, detected_lifts, saved_images
```

Each sample is 16 bytes: frame, edge, packedrange, phase.
