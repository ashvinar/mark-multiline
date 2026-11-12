import Foundation
import CoreBluetooth
import CryptoKit

setbuf(stdout, nil)

extension Data {
    mutating func u16(_ value: UInt16) { append(UInt8(truncatingIfNeeded: value)); append(UInt8(truncatingIfNeeded: value >> 8)) }
    mutating func u32(_ value: UInt32) { for shift in stride(from: 0, to: 32, by: 8) { append(UInt8(truncatingIfNeeded: value >> shift)) } }
    func read32(_ offset: Int) -> UInt32 {
        (0..<4).reduce(0) { $0 | UInt32(self[offset + $1]) << ($1 * 8) }
    }
}

enum CRC32 {
    static let table: [UInt32] = (0..<256).map { value in
        var c = UInt32(value)
        for _ in 0..<8 { c = (c >> 1) ^ (c & 1 == 1 ? 0xedb88320 : 0) }
        return c
    }
    static func update(_ final: UInt32, _ data: Data) -> UInt32 {
        var crc = final ^ 0xffffffff
        for byte in data { crc = table[Int((crc ^ UInt32(byte)) & 255)] ^ (crc >> 8) }
        return crc ^ 0xffffffff
    }
}

final class OTAClient: NSObject, CBCentralManagerDelegate, CBPeripheralDelegate {
    enum Stage { case connecting, info, begin, sending, apply, reboot, finished }
    let deviceID: UUID
    let expectedHash = "8bfce6857fd2c6e17aa30a94990660190d6dce53668df3b576ea22b76acc323c"
    let install = CommandLine.arguments.contains("--install")
    let session = UInt32.random(in: 1...UInt32.max)
    let firmware: Data
    var central: CBCentralManager!
    var pen: CBPeripheral?
    var write: CBCharacteristic?
    var stage: Stage = .connecting
    var timer: DispatchSourceTimer?
    var packets: [Data] = []
    var offsets: [Int] = []
    var rollingCRCs: [Int: UInt32] = [0: 0]
    var packetIndex = 0
    var acknowledgedIndex = 0
    var acknowledgedOffset = 0
    var lastEvent = Date()
    var started = Date()
    var verified = false
    var applyScheduled = false
    var success = false

    init(deviceID: UUID) {
        self.deviceID = deviceID
        let path = URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL.deletingLastPathComponent()
            .appendingPathComponent("ai-pen.capture-rewrite.experimental.bin")
        firmware = try! Data(contentsOf: path)
        super.init()
        let digest = SHA256.hash(data: firmware).map { String(format: "%02x", $0) }.joined()
        guard digest == expectedHash, firmware.count == 332782 else {
            fail("Payload does not match the audited experimental build."); return
        }
        print("Mode: \(install ? "INSTALL EXPERIMENTAL APPLICATION" : "READ-ONLY PREFLIGHT")")
        print("Payload: \(firmware.count) bytes; SHA256=\(digest)")
        central = CBCentralManager(delegate: self, queue: nil,
            options: [CBCentralManagerOptionShowPowerAlertKey: false])
        let clock = DispatchSource.makeTimerSource(queue: .main)
        clock.schedule(deadline: .now(), repeating: .milliseconds(40))
        clock.setEventHandler { [weak self] in self?.tick() }
        clock.resume()
        timer = clock
    }

