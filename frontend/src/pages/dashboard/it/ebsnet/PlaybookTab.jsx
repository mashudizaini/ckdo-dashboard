/**
 * Playbook — the improvement backlog for EBS access from HO, as a shared
 * checklist (state in ebsnet_settings.playbook_checklist, so every IT staff
 * member sees the same ticks). Order inside a group = suggested priority.
 */
import { useEffect, useState } from "react";
import { CheckSquare, Square } from "lucide-react";
import { ebsNetApi } from "@/api/dashboard";
import { Note, Panel, errText, fmtDate } from "./ui";

const GROUPS = [
  {
    title: "1 · Ukur dulu (baseline sebelum mengubah apa pun)",
    items: [
      ["base-agent", "Jalankan agen PowerShell di 3–5 laptop HO pada 08:00, 11:00, 14:00 dan 15:00–16:00 selama satu minggu.", "Membedakan masalah satu laptop (Case D) dari masalah jalur (Case B), dan memperlihatkan pola jam sibuk di Matriks waktu tes."],
      ["base-ebs-test", "Catat Network Test bawaan Oracle EBS (RTT + data rate) bersamaan dengan agen.", "Angka resmi Oracle yang bisa dibandingkan langsung dengan probe dashboard."],
      ["base-incident", "Setiap keluhan “EBS lambat”: catat insiden SAAT itu juga dengan snapshot dicentang.", "Timestamp yang tepat = korelasi firewall / VPN / app server / DB. Tanpa itu, root cause cuma tebakan."],
      ["base-change", "Aturan: tidak ada perubahan VPN, routing, MTU, firewall atau Oracle tanpa baseline sebelum & sesudah.", "Menghindari “sudah diubah tapi tidak tahu efeknya”."],
    ],
  },
  {
    title: "2 · Jalur HO ↔ Plant (FortiGate 121G / SD-WAN)",
    items: [
      ["fg-sla", "Buat SD-WAN performance SLA khusus EBS: probe ping + HTTP ke server EBS (172.21.2.x) lewat tunnel, target latency ≤ 50 ms, jitter ≤ 10 ms, loss ≤ 1 %.", "FortiGate sendiri jadi sensor 24 jam; hasilnya tampil di tab FortiGate."],
      ["fg-rule", "SD-WAN rule untuk subnet EBS dengan strategi Lowest Cost (SLA) / Best Quality — bukan load-balance yang bisa memindah sesi di tengah jalan.", "Satu sesi TCP Forms yang berpindah link = Forms hang / FRM-92101. Load-balance cocok untuk internet, bukan untuk EBS."],
      ["fg-dual-tunnel", "Tunnel IPsec kedua lewat iForte di Plant sebagai member SD-WAN, failover otomatis; uji failover di luar jam kerja.", "Saat ini satu tunnel = satu titik gagal. iForte radio rentan hujan, jadi pakai sebagai cadangan SLA-based, bukan jalur utama."],
      ["fg-mss", "Set tcp-mss (≈1350) pada policy tunnel EBS dan cek MTU tunnel; bandingkan dengan Path MTU dari agen.", "Fragmentasi paket IPsec (NET-06) gejalanya khas: login lancar, layar/LOV besar macet."],
      ["fg-qos", "Traffic shaping: prioritas + guaranteed bandwidth untuk port EBS; batasi Windows Update, OneDrive/backup, streaming di jam kerja, terutama di link Plant 30 Mbps.", "Forms sangat sensitif antrian (bufferbloat) — satu upload besar bisa menaikkan RTT semua user EBS."],
      ["fg-ttl", "Session-TTL policy EBS lebih panjang dari ICX Session Timeout dan heartbeat Forms; DPD on-idle aktif.", "Firewall yang memotong sesi idle diam-diam membuat Forms “hang” saat user kembali dari rapat."],
      ["fg-offload", "Pastikan tunnel EBS ter-offload NPU dan tidak melewati inspeksi proxy-based / deep SSL inspection.", "Inspeksi menambah latency & CPU firewall dan mematikan hardware offload untuk traffic internal yang tepercaya."],
      ["fg-license", "Perpanjang lisensi FortiGuard (jatuh tempo 11 Mei 2026).", "IPS/AV/Web Filter tidak lagi update — bukan penyebab lambat, tapi risiko keamanan di perangkat yang sama."],
      ["fg-snmp", "Monitor utilisasi WAN & tunnel (SNMP / FortiAnalyzer) dengan alarm > 70–80 %.", "Bandwidth saturation (NET-05) hanya terbukti dengan grafik utilisasi pada jam insiden."],
      ["fg-ho-isp", "Pertimbangkan link kedua di HO (saat ini hanya CBN).", "Kalau link HO putus, seluruh HO kehilangan EBS walau Plant punya dua ISP."],
    ],
  },
  {
    title: "3 · LAN HO & laptop",
    items: [
      ["cli-wired", "User Forms intensif (Finance, Purchasing, PPIC) memakai kabel LAN; Wi-Fi hanya 5 GHz dengan sinyal > 70 %.", "Wi-Fi menambah jitter di hop pertama — kalau gateway sudah jitter, sisa jalur tidak bisa memperbaikinya (Case A)."],
      ["cli-wifi-survey", "Survey Wi-Fi HO: overlap channel, jumlah klien per AP, roaming 802.11k/v/r.", "Laporan agen yang menunjukkan jitter ke gateway tinggi di banyak laptop = masalah AP, bukan laptop."],
      ["cli-ram", "Standar laptop: RAM ≥ 8 GB (16 GB untuk pengguna Excel + Teams + EBS), SSD.", "Agen menandai CLI-02 saat RAM bebas < 20 % — Java Forms ikut swap."],
      ["cli-java", "Standarisasi Java untuk Forms 12.2 (JRE 8 / Java Web Start) dengan versi seragam di semua laptop.", "Versi berbeda memaksa unduh ulang jar Forms lewat WAN dan memicu pesan keamanan yang membuat user menutup sesi."],
      ["cli-proxy-dns", "Bypass proxy untuk hostname EBS dan pastikan DNS internal me-resolve EBS ke IP privat.", "Proxy atau hairpin lewat IP publik menambah hop & latency di setiap request."],
      ["cli-power-av", "Power plan Balanced/High performance saat dicolok; matikan power-saving NIC; kecualikan cache Java/Forms dari scan real-time antivirus.", "CPU throttling & scan antivirus terasa seperti EBS lambat (CLI-01/CLI-05)."],
      ["cli-browser", "Profil browser khusus EBS tanpa ekstensi berat; bersihkan cache Java/JNLP saat ada keluhan satu laptop.", "Penyebab umum Case D (CLI-04)."],
    ],
  },
  {
    title: "4 · Oracle EBS 12.2 (application & database tier)",
    items: [
      ["ebs-forms-retry", "Atur networkRetries dan heartBeat Forms lewat AutoConfig (bukan edit manual formsweb.cfg).", "Membuat Forms tahan putus sesaat tunnel alih-alih langsung FRM-92101/92102."],
      ["ebs-compress", "Aktifkan kompresi HTTP & cache header file statis di OHS untuk halaman OAF.", "Mengurangi byte yang lewat link Plant 30 Mbps tanpa mengubah aplikasi."],
      ["ebs-schedule", "Jadwalkan request berat (Gather Schema Statistics, purge, report besar) di luar jam kerja HO; output report besar dikirim via email/NAS.", "Concurrent request berat menaikkan CPU/I/O DB saat user HO bekerja (DB-01/DB-03)."],
      ["ebs-purge", "Purge rutin FND_CONCURRENT_REQUESTS, Workflow & log; Gather Stats terjadwal.", "Tabel FND/WF yang menggembung memperlambat layar yang tampak “network”."],
      ["ebs-jvm", "Review heap & jumlah managed server oacore/forms sesuai jumlah user.", "Full GC JVM terasa persis seperti hang beberapa detik (EBS-02/EBS-03)."],
      ["ebs-awr", "Saat insiden Case C: ambil AWR/ASH di jendela waktu insiden (Top SQL, wait event, blocking).", "Tab EBS Server memberi gambaran cepat; AWR memberi bukti."],
    ],
  },
  {
    title: "5 · Kalau RTT HO → Plant memang tidak bisa turun",
    items: [
      ["arch-rds", "Jump host / RDS / Citrix di Plant untuk power user Forms.", "Hanya gambar layar yang lewat WAN; Forms bicara ke server via LAN Plant (~1 ms). Paling efektif untuk Forms yang “chatty”."],
      ["arch-oaf", "Arahkan transaksi ke halaman OAF/self-service (HTML) bila tersedia.", "Halaman HTML jauh lebih toleran latency daripada Forms Java applet."],
      ["arch-isp-sla", "Minta SLA latency/jitter/loss tertulis dari ISP, lampirkan baseline dari modul ini.", "Data probe 24/7 adalah bukti saat eskalasi ke ISP (NET-08)."],
    ],
  },
  {
    title: "Pertanyaan untuk Network Team (§12 script)",
    items: [
      ["q-provider", "Traffic EBS melewati provider mana, dan VPN tunnel memakai provider mana?", "Cek di tab FortiGate: kolom “Rute ke EBS via”."],
      ["q-lb", "Apakah kedua provider load-balance, dan bisakah satu sesi TCP berpindah provider?", ""],
      ["q-failover", "Bagaimana mekanisme failover, dan kapan terakhir diuji?", ""],
      ["q-metrics", "Berapa latency, loss, jitter, utilisasi tunnel, serta MTU/MSS tunnel saat ini?", "Sebagian besar sudah terbaca otomatis di tab FortiGate & Jalur."],
    ],
  },
];

