"""Monitoring Tagihan (versi ringkas) — Streamlit app.

Hanya berisi 3 tab: Pelacakan Kohort, Snapshot Comparison, Rekap Status.

Jalankan:  streamlit run app.py
Prasyarat: taruh file Daftar_Peserta_Layanan_DD_MM_YYYY.xlsx di folder data/
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from src.etl import (  # noqa: E402
    STATUS_DIAJUKAN,
    cohort_tracking,
    load_all_snapshots,
    parse_snapshot_date,
    transitions_between,
)

st.set_page_config(page_title="Monitoring Tagihan", page_icon="🧾", layout="wide")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ================================================================ header
st.title("🧾 Monitoring Tagihan — Kohort, Snapshot Comparison & Rekap Status")
st.caption(
    "Data berbasis snapshot download harian/mingguan dari Allcare. "
    "Waktu siklus adalah estimasi dari selisih snapshot, bukan timestamp aktual penerbitan."
)

# ================================================================ data
def data_signature(data_dir: Path) -> tuple:
    """Signature isi folder data -> cache otomatis invalid bila ada file
    baru/diubah/dihapus, tanpa perlu restart Streamlit."""
    files = sorted(data_dir.glob("*.xlsx"))
    return tuple((p.name, p.stat().st_mtime, p.stat().st_size) for p in files)


@st.cache_data(show_spinner="Membaca snapshot…")
def get_history(_signature: tuple) -> pd.DataFrame:
    return load_all_snapshots(DATA_DIR)


# ================================================================ kelola file snapshot
existing_files = sorted(DATA_DIR.glob("*.xlsx"))

with st.expander("📂 Kelola File Data Snapshot", expanded=(len(existing_files) == 0)):
    st.caption(
        "Nama file harus mengandung tanggal snapshot format **DD_MM_YYYY** "
        "(mis. `Daftar_Peserta_Layanan_16_09_2026.xlsx`)."
    )
    st.info(
        "☁️ **Jika app ini berjalan di Streamlit Community Cloud**: penyimpanan bersifat sementara "
        "(ephemeral). File yang diupload di sini bisa hilang saat app di-restart, di-redeploy, atau "
        "tidur karena lama tidak diakses — jadi simpan juga salinan file `.xlsx` asli di komputer/Allcare, "
        "dan upload ulang di sini bila datanya sudah tidak muncul.",
        icon="☁️",
    )
    tab_up, tab_list = st.tabs(
        ["⬆️ Upload File", f"🗂️ File Tersimpan ({len(existing_files)})"]
    )

    # --- upload manual, mendukung pilih banyak file sekaligus (Select All di dialog OS)
    with tab_up:
        st.caption(
            "Klik area di bawah lalu, di jendela pemilihan file, pilih beberapa file sekaligus "
            "(mis. Ctrl+A / Select All) atau drag-and-drop banyak file bersamaan."
        )
        uploaded = st.file_uploader(
            "Pilih satu atau beberapa file .xlsx",
            type=["xlsx"],
            accept_multiple_files=True,
            key="uploader_snapshot",
        )
        if uploaded:
            added, skipped, invalid = [], [], []
            for uf in uploaded:
                if parse_snapshot_date(uf.name) is None:
                    invalid.append(uf.name)
                    continue
                dest = DATA_DIR / uf.name
                if dest.exists():
                    skipped.append(uf.name)
                    continue
                with open(dest, "wb") as out:
                    out.write(uf.getbuffer())
                added.append(uf.name)

            if added:
                st.success(f"✅ {len(added)} file ditambahkan: {', '.join(added)}")
            if skipped:
                st.warning(f"⚠️ {len(skipped)} file dilewati (nama sudah ada di data/): {', '.join(skipped)}")
            if invalid:
                st.error(f"❌ {len(invalid)} file ditolak (nama tidak mengandung tanggal DD_MM_YYYY): {', '.join(invalid)}")
            if added:
                st.cache_data.clear()
                st.rerun()

    # --- daftar file yang sudah tersimpan, dengan opsi hapus
    with tab_list:
        if not existing_files:
            st.info("Belum ada file snapshot di folder data/. Tambahkan lewat tab Upload atau Import di atas.")
        else:
            hdr1, hdr2, hdr3 = st.columns([5, 3, 1])
            hdr1.markdown("**Nama file**")
            hdr2.markdown("**Tanggal snapshot**")
            hdr3.markdown("**Hapus**")
            for p in existing_files:
                snap = parse_snapshot_date(p.name)
                c1, c2, c3 = st.columns([5, 3, 1])
                c1.write(f"📄 {p.name}")
                c2.write(f"{snap:%d %b %Y}" if snap is not None else "⚠️ tanggal tak terbaca")
                if c3.button("🗑️", key=f"del_{p.name}", help=f"Hapus {p.name}"):
                    p.unlink()
                    st.cache_data.clear()
                    st.rerun()

try:
    hist = get_history(data_signature(DATA_DIR))
except FileNotFoundError:
    st.info(
        "👆 Belum ada file snapshot yang valid di folder data/. "
        "Tambahkan file lewat panel **📂 Kelola File Data Snapshot** di atas untuk mulai."
    )
    st.stop()

snap_dates = sorted(hist["snapshot_date"].unique())
earliest_snap = snap_dates[0]
latest_snap = snap_dates[-1]

# ================================================================ sidebar
st.sidebar.header("⚙️ Filter")
penjamin_opt = sorted(hist["Perusahaan Penjamin"].dropna().unique())
penjamin = st.sidebar.multiselect("Perusahaan Penjamin", penjamin_opt, default=penjamin_opt)
kat_opt = sorted(hist["Kategori Layanan"].dropna().unique())
kat = st.sidebar.multiselect("Kategori Layanan", kat_opt, default=kat_opt)

f = hist[hist["Perusahaan Penjamin"].isin(penjamin) & hist["Kategori Layanan"].isin(kat)].copy()

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Snapshot tersedia: {len(snap_dates)}\n\n"
    f"Terlama: {earliest_snap:%d %b %Y}\n\nTerbaru: {latest_snap:%d %b %Y}"
)
stale_days = (pd.Timestamp.today().normalize() - latest_snap).days
if stale_days > 10:
    st.sidebar.warning(f"⚠️ Snapshot terakhir sudah {stale_days} hari — segera download data terbaru dari Allcare.")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Muat ulang data dari folder data/", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

tab_koh, tab_snap, tab_rekap = st.tabs(
    ["🧬 Pelacakan Kohort", "🔄 Snapshot Comparison", "📋 Rekap Status"]
)

# ================================================================ TAB 1: KOHORT
with tab_koh:
    st.markdown(
        "Kohort = semua registrasi yang **belum diajukan** pada snapshot baseline. "
        "Aplikasi mengunci nomor-nomor itu lalu menelusuri nasibnya di semua snapshot berikutnya."
    )
    base_snap = st.selectbox(
        "Snapshot baseline (titik nol kohort)",
        snap_dates[:-1],
        index=0,
        format_func=lambda d: f"{d:%d %b %Y}",
    )
    hanya_bernilai = st.checkbox(
        "Hanya kohort dengan nilai tagihan > Rp 0",
        value=True,
        help="Centang untuk mengecualikan registrasi yang Subtotal Biayanya masih 0 (belum ada rincian tagihan).",
    )

    f_koh = f if not hanya_bernilai else f[f["Subtotal Biaya"] > 0]

    traj, members = cohort_tracking(f_koh, base_snap)
    if members.empty:
        st.info("Tidak ada backlog pada snapshot baseline tersebut.")
    else:
        n = len(members)
        resolved = members[members["outcome"] == "Sudah diajukan"]
        still = members[members["outcome"] == "Masih backlog"]
        gone = members[members["outcome"] == "Tidak muncul lagi"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ukuran kohort", f"{n:,}")
        c2.metric("Sudah diajukan", f"{len(resolved):,}", f"{len(resolved)/n*100:.0f}%")
        c3.metric("Masih backlog", f"{len(still):,}", f"{len(still)/n*100:.0f}%")
        c4.metric("Tidak muncul lagi di export", f"{len(gone):,}",
                  help="Registrasi baseline yang tidak ada lagi di snapshot-snapshot berikutnya. "
                       "Bisa jadi sudah selesai dikeluarkan dari daftar export Allcare, atau export terpotong rentangnya.")

        col_a, col_b = st.columns([3, 2])
        with col_a:
            st.markdown("#### Trajektori kohort per snapshot")
            tplot = traj.copy()
            tplot["snapshot_date"] = tplot["snapshot_date"].dt.strftime("%d %b")
            tplot = tplot.set_index("snapshot_date")
            st.bar_chart(tplot)

        with col_b:
            st.markdown("#### Median waktu penyelesaian")
            if len(resolved):
                st.metric("Baseline → terlihat 'Sudah diajukan'", f"{resolved['hari_sampai_diajukan'].median():.0f} hari")
                st.bar_chart(resolved["hari_sampai_diajukan"].clip(lower=0).value_counts().sort_index())
                st.caption("⚠️ Estimasi batas bawah: tagihan bisa jadi sudah diajukan sebelum snapshot berikutnya menangkapnya.")
            else:
                st.info("Belum ada anggota kohort yang terlihat 'Sudah diajukan'.")

        st.markdown("#### Daftar anggota kohort & outcome")
        outcome_order = {"Sudah diajukan": 0, "Masih backlog": 1, "Tidak muncul lagi": 2}
        show_cols = [c for c in ["Nomor Registrasi APS", "Nama Peserta", "Perusahaan Penjamin",
                                 "Tanggal Layanan", "Subtotal Biaya", "outcome", "hari_sampai_diajukan"]
                     if c in members.columns]
        tbl = members[show_cols].assign(_o=members["outcome"].map(outcome_order)).sort_values(["_o", "hari_sampai_diajukan"])
        st.dataframe(tbl.drop(columns="_o"), use_container_width=True, hide_index=True)

        sel = st.selectbox("Drill-down anggota kohort", members["Nomor Registrasi APS"].unique())
        tl = f_koh[f_koh["Nomor Registrasi APS"] == sel][["snapshot_date", "Status Layanan", "Subtotal Biaya"]]
        st.dataframe(tl, use_container_width=True, hide_index=True)

# ================================================================ TAB 2: SNAPSHOT COMPARISON
with tab_snap:
    if len(snap_dates) < 2:
        st.info("Butuh minimal 2 snapshot untuk perbandingan.")
    else:
        c1, c2 = st.columns(2)
        snap_a = c1.selectbox("Snapshot A", snap_dates[:-1], index=0, format_func=lambda d: f"{d:%d %b %Y}")
        snap_b = c2.selectbox("Snapshot B", snap_dates[1:], index=len(snap_dates) - 2, format_func=lambda d: f"{d:%d %b %Y}")

        tr = transitions_between(f, snap_a, snap_b)

        c1, c2, c3 = st.columns(3)
        baru_diajukan = tr[(tr["status_a"] != STATUS_DIAJUKAN) & (tr["status_b"] == STATUS_DIAJUKAN) & (tr["_merge"] == "both")]
        c1.metric("Baru diajukan di periode ini", f"{len(baru_diajukan):,}",
                  f"Rp {baru_diajukan['Subtotal Biaya'].sum():,.0f}")
        masuk = tr[tr["_merge"] == "right_only"]
        c2.metric("Registrasi baru muncul", f"{len(masuk):,}")
        hilang = tr[tr["_merge"] == "left_only"]
        c3.metric("Hilang dari snapshot B", f"{len(hilang):,}",
                  help="Bisa jadi sudah diajukan di luar rentang/filter, atau data tidak ikut ter-export.")

        st.markdown("#### Transisi status (A → B)")
        trans = (
            tr[tr["_merge"] == "both"]
            .groupby(["status_a", "status_b"]).size().rename("jumlah").reset_index()
        )
        trans["transisi"] = trans["status_a"].fillna("(baru)") + " → " + trans["status_b"].fillna("(hilang)")
        st.dataframe(trans[["transisi", "jumlah"]], use_container_width=True, hide_index=True)

        st.markdown("#### Detail kasus yang baru diajukan")
        show_cols = [c for c in ["Nomor Registrasi APS", "Nama Peserta", "status_a", "status_b",
                                 "Tanggal Layanan", "Subtotal Biaya"] if c in baru_diajukan.columns]
        st.dataframe(baru_diajukan[show_cols], use_container_width=True, hide_index=True)

# ================================================================ TAB 3: REKAP STATUS
with tab_rekap:
    st.markdown(
        "Rekap jumlah registrasi dan nilai tagihan per **Status Layanan**, "
        "pada satu titik snapshot pilihan — mirip pivot table Excel."
    )

    snap_pilih = st.selectbox(
        "📅 Pilih snapshot",
        snap_dates,
        index=len(snap_dates) - 1,
        format_func=lambda d: f"{d:%d %b %Y}",
        key="rekap_snapshot",
    )

    snap_df = f[f["snapshot_date"] == snap_pilih]

    if snap_df.empty:
        st.info("Tidak ada data pada snapshot ini (kemungkinan tersaring oleh filter di sidebar).")
    else:
        rekap = (
            snap_df.groupby("Status Layanan")
            .agg(jumlah=("Nomor Registrasi APS", "nunique"), nilai=("Subtotal Biaya", "sum"))
            .sort_index()
        )
        total_jumlah = int(rekap["jumlah"].sum())
        total_nilai = float(rekap["nilai"].sum())
        max_jumlah = int(rekap["jumlah"].max())

        c1, c2, c3 = st.columns(3)
        c1.metric("Total registrasi (semua status)", f"{total_jumlah:,}")
        c2.metric("Total nilai tagihan", f"Rp {total_nilai:,.0f}")
        c3.metric("Jumlah status berbeda", f"{len(rekap)}")

        st.markdown("---")
        col_tbl, col_chart = st.columns([3, 2])

        with col_tbl:
            st.markdown(f"##### Rekap per Status Layanan — {snap_pilih:%d %b %Y}")

            tampil = rekap.reset_index().rename(columns={
                "Status Layanan": "Row Labels",
                "jumlah": "Distinct Count of Nomor Registrasi APS",
                "nilai": "Sum of Subtotal Biaya",
            })
            grand_total = pd.DataFrame([{
                "Row Labels": "Grand Total",
                "Distinct Count of Nomor Registrasi APS": total_jumlah,
                "Sum of Subtotal Biaya": total_nilai,
            }])
            tampil_full = pd.concat([tampil, grand_total], ignore_index=True)

            def _style_rekap(row: pd.Series):
                is_total = row["Row Labels"] == "Grand Total"
                base = "font-weight: 700; background-color: rgba(120,120,120,0.18);" if is_total else ""
                return [base] * len(row)

            styled = (
                tampil_full.style
                .apply(_style_rekap, axis=1)
                .bar(
                    subset=pd.IndexSlice[tampil.index, "Distinct Count of Nomor Registrasi APS"],
                    color="#7fb3f0", vmin=0, vmax=max_jumlah,
                )
                .format({
                    "Distinct Count of Nomor Registrasi APS": "{:,.0f}",
                    "Sum of Subtotal Biaya": "Rp {:,.0f}",
                })
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)

            csv = tampil.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Unduh rekap (CSV)", csv,
                file_name=f"rekap_status_{snap_pilih:%Y%m%d}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_chart:
            st.markdown("##### Komposisi jumlah registrasi")
            st.bar_chart(rekap["jumlah"])
            st.markdown("##### Komposisi nilai tagihan")
            st.bar_chart(rekap["nilai"])
