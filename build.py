"""Build capture-controller application offline; never contacts hardware."""
from pathlib import Path
from io import BytesIO
import struct,hashlib,json,sys,subprocess
from elftools.elf.elffile import ELFFile
P=Path(__file__).resolve().parent
BASE=P/'vendor/ai-pen.hotupdate.recovered.bin'
EXPECTED='d4919df3e0a72cd8cb9dcd57e6c2e75d7e03391c0e655286a015bc6532111d44'

def branch(source,target,link=True):
 o=target-(source+4);assert not o&1 and -(1<<24)<=o<(1<<24)
 s=(o>>24)&1;j1=1^((o>>23)&1)^s;j2=1^((o>>22)&1)^s
 return struct.pack('<HH',0xf000|(s<<10)|((o>>12)&1023),(0xd000 if link else 0x9000)|(j1<<13)|(j2<<11)|((o>>1)&2047))

def main():
 assert all(a=='--monitor' for a in sys.argv[1:])
 flags=['clang','--target=armv7-linux-gnueabihf','-mcpu=cortex-a7','-mthumb','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-vectorize','-fno-slp-vectorize','-DMARK_KEY_MUTEX=0x7c864','-DMARK_WORKER_TRAMPOLINE=0x60121','-DMARK_CAMERA_TRAMPOLINE=0x60131']
 if '--monitor' in sys.argv:flags.append('-DMARK_MONITOR_ONLY')
 subprocess.run(flags+['-c',str(P/'capture.c'),'-o',str(P/'capture.o')],check=True)
 original=BASE.read_bytes();assert hashlib.sha256(original).hexdigest()==EXPECTED
 e=ELFFile(BytesIO(original));obj=ELFFile(BytesIO((P/'capture.o').read_bytes()))
 sections=[(i,s) for i,s in enumerate(obj.iter_sections()) if s.name.startswith('.text.mark_') and s.header.sh_size]
 loads=[(i,s) for i,s in enumerate(e.iter_segments()) if s.header.p_type=='PT_LOAD']
 text_index,text=loads[0];data_index,data=loads[1]
 # Keep all original virtual addresses/imports. A separate RX load in the
 # unused address gap holds a relocated program-header table and new code.
 # Offset-to-address congruence preserves the kernel AT_PHDR calculation.
 table_offset=(len(original)+4095)&~4095
 table_address=0x10000+table_offset
 phnum=e.header.e_phnum+1
 code_offset=(phnum*32+15)&~15
 trampoline=table_address+code_offset
 assert trampoline==0x60120 and phnum==9
 payload=bytes.fromhex('2de9f043')+branch(trampoline+4,0x4c880,False)+bytes(8)
 # Camera callback's displaced push/sub have no PC-relative operands.
 camera_trampoline=trampoline+len(payload)
 assert camera_trampoline==0x60130
 payload+=bytes.fromhex('f0b5d1b0')+branch(camera_trampoline+4,0x4c0f0,False)+bytes(8)
 addresses={}
 for i,s in sections:
  payload+=bytes((-len(payload))%4);addresses[i]=trampoline+len(payload);payload+=s.data()
 symbols=obj.get_section_by_name('.symtab')
 def symbol_address(sym):
  assert isinstance(sym.entry.st_shndx,int) and sym.entry.st_shndx in addresses,(sym.name,sym.entry)
  return addresses[sym.entry.st_shndx]+sym.entry.st_value
 functions={s.name:symbol_address(s) for s in symbols.iter_symbols() if s.name.startswith('mark_') and s.entry.st_info.type=='STT_FUNC'}
 code=bytearray(payload)
 for rel in obj.iter_sections():
  if rel.header.sh_type!='SHT_REL' or rel.header.sh_info not in addresses:continue
  target_section=addresses[rel.header.sh_info]
  for r in rel.iter_relocations():
   sym=symbols.get_symbol(r.entry.r_info_sym);value=symbol_address(sym)
   place=target_section+r.entry.r_offset;offset=place-trampoline;kind=r.entry.r_info_type
   if kind==2:
    old=struct.unpack_from('<I',code,offset)[0];struct.pack_into('<I',code,offset,(old+value)&0xffffffff)
   elif kind==3:
    old=struct.unpack_from('<I',code,offset)[0];struct.pack_into('<I',code,offset,(old+value-place)&0xffffffff)
   elif kind in (10,30):code[offset:offset+4]=branch(place,value&~1,kind==10)
   else:raise AssertionError(('Unsupported relocation',kind,sym.name))
 old_data_end=data.header.p_vaddr+data.header.p_memsz;state=(old_data_end+63)&~63
 assert state==0x7cd80
 state_size=struct.unpack('<I',obj.get_section_by_name('.mark_layout').data())[0]
 assert state_size<=512*1024
 segments=[dict(item.header) for item in e.iter_segments()]
 data_header=segments[data_index]
 data_header['p_memsz']=state+state_size-data.header.p_vaddr
 new_load=dict(p_type='PT_LOAD',p_offset=table_offset,p_vaddr=table_address,p_paddr=table_address,p_filesz=code_offset+len(code),p_memsz=code_offset+len(code),p_flags=5,p_align=4096)
 assert table_address+new_load['p_memsz']<(data.header.p_vaddr&~4095)
 segments.insert(data_index,new_load)
 phdr=next(item for item in segments if item['p_type']=='PT_PHDR')
 phdr.update(p_offset=table_offset,p_vaddr=table_address,p_paddr=table_address,p_filesz=phnum*32,p_memsz=phnum*32)
 types={'PT_LOAD':1,'PT_DYNAMIC':2,'PT_INTERP':3,'PT_PHDR':6,'PT_GNU_STACK':0x6474e551,'PT_GNU_RELRO':0x6474e552,'PT_ARM_EXIDX':0x70000001}
 table=b''.join(struct.pack('<8I',types[item['p_type']],item['p_offset'],item['p_vaddr'],item['p_paddr'],item['p_filesz'],item['p_memsz'],item['p_flags'],item['p_align']) for item in segments)
 result=bytearray(original)+bytes(table_offset-len(original))+table+bytes(code_offset-len(table))+code
 struct.pack_into('<I',result,28,table_offset)
 struct.pack_into('<H',result,44,phnum)
 hooks=[(0x4c1e4,'mark_frame',True,'d4f7e0eb'),(0x4dcf0,'mark_up',True,'fff744ff'),(0x4e084,'mark_down',False,'fff76ebf'),(0x4e0ca,'mark_down',True,'fff74bff'),(0x4e140,'mark_down',True,'fff710ff'),(0x4c87c,'mark_image',False,'2de9f043'),(0x4cc54,'mark_copy',True,'fff7e8fe'),(0x4c0ec,'mark_camera',False,'f0b5d1b0')]
 for address,name,link,expected in hooks:
  offset=address-0x10000;assert original[offset:offset+4].hex()==expected
  result[offset:offset+4]=branch(address,functions[name]&~1,link)
 check=ELFFile(BytesIO(result));loads=[s for s in check.iter_segments() if s.header.p_type=='PT_LOAD']
 assert [s.header.p_vaddr for s in loads]==sorted(s.header.p_vaddr for s in loads)
 for s in loads:
  assert s.header.p_vaddr%4096==s.header.p_offset%4096
  assert s.header.p_filesz<=s.header.p_memsz and s.header.p_flags&3!=3
 assert check.header.e_entry==e.header.e_entry
 assert check.header.e_phnum==phnum and check.header.e_phoff==table_offset
 assert phdr['p_vaddr']==0x10000+check.header.e_phoff
 assert new_load['p_offset']<=check.header.e_phoff and check.header.e_phoff+phnum*32<=new_load['p_offset']+new_load['p_filesz']
 for first,second in zip(loads,loads[1:]):
  assert (first.header.p_vaddr+first.header.p_memsz+4095)&~4095 <= second.header.p_vaddr&~4095
 for old,new in zip(e.iter_segments(),[item for item in check.iter_segments() if not(item.header.p_type=='PT_LOAD' and item.header.p_vaddr==table_address)]):
  if old.header.p_type not in ('PT_LOAD','PT_PHDR'):assert old.header==new.header
 out=P/'ai-pen.capture-rewrite.experimental.bin';out.write_bytes(result)
 manifest=dict(status='offline candidate; not installed',monitor_only='--monitor' in sys.argv,size=len(result),sha256=hashlib.sha256(result).hexdigest(),input_sha256=EXPECTED,code_bytes=len(code),functions={k:hex(v) for k,v in functions.items()},state_address=hex(state),state_bytes=state_size,program_headers=phnum,new_rx=hex(table_address),retail_sdk_modified=False,hooks=[hex(x[0]) for x in hooks])
 (P/'build.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
