"""Replay measured thumbnails through actual ARM camera/controller code.

Unavailable full-resolution pixels are nearest-neighbor reconstructed. This
tests motion/adaptive decisions, ownership and ordering, not OCR or timing
changes caused by keeping/stopping the real camera.
"""
from pathlib import Path
import struct,json,sys
from PIL import Image,ImageDraw
from check_queue import QueuedMachine,P,M

class Replay(QueuedMachine):
    def __init__(self):
        super().__init__();self.seeds=[];self.last_start=-1
    def push(self):
        start=self.operations.count('button_down')
        if start!=self.last_start:
            frame=self.r(2);cpu=self.words(frame+28,1)[0]
            pixels=bytes(self.u.mem_read(cpu,96*108))
            self.seeds.append(dict(start=start,serial=self.replay_serial,
                pixels=bytes(pixels[(y*4+2)*96+x*4+2] for y in range(27) for x in range(24))))
            self.last_start=start
        super().push()

results=[]
for name in sys.argv[1:]:
    path=Path(name);data=path.read_bytes();head=struct.unpack_from('<12I',data)
    records=[]
    for i in range(head[6]):
        block=data[48+i*704:48+(i+1)*704];meta=struct.unpack_from('<14I',block)
        if meta[0] and meta[13]==head[3]-1:records.append((meta[0],block[56:]))
    records.sort();m=Replay();boundaries=[]
    for serial,small in records:
        m.replay_serial=serial
        pixels=bytes(small[(y//4)*24+x//4] for y in range(108) for x in range(96))
        for _ in range(4):
            m.camera(pixels);m.sdk_drain()
            if m.jobs:
                boundaries.append(serial);m.drain()
    rotations=m.state(7);m.locked=True;m.call('mark_up',0xa9,0,500,1)
    m.sdk_drain();m.drain()
    assert not m.input_busy and m.words(0x7c668,1)==(0,) and m.field('queue_count')==0
    row=dict(application_sha256=M['sha256'],file=path.name,records=len(records),rotation_serials=boundaries,
             rotations=rotations,nonempty_mock_sdk_captures=m.exports,
             queue_peak=m.field('queue_peak'),queue_sent=m.field('queue_sent'),
             queue_released=m.field('queue_released'),queue_errors=m.field('queue_errors'),
             queue_fallbacks=m.field('queue_fallbacks'),seeds=[{k:v for k,v in r.items() if k!='pixels'} for r in m.seeds])
    results.append(row);print(json.dumps(row))
    sheet=Image.new('RGB',(max(1,len(m.seeds))*120,140),'#eee');draw=ImageDraw.Draw(sheet)
    for i,seed in enumerate(m.seeds):
        draw.text((i*120+2,2),f"line {seed['start']}\nrecord {seed['serial']}",fill='black')
        sheet.paste(Image.frombytes('L',(24,27),seed['pixels']).resize((72,81),Image.Resampling.NEAREST),(i*120+2,36))
    sheet.save(P/(path.stem+'-startup-seeds.png'))
(P/'replay-results.json').write_text(json.dumps(results,indent=2)+'\n')
