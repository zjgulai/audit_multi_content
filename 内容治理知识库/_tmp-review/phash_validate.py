import numpy as np, glob, os, json, time
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
def phash_img(im, size=32, hash_size=8):
    g=im.convert('L').resize((size,size), Image.LANCZOS)
    a=np.asarray(g,dtype=float)
    d=np.fft.rfft2(a)[:hash_size,:hash_size]
    d=d[1:,:]
    med=np.median(d)
    return (d>med).flatten()
def dist(a,b): return int(np.sum(a!=b))
lib=sorted(glob.glob('kb/l1/media/media_tbld8qE92YaY38Yz_*/*.png'))
print('images',len(lib),flush=True)
hashs=[]; names=[]
for p in lib:
    try:
        im=Image.open(p).convert('RGB')
        # downscale large for speed
        if im.size[0]*im.size[1] > 4_000_000:
            im=im.resize((im.size[0]//2, im.size[1]//2), Image.LANCZOS)
        hashs.append(phash_img(im)); names.append(p)
    except Exception as e:
        print('skip',p,e,flush=True)
print('hashed',len(hashs),flush=True)
ok=0; fails=[]; margins=[]
for i,p in enumerate(names):
    im=Image.open(p).convert('RGB')
    w,h=im.size
    im2=im.resize((max(1,int(w*0.8)),max(1,int(h*0.8))), Image.LANCZOS)
    if im2.size[0]*im2.size[1] > 4_000_000:
        im2=im2.resize((im2.size[0]//2, im2.size[1]//2), Image.LANCZOS)
    im2.save('/tmp/_ph_test.jpg', quality=70)
    hq=phash_img(Image.open('/tmp/_ph_test.jpg'))
    ds=[dist(hq,x) for x in hashs]
    ds[i]=999
    best=int(np.argmin(ds)); bd=int(ds[best])
    if bd<=10: ok+=1; margins.append(bd)
    else: fails.append((p,names[best],bd))
print('hit@10:',ok,'/',len(names),'fails:',len(fails),flush=True)
for f in fails[:10]: print('FAIL',f[0],'->',f[1],'dist',f[2],flush=True)
if margins: print('margins min/median/max:',min(margins),sorted(margins)[len(margins)//2],max(margins),flush=True)
json.dump({'total':len(names),'hit':ok,'fails':fails,'margins':margins},open('_tmp-review/phash_validate.json','w'))
