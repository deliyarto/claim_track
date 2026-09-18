# 🧾 Monitoring Tagihan — Kohort, Snapshot Comparison & Rekap Status

Versi ringkas dari tool Streamlit monitoring penerbitan tagihan — hanya berisi **3 tab**: Pelacakan Kohort, Snapshot Comparison, dan Rekap Status. Berbasis file export berkala dari sistem Allcare.

## Konsep: Monitoring Berbasis Snapshot

Akses ke sistem Allcare hanya memungkinkan **download file** `Daftar_Peserta_Layanan_DD_MM_YYYY.xlsx`. Setiap file adalah *foto keadaan sistem* pada tanggal download. Dengan menumpuk beberapa snapshot, app ini bisa menelusuri nasib kasus backlog dari waktu ke waktu dan membandingkan dua titik waktu.

> ⚠️ Karena tidak ada timestamp aktual saat tagihan benar-benar diterbitkan, semua angka waktu adalah **estimasi dari selisih snapshot**. Makin rutin download (idealnya mingguan), makin presisi.

## Struktur Direktori

```
klaim-monitor-mini/
├── app.py                  # aplikasi Streamlit (3 tab)
├── requirements.txt
├── README.md
├── .gitignore              # memastikan data/*.xlsx TIDAK ikut ter-push ke GitHub
├── src/
│   └── etl.py              # loader, normalisasi, perhitungan metrik
└── data/                   # file download Allcare disimpan di sini (isinya di-gitignore)
```

## Cara Pakai

```bash
pip install -r requirements.txt
streamlit run app.py
```

**Alur kerja rutin:**

1. Login ke Allcare, download file daftar peserta layanan (nama file otomatis bercap tanggal `DD_MM_YYYY`).
2. Masukkan file `.xlsx` ke folder `data/` aplikasi — lewat panel **📂 Kelola File Data Snapshot** di bagian atas app (upload satu/banyak file sekaligus), atau dengan menaruh file secara manual ke folder `data/` bila menjalankan di komputer sendiri. File lama **jangan dihapus** — histori snapshot justru sumber utama analisis. File dengan nama yang tidak mengandung tanggal `DD_MM_YYYY` akan ditolak.
3. Buka/refresh aplikasi — semua metrik dihitung ulang otomatis dari seluruh file di `data/` (cache otomatis invalid setiap kali ada file baru/diubah/dihapus).

## Panel Kelola File Data Snapshot

Terletak di atas, sebelum tab-tab metrik:

- **⬆️ Upload File** — upload satu atau banyak file `.xlsx` sekaligus lewat browser.
- **🗂️ File Tersimpan** — daftar semua file snapshot yang sudah ada, tanggalnya, dan tombol hapus per file.

> Versi ini **tidak punya** fitur "Import dari Folder" (baca path folder langsung dari disk server). Fitur itu hanya masuk akal saat app dijalankan di komputer sendiri; di Streamlit Cloud, "disk server" adalah container Streamlit itu sendiri — bukan komputer kamu — jadi fitur itu dibuang di versi ini supaya tidak membingungkan. Upload lewat browser tetap berfungsi normal di lokal maupun di cloud.

## ☁️ Catatan Khusus Deploy ke Streamlit Community Cloud

- **Penyimpanan bersifat sementara (ephemeral).** Folder `data/` di-reset setiap kali app di-redeploy, restart, atau "tidur" karena lama tidak dibuka (default tier gratis). File yang sudah diupload lewat panel di atas **akan hilang** dan perlu diupload ulang.
- Karena itu, jangan andalkan app ini sebagai penyimpanan histori snapshot jangka panjang di cloud — simpan juga file `.xlsx` asli di komputer/Google Drive, dan upload ulang ke app tiap kali dibuka kalau ternyata datanya sudah kosong.
- File `.xlsx` **tidak boleh** dimasukkan ke repo GitHub (lihat `.gitignore`) karena berisi data pribadi peserta (nama, nomor kartu, diagnosa).

## Filter (Sidebar)

