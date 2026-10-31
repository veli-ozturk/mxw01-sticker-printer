"""C9 yazıcı için hazır şablonlar: her biri doldurulabilir alanlar ve 384 px genişlikte çizim.

Şablon = (alanlar, çizim fonksiyonu). Alan = (anahtar, etiket, varsayılan, tür); tür "satir" tek satır,
"cok" çok satır (liste alanlarında her satır bir madde),
"dosyalar" her satırı bir görsel dosyası yolu (uygulamada "Fotoğraf ekle" düğmesi). Çizim fonksiyonu alan değerlerinden "L" görsel döndürür;
yalnız saf siyah/beyaz kullanır, termal baskıda gri kalmaz.
"""
import datetime as dt
import functools
import hashlib
import math
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

GEN = 384
FONTLAR = r"C:\Windows\Fonts"


def font(boyut, tur="kalin"):
    if tur == "dar":  # Bahnschrift Condensed: market etiketi havası
        f = ImageFont.truetype(rf"{FONTLAR}\bahnschrift.ttf", boyut)
        f.set_variation_by_name("Condensed")
        return f
    dosya = {"kalin": "segoeuib.ttf", "normal": "segoeui.ttf", "ince": "segoeuil.ttf", "el": "segoepr.ttf",
             "el_kalin": "segoeprb.ttf",
             "serif": "georgiab.ttf", "fis": "consola.ttf", "sembol": "seguisym.ttf", "yazi": "segoescb.ttf",
             "blok": "impact.ttf"}[tur]
    return ImageFont.truetype(rf"{FONTLAR}\{dosya}", boyut)


def bugun():
    return dt.date.today().strftime("%d.%m.%Y")


def sar(metin, f, genislik):
    """Kelime kelime satırlara böler; yazılan satır sonları korunur."""
    satirlar = []
    for paragraf in (metin or "").splitlines() or [""]:
        son = ""
        for kelime in paragraf.split():
            aday = f"{son} {kelime}".strip()
            if f.getlength(aday) <= genislik or not son:
                son = aday
            else:
                satirlar.append(son)
                son = kelime
        satirlar.append(son)
    return satirlar


