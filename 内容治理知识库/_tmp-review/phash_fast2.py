import numpy as np, glob, os, json
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
def phash_img(im, size=32, hash_size=8):
    w,h=im.size
    g=im.convert('L').resize((size,size), Image.LANCZOS)
    a=np.asarray(g,dtype=float)
    d=np.fft.rfft2(a)[:hash_size,:hash_size]
    d=d[1:,:]
    med=np.median(d)
    return (d>med).flatten()
def dist(a,b): return int(np.sum(a!=b))
lib=sorted(glob.glob('kb/l1/media/media_tbld8qE92YaY38Yz_*/*.png'))
hashs=[]; names=[]
for p in lib:
    try:
        im=Image.open(p).convert('RGB')
        hashs.append(phash_img(im)); names.append(p)
    except Exception as e:
        print('skip',p,e,flush=True)
print('hashed',len(hashs),flush=True)
ok=0; fails=[]; margins=[]; correct_ds=[]; sepds=[]
for i,p in enumerate(names):
    im=Image.open(p).convert('RGB')
    w,h=im.size
    im2=im.resize((max(1,int(w*0.8)),max(1,int(h*0.8))), Image.LANCZOS)
    im2.save('/tmp/_ph_test.jpg', quality=70)
    hq=phash_img(Image.open('/tmp/_ph_test.jpg'))
    cd=dist(hq,hashs[i])
    others=[dist(hq,x) for j,x in enumerate(hashs) if j!=i]
    sep=min(others)
    correct_ds.append(cd); sepds.append(sep)
    if cd<=10 and sep>=15: ok+=1
    elif cd>10: fails.append((p,'correct_dist',cd,sep))
print('hit(cd<=10 & sep>=15):',ok,'/',len(names),'fails',len(fails),flush=True)
print('correct dist min/median/max:',min(correct_ds),sorted(correct_ds)[len(correct_ds)//2],max(correct_ds),flush=True)
print('sep min/median:',min(sepds),sorted(sepds)[len(sepds)//2],flush=True)
for f in fails[:8]: print('FAIL',f,flush=True)
json.dump({'total':len(names),'hit':ok,'fails':fails,'correct':correct_ds,'sep':sepds},open('_tmp-review/phash_validate2.json','w'))
