"""Check acquisition loss, using actual ARM instructions and independent images.

The mild-focus image reproduces the high contrast and reduced gradient seen
immediately before a mid-line restart in trace-4, not a word or typeface.
"""
import json
import struct
from check_arm import Machine, P


def detail(m, contrast, step):
    # Sampled columns have exactly this contrast and largest two-pixel step.
    levels = list(range(0, contrast, step)) + [contrast]
    levels += list(reversed(levels[1:-1]))
    samples = [levels[i % len(levels)] for i in range(60)]
    row = bytes(samples[x // 2] for x in range(120))
    m.u.mem_write(0x1001000, row * 108)
    m.u.mem_write(0x1000100, struct.pack('<8I', 0, 120, 108, 0, 0,
                                      120 * 108, 0x41a92000, 0x1001000))
    return m.call('mark_frame', 123, 0, 0x1000100)


def run():
    results = []
    def check(name, body):
        try:
            body()
            results.append(dict(check=name, passed=True))
        except AssertionError as error:
            results.append(dict(check=name, passed=False, reason=str(error)))

    def whitespace():
        m = Machine(); m.call('mark_down', 0xa9); m.warm()
        for _ in range(16):
            m.frame(False)
        assert not m.jobs, 'A featureless white region restarted capture'
        assert m.native_frames == 40, 'Whitespace frames were silently dropped'
    check('plain white region preserves acquisition without restarting', whitespace)

    def mild():
        m = Machine(); m.call('mark_down', 0xa9); m.warm()
        for _ in range(16):
            detail(m, 230, 140)
        assert not m.jobs, 'High-contrast mild defocus restarted a line'
        assert m.native_frames == 40, 'Potential text frames were dropped'
    check('high contrast mild defocus preserves acquisition', mild)

    def transient():
        m = Machine(); m.call('mark_down', 0xa9); m.warm()
        for _ in range(2):
            detail(m, 100, 30)
        m.frame()
        assert not m.jobs, 'A brief focus dip restarted capture'
        assert m.native_frames == 27, 'Unconfirmed lift frames were discarded'
    check('unconfirmed focus dip preserves every frame', transient)

    def lift():
        m = Machine(); m.call('mark_down', 0xa9); m.warm()
        for _ in range(6):
            detail(m, 100, 30)
        assert len(m.jobs) == 1, 'Sustained defocus failed to complete a line'
        m.drain()
        assert m.exports == 1 and m.state(7) == 1
        m.frame(); m.locked = True; m.call('mark_up', 0xa9, 2, 500, 1)
        m.drain()
        assert m.exports == 2 and not m.held
    check('sustained defocus completes and restarts through native handlers', lift)

    def early():
        m = Machine(); m.call('mark_down', 0xa9)
        for _ in range(4): m.frame()
        for _ in range(2): detail(m, 100, 30)
        m.frame()
        assert not m.jobs and m.native_frames == 7, 'Initial text lost before lift arming'
    check('early uncertain frames survive before lift is armed', early)
    (P / 'preservation-checks.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return all(row['passed'] for row in results)


if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