def buyuk(s):
    """Türkçe büyük harf (str.upper i'yi I yapar)."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def maddeler(metin):
    return [m.strip() for m in (metin or "").splitlines() if m.strip()]


class Kagit:
    """Yukarıdan aşağı içerik yığan çizim yardımcısı; sonda kullanılan yüksekliğe kırpılır."""

    def __init__(self, yukseklik=2400):
        self.img = Image.new("L", (GEN, yukseklik), 255)
        self.d = ImageDraw.Draw(self.img)
        self.y = 0

    def yazi(self, metin, f, hiza="sol", x=8, genislik=GEN - 16, aralik=1.25, renk=0):
        for s in sar(metin, f, genislik):
            g = f.getlength(s)
            xx = {"orta": x + (genislik - g) / 2, "sag": x + genislik - g}.get(hiza, x)
            self.d.text((xx, self.y), s, font=f, fill=renk)
            self.y += round(f.size * aralik)

    def ikonlu(self, sembol, metin, f, aralik=1.3):
        """Ortalanmış 'sembol + metin' satırı; sembol, metnin fontunda olmayabileceği için sembol fontuyla çizilir."""
        fs = font(f.size, "sembol")
        gs, gm = fs.getlength(sembol), f.getlength(" " + metin)
        x = (GEN - gs - gm) / 2
        self.d.text((x, self.y), sembol, font=fs, fill=0)
        self.d.text((x + gs, self.y), " " + metin, font=f, fill=0)
        self.y += round(f.size * aralik)

    def bant(self, metin, f, yukseklik=None, hiza="orta"):
        """Ters renk başlık bandı."""
        h = yukseklik or round(f.size * 1.6)
        self.d.rectangle((0, self.y, GEN - 1, self.y + h), fill=0)
        g = f.getlength(metin)
        x = (GEN - g) / 2 if hiza == "orta" else 12
        self.d.text((x, self.y + (h - f.size) / 2 - f.size * 0.12), metin, font=f, fill=255)
        self.y += h + 1

    def kesikli(self, kalinlik=2, aralik=(10, 6), x0=0, x1=GEN):
        x = x0
        while x < x1:
            self.d.line((x, self.y, min(x + aralik[0], x1), self.y), fill=0, width=kalinlik)
            x += sum(aralik)
        self.y += kalinlik

    def bosluk(self, n):
        self.y += n

    def bitir(self, alt=16):
        return self.img.crop((0, 0, GEN, self.y + alt))


def kutu(d, x, y, boy, isaretli=False):
    d.rounded_rectangle((x, y, x + boy, y + boy), radius=4, outline=0, width=3)
    if isaretli:
        d.line((x + 5, y + boy // 2, x + boy // 2 - 1, y + boy - 6, x + boy - 4, y + 5), fill=0, width=4)


def barkod(d, tohum, x0, x1, y, h):
    """Metne göre değişen süs barkod."""
    x = x0
    for b in hashlib.md5(tohum.encode()).digest() * 4:
        w = 1 + b % 4
        if x + w > x1:
            break
        if b & 1:
            d.rectangle((x, y, x + w - 1, y + h), fill=0)
        x += w + 1


def yay_yazi(img, metin, f, cx, cy, r, alt=False, aralik=2):
    """Daire yayı üzerine harf harf yazı: üstte saat yönünde, altta soldan sağa okunur."""
    genislikler = [f.getlength(c) + aralik for c in metin]
    toplam = sum(genislikler) / r
    a = (math.pi / 2 + toplam / 2) if alt else (-math.pi / 2 - toplam / 2)
    yon = -1 if alt else 1
    kutu_h = round(f.size * 1.5)
    for c, w in zip(metin, genislikler):
        aci = a + yon * (w / 2) / r
        harf = Image.new("L", (round(w) + 8, kutu_h), 0)
        ImageDraw.Draw(harf).text((harf.width / 2, kutu_h / 2), c, font=f, fill=255, anchor="mm")
        donus = math.degrees(aci) - 90 if alt else math.degrees(aci) + 90
        harf = harf.rotate(-donus, resample=Image.BICUBIC, expand=True).point(lambda v: 255 if v > 110 else 0)
        x, y = cx + r * math.cos(aci), cy + r * math.sin(aci)
        img.paste(0, (round(x - harf.width / 2), round(y - harf.height / 2)), harf)
        a += yon * w / r


def dama(d, y, h, kare, x0=0, x1=GEN):
    """İki sıra dama deseni şerit (retro etiket kenarı)."""
    for sira in range(h // kare):
        for i, x in enumerate(range(x0, x1, kare)):
            if (i + sira) % 2 == 0:
                d.rectangle((x, y + sira * kare, min(x + kare, x1) - 1, y + (sira + 1) * kare - 1), fill=0)


# ---------- şablonlar ----------

def yapilacaklar(a):
    k = Kagit()
    k.bant(buyuk(a["baslik"]) or "YAPILACAKLAR", font(30))
    k.bosluk(6)
    k.yazi(a["tarih"], font(18, "normal"), hiza="sag")
    k.bosluk(6)
    f = font(24, "normal")
    for m in maddeler(a["maddeler"]):
        bas = k.y
        kutu(k.d, 10, bas + 6, 22)
        k.yazi(m, f, x=46, genislik=GEN - 56)
        k.bosluk(8)
        k.d.line((46, k.y - 4, GEN - 10, k.y - 4), fill=0, width=1)
    k.bosluk(10)
    k.ikonlu("✓", "bir bir bitir!", font(18, "el"))
    return k.bitir()


def alisveris(a):
    k = Kagit()
    k.bosluk(6)
    k.yazi("🛒", font(54, "sembol"), hiza="orta", aralik=1.05)
    k.yazi("ALIŞVERİŞ LİSTESİ", font(28), hiza="orta")
    k.kesikli()
    k.bosluk(10)
    f = font(24, "normal")
    for m in maddeler(a["maddeler"]):
        kutu(k.d, 10, k.y + 6, 20)
        k.yazi(m, f, x=42, genislik=GEN - 52)
        k.bosluk(4)
    if a["not"].strip():
        k.bosluk(6)
        k.kesikli(1)
        k.bosluk(6)
        k.yazi(a["not"], font(20, "el"), hiza="orta")
    return k.bitir()


def not_kagidi(a):
    k = Kagit()
    k.bosluk(14)
    bas = k.y
    k.bosluk(18)
    k.yazi(a["not"], font(int(a["boyut"] or 30) if str(a["boyut"]).isdigit() else 30, "el"), x=24,
           genislik=GEN - 48, hiza="orta")
    k.bosluk(10)
    k.yazi(a["imza"], font(18, "el"), x=24, genislik=GEN - 48, hiza="sag")
    k.bosluk(14)
    son = k.y
    k.d.polygon(((6, bas), (GEN - 40, bas), (GEN - 6, bas + 34), (GEN - 6, son), (6, son)), outline=0, width=3)
    k.d.polygon(((GEN - 40, bas), (GEN - 40, bas + 34), (GEN - 6, bas + 34)), outline=0, fill=0)  # kıvrık köşe
    k.d.text((14, bas + 4), "📌", font=font(22, "sembol"), fill=0)
    return k.bitir(alt=8)


def kavanoz(a):
    k = Kagit()
    k.bosluk(10)
    bas = k.y
    k.bosluk(22)
    k.yazi("❦", font(26, "sembol"), hiza="orta", aralik=1.0)
    k.yazi(a["ad"], font(46, "serif"), hiza="orta", x=26, genislik=GEN - 52, aralik=1.15)
    if a["alt"].strip():
        k.yazi(a["alt"], font(20, "el"), hiza="orta", x=26, genislik=GEN - 52)
    k.bosluk(6)
    k.d.line((110, k.y, GEN - 110, k.y), fill=0, width=2)
    k.bosluk(8)
    k.yazi(a["tarih"], font(18, "normal"), hiza="orta")
    k.bosluk(18)
    son = k.y
    k.d.rounded_rectangle((8, bas, GEN - 8, son), radius=26, outline=0, width=4)
    k.d.rounded_rectangle((16, bas + 8, GEN - 16, son - 8), radius=20, outline=0, width=1)
    return k.bitir(alt=10)


def isim(a):
    k = Kagit()
    k.bant("MERHABA", font(44), yukseklik=70)
    k.yazi("adım", font(22, "normal"), hiza="orta")
    k.bosluk(6)
    k.yazi(a["ad"], font(56, "el"), hiza="orta", aralik=1.2)
    if a["unvan"].strip():
        k.yazi(a["unvan"], font(20, "normal"), hiza="orta")
    k.bosluk(10)
    k.d.rectangle((0, k.y, GEN - 1, k.y + 14), fill=0)
    k.bosluk(14)
    return k.bitir(alt=2)


def hediye(a):
    k = Kagit()
    k.bosluk(8)
    bas = k.y
    k.d.ellipse((GEN // 2 - 9, bas + 8, GEN // 2 + 9, bas + 26), outline=0, width=3)  # ip deliği
    k.bosluk(34)
    k.yazi("✦  ✧  ✦", font(22, "sembol"), hiza="orta")
    k.yazi(a["mesaj"], font(30, "el"), hiza="orta", x=20, genislik=GEN - 40)
    k.bosluk(8)
    for etiket, deger in (("Kime:", a["kime"]), ("Kimden:", a["kimden"])):
        if deger.strip():
            k.d.text((28, k.y), etiket, font=font(20), fill=0)
            k.d.text((28 + font(20).getlength(etiket) + 8, k.y - 4), deger, font=font(24, "el"), fill=0)
            k.y += 34
    k.bosluk(12)
    son = k.y
    k.d.polygon(((60, bas), (GEN - 60, bas), (GEN - 8, bas + 52), (GEN - 8, son), (8, son), (8, bas + 52)),
                outline=0, width=3)
    return k.bitir(alt=10)


def wifi(a):
    import qrcode
    k = Kagit()
    k.bant("Wi-Fi", font(34))
    k.bosluk(10)
    def kacis(s):
        return "".join("\\" + c if c in "\\;,:\"" else c for c in s)
    veri = f"WIFI:T:{'WPA' if a['sifre'] else 'nopass'};S:{kacis(a['ag'])};P:{kacis(a['sifre'])};;"
    qr = qrcode.QRCode(border=1, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(veri)
    qr.make(fit=True)
    kare = qr.make_image(fill_color="black", back_color="white").convert("L")
    olcek = max(1, 220 // kare.width)
    kare = kare.resize((kare.width * olcek, kare.height * olcek), Image.NEAREST)  # keskin kareler
    k.img.paste(kare, ((GEN - kare.width) // 2, k.y))
    k.bosluk(kare.height + 8)
    k.ikonlu("📷", "telefonla okut, bağlan", font(17, "normal"))
    k.bosluk(4)
    k.kesikli(1)
    k.bosluk(8)
    k.yazi("AĞ", font(15), hiza="orta", aralik=1.6)  # büyük harf noktaları/çengelleri alttakine değmesin
    k.yazi(a["ag"], font(26, "fis"), hiza="orta")  # şifre yazılmaz, yalnız QR'da
    k.bosluk(6)
    return k.bitir()


def kablo(a):
    """Her kablo için bayrak etiket: ortadan katlanınca iki yüz de okunur (yazı bir yüzde ters)."""
    k = Kagit()
    f = font(int(a["boyut"]) if str(a["boyut"]).isdigit() else 26)
    for ad in maddeler(a["kablolar"]) or ["kablo"]:
        h = round(f.size * 1.7)
        yuz = Image.new("L", (150, h), 255)
        dd = ImageDraw.Draw(yuz)
        g = min(f.getlength(ad), 146)
        dd.text(((150 - g) / 2, (h - f.size) / 2 - f.size * 0.12), ad, font=f, fill=0)
        k.d.rectangle((8, k.y, GEN - 8, k.y + h), outline=0, width=2)
        k.img.paste(yuz, (14, k.y + 1))
        k.img.paste(yuz.rotate(180), (GEN - 164, k.y + 1))
        for yy in range(k.y + 4, k.y + h - 2, 8):  # kablonun saracağı orta bölge, katlama çizgileri
            k.d.line((GEN // 2 - 26, yy, GEN // 2 - 26, yy + 3), fill=0)
            k.d.line((GEN // 2 + 26, yy, GEN // 2 + 26, yy + 3), fill=0)
        k.y += h + 14
    k.ikonlu("✂", "kes · ortadan kablonun etrafına sar", font(15, "normal"))
    return k.bitir()


def aliskanlik(a):
    k = Kagit()
    k.bant(buyuk(a["baslik"]) or "BU HAFTA", font(28))
    k.bosluk(8)
    gunler = "Pt Sa Ça Pe Cu Ct Pz".split()  # 3 harf sütuna sığmıyor
    sol, hucre = 150, (GEN - 150 - 8) // 7
    for i, g in enumerate(gunler):
        f = font(15)
        k.d.text((sol + i * hucre + (hucre - f.getlength(g)) / 2, k.y), g, font=f, fill=0)
    k.bosluk(24)
    f = font(20, "normal")
    for m in maddeler(a["aliskanliklar"]):
        satir = sar(m, f, sol - 16)[0]
        k.d.text((8, k.y + 4), satir, font=f, fill=0)
        for i in range(7):
            kutu(k.d, sol + i * hucre + (hucre - 22) // 2, k.y + 4, 22)
        k.y += 38
    k.bosluk(6)
    k.ikonlu("★", "her kutu bir küçük zafer", font(17, "el"))
    return k.bitir()


def fis(a):
    k = Kagit()
    k.bosluk(6)
    k.yazi(buyuk(a["baslik"]) or "MUTLULUK MARKET", font(26, "fis"), hiza="orta")
    k.yazi(f"{a['tarih']}   FİŞ NO: {int(hashlib.md5(a['kalemler'].encode()).hexdigest()[:4], 16):05d}",
           font(16, "fis"), hiza="orta")
    k.kesikli(2, (6, 4))
    k.bosluk(8)
    f, toplam = font(20, "fis"), 0.0
    for m in maddeler(a["kalemler"]):
        ad, _, fiyat = m.rpartition(" ")
        try:
            tutar = float(fiyat.replace(",", "."))
        except ValueError:
            ad, tutar = m, None
        if tutar is not None:
            toplam += tutar
        sag = f"{tutar:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if tutar is not None else ""
        bas = k.y
        k.yazi(ad, f, x=8, genislik=GEN - 120)
        k.d.text((GEN - 8 - f.getlength(sag), bas), sag, font=f, fill=0)
    k.kesikli(2, (6, 4))
    k.bosluk(6)
    f2 = font(26, "fis")
    t = f"{toplam:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    k.d.text((8, k.y), "TOPLAM", font=f2, fill=0)
    k.d.text((GEN - 8 - f2.getlength(t), k.y), t, font=f2, fill=0)
    k.bosluk(40)
    barkod(k.d, a["baslik"] + a["kalemler"], 40, GEN - 40, k.y, 50)
    k.bosluk(58)
    k.yazi(a["dip"] or "Yine bekleriz ♥", font(20, "el"), hiza="orta")
    return k.bitir()


AYLAR = "Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
GUNLER = "Pazartesi Salı Çarşamba Perşembe Cuma Cumartesi Pazar".split()


def takvim(a):
    """Aylık takvim (Pazartesi başlar); notlardaki 'gün açıklama' satırlarının günü işaretlenir, altta listelenir."""
    import calendar
    try:
        yil, ay = (int(p) for p in a["ay"].strip().split("-"))
        assert 1 <= ay <= 12
    except (ValueError, AssertionError):
        yil, ay = dt.date.today().year, dt.date.today().month
    notlar = {}
    for m in maddeler(a["notlar"]):
        gun, _, aciklama = m.partition(" ")
        if gun.rstrip(".").isdigit():
            notlar[int(gun.rstrip("."))] = aciklama
    k = Kagit()
    k.bant(buyuk(f"{AYLAR[ay - 1]} {yil}"), font(30))
    k.bosluk(6)
    hw = GEN // 7
    x0 = (GEN - 7 * hw) // 2
    f = font(15)
    for i, g in enumerate("Pt Sa Ça Pe Cu Ct Pz".split()):
        k.d.text((x0 + i * hw + hw / 2, k.y + 8), g, font=f, fill=0, anchor="mm")
    k.bosluk(20)
    fg, hh = font(20), 44
    for hafta in calendar.Calendar(0).monthdayscalendar(yil, ay):
        for i, gun in enumerate(hafta):
            x = x0 + i * hw
            k.d.rectangle((x, k.y, x + hw, k.y + hh), outline=0, width=1)
            if not gun:
                continue
            if gun in notlar:  # işaretli gün: ters renk
                k.d.rectangle((x + 2, k.y + 2, x + hw - 2, k.y + hh - 2), fill=0)
            k.d.text((x + 5, k.y + 3), str(gun), font=fg, fill=255 if gun in notlar else 0)
        k.y += hh
    if notlar:
        k.bosluk(8)
        for gun in sorted(notlar):
            k.yazi(f"{gun:>2}  {notlar[gun]}", font(20, "normal"), x=10, genislik=GEN - 20, aralik=1.3)
    return k.bitir()


def gunluk(a):
    """Günlük plan: tarih, üç öncelik kutusu, saat saat satırlar, notlar."""
    try:
        bas, son = (int(s) for s in a["saatler"].split("-"))
        assert 0 <= bas < son <= 24
    except (ValueError, AssertionError):
        bas, son = 8, 20
    k = Kagit()
    k.bant(buyuk(a["baslik"]) or "GÜNLÜK PLAN", font(28))
    k.bosluk(4)
    k.yazi(a["tarih"], font(20, "el"), hiza="orta", aralik=1.4)
    k.yazi("ÖNCELİKLER", font(16), x=10, aralik=1.5)
    oncelikler = maddeler(a["oncelikler"]) + [""] * 3
    for m in oncelikler[:max(3, len(maddeler(a["oncelikler"])))]:
        kutu(k.d, 10, k.y + 4, 20)
        k.d.line((40, k.y + 26, GEN - 10, k.y + 26), fill=0, width=1)
        k.d.text((42, k.y + 2), m, font=font(20, "el"), fill=0)
        k.y += 32
    k.bosluk(8)
    k.d.line((0, k.y, GEN, k.y), fill=0, width=2)
    k.bosluk(6)
    for saat in range(bas, son + 1):
        k.d.text((10, k.y + 4), f"{saat:02d}", font=font(18, "fis"), fill=0)
        for x in range(48, GEN - 10, 8):  # yazı çizgisi
            k.d.line((x, k.y + 24, x + 3, k.y + 24), fill=0, width=1)
        k.y += 30
    if a["notlar"].strip():
        k.bosluk(8)
        k.yazi("NOTLAR", font(16), x=10, aralik=1.5)
        k.yazi(a["notlar"], font(20, "el"), x=10, genislik=GEN - 20)
    return k.bitir()


# ---------- sticker şablonları (termal sticker fikirleri) ----------

def rozet(a):
    """Yuvarlak sticker: üstte ve altta kavisli yazı, ortada sembol ve el yazısı."""
    k = Kagit()
    k.bosluk(8)
    cap = 364
    cx, cy, r = GEN // 2, k.y + cap // 2, cap // 2
    k.d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=0, width=5)
    k.d.ellipse((cx - r + 12, cy - r + 12, cx + r - 12, cy + r - 12), outline=0, width=2)
    k.d.ellipse((cx - r + 66, cy - r + 66, cx + r - 66, cy + r - 66), outline=0, width=2)
    fy = font(26)
    yay_yazi(k.img, buyuk(a["ust"]), fy, cx, cy, r - 40)
    yay_yazi(k.img, buyuk(a["alt"]), fy, cx, cy, r - 40, alt=True)
    fs = font(22, "sembol")
    for x in (cx - r + 40, cx + r - 40):  # yayların arasındaki yıldızlar
        k.d.text((x, cy), "✦", font=fs, fill=0, anchor="mm")
    f = font(40, "yazi")
    satirlar = sar(a["orta"], f, 2 * (r - 80))
    sembol = a["sembol"].strip()
    h = len(satirlar) * round(f.size * 1.2) + (40 if sembol else 0)
    y = cy - h / 2
    if sembol:
        k.d.text((cx, y + 16), sembol, font=font(32, "sembol"), fill=0, anchor="mm")
        y += 40
    for s in satirlar:
        k.d.text((cx, y + f.size * 0.6), s, font=f, fill=0, anchor="mm")
        y += round(f.size * 1.2)
    k.y = cy + r
    return k.bitir(alt=10)


def tesekkur(a):
    k = Kagit()
    k.bosluk(10)
    bas = k.y
    k.bosluk(16)
    k.yazi("♥  ✦  ♥", font(20, "sembol"), hiza="orta")
    k.yazi(a["baslik"], font(44, "yazi"), hiza="orta", x=28, genislik=GEN - 56, aralik=1.35)
    k.yazi(a["mesaj"], font(20, "normal"), hiza="orta", x=28, genislik=GEN - 56)
    if a["imza"].strip():
        k.bosluk(8)
        k.d.line((120, k.y, GEN - 120, k.y), fill=0, width=2)
        k.bosluk(8)
        k.yazi(a["imza"], font(20, "fis"), hiza="orta")
    k.bosluk(12)
    son = k.y
    k.d.rounded_rectangle((8, bas, GEN - 8, son), radius=18, outline=0, width=4)
    k.d.rounded_rectangle((16, bas + 8, GEN - 16, son - 8), radius=12, outline=0, width=1)
    return k.bitir(alt=10)


def retro(a):
    """Dama desen kenarlı retro etiket (happy mail / aç beni)."""
    k = Kagit()
    kare = int(a["kare"]) if str(a["kare"]).isdigit() and 6 <= int(a["kare"]) <= 48 else 16
    dama(k.d, k.y, kare * 2, kare)
    k.bosluk(kare * 2 + 12)
    k.yazi(buyuk(a["metin"]), font(64, "blok"), hiza="orta", aralik=1.15)
    if a["alt"].strip():
        k.yazi(a["alt"], font(26, "yazi"), hiza="orta", aralik=1.4)
    k.bosluk(8)
    dama(k.d, k.y, kare * 2, kare)
    k.bosluk(kare * 2)
    return k.bitir(alt=4)


def kirilir(a):
    """Kırılır / dikkatli taşı uyarı etiketi: kutulu ikonlar."""
    k = Kagit()
    k.d.rectangle((0, 0, GEN - 1, 6), fill=0)
    k.bosluk(10)
    k.bant(buyuk(a["baslik"]) or "KIRILIR", font(48, "blok"), yukseklik=74)
    k.bosluk(10)
    ikonlar = a["ikonlar"].split()[:4] or ["🍷"]
    boy = (GEN - 16 - 8 * (len(ikonlar) - 1)) // len(ikonlar)
    boy = min(boy, 120)
    x = (GEN - len(ikonlar) * boy - 8 * (len(ikonlar) - 1)) // 2
    fs = font(round(boy * 0.6), "sembol")
    for ik in ikonlar:
        k.d.rounded_rectangle((x, k.y, x + boy, k.y + boy), radius=10, outline=0, width=4)
        k.d.text((x + boy / 2, k.y + boy / 2), ik, font=fs, fill=0, anchor="mm")
        x += boy + 8
    k.bosluk(boy + 10)
    k.yazi(buyuk(a["alt"]), font(24), hiza="orta")
    k.bosluk(4)
    k.d.rectangle((0, k.y, GEN - 1, k.y + 6), fill=0)
    k.bosluk(6)
    return k.bitir(alt=2)


def serit(a):
    """Tekrarlanan kelime deseni: satırlar kaydırılır, istenirse bir satır ters renk."""
    k = Kagit()
    f, fs = font(34, "yazi"), font(22, "sembol")
    satir = int(a["satir"]) if str(a["satir"]).isdigit() and 1 <= int(a["satir"]) <= 30 else 6
    ters = a["ters"].strip().lower() in ("evet", "e", "1", "var")
    kelime, sembol = a["kelime"] or "kırılır", a["sembol"] or "✦"
    birim = f.getlength(kelime) + fs.getlength(sembol) + 36
    h = 56
    for i in range(satir):
        siyah = ters and i % 2 == 1
        if siyah:
            k.d.rectangle((0, k.y, GEN - 1, k.y + h - 1), fill=0)
        renk = 255 if siyah else 0
        x = -(birim / 2 if i % 2 else 0)
        while x < GEN:
            k.d.text((x, k.y + h / 2), kelime, font=f, fill=renk, anchor="lm")
            x += f.getlength(kelime) + 18
            k.d.text((x, k.y + h / 2), sembol, font=fs, fill=renk, anchor="lm")
            x += fs.getlength(sembol) + 18
        k.y += h
    return k.bitir(alt=0)


def kargo(a):
    """Eğlenceli kargo etiketi (Kuzey Kutbu öncelikli posta gibi); 'x ' ile başlayan seçenek işaretli."""
    k = Kagit()
    bas = k.y + 4
    k.bosluk(14)
    fn = font(58, "blok")
    numara = a["numara"].strip()
    nk = fn.getlength(numara) + 24 if numara else 0
    k.yazi(a["baslik"], font(34, "serif"), x=16, genislik=GEN - 40 - nk, aralik=1.1)
    k.yazi(a["alt"], font(20, "normal"), x=16, genislik=GEN - 40 - nk)
    if numara:
        k.d.rectangle((GEN - 14 - nk, bas + 8, GEN - 14, bas + 82), outline=0, width=3)
        k.d.text((GEN - 14 - nk / 2, bas + 45), numara, font=fn, fill=0, anchor="mm")
        k.y = max(k.y, bas + 86)
    k.bosluk(6)
    for etiket, deger, f in (("KİMDEN", a["kimden"], font(22, "el")), ("KİME", a["kime"], font(30, "el"))):
        k.d.line((4, k.y, GEN - 5, k.y), fill=0, width=3)
        k.bosluk(6)
        k.yazi(etiket + ":", font(15), x=16, aralik=1.3)
        k.yazi(deger, f, x=24, genislik=GEN - 48)
        k.bosluk(4)
    k.d.line((4, k.y, GEN - 5, k.y), fill=0, width=3)
    k.bosluk(10)
    f = font(24)
    for m in maddeler(a["secenekler"]):
        isaretli = m[:2].lower() == "x "
        kutu(k.d, 18, k.y + 4, 24, isaretli)
        k.yazi(m[2:] if isaretli else m, f, x=54, genislik=GEN - 70)
        k.bosluk(2)
    k.bosluk(8)
    barkod(k.d, a["baslik"] + a["kime"], 24, GEN - 24, k.y, 56)
    k.bosluk(62)
    if a["not"].strip():
        k.yazi(buyuk(a["not"]), font(15, "fis"), hiza="orta")
    k.bosluk(8)
    k.d.rectangle((4, bas, GEN - 5, k.y), outline=0, width=4)
    return k.bitir(alt=8)


def pul(a):
    """Tırtıklı kenarlı posta pulu."""
    k = Kagit()
    bas = k.y + 4
    f = font(40, "yazi")
    son = bas + 70 + len(sar(a["metin"], f, GEN - 80)) * round(f.size * 1.25) + 60
    d = k.d
    d.rectangle((4, bas, GEN - 5, son), fill=0)
    d.rectangle((16, bas + 12, GEN - 17, son - 12), fill=255)
    for x in range(4, GEN - 4, 20):  # delikli kenar
        for y in (bas, son):
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=255)
    for y in range(bas, son, 20):
        for x in (4, GEN - 5):
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=255)
    d.rectangle((26, bas + 22, GEN - 27, son - 22), outline=0, width=2)
    d.text((36, bas + 28), buyuk(a["ust"]), font=font(16), fill=0)
    fd = font(30)  # Impact'te ₺ yok
    d.text((GEN - 36 - fd.getlength(a["deger"]), bas + 22), a["deger"], font=fd, fill=0)
    k.y = bas + 64
    k.yazi(a["metin"], f, hiza="orta", x=40, genislik=GEN - 80)
    fa = font(16, "fis")
    d.text((GEN / 2, son - 36), " ".join(buyuk(a["alt"])), font=fa, fill=0, anchor="mm")
    k.y = son + 6
    return k.bitir(alt=4)


def kedi_not(a):
    """Kedi kulaklı çerçeveli not."""
    k = Kagit()
    k.bosluk(40)
    bas = k.y
    k.bosluk(24)
    boyut = int(a["boyut"]) if str(a["boyut"]).isdigit() and 12 <= int(a["boyut"]) <= 80 else 30
    k.yazi(a["metin"], font(boyut, "el"), hiza="orta", x=30, genislik=GEN - 60)
    k.bosluk(44)
    son = k.y
    d = k.d
    d.rounded_rectangle((10, bas, GEN - 10, son), radius=30, outline=0, width=5)
    for x0 in (36, GEN - 116):  # kulaklar: iç üçgen çerçeve çizgisini de siler, kafa çizgisi açılır
        d.polygon(((x0, bas + 4), (x0 + 40, bas - 36), (x0 + 80, bas + 4)), fill=0)
        d.polygon(((x0 + 9, bas + 6), (x0 + 40, bas - 25), (x0 + 71, bas + 6)), fill=255)
    d.text((GEN - 26, son - 22), "🐾", font=font(24, "sembol"), fill=0, anchor="rm")
    return k.bitir(alt=8)


def sayi(deger, varsayilan, en_az, en_cok):
    return int(deger) if str(deger).strip().isdigit() and en_az <= int(deger) <= en_cok else varsayilan


@functools.lru_cache(maxsize=32)
def _foto(yol, degisim, w, h):
    from c9_yazdir import noktala  # döngüsel içe aktarma yok; yalnız fotoğraflı şablonlarda gerekir
    with Image.open(yol) as r:
        r = ImageOps.exif_transpose(r).convert("RGBA")
    zemin = Image.new("RGBA", r.size, "white")
    zemin.alpha_composite(r)
    gri = ImageOps.autocontrast(ImageOps.fit(zemin.convert("L"), (w, h), Image.LANCZOS), cutoff=1)
    return noktala(gri).convert("L")


def foto(yol, w, h):
    """Görseli w×h kutuya kırparak sığdırır ve noktalar (eşiklemede kaybolmasın); açılamazsa None."""
    try:
        return _foto(yol, os.path.getmtime(yol), w, h)
    except Exception:
        return None


def minimal(a):
    """Sade market etiketi: NO. 45 / TUZ / BAHARAT / TAMAMEN DOĞAL."""
    k = Kagit()
    k.bosluk(34)
    if a["no"].strip():
        k.yazi("NO. " + a["no"].strip(), font(32, "dar"), hiza="orta", aralik=1.4)
    k.yazi(buyuk(a["ad"]), font(sayi(a["boyut"], 100, 30, 200), "dar"), hiza="orta", aralik=1.15)
    k.bosluk(20)
    if a["tur"].strip():
        f = font(34, "dar")
        k.yazi(buyuk(a["tur"]), f, hiza="orta", aralik=1.15)
        g = f.getlength(buyuk(a["tur"]))
        k.d.line((GEN / 2 - g / 2, k.y, GEN / 2 + g / 2, k.y), fill=0, width=2)
        k.bosluk(6)
    if a["alt"].strip():
        k.yazi(buyuk(a["alt"]), font(26, "dar"), hiza="orta")
    k.bosluk(30)
    return k.bitir(alt=0)


# ---------- orijinal sticker sayfalarından kesilenler (stickerlar/kes.py üretir) ----------

STICKER_KLASORU = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "stickerlar")
try:  # isteğe bağlı hazır sticker paketi (stickerlar/liste.json + parcalar/); yoksa yalnız kullanıcı sayfaları
    with open(os.path.join(STICKER_KLASORU, "liste.json"), encoding="utf-8") as _f:
        STICKERLAR = json.load(_f)
except OSError:
    STICKERLAR = []


@functools.lru_cache(maxsize=None)
def _parca(dosya):
    with Image.open(os.path.join(STICKER_KLASORU, "parcalar", dosya)) as r:
        return r.convert("L")


def _kutuya_yaz(d, kutu, metin, f_tur, boyut, renk=0):
    """Metni kutuya ortalar; sığmazsa küçültür."""
    x0, y0, x1, y1 = kutu
    boy = boyut
    while True:
        f = font(boy, f_tur)
        satirlar = sar(metin, f, x1 - x0)
        if boy <= 10 or (len(satirlar) * boy * 1.25 <= y1 - y0 and all(f.getlength(s) <= x1 - x0 for s in satirlar)):
            break
        boy -= 2
    y = (y0 + y1) / 2 - (len(satirlar) - 1) * boy * 0.625
    for s in satirlar:
        d.text(((x0 + x1) / 2, y), s, font=f, fill=renk, anchor="mm")
        y += boy * 1.25


YAZI_TIPLERI = {"el yazısı": "el", "süslü": "yazi", "kalın": "kalin", "normal": "normal"}


def hazir(kayit, a):
    """Kesilmiş orijinal sticker; çerçevenin içine yazı, film karelerine fotoğraf."""
    r = _parca(kayit["dosya"])
    w = min(GEN, round(sayi(a["genislik"], 48, 10, 48) * 8))
    o = w / r.width
    r = r.resize((w, max(1, round(r.height * o))), Image.LANCZOS)
    if kayit.get("noktali"):  # renkli çizim: gri tonlar noktaya
        from c9_yazdir import noktala
        r = noktala(r).convert("L")
    else:  # siyah çizgi: keskin
        r = r.point(lambda v: 255 if v >= 150 else 0)
    img = Image.new("L", (GEN, r.height + 8), 255)
    dx, dy = (GEN - r.width) // 2, 4
    img.paste(r, (dx, dy))
    d = ImageDraw.Draw(img)
    if kayit["tur"] == "cerceve" and a["yazi"].strip():
        x0, y0, x1, y1 = (v * o for v in kayit["kutu"])
        pay = (x1 - x0) * 0.06
        dx, dy = dx + a.get("_dx", 0), dy + a.get("_dy", 0)  # önizlemede fareyle kaydırma
        _kutuya_yaz(d, (dx + x0 + pay, dy + y0 + pay, dx + x1 - pay, dy + y1 - pay), a["yazi"],
                    YAZI_TIPLERI.get(a["tip"], "el"), sayi(a["boyut"], 28, 10, 80))
    elif kayit["tur"] == "film":
        for yol, kare in zip(maddeler(a["fotolar"]), kayit["kareler"]):
            x0, y0, x1, y1 = (round(v * o) for v in kare)
            resim = foto(yol, x1 - x0, y1 - y0)
            if resim is not None:
                img.paste(resim, (dx + x0, dy + y0))
    return img


def karakter(kayit, a):
    """Orijinal kahve karakteri (solda, noktalı) ve yanında düzenlenebilir söz; '*' ile başlayan satır büyük."""
    from c9_yazdir import noktala
    r = _parca(kayit["dosya"])
    o = min(190 / r.width, 300 / r.height)
    r = noktala(r.resize((round(r.width * o), round(r.height * o)), Image.LANCZOS)).convert("L")
    x0, x1 = r.width + 14, GEN - 6
    satirlar = []
    for s in (a["yazi"] or "").splitlines():
        if s.strip():
            vurgu = s.startswith("*")
            metin = buyuk(s.lstrip("*").strip())
            boy = 38 if vurgu else 26
            while boy > 12 and font(boy, "el_kalin").getlength(metin) > x1 - x0:
                boy -= 2
            satirlar.append((metin, font(boy, "el_kalin")))
    yazi_h = sum(round(f.size * 1.2) for _, f in satirlar)
    H = max(r.height, yazi_h) + 16
    img = Image.new("L", (GEN, H), 255)
    img.paste(r, (6, (H - r.height) // 2))
    d = ImageDraw.Draw(img)
    y = (H - yazi_h) / 2
    for metin, f in satirlar:
        d.text(((x0 + x1) / 2, y + f.size * 0.6), metin, font=f, fill=0, anchor="mm")
        y += round(f.size * 1.2)
    return img


IKON_DOSYALARI = {k["ikon_no"]: k["dosya"] for k in STICKERLAR if "ikon_no" in k}


def soz(kayit, a):
    """Yazılı kahve sticker'ı: yazı ve ikon değişmediyse orijinal resim; değiştiyse orijinal düzene benzer dizim.
    Satır: '*' el yazısı, '!' büyük blok, '=' kurdele bant, '~' dalgalı çizgi, diğerleri kalın büyük harf."""
    ikon = int(a["ikon"].split()[-1]) if a["ikon"].split()[-1].isdigit() else 0
    if a["yazi"].strip() == kayit["metin"].strip() and ikon == kayit["ikon"]:
        return hazir(kayit, a)
    k = Kagit()
    k.bosluk(8)
    if ikon in IKON_DOSYALARI:
        r = _parca(IKON_DOSYALARI[ikon])
        o = min(110 / r.height, 200 / r.width)
        r = r.resize((round(r.width * o), round(r.height * o)), Image.LANCZOS).point(lambda v: 255 if v >= 150 else 0)
        k.img.paste(r, ((GEN - r.width) // 2, k.y))
        k.bosluk(r.height + 6)
    turkce = any(c in a["yazi"] for c in "çğışöüÇĞİŞÖÜ")  # İngilizce yazıda i -> I kalmalı
    for s in a["yazi"].splitlines():
        if not s.strip():
            continue
        isaret, metin = (s[0], s[1:].strip()) if s[0] in "*!=~" else ("", s.strip())
        if isaret == "~":
            k.bosluk(4)
            k.d.line([(x, k.y + 6 + 6 * math.sin((x - 110) / 26)) for x in range(110, GEN - 110, 3)], fill=0, width=4)
            k.bosluk(22)
            continue
        # satır, orijinallerdeki gibi genişliği doldurur; üst sınır satır türüne göre
        tur, boy = {"*": ("yazi", 84), "!": ("blok", 110), "=": ("kalin", 36)}.get(isaret, ("kalin", 46))
        metin = metin if isaret == "*" else (buyuk(metin) if turkce else metin.upper())
        genislik = GEN - (90 if isaret == "=" else 24)
        while boy > 12 and font(boy, tur).getlength(metin) > genislik:
            boy -= 2
        f = font(boy, tur)
        if isaret == "=":  # kurdele: siyah bant, çatallı uçlar, beyaz yazı
            g, h, y = f.getlength(metin), round(boy * 1.6), k.y + 2
            x0, x1 = (GEN - g) / 2 - 20, (GEN + g) / 2 + 20
            for uc, yon in ((x0, -1), (x1, 1)):
                k.d.polygon(((uc, y + 8), (uc + yon * 26, y + 8), (uc + yon * 15, y + 8 + h / 2),
                             (uc + yon * 26, y + 8 + h), (uc, y + 8 + h)), fill=0)
            k.d.rectangle((x0, y, x1, y + h), fill=0)
            k.d.text((GEN / 2, y + h / 2), metin, font=f, fill=255, anchor="mm")
            k.y += h + 16
        else:
            k.yazi(metin, f, hiza="orta", aralik=1.25 if isaret == "*" else 1.12)
    return k.bitir(alt=12)


def baharat(a):
    """Orijinal boş baharat etiketine isimler (beyaz süslü yazı); bir baskıda çok sayıda.
    Dikeyde dar uzun etiketler, yazı aşağıdan yukarı."""
    dikey = a["yon"] == "dikey"
    kayit = next(k for k in STICKERLAR if k["tur"] == "baharat" and k["dikey"] == dikey)
    bos = _parca(kayit["dosya"])
    sutun = sayi(a["sutun"], 2, 1, 3) * (2 if dikey else 1)
    ara = 6
    w = (GEN - ara * (sutun + 1)) // sutun
    o = w / bos.width
    h = round(bos.height * o)
    etiket = bos.resize((w, h), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0)
    x0, y0, x1, y1 = (v * o for v in kayit["kutu"])
    adlar = maddeler(a["isimler"]) or ["Tarçın"]
    img = Image.new("L", (GEN, ((len(adlar) - 1) // sutun + 1) * (h + ara) + ara), 255)
    for i, ad in enumerate(adlar):
        e = etiket.copy()
        if dikey:  # yatay yazıp döndür
            yatay = Image.new("L", (round(y1 - y0), round(x1 - x0)), 0)
            _kutuya_yaz(ImageDraw.Draw(yatay), (4, 2, yatay.width - 4, yatay.height - 2), ad, "yazi", 60, 255)
            e.paste(255, (round(x0), round(y0)), yatay.rotate(90, expand=True))
        else:
            _kutuya_yaz(ImageDraw.Draw(e), (x0 + 6, y0 + 2, x1 - 6, y1 - 2), ad, "yazi", 60, 255)
        img.paste(e, (ara + (i % sutun) * (w + ara), ara + (i // sutun) * (h + ara)))
    return img


SABLONLAR = {
    "Yapılacaklar listesi": ([("baslik", "Başlık", "Yapılacaklar", "satir"), ("tarih", "Tarih", bugun(), "satir"),
                              ("maddeler", "Maddeler (her satıra bir)", "Faturayı öde\nSpor\nKitap oku 20 sayfa",
                               "cok")], yapilacaklar),
    "Alışveriş listesi": ([("maddeler", "Ürünler (her satıra bir)", "Süt\nYumurta\nEkmek\nKahve", "cok"),
                           ("not", "Alta not", "unutma!", "satir")], alisveris),
    "Not kağıdı": ([("not", "Not", "Bugün harika bir gün olacak", "cok"), ("imza", "İmza", "— Deniz", "satir"),
                    ("boyut", "Yazı boyu", "30", "satir")], not_kagidi),
    "Kavanoz / baharat etiketi": ([("ad", "Ad", "Tarçın", "satir"), ("alt", "Alt yazı", "Seylan", "satir"),
                                   ("tarih", "Tarih", bugun(), "satir")], kavanoz),
    "İsim etiketi": ([("ad", "Ad", "Deniz", "satir"), ("unvan", "Ünvan / not", "", "satir")], isim),
    "Hediye etiketi": ([("mesaj", "Mesaj", "İyi ki doğdun!", "cok"), ("kime", "Kime", "", "satir"),
                        ("kimden", "Kimden", "", "satir")], hediye),
    "Wi-Fi kartı (QR)": ([("ag", "Ağ adı (SSID)", "EvAgi", "satir"), ("sifre", "Şifre", "", "satir")], wifi),
    "Kablo etiketi": ([("kablolar", "Kablolar (her satıra bir)", "Monitör\nYazıcı\nModem", "cok"),
                       ("boyut", "Yazı boyu", "26", "satir")], kablo),
    "Haftalık alışkanlık takibi": ([("baslik", "Başlık", "Bu hafta", "satir"),
                                    ("aliskanliklar", "Alışkanlıklar (her satıra bir)",
                                     "Su 2 L\nYürüyüş\nKitap\nErken yat", "cok")], aliskanlik),
    "Komik fiş": ([("baslik", "Mağaza adı", "Mutluluk Market", "satir"), ("tarih", "Tarih", bugun(), "satir"),
                   ("kalemler", "Kalemler (ad fiyat)", "Sabah kahvesi 1\nGüneşli hava 0\nTatlı kaçamak 2,5\n"
                    "Bol kahkaha 0", "cok"), ("dip", "Alt yazı", "Yine bekleriz ♥", "satir")], fis),
    "Aylık takvim": ([("ay", "Ay (yıl-ay)", dt.date.today().strftime("%Y-%m"), "satir"),
                      ("notlar", "Önemli günler (gün açıklama)", "12 Doğum günü\n25 Fatura", "cok")], takvim),
    "Günlük plan": ([("baslik", "Başlık", "Günlük plan", "satir"),
                     ("tarih", "Tarih", f"{bugun()} {GUNLER[dt.date.today().weekday()]}", "satir"),
                     ("oncelikler", "Öncelikler (her satıra bir)", "Spor\nRapor", "cok"),
                     ("saatler", "Saatler (başlangıç-bitiş)", "8-20", "satir"),
                     ("notlar", "Notlar", "", "cok")], gunluk),
    "Sticker: yuvarlak rozet": ([("ust", "Üst kavis", "El yapımı", "satir"), ("orta", "Orta yazı", "sevgiyle", "cok"),
                                 ("sembol", "Sembol", "♥", "satir"), ("alt", "Alt kavis", "Küçük işletme", "satir")],
                                rozet),
    "Sticker: teşekkür": ([("baslik", "Başlık", "Teşekkürler!", "satir"),
                           ("mesaj", "Mesaj", "Küçük işletmemi desteklediğin için", "cok"),
                           ("imza", "İmza / hesap", "@dukkanim", "satir")], tesekkur),
    "Sticker: retro dama": ([("metin", "Yazı", "Aç beni!", "cok"), ("alt", "Alt yazı", "mutlu posta", "satir"),
                             ("kare", "Dama karesi (px)", "16", "satir")], retro),
    "Sticker: kırılır uyarısı": ([("baslik", "Başlık", "Kırılır", "satir"),
                                  ("ikonlar", "İkonlar (boşlukla, en çok 4)", "🍷 ☂ ⇈", "satir"),
                                  ("alt", "Alt yazı", "Dikkatli taşıyın", "satir")], kirilir),
    "Sticker: tekrar şerit": ([("kelime", "Kelime", "kırılır", "satir"), ("sembol", "Ayraç sembol", "✦", "satir"),
                               ("satir", "Satır sayısı", "6", "satir"), ("ters", "Ters renk satır", "evet", "secim:evet,hayır")], serit),
    "Sticker: kargo etiketi": ([("baslik", "Başlık", "Kuzey Kutbu", "satir"),
                                ("alt", "Alt başlık", "Öncelikli Posta", "satir"), ("numara", "Büyük numara", "24",
                                                                                    "satir"),
                                ("kimden", "Kimden", "Noel Baba", "satir"), ("kime", "Kime", "Deniz", "cok"),
                                ("secenekler", "Seçenekler ('x ' ile başlayan işaretli)",
                                 "x Uslu listesi\nYaramaz listesi", "cok"),
                                ("not", "Alt not", "Aralık'tan önce açma", "satir")], kargo),
    "Sticker: posta pulu": ([("ust", "Üst yazı", "Türkiye", "satir"), ("metin", "Yazı", "Sevgiyle gönderildi", "cok"),
                             ("deger", "Değer", "5₺", "satir"), ("alt", "Alt yazı", "posta", "satir")], pul),
    "Sticker: kedi notu": ([("metin", "Not", "Bugün de harikasın", "cok"), ("boyut", "Yazı boyu", "30", "satir")],
                           kedi_not),
    "Sticker: sade kavanoz (No.)": ([("no", "Numara", "45", "satir"), ("ad", "Ad", "Tuz", "satir"),
                                     ("tur", "Tür", "Baharat", "satir"), ("alt", "Alt yazı", "Tamamen doğal",
                                                                           "satir"),
                                     ("boyut", "Ad yazı boyu", "100", "satir")], minimal),
}
if {True, False} <= {k.get("dikey") for k in STICKERLAR if k["tur"] == "baharat"}:  # boş etiketler varsa
    SABLONLAR["Baharat: etiketler"] = ([("isimler", "İsimler (her satıra bir)",
                                          "Kimyon\nKekik\nPul Biber\nKarabiber\nNane\nTarçın", "cok"),
                                         ("sutun", "Sütun (1-3)", "2", "satir"),
                                         ("yon", "Yön", "yatay", "secim:yatay,dikey")], baharat)
_GENISLIK = ("genislik", "Genişlik (mm, en çok 48)", "48", "satir")
def _kaydet(_k):
    """Kesilmiş bir sticker'ı galeriye şablon olarak ekler (adı döner)."""
    _ad = f"{_k['kategori']}: {_k['ad'].rsplit(' ', 1)[-1]}"
    if _k["tur"] == "baharat":
        return None
    if _k["tur"] == "cerceve":
        _alanlar = [("yazi", "Yazı (çerçevenin içine)", "", "cok"),
                    ("tip", "Yazı tipi", "el yazısı", "secim:el yazısı,süslü,kalın,normal"),
                    ("boyut", "Yazı boyu (sığmazsa küçülür)", "28", "satir"), _GENISLIK]
    elif _k["tur"] == "karakter":
        SABLONLAR[_ad] = (
            [("yazi", "Yazı (her satır ayrı; * ile başlayan büyük)", _k["metin"], "cok")],
            lambda a, k=_k: karakter(k, a))
        return _ad
    elif _k["tur"] == "soz":
        _ikonlar = ["yok"] + [f"fincan {n}" for n in sorted(IKON_DOSYALARI)]
        _alanlar = [("yazi", "Yazı (* el yazısı, ! büyük blok, = kurdele, ~ dalga)", _k["metin"], "cok"),
                    ("ikon", "İkon (yazı değişince)", _ikonlar[_k["ikon"]] if _k["ikon"] else "yok",
                     "secim:" + ",".join(_ikonlar)), _GENISLIK]
        SABLONLAR[_ad] = (_alanlar, lambda a, k=_k: soz(k, a))
        return _ad
    elif _k["tur"] == "film":
        _alanlar = [("fotolar", f"Fotoğraflar ({len(_k['kareler'])} kare, sırayla)", "", "dosyalar"), _GENISLIK]
    else:
        _alanlar = [_GENISLIK]
    SABLONLAR[_ad] = (_alanlar, lambda a, k=_k: hazir(k, a))
    return _ad


