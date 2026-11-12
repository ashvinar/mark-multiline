"""Exercise the actual controller instructions with SDK/OS operations mocked."""
from pathlib import Path
from io import BytesIO
import struct,json
from elftools.elf.elffile import ELFFile
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_HOOK_CODE
from unicorn.arm_const import *
P=Path(__file__).resolve().parent
M=json.loads((P/'build.json').read_text());B=(P/'ai-pen.capture-rewrite.experimental.bin').read_bytes()
STATE=int(M['state_address'],16)
F={k:int(v,16) for k,v in M['functions'].items()}

class Machine:
 def __init__(self):
  u=self.u=Uc(UC_ARCH_ARM,UC_MODE_THUMB);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_A7)
  for s in ELFFile(BytesIO(B)).iter_segments():
   if s.header.p_type!='PT_LOAD':continue
   a=s.header.p_vaddr;n=s.header.p_memsz;start=a&~4095
   u.mem_map(start,((a+n+4095)&~4095)-start);u.mem_write(a,s.data())
   flags=s.header.p_flags;perms=(1 if flags&4 else 0)|(2 if flags&2 else 0)|(4 if flags&1 else 0)
   u.mem_protect(start,((a+n+4095)&~4095)-start,perms)
  u.mem_map(0x1000000,0x100000);u.mem_map(0x3000000,0x10000);u.mem_map(0x4000000,4096)
  self.held=0;self.locked=True;self.operations=[];self.jobs=[];self.native_frames=0;self.exports=0
  self.stop_error=0;self.start_error=0;self.queue_error=0;self.copy_error=0
  self.malloc_error=False;self.tokens=set();self.now=1000;self.stop_due=None;self.stop_delay=50;self.continue_error=0;self.token_index=0
  self.trace=None;self.last_frame=None;self.image_seen=None;self.files={};self.opened_path=None
  self.push_error=0;self.camera_result=0;self.camera_seen=None;self.invalidate_camera=False
  self.guard=b'\xa6'*16;u.mem_write(STATE-16,self.guard);u.mem_write(STATE+M['state_bytes'],self.guard)
  for address,method in [(0x4909c,self.key),(0x20be4,self.lock),(0x20984,self.unlock),(0x4df64,self.down),(0x4db7c,self.up),(0x209a8,self.push),(0x4c804,self.queue),(0x4bf38,self.stop),(0x4ca28,self.copy),(0x4c018,self.start),(0x20b28,self.open),(0x20bd8,self.write),(0x21478,self.close),(0x21414,self.format),(0x3a128,self.jpeg),(0x4c880,self.image),(0x4bfd4,self.clock),(0x20fc4,self.sleep),(0x20e24,self.malloc),(0x203d4,self.free)]:
   u.hook_add(UC_HOOK_CODE,lambda uc,a,n,x,fn=method:fn(),begin=address,end=address)
  u.hook_add(UC_HOOK_CODE,lambda *_:u.emu_stop(),begin=0x4000000,end=0x4000000)
  self.camera_hook=u.hook_add(UC_HOOK_CODE,lambda *_:self.camera_original(),begin=0x4c0f0,end=0x4c0f0)
 def r(self,n):return self.u.reg_read([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3][n])
 def ret(self,value=0):
  u=self.u;target=u.reg_read(UC_ARM_REG_LR)
  for i,r in enumerate([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R12]):u.reg_write(r,0xbad00000+i)
  u.reg_write(UC_ARM_REG_R0,value&0xffffffff);u.reg_write(UC_ARM_REG_CPSR,(u.reg_read(UC_ARM_REG_CPSR)&~32)|(32 if target&1 else 0));u.reg_write(UC_ARM_REG_PC,target)
 def words(self,a,n):return struct.unpack('<'+'I'*n,bytes(self.u.mem_read(a,n*4)))
 def state(self,i):return self.words(STATE+i*4,1)[0]
 def text(self,a):return bytes(self.u.mem_read(a,128)).split(b'\0')[0].decode()
 def call(self,name,*args):
  u=self.u;sp=0x300f000;u.reg_write(UC_ARM_REG_SP,sp);u.reg_write(UC_ARM_REG_LR,0x4000001)
  for i,v in enumerate(args):u.reg_write([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3][i],v)
  preserved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
  for i,r in enumerate(preserved):u.reg_write(r,0x41000000+i)
  try:u.emu_start(F[name] if isinstance(name,str) else name,0x4000004,count=2_000_000)
  except Exception:
   print('FAULT',name,hex(u.reg_read(UC_ARM_REG_PC)),hex(u.reg_read(UC_ARM_REG_LR)));raise
  assert u.reg_read(UC_ARM_REG_PC)==0x4000000
  assert u.reg_read(UC_ARM_REG_SP)==sp
  for i,r in enumerate(preserved):assert u.reg_read(r)==0x41000000+i,(name,i)
  assert bytes(u.mem_read(STATE-16,16))==self.guard
  assert bytes(u.mem_read(STATE+M['state_bytes'],16))==self.guard
  return u.reg_read(UC_ARM_REG_R0)
 def key(self):self.ret(self.held)
 def lock(self):assert self.r(0)==0x7c864 and not self.locked;self.locked=True;self.ret()
 def unlock(self):assert self.r(0)==0x7c864 and self.locked;self.locked=False;self.ret()
 def down(self):
  assert self.locked
  if self.stop_due is not None:
   assert not self.tokens and self.words(0x7c880,1)[0]==0
   assert self.now>=self.stop_due+80,'Full key-down ran before completion'
  self.operations.append('button_down');self.held=1;self.native_frames=0
  self.ret(0 if self.start_error else 1)
 def up(self):
  assert self.locked;self.operations.append('button_up');self.held=0
  self.stop_due=self.now+self.stop_delay;self.u.mem_write(0x7c4b8,struct.pack('<I',2))
  if self.stop_error:self.ret(0);return
  if not self.malloc_error:
   self.token_index+=1;token=0x1006000+self.token_index*32;self.tokens.add(token)
   pending=self.words(0x7c880,1)[0];self.u.mem_write(0x7c880,struct.pack('<I',pending+1))
   self.jobs.append((0x4cbe9,token))
  self.ret(1)
 def push(self):
  assert self.r(0)==123 and self.r(1)==0
  self.last_frame=self.r(2)
  if not self.push_error:self.native_frames+=1
  self.ret(self.push_error)
 def camera_original(self):
  self.camera_seen=self.r(0)
  if self.invalidate_camera:self.u.mem_write(0x1001000,b'\x00'*(96*108))
  sp=self.u.reg_read(UC_ARM_REG_SP);values=self.words(sp+0x144,5)
  for r,v in zip([UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_LR],values):self.u.reg_write(r,v)
  self.u.reg_write(UC_ARM_REG_SP,sp+0x144+20);self.ret(self.camera_result)
 def queue(self):
  callback=self.r(0);assert callback in (F['mark_rotate'],F['mark_continue'])
  error=self.queue_error or (self.continue_error if callback==F['mark_continue'] else 0)
  if not error:self.jobs.append((callback,self.r(1)))
  self.ret(error)
 def stop(self):raise AssertionError('Controller bypassed the complete key-up path')
 def copy(self):
  self.operations.append('copy')
  assert self.stop_due is not None and self.now>=self.stop_due+80,'Copied before async completion and normal settling interval'
  if self.native_frames and not self.copy_error:self.exports+=1
  self.ret(self.copy_error)
 def start(self):raise AssertionError('Controller bypassed the complete key-down path')
 def clock(self):self.ret(self.now);self.u.reg_write(UC_ARM_REG_R1,0)
 def sleep(self):
  self.now+=self.r(0)//1000
  if self.stop_due is not None and self.now>=self.stop_due:self.u.mem_write(0x7c4b8,struct.pack('<I',3))
  self.ret()
 def malloc(self):
  assert self.r(0)==16
  if self.malloc_error:self.ret(0)
  else:self.tokens.add(0x1006000);self.ret(0x1006000)
 def free(self):
  assert self.r(0) in self.tokens;self.tokens.remove(self.r(0));self.ret()
 def open(self):
  path=self.text(self.r(0));index=(self.state(0)>>1)&15
  assert path in [f'/media/Diagnostics/shadow/trace-{index}.bin',f'/media/Diagnostics/shadow/camera-{index}.bin',f'/media/Diagnostics/shadow/queue-{index}.bin']
  assert self.text(self.r(1))=='wb';self.opened_path=path;self.files[path]=b''
  if '/trace-' in path:self.trace=b''
  self.ret(42)
 def write(self):
  address=self.r(0);assert self.r(1)==1 and self.r(3)==42
  n=self.r(2);assert 0<=n<=M['state_bytes']
  assert (STATE<=address and address+n<=STATE+M['state_bytes']) or (0x3000000<=address and address+n<=0x3010000 and n in (48,64,68))
  chunk=bytes(self.u.mem_read(address,n));self.files[self.opened_path]+=chunk
  if '/trace-' in self.opened_path:self.trace+=chunk
  self.ret(n)
 def close(self):assert self.r(0)==42;self.ret()
 def format(self):
  fmt=self.text(self.r(1));assert fmt in ['line-%u','/media/Diagnostics/shadow/trace-%u.bin','/media/Diagnostics/shadow/camera-%u.bin','/media/Diagnostics/shadow/queue-%u.bin'] and self.r(2)<16
  b=fmt.replace('%u',str(self.r(2))).encode();assert len(b)<64
  self.u.mem_write(self.r(0),b+b'\0');self.ret(len(b))
 def jpeg(self):
  assert self.text(self.r(0))=='/media/Diagnostics/shadow/'
  assert self.text(self.r(1))==('latest-multiline-input' if M['monitor_only'] else f'line-{(self.state(14)-1)&15}')
  assert self.r(2)==0x1001000 and self.r(3)==120
  assert self.words(self.u.reg_read(UC_ARM_REG_SP),2)==(108,10)
  self.ret()
 def image(self):
  self.image_seen=self.r(0)
  # Displaced prologue pushed r4-r9,lr before the original worker.
  sp=self.u.reg_read(UC_ARM_REG_SP);values=self.words(sp,7)
  for r,v in zip([UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_LR],values):self.u.reg_write(r,v)
  self.u.reg_write(UC_ARM_REG_SP,sp+28);self.ret()
 def frame(self,contact=True,invalid=False,blurred=False):
  w,h=120,108;pixels=bytes((80+x) if blurred else ((20 if x%5==0 else 230) if contact else 200) for y in range(h) for x in range(w))
  self.u.mem_write(0x1001000,pixels)
  f=[0,w,h,0,0,w*h,0x41a92000,0x1001000];f[5]=1 if invalid else f[5]
  self.u.mem_write(0x1000100,struct.pack('<8I',*f))
  return self.call('mark_frame',123,0,0x1000100)
 def warm(self):
  for _ in range(24):self.frame()
 def run_job(self):
  self.locked=False;callback,arg=self.jobs.pop(0);self.call(callback,arg)
  assert not self.locked
 def drain(self):
  remaining=32
  while self.jobs:
   remaining-=1;assert remaining>=0,'Queue failed to drain';self.run_job()
  assert not self.tokens and self.words(0x7c880,1)[0]==0