- **Perusahaan Penjamin** dan **Kategori Layanan** — berlaku ke seluruh tab.
- Info jumlah snapshot tersedia beserta tanggal terlama/terbaru, dengan peringatan otomatis bila snapshot terakhir sudah >10 hari.
- Tombol **🔄 Muat ulang data dari folder data/** untuk memaksa refresh cache.

## Fitur per Tab

| Tab | Isi |
|---|---|
| 🧬 **Pelacakan Kohort** | Kunci semua registrasi backlog pada satu snapshot baseline, lalu telusuri nasibnya (sudah diajukan / masih backlog / tidak muncul lagi) di snapshot-snapshot berikutnya — trajektori per snapshot, median waktu penyelesaian, tabel outcome, drill-down timeline per registrasi. Ada opsi hanya kohort bernilai tagihan > Rp 0 |
| 🔄 **Snapshot Comparison** | Bandingkan dua tanggal download: kasus baru diajukan (& nilainya), registrasi baru muncul/hilang dari export, tabel transisi status A→B, detail kasus yang baru diajukan |
| 📋 **Rekap Status** | Pivot jumlah registrasi & nilai tagihan per Status Layanan pada satu snapshot, dengan grand total, grafik komposisi, dan export CSV |

## Definisi Status

- `Pelayanan Selesai` — layanan selesai, tagihan **belum** diajukan → masuk backlog
- `Menunggu Pelayanan` — layanan belum berjalan → masuk backlog
- `Sudah diajukan` — tagihan telah diajukan
- `Reinvoice` — penagihan ulang → dihitung terpisah, tidak mengotak-atik siklus pertama

## Catatan Teknis & Keterbatasan

1. **Kunci data**: `Nomor Registrasi APS`, 1 registrasi = 1 pasien. File export berbentuk *item-level* (banyak baris per pasien) — app otomatis mereduksi ke level pasien via `groupby().first()`.
2. **Normalisasi**: baris yang mengulang header (nilai `Nomor Registrasi APS` kosong/berisi ulang nama kolom) otomatis dibuang; pemilihan kolom eksplisit lewat `USE_COLS` di `src/etl.py` supaya tahan perbedaan minor antar export.
3. **Nilai uang**: `Subtotal Biaya` (per registrasi) dipakai untuk nilai kohort/rekap.
4. App akan memunculkan peringatan di sidebar bila snapshot terakhir sudah >10 hari.
5. Versi ini **tidak** menyertakan tab Overview, Aging & SLA, maupun Detail Kasus dari versi lengkap — bila nanti perlu tab-tab tersebut kembali, tambahkan lagi importnya dari `src/etl.py` (fungsi `backlog_at`, `cycle_time_table`, `aging_bucket` sudah tersedia di modul, hanya tidak dipakai di `app.py` versi ini).

## 🚀 Langkah Deploy ke Streamlit Community Cloud (Detail)

### A. Siapkan repo di GitHub

1. Buka [github.com](https://github.com) dan login (buat akun dulu kalau belum punya).
2. Klik tombol **+** di pojok kanan atas → **New repository**.
3. Isi **Repository name**, misal `klaim-monitor-mini`.
4. Pilih **Private** (bukan Public) — karena app ini nanti akan memproses data pribadi peserta.
5. Biarkan opsi "Add a README file" **tidak** dicentang (karena kita sudah punya README sendiri), lalu klik **Create repository**.
6. Di komputer, buka terminal di folder project (`klaim-monitor-mini/`) lalu jalankan:
   ```bash
   git init
   git add .
   git commit -m "Initial commit: klaim-monitor-mini"
   git branch -M main
   git remote add origin https://github.com/<username-kamu>/klaim-monitor-mini.git
   git push -u origin main
   ```
   Ganti `<username-kamu>` dengan username GitHub kamu. Karena ada `.gitignore` dengan `data/*.xlsx`, file Excel data pasien **tidak akan ikut ter-push** — hanya `app.py`, `src/etl.py`, `requirements.txt`, `README.md`, `.gitignore`, dan folder `data/` kosong (berkat `.gitkeep`).
7. Refresh halaman repo di GitHub untuk memastikan isinya sudah benar dan **tidak ada file `.xlsx`** di dalamnya.

### B. Deploy di Streamlit Community Cloud

1. Buka [share.streamlit.io](https://share.streamlit.io) dan login **pakai akun GitHub yang sama**.
2. Kalau pertama kali, Streamlit akan minta izin akses ke akun GitHub kamu — beri akses (bisa dipilih akses ke semua repo atau hanya repo tertentu, pilih `klaim-monitor-mini` saja kalau ingin lebih terbatas).
3. Klik **Create app** (atau **New app**).
4. Pilih opsi **"Deploy a public app from GitHub"** (app-nya sendiri bisa tetap dibatasi aksesnya di langkah D, ini hanya soal sumber kodenya).
5. Isi form deploy:
   - **Repository**: pilih `<username-kamu>/klaim-monitor-mini`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **App URL** (opsional): bisa diubah jadi subdomain custom, misal `klaim-monitor-mini`
6. Klik **Deploy**. Streamlit akan otomatis membaca `requirements.txt`, menginstall `streamlit`, `pandas`, `openpyxl`, lalu menjalankan `app.py`. Proses ini biasanya makan waktu 1–3 menit.
7. Setelah selesai, app akan otomatis terbuka di URL seperti `https://klaim-monitor-mini.streamlit.app`.

### C. Cek hasil deploy

1. Pastikan app terbuka tanpa error merah di layar.
2. Coba upload salah satu file `Daftar_Peserta_Layanan_DD_MM_YYYY.xlsx` lewat panel **📂 Kelola File Data Snapshot → ⬆️ Upload File** untuk memastikan pembacaan data berjalan normal.
3. Cek ketiga tab (Pelacakan Kohort, Snapshot Comparison, Rekap Status) menampilkan data dengan benar.

### D. Batasi siapa yang boleh mengakses app

1. Dari dashboard [share.streamlit.io](https://share.streamlit.io), klik app `klaim-monitor-mini` → menu **⋮ (titik tiga)** → **Settings**.
2. Buka tab **Sharing**.
3. Pilih **"Only specific people can view this app"**, lalu masukkan daftar email orang-orang yang boleh mengakses (mis. email kerja kamu dan tim terkait). Mereka harus login pakai akun Google/email yang sama untuk bisa membuka app.
4. Simpan perubahan. Sekarang app tidak lagi bisa diakses publik oleh sembarang orang yang tahu link-nya.

### E. Update app di kemudian hari

Setiap kali ada perubahan kode (`app.py` / `src/etl.py`), cukup:
```bash
git add .
git commit -m "Deskripsi perubahan"
git push
```
Streamlit Cloud otomatis mendeteksi push baru ke branch `main` dan me-redeploy app dalam beberapa menit — tidak perlu setting ulang dari awal. **Ingat**: redeploy ini juga akan mengosongkan folder `data/` (lihat catatan ephemeral storage di atas), jadi siapkan file snapshot untuk diupload ulang setelah redeploy.