for _k in STICKERLAR:  # kesilmiş orijinal stickerlar galeride kategori kategori
    _kaydet(_k)

# kullanıcının eklediği sayfalar (uygulamada "Sayfa ekle…")
KULLANICI = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "C9Yazici")
_KULLANICI_LISTE = os.path.join(KULLANICI, "sayfalar.json")
try:
    with open(_KULLANICI_LISTE, encoding="utf-8") as _f:
        for _k in json.load(_f):
            if os.path.exists(_k["dosya"]):
                _kaydet(_k)
except (OSError, ValueError):
    pass


def sayfa_ekle(yol, ad):
    """Görsel sayfayı stickerlara böler, kullanıcı klasörüne kaydeder, galeriye ekler; eklenen şablon adları."""
    import c9_sayfa
    with Image.open(yol) as r:
        parcalar = c9_sayfa.kes(r)
    klasor = os.path.join(KULLANICI, "sayfalar", "".join(c if c.isalnum() else "_" for c in ad))
    os.makedirs(klasor, exist_ok=True)
    try:
        with open(_KULLANICI_LISTE, encoding="utf-8") as f:
            liste = json.load(f)
    except (OSError, ValueError):
        liste = []
    kategori = f"Benim: {ad}"
    liste = [k for k in liste if k["kategori"] != kategori]  # aynı adla yeniden eklenirse eskisinin yerine
    adlar = []
    for i, (parca, kutu, renkli) in enumerate(parcalar, 1):
        dosya = os.path.join(klasor, f"{i:02d}.png")
        parca.save(dosya)
        k = {"ad": f"{ad} {i}", "kategori": kategori, "tur": "cerceve" if kutu else "resim", "dosya": dosya,
             "noktali": renkli}
        if kutu:
            k["kutu"] = kutu
        liste.append(k)
        _parca.cache_clear()
        adlar.append(_kaydet(k))
    with open(_KULLANICI_LISTE, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=1)
    return adlar

