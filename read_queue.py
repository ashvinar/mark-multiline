"""Read installed queue evidence, supporting both historical header versions."""
from pathlib import Path
import struct,json,sys
names=['magic','version','generation','capacity','peak','sent','released','errors',
       'fallbacks','direction','reference_detail','current_detail','moving_samples',
       'low_detail_count','remaining_queue','pending_frame','pool_nodes_observed_up_to_ten']
for name in sys.argv[1:]:
    p=Path(name);data=p.read_bytes()
    assert len(data) in (64,68)
    values=list(struct.unpack('<'+'I'*(len(data)//4),data))
    assert values[0]==0x31464251 and values[1] in (1,2)
    assert len(values)==(16 if values[1]==1 else 17)
    if values[9]>=0x80000000:values[9]-=0x100000000
    result=dict(file=p.name,**dict(zip(names,values)))
    print(json.dumps(result,indent=2))
