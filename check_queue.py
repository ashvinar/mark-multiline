"""Execute the real camera callback and retained-buffer queue in ARM emulation."""
import struct,json
from pathlib import Path
from unicorn import UC_HOOK_CODE
from check_arm import Machine,P,STATE,M

assert M['state_bytes']==377744
BASE=376912
O={'current_energy':BASE+4,'reference_energy':BASE+8,'direction':BASE+24,
   'forward_recent':BASE+28,'pending_frame':BASE+684,
   'queue_count':BASE+704,'queue_capacity':BASE+708,'queue_peak':BASE+712,
   'queue_sent':BASE+716,'queue_released':BASE+720,'queue_errors':BASE+724,
   'queue_fallbacks':BASE+728}

class QueuedMachine(Machine):
    def __init__(self,pool=10):
        super().__init__();self.u.hook_del(self.camera_hook)
        self.input_busy=set();self.submitted=[];self.payloads=[];self.input_sequence=0
        self.u.hook_add(UC_HOOK_CODE,lambda *_:self.put_buffer(),begin=0x20b58,end=0x20b58)
        self.word(0x7c4b4,123);self.word(0x7c66c,1);self.word(0x7c7cc,96)
        self.word(0x7c660,0x100a000)
        for i in range(pool):self.word(0x100a000+i*64,0x100a000+(i+1)*64 if i+1<pool else 0x7c660)
        self.call('mark_down',0xa9)
    def word(self,address,value):self.u.mem_write(address,struct.pack('<I',value&0xffffffff))
    def field(self,name,value=None):
        if value is not None:self.word(STATE+O[name],value)
        return self.words(STATE+O[name],1)[0]
    def put_buffer(self):
        index=self.r(0)-1
        assert index in self.input_busy,('Buffer returned twice or without ownership',index)
        self.input_busy.remove(index);self.ret(0)
    def push(self):
        frame=self.r(2);w,h=self.words(frame+4,2)
        assert self.words(frame+20,1)[0]>=w*h
        if not self.push_error:
            cpu=self.words(frame+28,1)[0]
            self.submitted.append(frame);self.payloads.append(bytes(self.u.mem_read(cpu,w*h)))
        super().push()
    def camera(self,pixels=None):
        index=next(i for i in range(16) if i not in self.input_busy)
        self.input_busy.add(index);cpu=0x1020000+index*0x4000
        self.input_sequence+=1
        if pixels is None:
            pixels=bytes((20+self.input_sequence if x%5==0 else 230) for y in range(108) for x in range(96))
        self.u.mem_write(cpu,pixels)
        info=[0]*84;info[0]=12288;info[20]=0x41a92000+index*0x4000
        info[32]=cpu;info[50]=index+1;info[52]=96;info[53]=108
        self.u.mem_write(0x1007000,struct.pack('<84I',*info))
        self.u.mem_write(0x1008000,struct.pack('<6I',0,0,0,1,0x1007000,10))
        result=self.call('mark_camera',0x1008000)
        return result,pixels
    def sdk_drain(self):
        while self.submitted:self.call(0x4c0bd,self.submitted.pop(0))
    def waiting(self):self.word(STATE+4,3);self.word(STATE+12,0)

