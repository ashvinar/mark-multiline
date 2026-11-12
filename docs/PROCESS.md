# Development process

## Observed behavior

The retail pen captured only the first line when the button stayed held across multiple physical lines. Normal release/press cycles produced scans that the standard app could combine into one highlight. That existing behavior supplied the integration point.

## Reverse engineering

The existing application executable was recovered and inspected as an ARM Linux ELF. Static analysis and disassembly located camera input, frame release, scan key handlers, the worker queue, completion/copy work, image encoding, and the Bluetooth hot-update path. The implementation reuses these existing functions at hash-pinned addresses instead of replacing the frozen SDK.

The resolved architecture is recorded in [DEVICE.md](DEVICE.md). The recovered application is bundled as the reproducible build input, not presented as manufacturer source or a complete flash backup.

## Early automatic restart attempts

The controller initially used focus changes to infer a line transition. Restarting just part of the scanner path was insufficient. The implementation was changed to run the complete ordinary key-up handler, asynchronous completion/copy work, and ordinary key-down handler, with cancellation on actual physical release.

Some multiline tests succeeded, but later passages still lost whole lines or large portions. A successful example did not establish reliable behavior.

## Separate capture from transfer and recognition

Bounded on-device traces, raw line JPEGs, camera thumbnails, and queue counters were added. JPEGs could be matched to database entries by exact byte count and CRC32. Fully acknowledged transfers still included tiny or blank captures, locating at least some loss before the phone's text recognition.

Camera journals also showed readable detail passing during a failed session. A sharp static edge after restart could imitate focused text. The precise native stitcher failure was not proven; the measurements supported improving startup selection and movement evidence.

## Movement and buffer ownership

A small gradient-matching estimator was added for direction and per-line detail changes. A startup FIFO retains actual native camera buffers and hands them to the SDK only after the original callback has updated its outstanding-frame count. Reusing returned buffer pointers would risk corrupted images, so ownership was tested explicitly.

This FIFO covers startup after the native camera resumes. It does not remove the approximately 250 ms completion/restart acquisition gap observed in earlier recordings.

## Buffer correction

The earlier buffered build, SHA256 `105047e2adf59260f86f9022f251b007e7014f6ce6200969e2d943061f5519ab`, executed on the pen but all seven fresh queue reports had capacity, peak, and sent counts of zero.

The current correction:

- Counts only ten distinct native descriptor nodes, enough to establish the maximum eight-frame queue plus headroom, rather than rejecting a valid pool at an arbitrary traversal limit.
- Reprobes when real input arrives if the pool was unavailable at physical key-down.
- Supports two/three-node pools with one native slot reserved, and larger pools with two reserved.
- Applies startup quality selection even when no FIFO can be retained.
- Adds observed pool-node count to queue format version 2 and changes the camera tag to `CQB2`.

The exact cause of zero capacity on the earlier device run was not established. The correction handles several software causes and exposes measurements for future diagnosis; it does not prove the pen has a particular pool size.

## Final snapshot

The exact current payload passed 110 software checks and four recorded ARM replays. Bluetooth transfer, checksum, replacement/reboot scheduling, and read-only reconnection were verified. The owner reported “great it works.” The exact installed build was retained without a cleanup reflash.

For explicit evidence limits, see [VALIDATION.md](VALIDATION.md). Historical unsuccessful binaries and private raw scans are not included in this focused repository.
