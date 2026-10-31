"""MXW01 (C9 ve benzeri, Fun Print uygulamalı) termal yazıcıya bilgisayardan Bluetooth LE ile baskı.

Kullanım:  python c9_yazdir.py dosya.png [dosya2.jpg notlar.txt ...] [--yogunluk 0-100] [--gri | --titrek]
           python c9_yazdir.py --metin "Merhaba"
           python c9_yazdir.py --durum
Görsel 384 px genişliğe ölçeklenir (57 mm kağıt, 203 dpi) ve siyah-beyaza çevrilir; --titrek fotoğraflar için
gri tonları nokta desenine çevirir. Protokol: github.com/clementvp/mxw01-thermal-printer (src/services/protocol.ts).
Yazıcı başka bir cihaza (telefondaki Fun Print) bağlıysa görünmez; önce oradan bağlantıyı kes.
"""
import argparse
import asyncio
import sys
import time

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

GENISLIK = 384               # nokta; satır başına 48 bayt
EN_AZ_SATIR = 90             # yazıcı bundan kısa veriyi kabul etmiyor
SERVISLER = ("ae30", "af30")
KONTROL, BILDIRIM, VERI = "ae01", "ae02", "ae03"
DURUM, YOGUNLUK, BASKI, VERI_BITTI, BASKI_BITTI = 0xA1, 0xA2, 0xA9, 0xAD, 0xAA
# Durum yanıtı (A1) verisi (başlıksız): [0] işlem, [3] pil %, [4] sıcaklık °C, [6] 0 = sorun yok, [7] hata kodu
# (kaynak: MaikelChan/CatPrinterBLE CatPrinter.cs; oradaki indeksler 6 baytlık başlık dahil)
HATALAR = {0x01: "kağıt bitti", 0x09: "kağıt bitti", 0x04: "aşırı ısınma", 0x08: "pil zayıf"}
ISLEMLER = {0: "hazır", 1: "basıyor", 2: "kağıt sürüyor", 3: "kağıt çıkarıyor"}


def crc8(veri):
    """CRC-8, polinom 0x07 (kaynaktaki tabloyla aynı sonuç)."""
    crc = 0
    for b in veri:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def komut(kod, veri):
    """22 21 | komut | 00 | uzunluk (LE) | veri | CRC8(veri) | FF"""
    veri = bytes(veri)
    return bytes([0x22, 0x21, kod, 0x00, len(veri) & 0xFF, len(veri) >> 8]) + veri + bytes([crc8(veri), 0xFF])


def gri_hazirla(resim, esik=128, fotograf=False):
    """Görsel -> 384 px genişlikte gri ("L"). fotograf: otomatik kontrast + hafif keskinleştirme (yüz hatları);
    esik 128'den farklıysa parlaklık kaydırılır (sola açık, sağa koyu)."""
    resim = ImageOps.exif_transpose(resim)
    if resim.mode in ("RGBA", "LA", "P"):
        zemin = Image.new("RGBA", resim.size, "white")
        zemin.alpha_composite(resim.convert("RGBA"))
        resim = zemin
    gri = resim.convert("L")
    if gri.width != GENISLIK:
        gri = gri.resize((GENISLIK, max(1, round(gri.height * GENISLIK / gri.width))), Image.LANCZOS)
    if fotograf:
        gri = gri.filter(ImageFilter.GaussianBlur(0.6))  # cilt/JPEG gürültüsü keskinleşip leke olmasın
        gri = ImageOps.autocontrast(gri, cutoff=0.5)
        gri = gri.filter(ImageFilter.UnsharpMask(radius=10, percent=35, threshold=0))  # yerel kontrast: yüz hatları
        gri = gri.filter(ImageFilter.UnsharpMask(radius=1.2, percent=90, threshold=10))  # yalnız belirgin kenarlar
        if esik != 128:
            gri = gri.point(lambda v: min(255, max(0, v + 128 - esik)))
    return gri


