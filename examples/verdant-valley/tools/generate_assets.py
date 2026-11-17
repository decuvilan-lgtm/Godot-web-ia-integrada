#!/usr/bin/env python3
"""Generate deterministic, original pixel-art assets for The Lantern Path."""
from pathlib import Path
from PIL import Image, ImageDraw
import random

ROOT = Path(__file__).resolve().parents[1] / "assets"
for folder in ["backgrounds", "characters", "environment"]:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

# A deliberately layered dusk palette: the playfield remains readable against the art.
random.seed(271828)
W, H = 4000, 900
sky = Image.new("RGBA", (W, H), (0, 0, 0, 255))
d = ImageDraw.Draw(sky)
for y in range(H):
    t = y / H
    color = (int(14 + 10*t), int(27 + 30*t), int(49 + 27*t), 255)
    d.line((0, y, W, y), fill=color)
for _ in range(150):
    x, y = random.randrange(W), random.randrange(35, 390)
    r = random.choice([1, 1, 2])
    d.rectangle((x-r, y-r, x+r, y+r), fill=(174, 215, 190, random.randrange(100, 225)))
# Soft moon halo and crisp crescent.
d.ellipse((3255, 145, 3425, 315), fill=(29, 52, 66, 255))
d.ellipse((3290, 170, 3410, 290), fill=(226, 231, 184, 245))
d.ellipse((3330, 150, 3450, 270), fill=(25, 48, 61, 255))
# Thin clouds break the empty upper sky without competing with the player.
for x, y in [(420, 245), (1450, 170), (2360, 290), (3650, 330)]:
    for ox, oy, rw in [(-42, 8, 35), (0, 0, 48), (44, 10, 30)]:
        d.ellipse((x+ox-rw, y+oy-12, x+ox+rw, y+oy+12), fill=(53, 83, 91, 110))
# Distant mountain silhouettes.
d.polygon([(0,570),(250,390),(440,545),(760,335),(1010,565),(1320,365),(1580,560),(1880,330),(2170,575),(2460,380),(2730,570),(3020,340),(3300,570),(3590,390),(3830,560),(4000,440),(4000,900),(0,900)], fill=(25,58,70,255))
d.polygon([(0,650),(300,495),(560,650),(880,460),(1180,675),(1510,475),(1830,670),(2150,485),(2470,665),(2790,470),(3120,670),(3440,490),(3720,650),(4000,510),(4000,900),(0,900)], fill=(28,76,76,255))
sky.save(ROOT / "backgrounds" / "sky.png")

hills = Image.new("RGBA", (W, H), (0, 0, 0, 0))
d = ImageDraw.Draw(hills)
d.polygon([(0,720),(180,625),(390,710),(620,560),(870,720),(1100,590),(1330,720),(1600,565),(1860,730),(2110,590),(2380,725),(2620,560),(2880,720),(3150,590),(3420,720),(3670,570),(4000,710),(4000,900),(0,900)], fill=(25,72,67,235))
d.polygon([(0,795),(250,685),(480,790),(760,660),(1010,800),(1270,680),(1530,800),(1790,655),(2050,805),(2320,675),(2600,800),(2870,660),(3140,800),(3420,680),(3690,800),(4000,675),(4000,900),(0,900)], fill=(30,91,72,245))
for x in range(25, W, 105):
    y = 690 + (x * 19 % 135)
    d.line((x, y, x-10, y-54), fill=(35, 105, 75, 220), width=7)
    d.ellipse((x-27, y-88, x+17, y-42), fill=(45, 124, 83, 225))
    d.ellipse((x-38, y-72, x-4, y-38), fill=(39, 112, 77, 220))
hills.save(ROOT / "backgrounds" / "far_hills.png")

# Character frames share a fixed 48x48 canvas and a common foot baseline (y=46).
def outline(draw, points, fill, edge=(17, 37, 43, 255)):
    draw.polygon(points, fill=fill, outline=edge)

