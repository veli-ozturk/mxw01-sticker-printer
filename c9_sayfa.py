"""Kullanıcının sticker sayfasını (Pinterest vb. görsel) tek tek stickerlara böler; yalnız PIL (exe küçük kalır).

Yöntem stickerlar/kes.py ile aynı: koyu pikselleri biraz genişletip bağlı kümeleri bul, her küme bir sticker;
çerçeveli olanlarda dış hatta değmeyen en geniş beyaz bölge yazı alanı. Hız için sayfa küçültülerek aranır,
kesim özgün çözünürlükten yapılır.
"""
from PIL import Image, ImageFilter, ImageOps

ARAMA = 500  # arama çözünürlüğü (uzun kenar, px)


def _kumeler(maske, w, h):
    """İkili maskede (bytes, 1 = dolu) 4-komşu bağlı kümelerin (alan, kutu) listesi."""
    gorulen = bytearray(w * h)
    sonuc = []
    for bas in range(w * h):
        if not maske[bas] or gorulen[bas]:
            continue
        gorulen[bas] = 1
        yigin = [bas]
        alan, x0, y0, x1, y1 = 0, w, h, 0, 0
        while yigin:
            i = yigin.pop()
            x, y = i % w, i // w
            alan += 1
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
            for j in (i - 1 if x else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < w * h and maske[j] and not gorulen[j]:
                    gorulen[j] = 1
                    yigin.append(j)
        sonuc.append((alan, (x0, y0, x1 + 1, y1 + 1)))
    return sonuc


def _gri(resim):
    resim = ImageOps.exif_transpose(resim)
    if resim.mode in ("RGBA", "LA", "P"):
        zemin = Image.new("RGBA", resim.size, "white")
        zemin.alpha_composite(resim.convert("RGBA"))
        resim = zemin
    return resim.convert("L")


def yazi_alani(parca):
    """Çerçevenin içi: kenara değmeyen beyaz bölgelerden ortadakini (yoksa en geniş olanı) döndürür; yoksa None."""
    o = min(1.0, 200 / max(parca.size))
    k = parca.resize((max(1, round(parca.width * o)), max(1, round(parca.height * o))))
    koyu = k.point(lambda v: 255 if v < 150 else 0).filter(ImageFilter.MaxFilter(3))  # kesikli hatları kapat
    w, h = k.size
    beyaz = bytes(1 if v == 0 else 0 for v in koyu.getdata())
    adaylar = []
    for alan, (x0, y0, x1, y1) in _kumeler(beyaz, w, h):
        if x0 == 0 or y0 == 0 or x1 == w or y1 == h or alan < 0.03 * w * h:
            continue
        orta = x0 <= w / 2 < x1 and y0 <= h / 2 < y1
        adaylar.append((orta, alan, (x0 / o, y0 / o, x1 / o, y1 / o)))
    if not adaylar:
        return None
    _, alan, kutu = max(adaylar)
    return kutu if alan >= 0.15 * w * h else None


def kes(resim):
    """Sayfa -> [(parça "L" görsel, yazı alanı kutusu ya da None, renkli mi)] soldan sağa, yukarıdan aşağı."""
    gri = _gri(resim)
    renk = ImageOps.exif_transpose(resim).convert("RGB")
    o = min(1.0, ARAMA / max(gri.size))
    k = gri.resize((max(1, round(gri.width * o)), max(1, round(gri.height * o))), Image.LANCZOS)
    w, h = k.size
    koyu = k.point(lambda v: 255 if v < 160 else 0).filter(ImageFilter.MaxFilter(3))
    kumeler = [kutu for alan, kutu in _kumeler(bytes(1 if v else 0 for v in koyu.getdata()), w, h)
               if (kutu[2] - kutu[0]) * (kutu[3] - kutu[1]) >= 0.004 * w * h
               and min(kutu[2] - kutu[0], kutu[3] - kutu[1]) >= 0.03 * max(w, h)]  # ince çizgi kırıntısı değil
    # başka bir kümenin içinde kalanlar (iç süs) ayrı sticker değil
    kumeler = [a for a in kumeler if not any(b is not a and b[0] <= a[0] and b[1] <= a[1] and a[2] <= b[2]
                                             and a[3] <= b[3] for b in kumeler)]
    kumeler.sort(key=lambda b: (round(b[1] / (h / 12)), b[0]))
    sonuc = []
    for x0, y0, x1, y1 in kumeler:
        kutu = (max(0, x0 / o - 6), max(0, y0 / o - 6), min(gri.width, x1 / o + 6), min(gri.height, y1 / o + 6))
        kutu = tuple(round(v) for v in kutu)
        parca = gri.crop(kutu)
        # renkli/gri tonlu çizim (fotoğraf benzeri) noktalanır, düz çizim keskin basılır
        ara_ton = sum(1 for v in parca.getdata() if 60 < v < 200) / (parca.width * parca.height)
        sonuc.append((parca, yazi_alani(parca), ara_ton > 0.12 or _renkli(renk.crop(kutu))))
    return sonuc


def _renkli(parca):
    kucuk = parca.resize((40, 40))
    return sum(1 for r, g, b in kucuk.getdata() if max(r, g, b) - min(r, g, b) > 40) > 80


if __name__ == "__main__":  # öz-sınama: çizilmiş iki çerçeve ve bir dolu kare ayrı ayrı bulunmalı
    from PIL import ImageDraw
    s = Image.new("L", (600, 300), 255)
    d = ImageDraw.Draw(s)
    d.rounded_rectangle((20, 20, 260, 280), 20, outline=0, width=6)
    d.rounded_rectangle((320, 20, 460, 140), 10, outline=0, width=6)
    d.rectangle((500, 200, 580, 280), fill=0)
    p = kes(s)
    assert len(p) == 3, len(p)
    assert p[0][1] is not None and p[2][1] is None, [x[1] for x in p]
    print("tamam:", [(x[0].size, x[1] is not None) for x in p])
