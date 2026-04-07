import { useState } from "react";
import { FileText, Mic, Upload, Sparkles, Clock, Users, Copy, Download } from "lucide-react";

export default function MeetingNotes() {
  const [tab, setTab] = useState("new");

  const history = [
    { id: 1, title: "Rapat Koordinasi IT",     date: "10 Mar 2026", duration: "45 min", participants: 6 },
    { id: 2, title: "Review Produksi Bulanan", date: "08 Mar 2026", duration: "60 min", participants: 12 },
    { id: 3, title: "Meeting HR Q1 2026",      date: "05 Mar 2026", duration: "30 min", participants: 4 },
  ];

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-3">
          <FileText className="text-purple-400" size={26} />
          Meeting Notes
        </h1>
        <p className="text-gray-500 text-sm mt-1">Rekam rapat — Transkrip otomatis — Minutes of Meeting (AI-powered)</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-900 border border-gray-800 p-1 w-fit">
        {[
          { id: "new",     label: "Rekam Baru" },
          { id: "history", label: "Riwayat" },
        ].map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
              tab === t.id ? "bg-blue-600 text-white" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Rekam Baru */}
      {tab === "new" && (
        <div className="space-y-4">
          {/* Info form */}
          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <h3 className="text-sm font-semibold text-gray-200 mb-4">Informasi Rapat</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Judul Rapat</label>
                <input
                  type="text"
                  placeholder="Contoh: Rapat Koordinasi IT"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1.5">Peserta</label>
                <input
                  type="text"
                  placeholder="Nama peserta, pisahkan dengan koma"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-gray-200 placeholder-gray-600 outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            </div>
          </div>

          {/* Record / Upload */}
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-5 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 border border-red-500/30 mx-auto mb-3">
                <Mic size={28} className="text-red-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Rekam Langsung</p>
              <p className="text-xs text-gray-600 mb-4">Rekam audio rapat secara real-time</p>
              <button className="w-full rounded-lg bg-red-600 hover:bg-red-700 text-white text-sm font-medium py-2 transition-colors">
                Mulai Rekam
              </button>
            </div>

            <div className="rounded-xl border border-dashed border-gray-700 bg-gray-900 p-5 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-blue-500/10 border border-blue-500/30 mx-auto mb-3">
                <Upload size={28} className="text-blue-400" />
              </div>
              <p className="text-sm font-medium text-gray-200 mb-1">Upload Audio</p>
              <p className="text-xs text-gray-600 mb-4">MP3, WAV, M4A — maks 100MB</p>
              <button className="w-full rounded-lg border border-blue-600 text-blue-400 hover:bg-blue-600/10 text-sm font-medium py-2 transition-colors">
                Pilih File
              </button>
            </div>
          </div>

          {/* AI Generate */}
          <div className="rounded-xl border border-purple-500/30 bg-purple-500/5 p-5">
            <div className="flex items-center gap-3 mb-3">
              <Sparkles size={18} className="text-purple-400" />
              <h3 className="text-sm font-semibold text-gray-200">Generate MOM dengan AI</h3>
            </div>
            <p className="text-xs text-gray-500 mb-4">
              AI akan otomatis membuat transkrip, meringkas poin penting, dan menghasilkan Minutes of Meeting.
            </p>
            <button className="flex items-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium px-4 py-2 transition-colors">
              <Sparkles size={14} />Generate MOM
            </button>
          </div>
        </div>
      )}

      {/* Tab: Riwayat */}
      {tab === "history" && (
        <div className="rounded-xl border border-gray-800 bg-gray-900">
          <div className="px-5 py-4 border-b border-gray-800">
            <h3 className="text-sm font-semibold text-gray-200">Riwayat Meeting Notes</h3>
          </div>
          <div className="divide-y divide-gray-800">
            {history.map((item) => (
              <div key={item.id} className="flex items-center justify-between px-5 py-4 hover:bg-gray-800/40 transition-colors">
                <div className="flex items-center gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-500/10 border border-purple-500/20">
                    <FileText size={16} className="text-purple-400" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-200">{item.title}</p>
                    <div className="flex items-center gap-3 mt-0.5">
                      <span className="flex items-center gap-1 text-xs text-gray-500">
                        <Clock size={11} />{item.date}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-gray-500">
                        <Mic size={11} />{item.duration}
                      </span>
                      <span className="flex items-center gap-1 text-xs text-gray-500">
                        <Users size={11} />{item.participants} peserta
                      </span>
                    </div>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button className="flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-xs text-gray-400 hover:text-gray-200 transition-colors">
                    <Copy size={12} />Salin
                  </button>
                  <button className="flex items-center gap-1 rounded-md bg-blue-600 hover:bg-blue-700 px-2.5 py-1.5 text-xs text-white transition-colors">
                    <Download size={12} />Download
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