for kind in ["hero", "critter"]:
    animations = [("idle", 2), ("run", 4), ("jump", 1)]
    for anim, count in animations:
        for frame in range(count):
            im = Image.new("RGBA", (48, 48), (0,0,0,0))
            p = ImageDraw.Draw(im)
            bob = (frame % 2) if anim == "idle" else (frame % 2) * 2 if anim == "run" else -2
            p.ellipse((9, 41, 39, 47), fill=(5, 17, 24, 105))
            if kind == "hero":
                # Boots and legs: the bottom pixel row is aligned to the collision capsule.
                leg_shift = 0 if anim != "run" else (-3 if frame in (0,3) else 3)
                p.rectangle((14, 32+bob, 21, 41), fill=(42, 61, 63, 255))
                p.rectangle((26, 32+bob, 33, 41), fill=(42, 61, 63, 255))
                p.rectangle((12+leg_shift, 40, 23+leg_shift, 46), fill=(35, 47, 52, 255))
                p.rectangle((25-leg_shift, 40, 36-leg_shift, 46), fill=(35, 47, 52, 255))
                outline(p, [(12,18+bob),(17,15+bob),(31,15+bob),(37,21+bob),(34,37),(13,37)], (67, 151, 126, 255))
                p.rectangle((17, 20+bob, 31, 29+bob), fill=(100, 192, 153, 255))
                p.line((15, 27+bob, 33, 27+bob), fill=(43, 111, 100, 255), width=2)
                # Backpack and warm scarf make the facing direction easy to read.
                p.rectangle((8, 22+bob, 14, 33), fill=(145, 105, 65, 255), outline=(48, 52, 48, 255))
                p.polygon([(16,16+bob),(29,14+bob),(35,20+bob),(30,25+bob),(17,22+bob)], fill=(231, 174, 91, 255))
                p.ellipse((13, 4+bob, 35, 26+bob), fill=(229, 197, 151, 255), outline=(27, 44, 47, 255), width=2)
                p.polygon([(11,13+bob),(14,4+bob),(22,1+bob),(34,5+bob),(38,15+bob),(30,11+bob),(20,10+bob)], fill=(48, 68, 66, 255))
                p.rectangle((27, 14+bob, 30, 17+bob), fill=(21, 39, 42, 255))
                p.line((19, 21+bob, 30, 21+bob), fill=(188, 128, 89, 255), width=1)
                if anim == "jump":
                    p.line((14, 24+bob, 7, 18+bob), fill=(67, 151, 126, 255), width=4)
                    p.line((34, 24+bob, 41, 18+bob), fill=(67, 151, 126, 255), width=4)
                else:
                    p.line((15, 25+bob, 10, 31+bob), fill=(67, 151, 126, 255), width=4)
                    p.line((34, 25+bob, 39, 30+bob), fill=(67, 151, 126, 255), width=4)
                # Tiny highlight pixels add volume without making the sprite noisy.
                p.point((17, 7+bob), fill=(255, 232, 190, 255))
                p.point((19, 23+bob), fill=(161, 224, 180, 255))
            else:
                p.ellipse((7, 17+bob, 41, 43+bob), fill=(192, 119, 72, 255), outline=(65, 45, 39, 255), width=2)
                p.ellipse((12, 8+bob, 36, 31+bob), fill=(231, 174, 99, 255), outline=(65, 45, 39, 255), width=2)
                p.ellipse((17, 18+bob, 21, 22+bob), fill=(38, 35, 34, 255))
                p.ellipse((28, 18+bob, 32, 22+bob), fill=(38, 35, 34, 255))
                p.arc((18, 20+bob, 31, 29+bob), 5, 165, fill=(88, 48, 40, 255), width=2)
                p.ellipse((9, 25+bob, 15, 31+bob), fill=(244, 190, 120, 255))
            im.save(ROOT / "characters" / f"{kind}_{anim}_{frame}.png")

# 64x64 modular tiles: platforms are tiled at native resolution in world.gd.
for name in ["moss", "stone", "crystal", "gold", "hazard"]:
    im = Image.new("RGBA", (64,64), (0,0,0,0))
    p = ImageDraw.Draw(im)
    if name == "moss":
        p.rectangle((0, 8, 63, 63), fill=(63, 111, 79, 255))
        p.rectangle((0, 5, 63, 13), fill=(92, 157, 91, 255))
        p.rectangle((0, 13, 63, 18), fill=(72, 128, 82, 255))
        p.line((0, 7, 63, 7), fill=(151, 194, 112, 255), width=2)
        for x in (6, 20, 39, 54):
            p.line((x, 6, x+2, 1), fill=(171, 207, 127, 255), width=2)
            p.rectangle((x+5, 31+(x%3)*5, x+8, 34+(x%3)*5), fill=(103, 143, 91, 255))
        p.line((5, 47, 18, 47), fill=(48, 91, 72, 255), width=2)
        p.line((35, 56, 56, 56), fill=(48, 91, 72, 255), width=2)
    elif name == "stone":
        p.rectangle((0,0,63,63), fill=(69, 91, 91, 255))
        p.rectangle((0,0,63,4), fill=(122, 145, 130, 255))
        p.line((0,22,63,22), fill=(105, 128, 119, 255), width=2)
        p.line((30,22,30,63), fill=(43, 63, 68, 255), width=2)
        p.line((0,48,30,48), fill=(43, 63, 68, 255), width=2)
        p.line((7,9,22,9), fill=(150, 164, 140, 255), width=2)
        p.point((43,36), fill=(134, 145, 123, 255))
    elif name == "crystal":
        p.polygon([(32,2),(53,22),(42,59),(19,52),(10,23)], fill=(86, 183, 164, 230), outline=(203, 255, 224, 255))
        p.polygon([(32,5),(30,47),(17,24)], fill=(143, 230, 197, 255))
        p.polygon([(32,5),(48,23),(36,49),(30,47)], fill=(65, 147, 151, 255))
        p.line((32,7,30,47), fill=(230, 255, 228, 235), width=2)
    elif name == "gold":
        p.ellipse((8,8,56,56), fill=(177, 113, 49, 255), outline=(255, 241, 170, 255), width=3)
        p.ellipse((12,6,52,50), fill=(249, 194, 83, 255), outline=(255, 235, 156, 255), width=3)
        p.ellipse((21,15,43,37), fill=(255, 235, 158, 255))
        p.point((20,12), fill=(255,255,224,255))
    else:
        p.polygon([(0,63),(12,14),(23,63),(34,9),(47,63),(57,20),(64,63)], fill=(188, 76, 76, 255))
        p.line((0,63,64,63), fill=(100, 48, 58, 255), width=2)
        p.line((12,16,12,40), fill=(244, 145, 117, 255), width=2)
        p.line((34,11,34,38), fill=(244, 145, 117, 255), width=2)
    im.save(ROOT / "environment" / f"{name}.png")

fern = Image.new("RGBA", (96,128), (0,0,0,0))
p = ImageDraw.Draw(fern)
p.line((48,122,48,37), fill=(55,119,75,255), width=7)
for x,y,c in [(25,48,(78,157,99,255)),(68,64,(65,142,88,255)),(30,83,(96,177,105,255)),(62,30,(112,193,119,255)),(43,101,(73,153,91,255))]:
    p.ellipse((x-21,y-12,x+20,y+12), fill=c, outline=(34,91,65,255))
    p.line((x-12,y,x+12,y), fill=(145,203,123,220), width=2)
fern.save(ROOT / "environment" / "fern.png")
print("Generated original, collision-aligned pixel art in", ROOT)