    func centralManagerDidUpdateState(_ manager: CBCentralManager) {
        guard manager.state == .poweredOn else {
            if manager.state != .unknown && manager.state != .resetting { fail("Bluetooth is unavailable.") }
            return
        }
        if let known = manager.retrievePeripherals(withIdentifiers: [deviceID]).first { connect(known) }
        manager.scanForPeripherals(withServices: [CBUUID(string: "EE01")])
    }
    func connect(_ peripheral: CBPeripheral) {
        guard pen == nil else { return }
        pen = peripheral; peripheral.delegate = self; central.connect(peripheral)
        print("Connecting to the previously identified Mark pen.")
    }
    func centralManager(_ manager: CBCentralManager, didDiscover peripheral: CBPeripheral,
                        advertisementData: [String: Any], rssi RSSI: NSNumber) {
        if peripheral.identifier == deviceID { connect(peripheral) }
    }
    func centralManager(_ manager: CBCentralManager, didConnect peripheral: CBPeripheral) {
        central.stopScan(); lastEvent = Date(); peripheral.discoverServices([CBUUID(string: "EE01")])
    }
    func centralManager(_ manager: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        fail("Could not connect: \(String(describing: error))")
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil, let service = peripheral.services?.first else { fail("Mark service unavailable."); return }
        peripheral.discoverCharacteristics(nil, for: service)
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { fail("Could not inspect Mark characteristics."); return }
        let chars = service.characteristics ?? []
        write = chars.first { $0.uuid.uuidString.hasPrefix("0000EE02-") }
        guard write?.properties.contains(.writeWithoutResponse) == true,
              let notify = chars.first(where: { $0.uuid.uuidString.hasPrefix("0000EE03-") }),
              notify.properties.contains(.notify) else { fail("Unexpected Mark interface."); return }
        peripheral.setNotifyValue(true, for: notify)
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, characteristic.isNotifying else { fail("Notification subscription failed."); return }
        stage = .info; lastEvent = Date(); send(Data([3, 1]))
    }
    func preparePackets() {
        guard let pen else { return }
        let chunkSize = min(180, pen.maximumWriteValueLength(for: .withoutResponse) - 24)
        guard chunkSize > 0 else { fail("Negotiated Bluetooth payload is too small."); return }
        var offset = 0, rolling: UInt32 = 0
        while offset < firmware.count {
            let end = min(offset + chunkSize, firmware.count)
            let chunk = firmware.subdata(in: offset..<end)
            rolling = CRC32.update(rolling, chunk)
            var packet = Data([6, 2]); packet.u32(session); packet.u32(UInt32(packets.count))
            packet.u32(UInt32(offset)); packet.u16(UInt16(chunk.count))
            packet.u32(CRC32.update(0, chunk)); packet.u32(rolling); packet.append(chunk)
            offsets.append(offset); packets.append(packet); rollingCRCs[end] = rolling
            offset = end
        }
        guard rolling == CRC32.update(0, firmware), rolling != 0 else { fail("CRC preparation failed."); return }
        print("Prepared \(packets.count) packets, \(chunkSize)-byte chunks; CRC32=\(String(rolling, radix: 16)).")
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        guard error == nil, let data = characteristic.value, data.count >= 2 else { return }
        lastEvent = Date()
        if data[0] == 3 && data[1] == 1 && stage == .info {
            guard data.count >= 22, Array(data[18..<22]) == [7, 6, 2, 2] else {
                fail("Live firmware information does not match the recovered 7.6.2.2 base."); return
            }
            print("Live firmware information matches 7.6.2.2.")
            preparePackets()
            guard stage != .finished else { return }
            if !install { finish(true, "Preflight passed. No OTA session or firmware write was started."); return }
            var begin = Data([6, 1]); begin.u32(session); begin.u32(0)
            // The recovered receiver rejects its own version word. This is the
            // next test version in the session header; the base app's displayed
            // version remains 7.6.2.2 because its info reply is unchanged.
            begin.u32(0x03020607); begin.u32(UInt32(firmware.count))
            begin.u32(UInt32(packets.count)); begin.u32(CRC32.update(0, firmware))
            stage = .begin; started = Date(); send(begin)
            print("Started experimental OTA session \(session).")
            return
        }
        guard data[0] == 6, data.count >= 6, data.read32(2) == session else { return }
        switch data[1] {
        case 1:
            guard stage == .begin, data.count >= 12 else { return }
            guard data[6] == 0, data[7] == 0, data.read32(8) == 0 else {
                fail("OTA begin rejected: \(data.map { String(format: "%02x", $0) }.joined())."); return
            }
            stage = .sending; print("Receiver accepted the session.")
        case 3:
            guard data.count >= 15, stage == .sending || stage == .apply else { return }
            let offset = Int(data.read32(6)), crc = data.read32(10), status = data[14]
            guard offset <= firmware.count, rollingCRCs[offset] == crc, status == 0 || status == 2 else {
                fail("Receiver progress failed its offset/CRC checks."); return
            }
            guard status != 2 else {
                fail("Receiver requested retransmission; stopped this session so a fresh transfer can start safely."); return
            }
            guard offset >= acknowledgedOffset else { return }
            acknowledgedOffset = offset
            acknowledgedIndex = offsets.firstIndex(where: { $0 >= offset }) ?? packets.count
            print("Verified transfer: \(offset)/\(firmware.count) bytes.")
        case 4:
            guard data.count >= 8, data[6] == 0, data[7] == 0 else {
                fail("Receiver rejected the completed image CRC."); return
            }
            verified = true; stage = .apply
            print("Receiver verified the complete image CRC.")
        case 5:
            guard data.count >= 8, data[6] == 0, data[7] == 0, verified else {
                fail("Receiver did not confirm scheduling the update."); return
            }
            applyScheduled = true; stage = .reboot
            print("Receiver scheduled the application replacement and reboot.")
        default: break
        }
    }
    func tick() {
        guard stage != .finished else { return }
        if Date().timeIntervalSince(lastEvent) > 40 { fail("Timed out waiting for the pen."); return }
        guard stage == .sending, let pen, pen.canSendWriteWithoutResponse else { return }
        if packetIndex - acknowledgedIndex >= 64 { return }
        if packetIndex < packets.count {
            send(packets[packetIndex]); packetIndex += 1
            if packetIndex == packets.count { stage = .apply; print("All bytes sent; waiting for receiver verification.") }
        }
    }
    func send(_ data: Data) {
        guard let pen, let write else { fail("Bluetooth write channel unavailable."); return }
        guard data.count <= pen.maximumWriteValueLength(for: .withoutResponse) else {
            fail("Packet exceeds the negotiated Bluetooth limit."); return
        }
        pen.writeValue(data, for: write, type: .withoutResponse)
    }
    func centralManager(_ manager: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        guard stage != .finished else { return }
        if applyScheduled && verified {
            finish(true, "Transfer verified; the pen disconnected for the scheduled reboot. Runtime behavior still needs testing.")
        } else { fail("Disconnected before verified update scheduling. Do not assume the update installed.") }
    }
    func fail(_ message: String) { finish(false, "ERROR: " + message) }
    func finish(_ ok: Bool, _ message: String) {
        guard stage != .finished else { return }
        success = ok; stage = .finished; timer?.cancel(); central?.stopScan()
        if let pen { central?.cancelPeripheralConnection(pen) }
        print(message)
    }
}

let usage = """
Usage: ota_client --device <macOS-Bluetooth-UUID> [--install]

Defaults to read-only preflight. --install transfers the pinned application and
schedules replacement/reboot after receiver verification. The displayed version
alone does not prove compatibility; see docs/INSTALL.md before using another pen.
"""
let arguments = Array(CommandLine.arguments.dropFirst())
if arguments == ["--help"] { print(usage); exit(0) }
var deviceID: UUID?
var index = 0
var sawInstall = false
while index < arguments.count {
    if arguments[index] == "--device", deviceID == nil,
       index + 1 < arguments.count, let value = UUID(uuidString: arguments[index + 1]) {
        deviceID = value; index += 2
    } else if arguments[index] == "--install", !sawInstall {
        sawInstall = true; index += 1
    } else {
        print("Invalid or repeated argument.\n" + usage); exit(64)
    }
}
guard let selectedDevice = deviceID else { print(usage); exit(64) }
let client = OTAClient(deviceID: selectedDevice)
while client.stage != .finished { RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.1)) }
exit(client.success ? 0 : 1)
