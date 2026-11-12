"""Decode the bounded raw-camera journal; never contacts the pen."""
from pathlib import Path
import json,struct,sys
from PIL import Image,ImageDraw

source=Path(sys.argv[1]);data=source.read_bytes()
names=['magic','version','build_tag','generation','camera_frames','records','stored',
       'stride','pushes','rejections','last_push','controller_errors']
header=dict(zip(names,struct.unpack_from('<12I',data)))
assert header['magic']==0x314d4143 and header['version']==1 and header['build_tag'] in (0x31445143,0x31425143,0x32425143)
assert header['stored']<=512 and header['stride']==704
assert len(data)==48+header['stored']*704
fields=['serial','time','phase','sdk_before','sdk_after','pushes','rejections',
        'last_push','callback_result','width','height','edge','range','generation']
records=[]
for index in range(header['stored']):
    block=data[48+index*704:48+(index+1)*704]
    row=dict(zip(fields,struct.unpack_from('<14I',block)))
    if not row['serial'] or row['generation']!=header['generation']-1:continue
    if (row['serial']-1)&511!=index:continue
    assert row['width']==96 and row['height']==108
    row['contrast']=row['range']&65535;row['step']=row['range']>>16
    row['detail']='uncertain' if row['contrast']<12 else (
        'sharp' if row['edge']>=2 and row['step']*3>=row['contrast']*2 else (
        'blurred' if row['step']*2<=row['contrast'] else 'uncertain'))
    row['pixels']=block[56:];records.append(row)
records.sort(key=lambda row:row['serial'])
spans=[]
for row in records:
    key=(row['phase'],row['sdk_before'],row['sdk_after'])
    if spans and spans[-1]['key']==key:
        spans[-1]['end']=row['time'];spans[-1]['last_serial']=row['serial']
    else:spans.append(dict(key=key,start=row['time'],end=row['time'],first_serial=row['serial'],last_serial=row['serial']))
summary=dict(header=header,valid_records=len(records),spans=spans,
             samples=[{k:v for k,v in row.items() if k!='pixels'} for row in records])
source.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n')
for batch in range((len(records)+119)//120):
    selection=records[batch*120:(batch+1)*120]
    canvas=Image.new('RGB',(12*106,((len(selection)+11)//12)*132),'#ddd')
    draw=ImageDraw.Draw(canvas)
    for i,row in enumerate(selection):
        x=(i%12)*106;y=(i//12)*132
        label=f"{row['serial']} p{row['phase']} s{row['sdk_after']}\n{row['detail']} r{row['rejections']}"
        draw.text((x+2,y+1),label,fill='black')
        picture=Image.frombytes('L',(24,27),row['pixels']).resize((72,81),Image.Resampling.NEAREST)
        canvas.paste(picture,(x+2,y+34))
    canvas.save(source.with_name(source.stem+f'-sheet-{batch}.png'))
print(json.dumps(dict(header=header,valid_records=len(records),spans=spans),indent=2))
