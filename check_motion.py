"""Actual ARM checks of movement confidence, independent of book/typeface."""
import json,random,struct
from check_arm import Machine,P

rng=random.Random(73081)
previous=bytes(rng.randrange(25,195) for _ in range(24*27))
checks=[]
def run(current):
    m=Machine();m.u.mem_write(0x1002000,previous);m.u.mem_write(0x1003000,current)
    valid=m.call('mark_motion',0x1002000,0x1003000,0x1004000)
    return valid,struct.unpack('<ii4I',bytes(m.u.mem_read(0x1004000,24)))

for dx,dy in [(-4,0),(-2,0),(-1,0),(1,0),(2,0),(4,0),(-2,-1),(2,1),(0,-2),(0,2)]:
    current=bytearray([210]*(24*27))
    for y in range(27):
        for x in range(24):
            if 0<=x+dx<24 and 0<=y+dy<27:current[(y+dy)*24+x+dx]=previous[y*24+x]+20
    # Static edge is deliberately stronger than much of the moving texture.
    for y in range(27):
        for x in range(3):current[y*24+x]=0
    valid,motion=run(bytes(current))
    assert valid and motion[:2]==(dx,dy),(dx,dy,valid,motion)
    checks.append(dict(check=f'translation {dx},{dy} with exposure change and static border',passed=True))

valid,motion=run(previous);assert not valid and motion[:2]==(0,0)
checks.append(dict(check='stationary detail does not claim movement',passed=True))
previous=bytes(0 if x<3 else 200 for y in range(27) for x in range(24))
valid,_=run(previous);assert not valid
checks.append(dict(check='sharp stationary border alone cannot claim text movement',passed=True))
previous=bytes([180]*(24*27));valid,_=run(bytes([220]*(24*27)));assert not valid
checks.append(dict(check='featureless exposure change cannot claim movement',passed=True))
previous=bytes(rng.randrange(25,195) for _ in range(24*27))
valid,_=run(bytes(rng.randrange(25,195) for _ in range(24*27)));assert not valid
checks.append(dict(check='unrelated images do not produce a confident displacement',passed=True))

previous=bytes(rng.randrange(150,165) for _ in range(24*27))
current=bytearray([160]*(24*27))
for y in range(27):
    for x in range(2,24):current[y*24+x-2]=previous[y*24+x]+10
valid,motion=run(bytes(current));assert valid and motion[:2]==(-2,0)
checks.append(dict(check='well-matched low-contrast detail can establish movement',passed=True))
(P/'motion-checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(json.dumps(checks,indent=2))
