"""Actual ARM proof for diagnostic copying and bounded storage, not a queue fix."""
import json,struct
from check_arm import Machine,P,STATE,M
from unicorn import UC_HOOK_CODE

CAMERA_OFFSET=16444+20
RECORD_SIZE=704

def event(m,valid=True):
    pixels=bytes((x+2*y)&255 for y in range(108) for x in range(96))
    m.u.mem_write(0x1001000,pixels)
    info=[0]*84;info[0]=12288;info[20]=0x41a92000;info[32]=0x1001000
    info[52]=96 if valid else 95;info[53]=108
    m.u.mem_write(0x1007000,struct.pack('<84I',*info))
    m.u.mem_write(0x1008000,struct.pack('<6I',0,0,0,1,0x1007000,10))
    return pixels

def run():
    checks=[]
    def passed(name):checks.append(dict(check=name,passed=True))
    m=Machine();m.call('mark_down',0xa9);m.camera_result=-7
    for _ in range(4):event(m);assert m.call('mark_camera',0x1008000)==0xfffffff9
    assert m.camera_seen==0x1008000 and m.words(STATE+16444,2)==(4,1)
    sample=bytes(m.u.mem_read(STATE+CAMERA_OFFSET,RECORD_SIZE))
    assert struct.unpack_from('<14I',sample)[9:11]==(96,108)
    passed('original camera callback and result are preserved')

    m=Machine();m.call('mark_down',0xa9);m.invalidate_camera=True
    for _ in range(4):pixels=event(m);m.call('mark_camera',0x1008000)
    sample=bytes(m.u.mem_read(STATE+CAMERA_OFFSET,RECORD_SIZE))
    expected=bytes(pixels[(y*4+2)*96+x*4+2] for y in range(27) for x in range(24))
    assert sample[56:]==expected and any(expected)
    passed('camera bytes are copied before the driver can reuse its buffer')

    m=Machine();m.call('mark_down',0xa9)
    for _ in range(4):event(m,valid=False);m.call('mark_camera',0x1008000)
    assert m.words(STATE+16444,2)==(4,0) and m.camera_seen==0x1008000
    passed('unknown camera dimensions leave the native callback unchanged')

    m=Machine();m.call('mark_down',0xa9);m.push_error=-22;m.frame()
    assert m.words(STATE+16444+8,3)==(1,1,0xffffffea)
    passed('native SDK input failures are recorded without rewriting the return code')

    m=Machine();m.call('mark_down',0xa9)
    # Seed the sequence near wrap; no need to repeat 2048 equivalent camera calls.
    m.u.mem_write(STATE+16444+4,struct.pack('<I',512))
    for _ in range(4):event(m);m.call('mark_camera',0x1008000)
    assert m.words(STATE+16444+4,1)==(513,)
    assert m.words(STATE+CAMERA_OFFSET,1)==(513,)
    m.call('mark_up',0xa9,2,500,1)
    data=m.files['/media/Diagnostics/shadow/camera-1.bin']
    header=struct.unpack_from('<12I',data)
    assert header[:3]==(0x314d4143,1,0x32425143)
    assert header[5:8]==(513,512,RECORD_SIZE)
    assert len(data)==48+512*RECORD_SIZE
    passed('ring wrap and exported recording length are bounded and versioned')

    # Execute the actual original camera callback, including its SDK gate,
    # descriptor ownership and counters, instead of replacing that body.
    def native_camera(enabled):
        m=Machine();m.call('mark_down',0xa9);m.u.hook_del(m.camera_hook)
        m.u.hook_add(UC_HOOK_CODE,lambda *_:m.ret(0),begin=0x20b58,end=0x20b58)
        def word(address,value):m.u.mem_write(address,struct.pack('<I',value))
        word(0x7c4b4,123);word(0x7c66c,int(enabled));word(0x7c7cc,96)
        word(0x7c660,0x1009000);word(0x1009000,0x7c660)
        for _ in range(4):
            event(m)
            result=m.call('mark_camera',0x1008000)
            assert result==(0 if enabled else 0xffffffff)
            if enabled:
                assert m.last_frame==0x1009008
                m.call(0x4c0bd,0x1009008)  # Actual original SDK buffer-pop handler.
        assert m.native_frames==(4 if enabled else 0)
        assert m.words(STATE+16444+4,1)==(1,)
        assert m.words(0x7c668,1)==(0,),'Native outstanding-frame counter leaked'
        return m
    native_camera(True)
    passed('real native camera callback, submission and release balance buffers')
    native_camera(False)
    passed('recording observes camera frames even while the native SDK gate is disabled')

    m=Machine();m.call('mark_down',0xa9);m.warm()
    for _ in range(6):m.frame(False,blurred=True)
    m.run_job()  # Virtual release queued completion plus a possible restart.
    assert m.state(1)==2 and not m.held
    # Physical key-down normally sets the native pending-release flag.
    m.u.mem_write(0x7c8a8,struct.pack('<I',1))
    m.u.hook_add(UC_HOOK_CODE,lambda *_:m.ret(1),begin=0x49428,end=0x49428)
    m.locked=False;m.call(0x4dccd,0xa9,0,500,1)
    assert m.state(1)==0 and not m.locked
    m.drain();assert not m.held and m.exports==1
    passed('real physical-release wrapper cancels queued restart with normal key bookkeeping')

    (P/'camera-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps(checks,indent=2))

if __name__=='__main__':run()
