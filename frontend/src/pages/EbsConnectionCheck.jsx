/**
 * Cek Koneksi Oracle EBS — the HO user's side of EBS Network Monitoring.
 * Open to any logged-in employee (no IT role): IT sends this link to a user
 * who reports EBS as slow, the user runs the test while it is slow, and the
 * result lands in IT > Oracle EBS Network Monitoring > Client Test.
 */
import BrowserTest from "@/pages/dashboard/it/ebsnet/BrowserTest";
import { Note, Panel } from "@/pages/dashboard/it/ebsnet/ui";

export default function EbsConnectionCheck() {
  return (
    <div className="p-6 max-w-5xl">
      <Panel title="Cek Koneksi Oracle EBS" subtitle="Tes ±20 detik dari laptop Anda ke server di Plant, melewati jalur yang sama dengan Oracle EBS">
        <Note>
          Jalankan tes ini <b>saat EBS terasa lambat</b> — jangan tutup EBS dulu. Pilih kondisi EBS saat ini, klik <b>Mulai Tes</b>,
          lalu <b>Kirim hasil ke tim IT</b>. Tes tidak mengubah apa pun di laptop Anda.
        </Note>
        <div className="h-4" />
        <BrowserTest />
      </Panel>
    </div>
  );
}
