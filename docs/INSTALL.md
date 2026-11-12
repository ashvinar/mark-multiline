# OTA installation

This repository contains an application hot-update payload, not a complete factory firmware or verified recovery image.

The fixed hooks target one exact recovered retail application. Another pen reporting `7.6.2.2` is not sufficient evidence that its binary layout is compatible. Establish the exact base hash and hardware compatibility separately before flashing another unit. No universal installer or verified recovery procedure is included.

## Original installation

The accepted payload is SHA256 `8bfce6857fd2c6e17aa30a94990660190d6dce53668df3b576ea22b76acc323c`, 332782 bytes, CRC32 `32d3e656`. It was transferred with 40 ms packet pacing. The receiver verified the complete checksum, scheduled replacement/reboot, and answered a subsequent read-only Bluetooth preflight. The owner then reported that multiline scanning worked.

USB exposed retained diagnostics. The update itself used Bluetooth, with the Mark phone app fully closed and the pen awake.

## Shared uploader

Compile `ota_client.swift` as described in [BUILD.md](BUILD.md). Keep the resulting executable beside the pinned `.bin` file.

Supply the target's **macOS CoreBluetooth UUID**, not a MAC address. The original device identifier is not in this repository. Obtain the identifier through your own Bluetooth discovery/diagnostic tools; this repository does not implement a device-selection browser.

Read-only check:

```sh
./ota_client --device YOUR-MACOS-BLUETOOTH-UUID
```

After independent compatibility checks, installing is an explicit separate invocation:

```sh
./ota_client --device YOUR-MACOS-BLUETOOTH-UUID --install
```

`--install` transfers the application and automatically schedules replacement/reboot after receiver verification. It is not a download-only or staging command. Running without it does not start an OTA session. Invalid/missing arguments exit before Bluetooth starts.

The client pins payload SHA256 and length, checks the device version reply, validates progress offsets and rolling CRCs, and aborts if the receiver requests retransmission. A disconnect before verified scheduling is a failed update attempt. Do not infer installation from files merely existing locally.

After a successful scheduled reboot, run the read-only command again. The displayed version remains `7.6.2.2`; it is not a runtime fingerprint for this patch.

## Capture acceptance

1. Unplug, open Mark, and scan multiple known lines with one physical hold and normal lifts.
2. Check the exact newest saved text against all intended lines.
3. Reconnect USB without another button press and copy retained diagnostics before further tests.
4. Verify fresh camera tag `CQB2`, queue version 2, observed pool count, capacity/peak/sent, error counters, and no leftover retained buffers.
5. Inspect every raw line image. A transfer acknowledgement establishes delivery, not correct capture or recognition.

See [DEVICE.md](DEVICE.md) for paths and formats. Do not remove diagnostics by flashing a different “clean” build after a successful test without testing that exact build again.
