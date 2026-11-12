"""Test camera classification without depending on a book, word or font ID."""
from pathlib import Path
import struct,json
from PIL import Image,ImageDraw,ImageFont,ImageFilter
from check_arm import Machine,P

fonts=['/System/Library/Fonts/Helvetica.ttc','/System/Library/Fonts/Times.ttc','/System/Library/Fonts/Courier.ttc']
results=[]
def submit(m,image):
 w,h=image.size;m.u.mem_write(0x1001000,image.tobytes())
 m.u.mem_write(0x1000100,struct.pack('<8I',0,w,h,0,0,w*h,0x41a92000,0x1001000))
 return m.call('mark_frame',123,0,0x1000100)

for fontpath in fonts:
 for size in [24,36,48]:
  font=ImageFont.truetype(fontpath,size)
  for ink in [0,150]:
   for text in ['Abc','ill','WAV']:
    image=Image.new('L',(96,108),240)
    ImageDraw.Draw(image).text((8,40),text,font=font,fill=ink,anchor='lt')
    m=Machine();m.call('mark_down',0xa9)
    for _ in range(24):submit(m,image)
    armed=m.state(3)==20
    blurred=image.filter(ImageFilter.GaussianBlur(5))
    for _ in range(6):submit(m,blurred)
    gap=len(m.jobs)==1
    row=dict(font=Path(fontpath).stem,size=size,ink=ink,text=text,armed=armed,lift_detected=gap)
    results.append(row)
(P/'font-checks.json').write_text(json.dumps(results,indent=2)+'\n')
failed=[r for r in results if not r['armed'] or not r['lift_detected']]
print(json.dumps(dict(cases=len(results),passed=len(results)-len(failed),failed=failed),indent=2))
assert not failed,'Font-independent classifier tests failed'