def run():
    results=[]
    def passed(name):results.append(dict(check=name,passed=True))

    m=QueuedMachine();m.waiting();expected=[]
    for _ in range(3):
        _,pixels=m.camera();expected.append(pixels)
    assert m.payloads==expected and m.field('queue_count')==0
    assert m.field('queue_peak')==3 and m.words(0x7c668,1)[0]==3
    m.sdk_drain();assert not m.input_busy and m.words(0x7c668,1)==(0,)
    passed('native buffers remain owned and pixel-exact until FIFO startup delivery')

    m=QueuedMachine();m.waiting();m.field('direction',-1);expected=[]
    for i in range(8):
        _,pixels=m.camera();expected.append(pixels)
        if i<7:assert not m.payloads and m.field('queue_count')==i+1
    assert m.payloads==expected and m.field('queue_fallbacks')==1
    assert m.field('queue_peak')==8 and m.field('queue_count')==0
    m.sdk_drain();assert not m.input_busy
    passed('capacity fallback delivers every buffered frame without overwriting or starving the pool')

    m=QueuedMachine();m.waiting();expected=[]
    for _ in range(2):
        _,pixels=m.camera();expected.append(pixels)
    m.call('mark_up',0xa9,0,500,1)
    assert m.payloads==expected and m.state(1)==0 and not m.held
    qheader=struct.unpack('<17I',m.files['/media/Diagnostics/shadow/queue-1.bin'])
    assert qheader[:3]==(0x31464251,2,2) and qheader[3]==8 and qheader[4]==2 and qheader[16]==10
    m.sdk_drain();m.drain();assert not m.input_busy and m.exports==1
    passed('physical release flushes queued text before native stop and never restarts')

    m=QueuedMachine();m.waiting()
    for _ in range(2):m.camera()
    m.push_error=-22;m.camera()
    assert m.field('queue_errors')==3 and not m.input_busy
    assert m.words(0x7c668,1)==(0,) and m.field('queue_count')==0
    passed('SDK rejection returns each retained frame exactly once and reports data loss')

    m=QueuedMachine();m.waiting()
    hook=m.u.hook_add(UC_HOOK_CODE,lambda *_:m.ret(0),begin=int(M['functions']['mark_handoff'],16)&~1,end=int(M['functions']['mark_handoff'],16)&~1)
    m.camera();assert m.field('pending_frame') and len(m.input_busy)==1
    m.call('mark_up',0xa9,0,500,1)
    m.u.hook_del(hook);m.call('mark_handoff')
    assert not m.input_busy and m.words(0x7c668,1)==(0,) and not m.payloads
    m.drain();assert not m.held
    passed('release before camera handoff cancels stale input without leaking or double-freeing')

    m=QueuedMachine(pool=4);assert m.field('queue_capacity')==2
    m.waiting();m.camera();m.camera();m.sdk_drain()
    assert m.field('queue_peak')==2 and not m.input_busy
    passed('queue reserves camera-pool headroom even on a smaller native pool')

    m=QueuedMachine();m.waiting();m.field('reference_energy',20000)
    m.field('current_energy',1000);m.field('direction',-1);m.field('forward_recent',2)
    for _ in range(3):m.camera()
    assert len(m.payloads)==3 and m.field('reference_energy')==0
    m.sdk_drain();assert not m.input_busy
    passed('confirmed movement admits a fainter next line and relearns its contrast')

    m=QueuedMachine(pool=64)
    assert m.field('queue_capacity')==8,'Large valid native pool disabled the queue'
    m.waiting()
    for _ in range(3):m.camera()
    m.sdk_drain();assert m.field('queue_peak')==3 and not m.input_busy
    passed('large native pool retains a bounded queue instead of disabling it')

    m=QueuedMachine();m.field('queue_capacity',0);m.waiting()
    for _ in range(3):m.camera()
    m.sdk_drain()
    assert m.field('queue_capacity')==8 and m.field('queue_peak')==3
    assert not m.input_busy
    passed('new-line input rechecks a pool that was unavailable during key-down')

    m=QueuedMachine(pool=2)
    assert m.field('queue_capacity')==1,'Two-slot pool can safely retain one frame'
    m.waiting();m.camera();m.sdk_drain()
    assert m.field('queue_peak')==1 and not m.input_busy
    passed('two-slot native pool retains one frame while reserving one native slot')

    m=QueuedMachine(pool=1);m.waiting()
    m.field('reference_energy',20000);m.field('current_energy',1000)
    for _ in range(3):m.camera()
    assert not m.payloads and not m.input_busy and m.state(1)==3
    passed('startup quality guard remains active even if native buffering is unavailable')

    (P/'queue-checks.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))

if __name__=='__main__':run()
