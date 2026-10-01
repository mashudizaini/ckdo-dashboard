// Membuka aplikasi lain di jendela sempit yang menempel di tepi kanan layar,
// bukan tab baru — supaya dashboard tetap terlihat di sebelahnya.
//
// Kenapa jendela popup dan bukan panel <iframe> di dalam halaman: Gemini (dan
// hampir semua layanan Google) mengirim header yang melarang dirinya
// ditampilkan di dalam frame situs lain. Panel iframe akan selalu tampil
// kosong, tanpa pesan error yang jelas. Jendela terpisah adalah satu-satunya
// cara yang benar-benar bekerja.
//
// Batasnya jujur saja: ini jendela sistem operasi yang berdiri sendiri, bukan
// panel yang menempel. Ia tidak ikut bergerak kalau jendela browser
// dipindahkan, dan browser yang disetel "buka popup sebagai tab baru" akan
// mengabaikan ukuran serta posisinya.

const WIDTH = 480;

export function openSidePopup(url, name) {
  // Lebar tetap 480px, tapi jangan sampai menutupi layar sempit.
  const width = Math.min(WIDTH, Math.round(window.screen.availWidth * 0.45));
  const height = window.screen.availHeight;
  const left = window.screen.availWidth - width;

  // `name` dipakai berulang dengan sengaja: klik kedua memakai jendela yang
  // sama, bukan menumpuk jendela baru tiap kali.
  const features = `width=${width},height=${height},left=${left},top=0,resizable=yes,scrollbars=yes`;
  let win = window.open(url, name, features);

  // Sebagian pemblokir popup menolak window.open yang membawa daftar fitur,
  // tapi masih mengizinkan yang tanpa fitur. Daripada tidak terjadi apa-apa
  // saat diklik, buka saja tanpa pengaturan ukuran.
  if (!win) win = window.open(url, name);
  if (win) win.focus();
  return win;
}

// Gemini: akun Workspace karyawan sudah termasuk Gemini berbayar, jadi tidak
// ada yang perlu disiapkan selain login Google yang memang sudah ada.
//
// `authuser` hanya PETUNJUK akun, bukan jaminan: berguna saat seseorang login
// ke beberapa akun Google sekaligus (mis. akun pribadi lebih dulu), dan
// diabaikan kalau akun itu belum login — Google akan menampilkan pemilih akun
// seperti biasa. Parameter dihilangkan sama sekali kalau email tidak diketahui,
// supaya tidak mengirim `authuser=` kosong yang justru membingungkan Google.
export function openGemini(email) {
  const url = email
    ? `https://gemini.google.com/app?authuser=${encodeURIComponent(email)}`
    : "https://gemini.google.com/app";
  return openSidePopup(url, "gemini");
}
