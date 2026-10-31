"""C9 Yazıcı: MXW01 (Fun Print) termal yazıcı için masaüstü uygulaması.

Görsel (dosya ya da panodan), metin ve hazır şablonlar; yazıcının basacağı haliyle önizleme, koyuluk, kopya.
Bluetooth işleri ayrı bir asyncio döngüsünde çalışır, pencere donmaz. Baskı kodu: c9_yazdir.py.
Çalıştır: python c9_uygulama.py [görsel]
"""
import asyncio
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageGrab, ImageOps, ImageTk

import c9_sablonlar as sb
import c9_yazdir as c9

MM = 8  # 203 dpi: 1 mm = 8 nokta


class Uygulama:
    def __init__(self, kok, ilk_dosya=None):
        self.kok = kok
        self.kaynak = None         # görsel sekmesindeki özgün resim
        self.son = None            # basılacak siyah-beyaz 384 px resim
        self.mesgul = False
        self.dongu = asyncio.new_event_loop()  # Bluetooth için arka plan döngüsü
        threading.Thread(target=self.dongu.run_forever, daemon=True).start()
        # Tkinter iş parçacığı güvenli değil: arka plan işleri arayüz güncellemelerini bu kuyruğa bırakır
        self.olaylar = queue.SimpleQueue()

        kok.title("C9 Yazıcı")
        ikon = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "c9.ico")
        if os.path.exists(ikon):  # exe'de ikon PyInstaller'ın açtığı geçici klasörde
            kok.iconbitmap(ikon)
        kok.geometry("1180x880")
        kok.minsize(1000, 700)
        stil = ttk.Style()
        stil.configure("Buyuk.TButton", font=("Segoe UI", 12, "bold"), padding=8)

        ana = ttk.Frame(kok, padding=10)
        ana.pack(fill="both", expand=True)
        ana.columnconfigure(0, weight=1)
        ana.rowconfigure(0, weight=1)

        # sol: önizleme (gerçek boy, kaydırılabilir)
        sol = ttk.LabelFrame(ana, text="Önizleme (kağıtta çıkacağı gibi)", padding=6)
        sol.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        sol.rowconfigure(0, weight=1)
        sol.columnconfigure(0, weight=1)
        self.tuval = tk.Canvas(sol, width=c9.GENISLIK + 20, background="#d9d9de", highlightthickness=0)
        kaydir = ttk.Scrollbar(sol, orient="vertical", command=self.tuval.yview)
        self.tuval.configure(yscrollcommand=kaydir.set)
        self.tuval.grid(row=0, column=0, sticky="nsew")
        kaydir.grid(row=0, column=1, sticky="ns")
        self.tuval.bind("<MouseWheel>", lambda e: self.tuval.yview_scroll(-e.delta // 120, "units"))
        self.kaydirma = {}  # şablon adı -> yazının fareyle kaydırılması (px)
        self.tuval.bind("<ButtonPress-1>", self._surukle_bas)
        self.tuval.bind("<B1-Motion>", self._surukle_hareket)
        self.boy_yazisi = ttk.Label(sol, text="")
        self.boy_yazisi.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # sağ: sekmeler ve baskı ayarları
        sag = ttk.Frame(ana)
        sag.grid(row=0, column=1, sticky="ns")
        self.sekmeler = ttk.Notebook(sag)
        self.sekmeler.pack(fill="x")
        self.sekmeler.add(self._gorsel_sekmesi(), text="Görsel")
        self.sekmeler.add(self._metin_sekmesi(), text="Metin")
        self.sekmeler.add(self._sablon_sekmesi(), text="Şablonlar")
        self.sekmeler.bind("<<NotebookTabChanged>>", lambda e: self.onizle())

        ayar = ttk.LabelFrame(sag, text="Baskı", padding=8)
        ayar.pack(fill="x", pady=(10, 0))
        ttk.Label(ayar, text="Koyuluk").grid(row=0, column=0, sticky="w")
        self.yogunluk = tk.IntVar(value=100)  # denendi: fotoğraf %100 koyulukta en iyi
        ttk.Scale(ayar, from_=20, to=100, variable=self.yogunluk, length=180).grid(row=0, column=1, padx=6)
        ttk.Label(ayar, textvariable=self.yogunluk, width=3).grid(row=0, column=2)
        ttk.Label(ayar, text="Kopya").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.kopya = tk.IntVar(value=1)
        ttk.Spinbox(ayar, from_=1, to=20, textvariable=self.kopya, width=5).grid(row=1, column=1, sticky="w", padx=6,
                                                                                  pady=(6, 0))
        ttk.Label(ayar, text="Yan yana").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.sutun = tk.IntVar(value=1)
        ttk.Spinbox(ayar, from_=1, to=4, textvariable=self.sutun, width=5, command=self.onizle).grid(
            row=2, column=1, sticky="w", padx=6, pady=(6, 0))
        self.yazici_durumu = ttk.Label(ayar, text="Yazıcı: henüz bağlanılmadı", foreground="#666")
        self.yazici_durumu.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.kesim = tk.BooleanVar(value=False)
        ttk.Checkbutton(ayar, text="Kesim çizgisi", variable=self.kesim, command=self.onizle).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.yazdir_dugmesi = ttk.Button(sag, text="Yazdır  (Ctrl+P)", style="Buyuk.TButton", command=self.yazdir)
        self.yazdir_dugmesi.pack(fill="x", pady=(10, 4))
        ttk.Button(sag, text="Yazıcı durumunu sına", command=self.durum).pack(fill="x")
        self.ilerleme = ttk.Progressbar(sag, maximum=1.0)
        self.ilerleme.pack(fill="x", pady=(10, 2))
        self.durum_yazisi = ttk.Label(sag, text="Hazır. Yazıcıyı aç; telefondaki Fun Print bağlı olmasın.",
                                      wraplength=300, justify="left")
        self.durum_yazisi.pack(fill="x")

        kok.bind("<Control-v>", lambda e: self.yapistir())
        kok.bind("<Control-o>", lambda e: self.dosya_ac())
        kok.bind("<Control-p>", lambda e: self.yazdir())
        if ilk_dosya:
            self.dosya_yukle(ilk_dosya)
        self.onizle()
        self._olaylari_isle()

    def ui(self, is_):
        """Başka iş parçacığından arayüzde iş yaptırır (ana iş parçacığında çalışır)."""
        self.olaylar.put(is_)

    def _olaylari_isle(self):
        while True:
            try:
                self.olaylar.get_nowait()()
            except queue.Empty:
                break
        self.kok.after(50, self._olaylari_isle)

    # ---------- sekmeler ----------

    def _gorsel_sekmesi(self):
        f = ttk.Frame(self.sekmeler, padding=8)
        ttk.Button(f, text="Dosya aç…  (Ctrl+O)", command=self.dosya_ac).pack(fill="x")
        ttk.Button(f, text="Panodan yapıştır  (Ctrl+V)", command=self.yapistir).pack(fill="x", pady=4)
        ttk.Button(f, text="90° döndür", command=self.dondur).pack(fill="x")
        ttk.Button(f, text="Ayar şeridi (açıklık karşılaştırma)", command=self.kalibrasyon).pack(fill="x", pady=(4, 0))
        self.foto_mod = tk.StringVar(value="keskin")
        for i, (deger, ad) in enumerate((("keskin", "Keskin (yazı, logo, ekran görüntüsü)"),
                                         ("gri", "Fotoğraf – gri ton"),
                                         ("noktali", "Fotoğraf – noktalı (en iyisi)"))):
            ttk.Radiobutton(f, text=ad, variable=self.foto_mod, value=deger,
                            command=self.onizle).pack(anchor="w", pady=(10 if i == 0 else 0, 0))
        ttk.Label(f, text="Açıklık").pack(anchor="w", pady=(8, 0))
        self.esik = tk.IntVar(value=128)
        ttk.Scale(f, from_=60, to=200, variable=self.esik, command=lambda _: self.onizle()).pack(fill="x")
        ttk.Label(f, text="sola: daha açık · sağa: daha koyu", foreground="#666").pack(anchor="w")
        return f

    def _metin_sekmesi(self):
        f = ttk.Frame(self.sekmeler, padding=8)
        self.metin = tk.Text(f, width=34, height=8, wrap="word", font=("Segoe UI", 10))
        self.metin.pack(fill="x")
        self.metin.insert("1.0", "Merhaba!")
        self.metin.bind("<KeyRelease>", lambda e: self.onizle())
        satir = ttk.Frame(f)
        satir.pack(fill="x", pady=(6, 0))
        ttk.Label(satir, text="Boyut").pack(side="left")
        self.boyut = tk.IntVar(value=32)
        ttk.Spinbox(satir, from_=12, to=120, textvariable=self.boyut, width=5,
                    command=self.onizle).pack(side="left", padx=4)
        self.kalin = tk.BooleanVar(value=True)
        ttk.Checkbutton(satir, text="Kalın", variable=self.kalin, command=self.onizle).pack(side="left", padx=8)
        self.hizalama = tk.StringVar(value="sol")
        hiza = ttk.Frame(f)
        hiza.pack(fill="x", pady=(6, 0))
        for deger, ad in (("sol", "Sola"), ("orta", "Ortaya"), ("sag", "Sağa")):
            ttk.Radiobutton(hiza, text=ad, variable=self.hizalama, value=deger,
                            command=self.onizle).pack(side="left", padx=(0, 8))
        return f

    def _sablon_sekmesi(self):
        """Üstte tüm şablonların küçük resimli galerisi (tıkla seç), altta seçilenin alanları."""
        f = ttk.Frame(self.sekmeler, padding=8)
        self.sablon_adi = tk.StringVar(value=next(iter(sb.SABLONLAR)))
        galeri = ttk.Frame(f)
        galeri.pack(side="left", fill="y")
        kategoriler = list(dict.fromkeys(self._kategori(ad) for ad in sb.SABLONLAR))
        self.kategori = tk.StringVar(value="Tümü")
        ust = ttk.Frame(galeri)
        ust.pack(fill="x", pady=(0, 4))
        self.kategori_secim = ttk.Combobox(ust, textvariable=self.kategori, values=["Tümü"] + kategoriler,
                                           state="readonly")
        self.kategori_secim.pack(side="left", fill="x", expand=True)
        self.kategori_secim.bind("<<ComboboxSelected>>", lambda e: self._galeri_doldur())
        ttk.Button(ust, text="Sayfa ekle…", command=self.sayfa_ekle).pack(side="right", padx=(4, 0))
        self._sutun, self._hw, self._hh = 4, 82, 96  # hücre: 74×70 küçük resim + ad
        self.galeri = tk.Canvas(galeri, width=self._sutun * self._hw + 2, height=5 * self._hh + 50,
                                background="#ececf0", highlightthickness=0)
        kaydir = ttk.Scrollbar(galeri, orient="vertical", command=self.galeri.yview)
        self.galeri.configure(yscrollcommand=kaydir.set)
        self.galeri.pack(side="left", fill="y")
        kaydir.pack(side="right", fill="y")
        self.galeri.bind("<MouseWheel>", lambda e: self.galeri.yview_scroll(-e.delta // 120, "units"))
        self._kucukler, self._hucreler = {}, {}
        self._galeri_doldur()
        form = ttk.Frame(f)
        form.pack(side="left", fill="both", expand=True, padx=(10, 0))
        kayit = ttk.Frame(form)  # kayıtlı tasarımlar: doldurulmuş şablonu adıyla sakla, tek tıkla geri getir
        kayit.pack(fill="x", pady=(0, 6))
        self.tasarim = tk.StringVar()
        self.tasarim_secim = ttk.Combobox(kayit, textvariable=self.tasarim, state="readonly",
                                          values=sorted(self._tasarimlar()))
        self.tasarim_secim.pack(side="left", fill="x", expand=True)
        self.tasarim_secim.set("Kayıtlı tasarımlar…")
        self.tasarim_secim.bind("<<ComboboxSelected>>", lambda e: self.tasarim_yukle(self.tasarim.get()))
        ttk.Button(kayit, text="Kaydet…", command=self.tasarim_kaydet).pack(side="left", padx=(4, 0))
        ttk.Button(kayit, text="Sil", width=4, command=self.tasarim_sil).pack(side="left", padx=(4, 0))
        self.sablon_baslik = ttk.Label(form, text="", font=("Segoe UI", 10, "bold"))
        self.sablon_baslik.pack(anchor="w")
        self.sablon_alanlari = ttk.Frame(form)
        self.sablon_alanlari.pack(fill="x")
        self._sablon_sec(self.sablon_adi.get())
        return f

    @staticmethod
    def _kategori(ad):
        return ad.rsplit(": ", 1)[0] if ": " in ad else "Listeler ve etiketler"

    def _galeri_doldur(self):
        """Seçili kategorideki şablonların küçük resimleri; resimler bir kez çizilip saklanır."""
        self.galeri.delete("all")
        self._hucreler = {}
        sutun, hw, hh = self._sutun, self._hw, self._hh
        adlar = [ad for ad in sb.SABLONLAR if self.kategori.get() in ("Tümü", self._kategori(ad))]
        for i, ad in enumerate(adlar):
            x, y = (i % sutun) * hw + 2, (i // sutun) * hh + 2
            if ad not in self._kucukler:
                self._kucukler[ad] = ImageTk.PhotoImage(ImageOps.contain(sb.ciz(ad).convert("L"), (hw - 8, hh - 26)))
            cerceve = self.galeri.create_rectangle(x, y, x + hw - 4, y + hh - 4, fill="white", outline="#c8c8d0",
                                                   width=2)
            self.galeri.create_image(x + (hw - 4) / 2, y + 3, anchor="n", image=self._kucukler[ad])
            kisa = ad.rsplit(": ", 1)[-1]
            self.galeri.create_text(x + (hw - 4) / 2, y + hh - 14, text=kisa if len(kisa) <= 13 else kisa[:12] + "…",
                                    font=("Segoe UI", 7))
            self._hucreler[ad] = cerceve
            for oge in self.galeri.find_overlapping(x, y, x + hw - 4, y + hh - 4):
                self.galeri.tag_bind(oge, "<Button-1>", lambda e, ad=ad: self._sablon_sec(ad))
        self.galeri.configure(scrollregion=(0, 0, sutun * hw, ((len(adlar) - 1) // sutun + 1) * hh + 4))
        self.galeri.yview_moveto(0)
        if hasattr(self, "sablon_baslik"):
            self._sablon_sec(self.sablon_adi.get(), formu_kur=False)

    def _sablon_sec(self, ad, formu_kur=True):
        for a, oge in self._hucreler.items():
            self.galeri.itemconfigure(oge, outline="#2f6fd6" if a == ad else "#c8c8d0", width=3 if a == ad else 2)
        if formu_kur:
            self.sablon_adi.set(ad)
            self.sablon_baslik.config(text=ad)
            self._sablon_formu()

    def sayfa_ekle(self):
        """Kendi sticker sayfanı (ör. Pinterest görseli) tek tek stickerlara böler ve galeriye ekler."""
        yol = filedialog.askopenfilename(filetypes=[("Görseller", "*.png *.jpg *.jpeg *.bmp *.webp")])
        if not yol:
            return
        ad = simpledialog.askstring("C9 Yazıcı", "Sayfanın adı:", parent=self.kok,
                                    initialvalue=os.path.splitext(os.path.basename(yol))[0])
        if not ad or not ad.strip():
            return
        try:
            adlar = [a for a in sb.sayfa_ekle(yol, ad.strip()) if a]
        except Exception as e:
            messagebox.showerror("C9 Yazıcı", f"Sayfa eklenemedi: {e}")
            return
        if not adlar:
            self.durum_yaz("Sayfada sticker bulunamadı.")
            return
        for a in adlar:
            self._kucukler.pop(a, None)
        self.kategori_secim["values"] = ["Tümü"] + list(dict.fromkeys(self._kategori(a) for a in sb.SABLONLAR))
        self.kategori.set(self._kategori(adlar[0]))
        self._galeri_doldur()
        self._sablon_sec(adlar[0])
        self.durum_yaz(f"{len(adlar)} sticker eklendi: {self.kategori.get()}")

    def _foto_ekle(self, g):
        yollar = filedialog.askopenfilenames(filetypes=[("Görseller", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")])
        if yollar:
            onceki = g.get("1.0", "end-1c").strip()
            g.delete("1.0", "end")
            g.insert("1.0", "\n".join(([onceki] if onceki else []) + list(yollar)))
            self.onizle()

    def _sablon_formu(self):
        """Seçilen şablonun alanları için form; her tuşta önizleme güncellenir."""
        for w in self.sablon_alanlari.winfo_children():
            w.destroy()
        self.sablon_girdileri = {}
        for anahtar, etiket, varsayilan, tur in sb.SABLONLAR[self.sablon_adi.get()][0]:
            ttk.Label(self.sablon_alanlari, text=etiket).pack(anchor="w", pady=(4, 0))
            if tur in ("cok", "dosyalar"):
                g = tk.Text(self.sablon_alanlari, width=34, height=3 if tur == "dosyalar" else 4,
                            wrap="none" if tur == "dosyalar" else "word", font=("Segoe UI", 10))
                g.insert("1.0", varsayilan)
            elif tur.startswith("secim:"):  # "secim:a,b,c" açılır liste
                g = ttk.Combobox(self.sablon_alanlari, values=tur[6:].split(","), state="readonly", width=34)
                g.set(varsayilan)
                g.bind("<<ComboboxSelected>>", lambda e: self.onizle())
            else:
                g = ttk.Entry(self.sablon_alanlari, width=36)
                g.insert(0, varsayilan)
            g.pack(fill="x")
            if tur == "dosyalar":
                ttk.Button(self.sablon_alanlari, text="Fotoğraf ekle…",
                           command=lambda g=g: self._foto_ekle(g)).pack(anchor="w", pady=(2, 0))
            g.bind("<KeyRelease>", lambda e: self.onizle())
            self.sablon_girdileri[anahtar] = g
        # toplu baskı: seçilen alan listedeki her satırla doldurulup ayrı etiket olarak alt alta basılır
        yazi_alanlari = [(a, e) for a, e, _, t in sb.SABLONLAR[self.sablon_adi.get()][0] if t in ("satir", "cok")]
        self.toplu_alan = None
        if yazi_alanlari:
            kutu = ttk.LabelFrame(self.sablon_alanlari, text="Toplu baskı (her satıra ayrı etiket)", padding=4)
            kutu.pack(fill="x", pady=(8, 0))
            etiketler = {e: a for a, e in yazi_alanlari}
            secim = ttk.Combobox(kutu, values=list(etiketler), state="readonly")
            secim.set(yazi_alanlari[0][1])
            secim.pack(fill="x")
            secim.bind("<<ComboboxSelected>>", lambda e: self.onizle())
            self.toplu_liste = tk.Text(kutu, width=34, height=3, wrap="none", font=("Segoe UI", 10))
            self.toplu_liste.pack(fill="x", pady=(4, 0))
            self.toplu_liste.bind("<KeyRelease>", lambda e: self.onizle())
            self.toplu_alan = lambda: etiketler[secim.get()]
        if hasattr(self, "tuval"):
            self.onizle()

    def _sablon_degerleri(self):
        dx, dy = self.kaydirma.get(self.sablon_adi.get(), (0, 0))
        return {**{a: (g.get("1.0", "end-1c") if isinstance(g, tk.Text) else g.get())
                   for a, g in self.sablon_girdileri.items()}, "_dx": dx, "_dy": dy}

    # ---------- kayıtlı tasarımlar (%APPDATA%\C9Yazici\tasarimlar.json) ----------

    @staticmethod
    def _tasarim_dosyasi():
        return os.path.join(sb.KULLANICI, "tasarimlar.json")

    def _tasarimlar(self):
        try:
            with open(self._tasarim_dosyasi(), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _tasarimlari_yaz(self, tasarimlar):
        os.makedirs(sb.KULLANICI, exist_ok=True)
        with open(self._tasarim_dosyasi(), "w", encoding="utf-8") as f:
            json.dump(tasarimlar, f, ensure_ascii=False, indent=1)
        self.tasarim_secim["values"] = sorted(tasarimlar)

    def tasarim_kaydet(self):
        ad = simpledialog.askstring("C9 Yazıcı", "Tasarımın adı:", parent=self.kok)
        if not ad or not ad.strip():
            return
        tasarimlar = self._tasarimlar()
        degerler = self._sablon_degerleri()
        tasarimlar[ad.strip()] = {"sablon": self.sablon_adi.get(),
                                  "kaydirma": [degerler.pop("_dx"), degerler.pop("_dy")], "degerler": degerler}
        self._tasarimlari_yaz(tasarimlar)
        self.tasarim_secim.set(ad.strip())
        self.durum_yaz(f"Kaydedildi: {ad.strip()}")

    def tasarim_yukle(self, ad):
        t = self._tasarimlar().get(ad)
        if not t or t["sablon"] not in sb.SABLONLAR:
            self.durum_yaz("Tasarımın şablonu bulunamadı (silinmiş sayfa olabilir).")
            return
        self.kategori.set("Tümü")
        self._galeri_doldur()
        self._sablon_sec(t["sablon"])
        self.kaydirma[t["sablon"]] = tuple(t["kaydirma"])
        for anahtar, deger in t["degerler"].items():
            g = self.sablon_girdileri.get(anahtar)
            if isinstance(g, tk.Text):
                g.delete("1.0", "end")
                g.insert("1.0", deger)
            elif isinstance(g, ttk.Combobox):
                g.set(deger)
            elif g is not None:
                g.delete(0, "end")
                g.insert(0, deger)
        self.onizle()
        self.durum_yaz(f"Yüklendi: {ad}")

    def tasarim_sil(self):
        tasarimlar = self._tasarimlar()
        ad = self.tasarim.get()
        if ad in tasarimlar and messagebox.askyesno("C9 Yazıcı", f"'{ad}' silinsin mi?"):
            del tasarimlar[ad]
            self._tasarimlari_yaz(tasarimlar)
            self.tasarim_secim.set("Kayıtlı tasarımlar…")

    def _surukle_bas(self, e):
        self._surukle_son = (e.x, e.y)

    def _surukle_hareket(self, e):
        """Şablonlar sekmesinde önizlemedeki yazıyı fareyle taşır (çerçeveli stickerlar)."""
        if self.sekmeler.index("current") != 2:
            return
        ad = self.sablon_adi.get()
        x, y = self.kaydirma.get(ad, (0, 0))
        self.kaydirma[ad] = (x + e.x - self._surukle_son[0], y + e.y - self._surukle_son[1])
        self._surukle_son = (e.x, e.y)
        self.onizle()

    # ---------- içerik ----------

    def dosya_ac(self):
        yol = filedialog.askopenfilename(filetypes=[("Görseller", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                                                    ("Tüm dosyalar", "*.*")])
        if yol:
            self.dosya_yukle(yol)

    def dosya_yukle(self, yol):
        try:
            with Image.open(yol) as r:
                self.kaynak = r.copy()
        except Exception as e:
            messagebox.showerror("C9 Yazıcı", f"Görsel açılamadı:\n{e}")
            return
        self.sekmeler.select(0)
        self.durum_yaz(f"Yüklendi: {os.path.basename(yol)}")
        self.onizle()

    def yapistir(self):
        pano = ImageGrab.grabclipboard()
        if isinstance(pano, list) and pano:  # panoda dosya
            return self.dosya_yukle(pano[0])
        if isinstance(pano, Image.Image):
            self.kaynak = pano
            self.sekmeler.select(0)
            self.durum_yaz("Panodaki görsel yapıştırıldı.")
            return self.onizle()
        if self.sekmeler.index("current") in (1, 2):  # metin ve şablon alanlarında normal yapıştırma
            return None
        self.durum_yaz("Panoda görsel yok (Win+Shift+S ile ekran alıntısı alabilirsin).")
        return "break"

    def kalibrasyon(self):
        """Yüklü fotoğrafla (yoksa yalnız ton merdiveni) ayar şeridi; keskin modda basılır (zaten noktalı)."""
        self.kaynak = c9.kalibrasyon(self.kaynak, int(self.yogunluk.get()))
        self.foto_mod.set("keskin")
        self.esik.set(128)
        self.durum_yaz("Ayar şeridi hazır: bas, en iyi görünen açıklığı seç. Koyuluğu değiştirip tekrar basabilirsin.")
        self.onizle()

    def dondur(self):
        if self.kaynak is not None:
            self.kaynak = self.kaynak.rotate(-90, expand=True)
            self.onizle()

    def onizle(self):
        sekme = self.sekmeler.index("current")
        try:
            if sekme == 0:
                kaynak = self.kaynak
                mod, esik = self.foto_mod.get(), self.esik.get()
                if kaynak is None:
                    self.son = None
                elif mod == "gri":  # "L" görsel: yazıcı 16 tonla basar
                    self.son = c9.gri_ton(kaynak, esik)
                else:
                    self.son = c9.tek_renk(kaynak, mod == "noktali", esik)
            elif sekme == 1:
                yazi = self.metin.get("1.0", "end").rstrip()
                self.son = c9.tek_renk(c9.metin_resmi(yazi, int(self.boyut.get()), self.kalin.get(),
                                                      self.hizalama.get())) if yazi else None
            else:
                liste = self.toplu_liste.get("1.0", "end").strip() if self.toplu_alan else ""
                if liste:
                    self.son = c9.tek_renk(sb.toplu(self.sablon_adi.get(), self._sablon_degerleri(),
                                                    self.toplu_alan(), liste))
                else:
                    self.son = c9.tek_renk(sb.ciz(self.sablon_adi.get(), self._sablon_degerleri()))
            if self.son is not None:
                self.son = c9.yerlestir(self.son, int(self.sutun.get()), self.kesim.get())
        except (tk.TclError, ValueError):
            return
        self.tuval.delete("all")
        if self.son is None:
            self.tuval.create_text(c9.GENISLIK // 2 + 10, 60, text="Basılacak bir şey yok", fill="#555")
            self.boy_yazisi.config(text="")
            return
        self._foto = ImageTk.PhotoImage(self.son.convert("L"))
        self.tuval.create_rectangle(8, 8, 12 + c9.GENISLIK, 12 + self.son.height, fill="white", outline="#aaa")
        self.tuval.create_image(10, 10, anchor="nw", image=self._foto)
        self.tuval.configure(scrollregion=(0, 0, c9.GENISLIK + 20, self.son.height + 20))
        boy = max(self.son.height, c9.EN_AZ_SATIR) / MM
        self.boy_yazisi.config(text=f"Kağıt: 48 × {boy:.0f} mm   (kopya başına)")

    # ---------- yazıcı ----------

    def durum_yaz(self, metin):
        self.durum_yazisi.config(text=metin)

    def _calistir(self, isim, eylem):
        """eylem(yazici) eşyordamını Bluetooth döngüsünde bağlanıp çalıştırır; bitince arayüzü günceller."""
        if self.mesgul:
            return
        self.mesgul = True
        self.yazdir_dugmesi.state(["disabled"])
        self.ilerleme["value"] = 0

        async def gorev():
            yazici = c9.Yazici()
            try:
                self.ui(lambda: self.durum_yaz("Yazıcı aranıyor…"))
                cihaz = await yazici.bul()
                self.ui(lambda: self.durum_yaz(f"{cihaz.name} bulundu, bağlanılıyor…"))
                await yazici.baglan(cihaz)
                return await eylem(yazici)
            finally:
                if yazici.bilgi:
                    self.ui(lambda b=yazici.bilgi: self._durum_goster(b))
                await yazici.kapat()

        def bitti(f):
            try:
                sonuc = f.result()
                metin = sonuc or f"{isim} tamamlandı."
            except BaseException as e:  # SystemExit: c9_yazdir'in anlaşılır hata iletileri
                metin = f"{isim} başarısız: {e or type(e).__name__}"
            self.ui(lambda: self._serbest(metin))

        asyncio.run_coroutine_threadsafe(gorev(), self.dongu).add_done_callback(bitti)

    def _durum_goster(self, b):
        """Baskı kutusunun altında yazıcının son bilinen durumu (her bağlantıda güncellenir)."""
        parca = [f"Pil %{b['pil']}" if b["pil"] is not None else None,
                 f"{b['sicaklik']}°C" if b["sicaklik"] is not None else None,
                 ", ".join(b["sorunlar"]) or b["islem"]]
        self.yazici_durumu.config(text="Yazıcı: " + " · ".join(p for p in parca if p),
                                  foreground="#b00020" if b["sorunlar"] else "#1b6e20")

    def _serbest(self, metin):
        self.mesgul = False
        self.yazdir_dugmesi.state(["!disabled"])
        self.durum_yaz(metin)

    def durum(self):
        async def eylem(yazici):
            sorunlar, hata, _ = await yazici.durum()
            b = yazici.bilgi
            return (f"Yazıcı: {', '.join(sorunlar) or ('hata bildiriyor' if hata else 'hazır')}"
                    f" · pil %{b['pil']} · {b['sicaklik']}°C")
        self._calistir("Durum", eylem)

    def yazdir(self):
        if self.son is None:
            self.durum_yaz("Önce basılacak bir şey seç.")
            return
        gri = self.son.mode == "L"
        veri, satir = c9.gri_satirlari(self.son) if gri else c9.bit_satirlari(self.son)
        kopya, yogunluk = max(1, int(self.kopya.get())), int(self.yogunluk.get())

        async def eylem(yazici):
            for k in range(kopya):
                self.ui(lambda k=k: self.durum_yaz(f"Basılıyor… ({k + 1}/{kopya})"))
                await yazici.bas(veri, satir, yogunluk, gri=gri, ilerleme=lambda o, k=k: self.ui(
                    lambda: self.ilerleme.configure(value=(k + o) / kopya)))
            self.ui(lambda: self.ilerleme.configure(value=1.0))
            return f"Basıldı: {kopya} kopya, {satir / MM:.0f} mm."
        self._calistir("Baskı", eylem)


def sina():
    """--sina: pencere açmadan yazıcıyı bulup durumunu okur, sonucu exe'nin yanına c9_sina.txt'ye yazar (teşhis)."""
    klasor = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

    async def is_():
        yazici = c9.Yazici()
        try:
            cihaz = await yazici.bul()
            await yazici.baglan(cihaz)
            sorunlar, hata, ham = await yazici.durum()
            return f"{cihaz.name} {cihaz.address}: {', '.join(sorunlar) or ('hata' if hata else 'hazır')} ({ham.hex()})"
        finally:
            await yazici.kapat()
    try:
        sonuc = asyncio.run(is_())
    except BaseException as e:
        sonuc = f"HATA: {e or type(e).__name__}"
    with open(os.path.join(klasor, "c9_sina.txt"), "w", encoding="utf-8") as f:
        f.write(sonuc + "\n")


def pano_hazirla():
    """Panodaki görsel (ekran alıntısı ya da kopyalanan dosya) veya metin -> (basılacak görsel, gri mi); yoksa None.
    Fotoğraf benzeri (ara tonu bol) görsel noktalı, ekran alıntısı/yazı keskin basılır."""
    pano = ImageGrab.grabclipboard()
    if isinstance(pano, list) and pano:
        with Image.open(pano[0]) as r:
            pano = r.copy()
    if isinstance(pano, Image.Image):
        kucuk = pano.convert("L").resize((64, 64))
        foto = sum(1 for v in kucuk.getdata() if 40 < v < 215) > 0.35 * 64 * 64
        return c9.tek_renk(pano, titrek=foto)
    kok = tk.Tk()
    kok.withdraw()
    try:
        yazi = kok.clipboard_get().strip()
    except tk.TclError:
        yazi = ""
    finally:
        kok.destroy()
    return c9.tek_renk(c9.metin_resmi(yazi, 32, True, "sol")) if yazi else None


def pano():
    """--pano: pencere açmadan panodakini basar (masaüstü kısayolunun tuşuyla, ör. Ctrl+Alt+P)."""
    def uyar(baslik, metin):
        k = tk.Tk()
        k.withdraw()
        (messagebox.showerror if baslik == "hata" else messagebox.showinfo)("C9 Yazıcı", metin)
        k.destroy()
    son = pano_hazirla()
    if son is None:
        return uyar("hata", "Panoda basılacak görsel ya da metin yok.")
    veri, satir = c9.bit_satirlari(son)

    async def is_():
        yazici = c9.Yazici()
        try:
            await yazici.baglan(await yazici.bul())
            await yazici.bas(veri, satir, 100)
        finally:
            await yazici.kapat()
    try:
        asyncio.run(is_())
    except BaseException as e:
        uyar("hata", f"Basılamadı: {e or type(e).__name__}")


def main():
    if "--sina" in sys.argv:
        return sina()
    if "--pano" in sys.argv:
        return pano()
    kok = tk.Tk()
    Uygulama(kok, sys.argv[1] if len(sys.argv) > 1 and os.path.exists(sys.argv[1]) else None)
    kok.mainloop()


if __name__ == "__main__":
    main()