def atkinson(gri):
    """Atkinson titreştirmesi: hatanın yalnız 6/8'ini dağıtır; Floyd-Steinberg'e göre daha az gürültülü,
    açık ve koyu alanlar temiz kalır (termal yazıcı uygulamalarının tercihi)."""
    w, h = gri.size
    p = list(gri.getdata())
    for y in range(h):
        for x in range(w):
            i = y * w + x
            eski = p[i]
            yeni = 255 if eski >= 128 else 0
            p[i] = yeni
            hata = (eski - yeni) >> 3
            if hata:
                for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                    xx, yy = x + dx, y + dy
                    if 0 <= xx < w and yy < h:
                        p[yy * w + xx] += hata
    sonuc = Image.new("L", (w, h))
    sonuc.putdata(p)
    return sonuc.convert("1")


# Termal kağıt ayarları (gözle kalibre: yazıcıda deneyip değiştir).
# Noktalı: nokta yayılması ara tonları koyulaştırır, orta tonlar açılır.
NOKTA_EGRISI = [round(255 * (v / 255) ** 0.78) for v in range(256)]
# Gri: yazıcı açık tonları neredeyse basmaz (silik çıkar); %5'ten koyu her ton en az ~2. seviyeden başlar
# ve orta tonlar koyulaşır. 0 beyaz kalır.
GRI_EGRISI = [255 if (1 - v / 255) < 0.05 else round(255 * (1 - (0.12 + 0.88 * (1 - v / 255) ** 0.8)))
              for v in range(256)]


def noktala(gri):
    """Gri -> siyah-beyaz Floyd-Steinberg noktalama (PIL, hızlı); ara tonlar Atkinson'dan iyi korunur."""
    return gri.point(NOKTA_EGRISI).convert("1")


def tek_renk(resim, titrek=False, esik=128):
    """Görsel -> yazıcının basacağı haliyle 384 px genişlikte siyah-beyaz ("1") görsel.
    titrek: fotoğraf, gri tonlar nokta desenine; değilse esik'ten koyu pikseller siyah (yazı, logo)."""
    if titrek:
        return noktala(gri_hazirla(resim, esik, fotograf=True))
    return gri_hazirla(resim).point(lambda v: 255 if v >= esik else 0).convert("1")


def yerlestir(resim, sutun=1, kesim=False):
    """Basılacak 384 px görseli düzenler: boş kenarları kırpar, istenirse kesikli kesim çizgisi çizer ve
    aynı sticker'dan `sutun` tanesini yan yana dizer (sığmazsa küçültür). "1" ya da gri "L" korunur."""
    if sutun <= 1 and not kesim:
        return resim
    mod = resim.mode
    gri = resim.convert("L")
    kutu = ImageOps.invert(gri).getbbox()
    if kutu is None:
        return resim
    pay = 6
    gri = gri.crop((max(0, kutu[0] - pay), max(0, kutu[1] - pay), min(gri.width, kutu[2] + pay),
                    min(gri.height, kutu[3] + pay)))
    if kesim:  # kesikli çerçeve: makasla kesme kılavuzu
        d = ImageDraw.Draw(gri)
        w, h = gri.size
        for x in range(0, w, 10):
            d.line((x, 0, min(x + 5, w - 1), 0), fill=0, width=2)
            d.line((x, h - 1, min(x + 5, w - 1), h - 1), fill=0, width=2)
        for y in range(0, h, 10):
            d.line((0, y, 0, min(y + 5, h - 1)), fill=0, width=2)
            d.line((w - 1, y, w - 1, min(y + 5, h - 1)), fill=0, width=2)
    hucre = (GENISLIK - 4 * (sutun - 1)) // sutun
    if gri.width > hucre:  # noktalı desen bulanmasın diye en yakın komşu
        gri = gri.resize((hucre, max(1, round(gri.height * hucre / gri.width))),
                         Image.NEAREST if mod == "1" else Image.LANCZOS)
    tuval = Image.new("L", (GENISLIK, gri.height + 4), 255)
    bosluk = (GENISLIK - sutun * gri.width) // (sutun + 1)
    for i in range(sutun):
        tuval.paste(gri, (bosluk + i * (gri.width + bosluk), 2))
    return tuval.convert("1") if mod == "1" else tuval