export default function PlaybookTab({ settings, user }) {
  const [state, setState] = useState(settings?.playbook_checklist || {});
  useEffect(() => { setState(settings?.playbook_checklist || {}); }, [settings]);

  const toggle = async (id) => {
    const next = { ...state };
    if (next[id]?.done) delete next[id];
    else next[id] = { done: true, by: user, at: new Date().toISOString() };
    setState(next);
    try { await ebsNetApi.putSettings({ playbook_checklist: next }); }
    catch (e) { alert(errText(e, "Gagal menyimpan")); setState(state); }
  };

  const total = GROUPS.reduce((n, g) => n + g.items.length, 0);
  const done = Object.values(state).filter((v) => v?.done).length;

  return (
    <>
      <Note>
        Rekomendasi agar akses Oracle EBS dari HO stabil. Prinsipnya: <b>Forms EBS sensitif terhadap round-trip dan stabilitas, bukan bandwidth</b> —
        satu layar Forms bisa ratusan round-trip, jadi 60 ms × 200 = 12 detik. Turunkan jitter & loss, jaga sesi TCP tidak berpindah jalur, dan buktikan setiap
        perubahan dengan data sebelum/sesudah. Progres: <b>{done}/{total}</b> selesai.
      </Note>
      <div className="h-4" />
      {GROUPS.map((g) => (
        <Panel key={g.title} title={g.title}>
          <div className="space-y-2.5">
            {g.items.map(([id, text, why]) => {
              const st = state[id];
              const Icon = st?.done ? CheckSquare : Square;
              return (
                <button key={id} type="button" onClick={() => toggle(id)} className="flex items-start gap-2.5 text-left w-full rounded-lg p-2 hover:bg-slate-50">
                  <Icon size={16} style={{ color: st?.done ? "#0ca30c" : "#94a3b8", flexShrink: 0, marginTop: 1 }} />
                  <div>
                    <p style={{ fontSize: 12.5, color: "#0f172a", fontWeight: 600, textDecoration: st?.done ? "line-through" : "none", opacity: st?.done ? 0.7 : 1 }}>{text}</p>
                    {why && <p style={{ fontSize: 11.5, color: "#64748b", marginTop: 2 }}>{why}</p>}
                    {st?.done && <p style={{ fontSize: 10.5, color: "#0ca30c", marginTop: 2 }}>Selesai · {st.by} · {fmtDate(st.at)}</p>}
                  </div>
                </button>
              );
            })}
          </div>
        </Panel>
      ))}
    </>
  );
}