def run_checks():
 results=[]
 def passed(name):results.append(dict(check=name,passed=True))
 def lifted(m):
  for _ in range(6):m.frame(False,blurred=True)

 if M['monitor_only']:
  m=Machine();m.call('mark_down',0xa9)
  for _ in range(4):m.frame()
  lifted(m);assert not m.jobs and m.native_frames==7
  m.call('mark_up',0xa9,2,500,1);m.drain();assert m.exports==1
  passed('monitor leaves SDK frame submission unchanged')
 else:
  m=Machine();m.call('mark_down',0xa9);m.operations=[];m.warm();lifted(m)
  assert len(m.jobs)==1 and m.state(1)==2
  m.drain();assert m.operations==['button_up','copy','button_down'] and m.exports==1 and m.state(1)==3
  assert m.frame(False)==0xffffffff
  m.frame();m.locked=True;m.call('mark_up',0xa9,2,500,1);m.drain();assert m.exports==2
  passed('complete existing key-up, asynchronous copy, key-down sequence')

  m=Machine();m.call('mark_down',0xa9);m.warm();lifted(m)
  m.run_job();assert not m.held and len(m.jobs)==2
  m.locked=True;m.call('mark_up',0xa9,2,500,1)
  assert sum(fn==0x4cbe9 for fn,arg in m.jobs)==1
  m.drain();assert m.exports==1 and m.held==0 and m.state(1)==0
  passed('physical release during queued completion cancels restart without duplicate capture')

  m=Machine();m.call('mark_down',0xa9);m.warm();lifted(m)
  m.locked=True;m.call('mark_up',0xa9,2,500,1);m.drain()
  assert m.held==0 and m.state(1)==0 and m.exports==1
  passed('stale rotation before key-up cannot resurrect capture')

  for name,field in [('rotation queue','queue_error'),('continuation queue','continue_error'),('release','stop_error'),('copy','copy_error'),('press','start_error'),('completion allocation','malloc_error')]:
   m=Machine();m.call('mark_down',0xa9);setattr(m,field,-1);m.warm();lifted(m);m.drain()
   assert m.state(12)>0,(name,'error not recorded')
   if name in ['release','copy','completion allocation','continuation queue']:
    assert m.operations.count('button_down')==1,(name,'started a new capture after failed completion')
   passed(name+' failure preserves queue ownership and records error')

  m=Machine();m.call('mark_down',0xa9);m.warm();m.frame(False);m.frame(False);m.frame();assert not m.jobs
  passed('brief blank does not finish a line')
  m=Machine();m.call('mark_down',0xa9)
  for _ in range(12):assert m.frame(False)==0
  assert not m.jobs
  passed('blank startup emits no empty capture cycle')

  rows=json.loads((P/'tests/fixtures/six-pass-timing.json').read_text())['samples']
  m=Machine();m.call('mark_down',0xa9)
  for row in rows:
   contact=row['edge']>=8 and row['range']>=35
   for _ in range(4):
    m.frame(contact,blurred=not contact)
    if m.jobs:m.drain()
  assert m.state(7)==6,('Recorded physical sequence rotations',m.state(7))
  passed('recorded six-pass contact timing rejects transient focus flashes')

  for delay in [20,180,220]:
   m=Machine();m.stop_delay=delay;m.call('mark_down',0xa9);m.warm();lifted(m);m.drain()
   assert m.now>=1000+delay+80
   passed(f'original completion worker waits for {delay}ms asynchronous stop')

 m=Machine();m.call('mark_down',0xa9);assert m.frame(invalid=True)==0 and not m.jobs
 passed('unknown camera layout passes to existing SDK')
 m=Machine();m.u.mem_write(0x1000100,struct.pack('<III',120,108,0x1001000));m.call('mark_image',0x1000100);assert m.image_seen==0x1000100
 passed('whole image reaches original encoder without width cutting')
 (P/'arm-checks.json').write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))

if __name__=='__main__':run_checks()