def kalibrasyon(resim=None, yogunluk=100):
    """Ayar şeridi: noktalı modda üç açıklık (100/128/156) yan yana ve 16 basamaklı ton merdiveni.
    Koyuluk baskı başına tek değer olduğundan şeride yazılır; farklı koyulukları ayrı şeritlerle karşılaştır."""
    f = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 18)
    w = (GENISLIK - 8) // 3
    parcalar = []
    if resim is not None:
        for esik in (100, 128, 156):
            gri = gri_hazirla(resim, esik, fotograf=True)
            gri = gri.resize((w, max(1, round(gri.height * w / gri.width))), Image.LANCZOS)
            parcalar.append((esik, noktala(gri).convert("L")))
    h = max((p.height for _, p in parcalar), default=0)
    img = Image.new("L", (GENISLIK, h + 150), 255)
    d = ImageDraw.Draw(img)
    d.text((GENISLIK / 2, 14), f"KOYULUK %{yogunluk}", font=f, fill=0, anchor="mm")
    for i, (esik, p) in enumerate(parcalar):
        x = 4 + i * (w + 2)
        img.paste(p, (x, 30))
        d.text((x + w / 2, 40 + h), f"açıklık {esik}", font=f, fill=0, anchor="mt")
    y = 70 + h
    merdiven = Image.new("L", (GENISLIK, 50), 255)
    for i in range(16):  # 0 beyaz .. 15 siyah, noktalı
        ImageDraw.Draw(merdiven).rectangle((i * 24, 0, i * 24 + 23, 49), fill=255 - i * 17)
    img.paste(noktala(merdiven).convert("L"), (0, y))
    for i in range(0, 16, 3):
        d.text((i * 24 + 12, y + 56), str(i), font=f, fill=0, anchor="mt")
    return img.crop((0, 0, GENISLIK, y + 80)).convert("1")


def gri_ton(resim, esik=128):
    """Görsel -> yazıcının 16 ton gri modunda basacağı haliyle 384 px "L" görsel (fotoğraflar için en iyisi).
    16 seviyeye düz yuvarlama yüzde yamalar yapar; seviyeler arası Floyd-Steinberg ile yumuşatılır."""
    gri = gri_hazirla(resim, esik, fotograf=True).point(GRI_EGRISI)
    palet = Image.new("P", (1, 1))
    palet.putpalette([c for i in range(16) for c in (i * 17,) * 3] * 16)
    return gri.convert("RGB").quantize(palette=palet, dither=Image.Dither.FLOYDSTEINBERG).convert("L")