def varsayilanlar(ad):
    return {a: v for a, _, v, _ in SABLONLAR[ad][0]}


def ciz(ad, degerler=None):
    alanlar, fonksiyon = SABLONLAR[ad]
    return fonksiyon({**varsayilanlar(ad), **(degerler or {})})


def toplu(ad, degerler, alan, liste):
    """Listedeki her satır için şablonun `alan` alanı değiştirilip ayrı etiket; alt alta, aralarında kesik çizgi."""
    resimler = [ciz(ad, {**degerler, alan: s}) for s in maddeler(liste)]
    if not resimler:
        return ciz(ad, degerler)
    img = Image.new("L", (GEN, sum(r.height for r in resimler) + 14 * (len(resimler) - 1)), 255)
    d, y = ImageDraw.Draw(img), 0
    for i, r in enumerate(resimler):
        if i:
            for x in range(0, GEN, 12):  # ayırma çizgisi: buradan kes
                d.line((x, y + 6, x + 5, y + 6), fill=0, width=1)
            y += 14
        img.paste(r.convert("L"), (0, y))
        y += r.height
    return img


if __name__ == "__main__":  # tüm şablonları varsayılan değerlerle yan yana kaydeder (önizleme)
    import os
    import sys
    resimler = [ciz(ad) for ad in SABLONLAR]
    for ad, r in zip(SABLONLAR, resimler):
        assert r.width == GEN and r.height > 40, ad
    sirlar = [resimler[i:i + 5] for i in range(0, len(resimler), 5)]
    yuks = [max(r.height for r in s) for s in sirlar]
    genis = Image.new("L", (GEN * 5 + 40, sum(yuks) + 20 * len(sirlar)), 200)
    for j, s in enumerate(sirlar):
        for i, r in enumerate(s):
            genis.paste(r, (i * (GEN + 10), sum(yuks[:j]) + 20 * j))
    hedef = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("TEMP", "."), "sablonlar.png")
    genis.save(hedef)
    print("kaydedildi:", hedef, genis.size)
