"""Modul ETL untuk monitoring penerbitan tagihan berbasis snapshot.

Data source: file hasil download sistem Allcare (Daftar_Peserta_Layanan_DD_MM_YYYY.xlsx).
Satu file = satu foto keadaan sistem pada tanggal download.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------- konstanta
STATUS_DIAJUKAN = "Sudah diajukan"
STATUS_REINVOICE = "Reinvoice"
STATUSES_BELUM_DIAJUKAN = ["Pelayanan Selesai", "Menunggu Pelayanan"]

# kolom yang dipakai (eksplisit, supaya tahan perbedaan minor antar export,
# mis. kolom 'cek' yang hanya ada di file baru)
USE_COLS = [
    "Tanggal Registrasi", "Nomor Registrasi APS", "Nomor Kartu", "Nama Peserta",
    "Kategori Layanan", "Perusahaan Penjamin", "Dokter",
    "Diagnosa Utama", "Diagnosa Sekunder", "Diagnosa Tambahan",
    "Subtotal Biaya", "Tanggal Layanan", "Status Layanan",
]

# ---------------------------------------------------------------- util tanggal
def parse_snapshot_date(file_name: str) -> pd.Timestamp | None:
    """Ambil tanggal snapshot dari nama file: ..._DD_MM_YYYY.xlsx."""
    m = re.search(r"(\d{2})_(\d{2})_(\d{4})", Path(file_name).stem)
    if not m:
        return None
    d, mth, y = m.groups()
    return pd.Timestamp(f"{y}-{mth}-{d}")


# ---------------------------------------------------------------- loading
def _clean(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalisasi satu file export."""
    df = raw.copy()
    # file export punya baris kedua yang mengulang nama kolom -> buang
    df = df[df["Nomor Registrasi APS"] != "Nomor Registrasi APS"]
    df = df.dropna(subset=["Nomor Registrasi APS"])

    keep = [c for c in USE_COLS if c in df.columns]
    df = df[keep].copy()

    df["Nomor Registrasi APS"] = df["Nomor Registrasi APS"].astype(str).str.strip()
    for c in ["Tanggal Registrasi", "Tanggal Layanan"]:
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["Subtotal Biaya"] = pd.to_numeric(df["Subtotal Biaya"], errors="coerce").fillna(0)
    return df


def to_patient_level(df: pd.DataFrame) -> pd.DataFrame:
    """Item-level -> 1 baris per Nomor Registrasi APS."""
    # first() ambil baris pertama per APS; semua kolom konteks konsisten per APS
    return df.groupby("Nomor Registrasi APS", as_index=False).first()


def load_all_snapshots(data_dir: str | Path) -> pd.DataFrame:
    """Baca semua xlsx di folder data -> long-format history:
    1 baris per (snapshot_date, Nomor Registrasi APS)."""
    data_dir = Path(data_dir)
    frames = []
    for path in sorted(data_dir.glob("*.xlsx")):
        snap = parse_snapshot_date(path.name)
        if snap is None:
            continue  # file tanpa date stamp tidak bisa dipakai
        df = to_patient_level(_clean(pd.read_excel(path)))
        df["snapshot_date"] = snap
        frames.append(df)

    if not frames:
        raise FileNotFoundError(
            f"Tidak ada file Daftar_Peserta_Layanan_DD_MM_YYYY.xlsx di {data_dir}"
        )
    hist = pd.concat(frames, ignore_index=True)
    return hist.sort_values(["snapshot_date", "Nomor Registrasi APS"]).reset_index(drop=True)


# ---------------------------------------------------------------- metrik
def cycle_time_table(hist: pd.DataFrame) -> pd.DataFrame:
    """Estimasi waktu siklus: Tanggal Layanan -> pertama kali terlihat 'Sudah diajukan'.

    Kolom 'estimasi' = True bila pasien SUDAH 'Sudah diajukan' pada snapshot
    pertama yang memuatnya -> nilai cycle_time hanyalah BATAS ATAS.
    """
    diajukan = hist[hist["Status Layanan"] == STATUS_DIAJUKAN]
    first_seen = diajukan.groupby("Nomor Registrasi APS")["snapshot_date"].min().rename("first_diajukan_seen")

    earliest = hist.groupby("Nomor Registrasi APS")["snapshot_date"].min().rename("first_seen_anywhere")

    base_df = (
        hist.sort_values("snapshot_date")
            .groupby("Nomor Registrasi APS", as_index=False)
            .first()
            .merge(first_seen, on="Nomor Registrasi APS", how="inner")
            .merge(earliest, on="Nomor Registrasi APS")
    )
    base_df["cycle_time_hari"] = (base_df["first_diajukan_seen"] - base_df["Tanggal Layanan"]).dt.days
    base_df["estimasi_batas_atas"] = base_df["first_diajukan_seen"] == base_df["first_seen_anywhere"]
    return base_df.dropna(subset=["cycle_time_hari"])