def gri_satirlari(gri16):
    """16 tonlu 384 px görsel -> (4 bit/piksel veri, satır sayısı). Baytta çift piksel üst 4 bitte;
    0 beyaz, 15 siyah (kaynak: MaikelChan/CatPrinterBLE ImageProcessor.cs)."""
    piksel = gri16.load()
    veri = bytearray()
    for y in range(gri16.height):
        for x in range(0, GENISLIK, 2):
            veri.append(((255 - piksel[x, y]) >> 4) << 4 | ((255 - piksel[x + 1, y]) >> 4))
    satir = max(gri16.height, EN_AZ_SATIR)
    return bytes(veri) + bytes((satir - gri16.height) * (GENISLIK // 2)), satir


def satirlara(resim, titrek=False, esik=128):
    """Görsel -> 384 px genişlikte satır baytları (1 = siyah, her baytta ilk piksel en düşük bit)."""
    return bit_satirlari(tek_renk(resim, titrek, esik))


def bit_satirlari(tek):
    """Siyah-beyaz 384 px görsel -> (yazıcı verisi, satır sayısı); en az 90 satıra tamamlanır."""
    piksel = tek.load()
    veri = bytearray()
    for y in range(tek.height):
        for bayt in range(GENISLIK // 8):
            deger = 0
            for bit in range(8):
                if piksel[bayt * 8 + bit, y] == 0:  # siyah
                    deger |= 1 << bit
            veri.append(deger)
    satir = max(tek.height, EN_AZ_SATIR)
    return bytes(veri) + bytes((satir - tek.height) * (GENISLIK // 8)), satir


def metin_resmi(metin, boyut=28, kalin=True, hizalama="sol"):
    """Metni 384 px genişliğe sığacak şekilde satırlara böler (yazılan satır sonları korunur)."""
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf" if kalin else r"C:\Windows\Fonts\segoeui.ttf", boyut)
    satirlar = []
    for paragraf in metin.splitlines() or [""]:
        son = ""
        for kelime in paragraf.split():
            aday = f"{son} {kelime}".strip()
            if font.getlength(aday) <= GENISLIK - 8 or not son:
                son = aday
            else:
                satirlar.append(son)
                son = kelime
        satirlar.append(son)
    aralik = round(boyut * 1.3)
    resim = Image.new("L", (GENISLIK, aralik * len(satirlar) + 16), 255)
    d = ImageDraw.Draw(resim)
    for i, s in enumerate(satirlar):
        g = font.getlength(s)
        x = {"orta": (GENISLIK - g) / 2, "sag": GENISLIK - 4 - g}.get(hizalama, 4)
        d.text((x, 8 + aralik * i), s, font=font, fill=0)
    return resim


def uuid(kisa):
    return f"0000{kisa}-0000-1000-8000-00805f9b34fb"


class Yazici:
    """bleak (Bluetooth LE) ile MXW01 bağlantısı. Yazıcı yayında AF30, bağlanınca AE30 servisini gösterir.
    Not: bağlantı Bluetooth adaptörü USB 3.0 portundayken parazitten kurulamıyordu; USB 2.0 portta çalışıyor."""

    def __init__(self):
        self.bildirimler = asyncio.Queue()
        self.istemci = None
        self.bilgi = None  # son durum: pil, sıcaklık, işlem, sorunlar

    async def bul(self, sure=20):
        from bleak import BleakScanner
        cihaz = await BleakScanner.find_device_by_filter(
            lambda d, r: (d.name or "").upper().startswith("MXW")
            or bool({u[4:8] for u in r.service_uuids} & set(SERVISLER)), timeout=sure)
        if cihaz is None:
            raise SystemExit("Yazıcı bulunamadı: açık mı, telefondaki Fun Print'e bağlı mı?")
        return cihaz

    async def baglan(self, cihaz):
        from bleak import BleakClient
        self.istemci = BleakClient(cihaz, timeout=30)
        await self.istemci.connect()
        await self.istemci.start_notify(uuid(BILDIRIM), lambda _, v: self.bildirimler.put_nowait(bytes(v)))

    async def _yaz(self, kisa_uuid, veri):
        await self.istemci.write_gatt_char(uuid(kisa_uuid), bytes(veri), response=False)

    async def bekle(self, kod, sure=5):
        """Belirli komutun bildirimi gelene kadar bekler; yükünü döndürür."""
        dongu = asyncio.get_running_loop()
        bitis = dongu.time() + sure
        while True:
            kalan = bitis - dongu.time()
            if kalan <= 0:
                raise TimeoutError(f"Yazıcı yanıt vermedi (0x{kod:02X})")
            mesaj = await asyncio.wait_for(self.bildirimler.get(), kalan)
            if len(mesaj) >= 6 and mesaj[:2] == b"\x22\x21" and mesaj[2] == kod:
                return mesaj[6:6 + (mesaj[4] | mesaj[5] << 8)]

    async def durum(self):
        await self._yaz(KONTROL, komut(DURUM, [0]))
        yuk = await self.bekle(DURUM)
        sorunsuz = len(yuk) < 8 or yuk[6] == 0
        sorunlar = [] if sorunsuz else [HATALAR.get(yuk[7], f"hata 0x{yuk[7]:02X}")]
        hata = not sorunsuz and sorunlar != ["pil zayıf"]
        self.bilgi = {"pil": yuk[3] if len(yuk) > 3 else None, "sicaklik": yuk[4] if len(yuk) > 4 else None,
                      "islem": ISLEMLER.get(yuk[0], "?") if yuk else "?", "sorunlar": sorunlar}
        return sorunlar, hata, yuk

    async def bas(self, veri, satir, yogunluk, ilerleme=None, gri=False):
        """gri: veri 4 bit/piksel (gri_satirlari), yazıcı 16 tonla basar; değilse 1 bit/piksel.
        ilerleme: isteğe bağlı fonksiyon, veri gönderimi sırasında 0-1 arası oranla çağrılır."""
        satir_bayt = GENISLIK // 2 if gri else GENISLIK // 8
        await self._yaz(KONTROL, komut(YOGUNLUK, [yogunluk]))
        await asyncio.sleep(0.05)
        sorunlar, hata, _ = await self.durum()
        if hata or (set(sorunlar) - {"pil zayıf"}):
            raise SystemExit("Yazıcı basmaya hazır değil: " + (", ".join(sorunlar) or "bilinmeyen hata"))
        await self._yaz(KONTROL, komut(BASKI, [satir & 0xFF, satir >> 8, 0x30, 2 if gri else 0]))  # 2: gri ton
        onay = await self.bekle(BASKI)
        if not onay or onay[0] != 0:
            raise SystemExit(f"Yazıcı baskı isteğini reddetti: {onay.hex()}")
        for i in range(0, len(veri), satir_bayt):
            await self._yaz(VERI, veri[i:i + satir_bayt])
            await asyncio.sleep(0.015)
            if ilerleme and i % (satir_bayt * 20) == 0:
                ilerleme(i / len(veri))
        await self._yaz(KONTROL, komut(VERI_BITTI, [0]))
        await self.bekle(BASKI_BITTI, sure=20 + satir / 20)

    async def kapat(self):
        if self.istemci and self.istemci.is_connected:
            await self.istemci.disconnect()


async def calistir(arg):
    isler = []
    if arg.metin:
        isler.append(("metin", satirlara(metin_resmi(arg.metin)), False))
    for yol in arg.dosyalar:
        if yol.lower().endswith(".txt"):
            with open(yol, encoding="utf-8-sig", errors="replace") as f:
                isler.append((yol, satirlara(metin_resmi(f.read())), False))
            continue
        with Image.open(yol) as resim:
            isler.append((yol, gri_satirlari(gri_ton(resim)) if arg.gri else satirlara(resim, arg.titrek), arg.gri))
    yazici = Yazici()
    cihaz = await yazici.bul()
    print(f"Bulundu: {cihaz.name} ({cihaz.address}), bağlanılıyor...", flush=True)
    try:
        await yazici.baglan(cihaz)
        sorunlar, hata, ham = await yazici.durum()
        print(f"Durum: {', '.join(sorunlar) or ('hata' if hata else 'hazır')}", flush=True)
        if arg.durum:
            print("Ham durum:", ham.hex())
            return
        for ad_, (veri, satir), gri in isler:
            print(f"Basılıyor: {ad_} ({satir} satır = {satir / 8:.0f} mm{', gri ton' if gri else ''})...", flush=True)
            await yazici.bas(veri, satir, min(max(arg.yogunluk, 0), 100), gri=gri)
            print("  tamam", flush=True)
    finally:
        await yazici.kapat()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="MXW01 / C9 termal yazıcıya Bluetooth ile baskı")
    p.add_argument("dosyalar", nargs="*", help="basılacak görseller (png, jpg, bmp...)")
    p.add_argument("--metin", help="dosya yerine bu metni bas")
    p.add_argument("--yogunluk", type=int, default=93, help="koyuluk 0-100 (varsayılan 93 = uygulamanın 0x5D'si)")
    p.add_argument("--titrek", action="store_true", help="fotoğraflar için gri tonları nokta desenine çevir")
    p.add_argument("--gri", action="store_true", help="fotoğraflar için yazıcının 16 tonlu gri modu (en iyisi)")
    p.add_argument("--durum", action="store_true", help="yalnız yazıcı durumunu göster")
    p.add_argument("--bekle", action="store_true", help="bitince pencere 6 sn açık kalsın (Gönder menüsü için)")
    arg = p.parse_args()
    if not (arg.dosyalar or arg.metin or arg.durum):
        p.error("basılacak dosya, --metin ya da --durum ver")
    try:
        asyncio.run(calistir(arg))
    except (SystemExit, Exception) as e:
        print("HATA:", e if str(e) else type(e).__name__)
        if arg.bekle:
            time.sleep(6)
        raise SystemExit(1)
    if arg.bekle:
        time.sleep(3)


if __name__ == "__main__":
    main()
