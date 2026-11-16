#!/usr/bin/env python3
"""Generate deterministic, original pixel-art assets for the benchmark."""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1] / "assets"
for folder in ["backgrounds", "characters", "environment"]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

# Painted night sky and layered valley silhouettes, repeated across the long level.
for name in ["sky", "far_hills"]:
    im = Image.new("RGBA", (1600, 900), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if name == "sky":
        d.rectangle((0, 0, 1600, 900), fill=(20, 36, 58, 255))
        for x, y, r in [(180,140,3),(330,90,2),(760,170,3),(1120,100,2),(1410,210,2),(1280,55,2)]:
            d.ellipse((x-r,y-r,x+r,y+r), fill=(184,227,193,210))
        d.ellipse((1210,105,1360,255), fill=(207,231,174,25))
        d.ellipse((1230,125,1340,235), fill=(207,231,174,60))
        d.rectangle((0,540,1600,900), fill=(24,53,66,255))
        d.polygon([(0,590),(180,420),(330,570),(510,390),(730,600),(950,410),(1170,590),(1390,430),(1600,590),(1600,900),(0,900)], fill=(28,73,77,255))
        d.polygon([(0,680),(250,520),(430,680),(700,500),(930,690),(1180,520),(1400,680),(1600,550),(1600,900),(0,900)], fill=(30,91,77,255))
    else:
        d.polygon([(0,760),(170,620),(350,720),(540,560),(760,740),(970,580),(1190,730),(1400,590),(1600,710),(1600,900),(0,900)], fill=(23,66,64,220))
        for x in range(20,1600,95):
            y=600+(x*17%130)
            d.line((x,y,x-20,y-65), fill=(40,104,77,230), width=12)
            d.ellipse((x-42,y-105,x+18,y-45), fill=(42,119,82,190))
    im.resize((4000,900), Image.Resampling.LANCZOS).save(ROOT/"backgrounds"/f"{name}.png")

# Animated 48x48 characters: idle/run/jump for the player and a friendly patrol creature.
for kind, color in {"hero":(103,208,176), "critter":(237,174,99)}.items():
    for anim, count in [("idle",2),("run",4),("jump",1)]:
        for i in range(count):
            im=Image.new("RGBA",(48,48),(0,0,0,0)); d=ImageDraw.Draw(im)
            bob=(i%2)*2 if anim=="idle" else (i%2)*3 if anim=="run" else -2
            d.ellipse((10,40,38,46), fill=(8,20,26,100))
            if kind=="hero":
                d.polygon([(15,19+bob),(32,19+bob),(37,38),(10,38)], fill=color+(255,), outline=(16,45,48,255))
                d.ellipse((14,5+bob,34,26+bob), fill=(231,207,157,255), outline=(16,45,48,255), width=2)
                d.polygon([(12,12+bob),(17,1+bob),(32,4+bob),(37,14+bob),(30,10+bob),(17,9+bob)], fill=(42,75,76,255))
                d.ellipse((26,14+bob,29,17+bob), fill=(20,40,42,255))
                if anim=="run":
                    d.line((17,35,10+(i%2)*5,43), fill=(20,45,48,255), width=4)
                    d.line((29,35,36-(i%2)*5,43), fill=(20,45,48,255), width=4)
                else:
                    d.line((17,36,14,43), fill=(20,45,48,255), width=4)
                    d.line((29,36,32,43), fill=(20,45,48,255), width=4)
            else:
                d.ellipse((8,15+bob,40,40+bob), fill=color+(255,), outline=(65,48,37,255), width=2)
                d.ellipse((14,8+bob,34,29+bob), fill=color+(255,), outline=(65,48,37,255), width=2)
                d.ellipse((18,17+bob,21,21+bob), fill=(40,35,30,255))
                d.ellipse((28,17+bob,31,21+bob), fill=(40,35,30,255))
                d.arc((18,20+bob,30,28+bob),0,180,fill=(80,45,35,255),width=2)
            im.save(ROOT/"characters"/f"{kind}_{anim}_{i}.png")

# Modular tile and interaction art.
for name, color in [("moss",(67,133,92)),("stone",(79,105,104)),("crystal",(108,209,188)),("gold",(247,205,105)),("hazard",(228,112,91))]:
    im=Image.new("RGBA",(64,64),(0,0,0,0)); d=ImageDraw.Draw(im)
    if name=="moss":
        d.rectangle((0,10,63,63),fill=color+(255,))
        d.rectangle((0,5,63,17),fill=(103,171,108,255))
        for x in range(4,64,12): d.line((x,7,x+4,1),fill=(156,198,123,255),width=3)
    elif name=="stone":
        d.rectangle((0,0,63,63),fill=color+(255,))
        d.line((0,22,63,22),fill=(117,139,128,255),width=2)
        d.line((30,22,30,63),fill=(48,75,77,255),width=2)
        d.line((0,48,30,48),fill=(48,75,77,255),width=2)
    elif name=="crystal":
        d.polygon([(32,2),(53,22),(42,59),(19,52),(10,23)],fill=color+(210,),outline=(206,255,228,255))
        d.line((32,5,30,48),fill=(222,255,235,220),width=3)
    elif name=="gold":
        d.ellipse((8,8,56,56),fill=(255,220,111,255),outline=(255,245,185,255),width=4)
        d.ellipse((20,20,44,44),fill=(255,245,184,255))
    else:
        d.polygon([(0,63),(16,8),(32,63),(48,8),(64,63)],fill=color+(255,))
    im.save(ROOT/"environment"/f"{name}.png")

im=Image.new("RGBA",(96,128),(0,0,0,0)); d=ImageDraw.Draw(im)
d.line((48,120,48,35),fill=(63,135,87,255),width=8)
for x,y,c in [(25,48,(88,174,112,255)),(68,64,(77,157,99,255)),(30,83,(101,191,113,255)),(62,30,(105,199,131,255))]:
    d.ellipse((x-20,y-12,x+20,y+12),fill=c)
d.ellipse((38,10,58,30),fill=(247,211,125,255))
im.save(ROOT/"environment/fern.png")
print("Generated original valley art in", ROOT)