def backlog_at(hist: pd.DataFrame, snap_date: pd.Timestamp) -> pd.DataFrame:
    """Pasien yang BELUM diajukan pada snapshot tertentu + usianya."""
    on_date = hist[hist["snapshot_date"] == snap_date]
    bl = on_date[on_date["Status Layanan"].isin(STATUSES_BELUM_DIAJUKAN)].copy()
    bl["aging_hari"] = (snap_date - bl["Tanggal Layanan"]).dt.days
    return bl.sort_values("aging_hari", ascending=False)


def transitions_between(hist: pd.DataFrame, snap_a: pd.Timestamp, snap_b: pd.Timestamp) -> pd.DataFrame:
    """Perubahan status tiap registrasi antara dua snapshot."""
    a = hist[hist["snapshot_date"] == snap_a][["Nomor Registrasi APS", "Status Layanan"]].rename(columns={"Status Layanan": "status_a"})
    b = hist[hist["snapshot_date"] == snap_b][["Nomor Registrasi APS", "Status Layanan", "Subtotal Biaya"]].rename(columns={"Status Layanan": "status_b"})
    merged = b.merge(a, on="Nomor Registrasi APS", how="outer", indicator=True)
    merged["snap_a"], merged["snap_b"] = snap_a, snap_b
    return merged


def aging_bucket(days: float, sla: int = 14) -> str:
    if pd.isna(days):
        return "Tgl layanan kosong"
    if days < 0:
        return "Layanan setelah snapshot"
    if days <= 7:
        return "0-7 hari"
    if days <= sla:
        return f"8-{sla} hari"
    if days <= 30:
        return f"{sla+1}-30 hari"
    return ">30 hari"


def cohort_tracking(hist: pd.DataFrame, base_snap: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Telusuri nasib kohort: semua APS yang BELUM diajukan pada base_snap.

    Return:
      traj      -> komposisi kohort per snapshot_date (>= base_snap)
      members   -> outcome per anggota kohort
    """
    base = hist[hist["snapshot_date"] == base_snap]
    cohort_aps = base.loc[base["Status Layanan"].isin(STATUSES_BELUM_DIAJUKAN), "Nomor Registrasi APS"].unique()
    if len(cohort_aps) == 0:
        return pd.DataFrame(), pd.DataFrame()

    sub = hist[hist["Nomor Registrasi APS"].isin(cohort_aps)].copy()
    n = len(cohort_aps)

    # --- trajektori komposisi per snapshot
    rows = []
    for d in sorted(sub["snapshot_date"].unique()):
        if d < base_snap:
            continue
        g = sub[sub["snapshot_date"] == d]
        st = g["Status Layanan"]
        rows.append({
            "snapshot_date": d,
            "sudah_diajukan": int((st == STATUS_DIAJUKAN).sum()),
            "belum_diajukan": int(st.isin(STATUSES_BELUM_DIAJUKAN).sum()),
            "reinvoice": int((st == STATUS_REINVOICE).sum()),
            "tidak_muncul_lagi": n - g["Nomor Registrasi APS"].nunique(),
        })
    traj = pd.DataFrame(rows)

    # --- outcome per anggota
    first_diajukan = (
        sub[sub["Status Layanan"] == STATUS_DIAJUKAN]
        .groupby("Nomor Registrasi APS")["snapshot_date"].min()
    )
    latest_status = sub.sort_values("snapshot_date").groupby("Nomor Registrasi APS")["Status Layanan"].last()

    members = base[base["Status Layanan"].isin(STATUSES_BELUM_DIAJUKAN)].copy()

    def outcome_of(aps: str) -> str:
        if aps in first_diajukan.index:
            return "Sudah diajukan"
        if aps in latest_status.index and latest_status[aps] in STATUSES_BELUM_DIAJUKAN:
            return "Masih backlog"
        return "Tidak muncul lagi"

    members["outcome"] = members["Nomor Registrasi APS"].map(outcome_of)
    if first_diajukan.empty:
        # Tidak ada satupun anggota kohort yang pernah berstatus "Sudah diajukan"
        # (misal karena filter mempersempit banget, atau baseline-nya terlalu baru).
        # groupby kosong di pandas mengembalikan Series datetime64 kosong, dan me-map-kan
        # itu ke kolom lain bisa memicu TypeError saat pandas coba menyamakan dtype.
        # Jadi di-skip saja: seluruh kolom diisi NaT (kosong).
        members["hari_sampai_diajukan"] = pd.NaT
    else:
        members["hari_sampai_diajukan"] = members["Nomor Registrasi APS"].map(first_diajukan)
    members["hari_sampai_diajukan"] = pd.to_datetime(members["hari_sampai_diajukan"], errors="coerce")
    members["hari_sampai_diajukan"] = (members["hari_sampai_diajukan"] - base_snap).dt.days
    return traj, members
