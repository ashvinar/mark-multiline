# Evidence and limitations

## Historical accepted payload

The historical files in `evidence/` belong to SHA256 `8bfce6857fd2c6e17aa30a94990660190d6dce53668df3b576ea22b76acc323c`.

- 110 software cases passed: 17 controller, 5 preservation, 8 camera/integration, 11 queue, 15 movement, and 54 synthetic font cases.
- Four recorded camera replays passed with zero reported queue errors and no outstanding retained-buffer leaks in the emulator.
- Receiver verified CRC32 `32d3e656` for all 332782 payload bytes, scheduled application replacement/reboot, and passed a subsequent read-only Bluetooth reconnect.
- Owner reported the installed correction working.

The historical `hardware_verified: false` field means independent raw capture acceptance was not completed. It does not contradict `hardware_installed: true` or the owner's working report. The final fresh `CQB2` camera tag, queue activation counters, and exact complete phone text were not independently collected after that report.

## Repository verification

Packaging preserves `capture.c` and `motion.c` byte-for-byte. Build input location and the scalar test-fixture path were adapted to the standalone repository. The uploader's owner-specific Bluetooth UUID was replaced by a required `--device` argument; its firmware pin and transfer protocol are retained.

`verify.py` checks the local payload hash and all case counts. Local results are separate from historical evidence. A complete offline pass is not a physical device acceptance test, and the packaging checks never install firmware.

## Remaining limits

1. Lift detection infers contact from focus, detail, and movement; it does not measure physical distance.
2. The native camera can pause for roughly 250 ms during completion/restart. The startup FIFO does not provide continuous acquisition through that gap.
3. The final device's actual pool size and FIFO activation were not independently measured. Buffer-zero fallbacks are still relevant.
4. Text recognition and app grouping are unchanged. Correct transfer does not establish correct recognition.
5. A generation change can cancel an in-flight frame during physical release; perfect final-frame preservation is not established.
6. No complete factory flash backup or independently verified recovery procedure is bundled.
7. Compatibility with other pens, SDK builds, languages, scan speeds, and lighting conditions is not established by the version label or synthetic checks.

These are reasons to keep measured evidence separate from an installation success or a single successful scan.
