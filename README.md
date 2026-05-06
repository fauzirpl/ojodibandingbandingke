# 🚀 InfraSync AI: Fuzzy Matcher & AI Validator

**InfraSync AI** adalah aplikasi web berkinerja tinggi untuk mencocokkan data program/kegiatan infrastruktur Pekerjaan Umum (SDA, Bina Marga, Cipta Karya) menggunakan algoritma **Fuzzy Matching** dan verifikasi tingkat lanjut berbasis **AI (LLM)**.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-yellow.svg)
![React](https://img.shields.io/badge/react-18+-61dafb.svg)
![FastAPI](https://img.shields.io/badge/fastapi-latest-05998b.svg)

## ✨ Fitur Utama

-   **Dual-Source Ingestion**: Upload dua file (CSV/Excel) sebagai Master dan Target.
-   **Dynamic Column Mapping**: Hubungkan kolom mana saja dari kedua sumber secara interaktif.
-   **High-Speed Fuzzy Matching**: Menggunakan pustaka `RapidFuzz` untuk pencocokan semantik teks yang sangat cepat.
-   **AI-Powered Verification**: Verifikasi otomatis menggunakan AI (via OpenRouter) untuk menganalisis substansi teknis bidang Pekerjaan Umum (misal: membedakan "Rehab" dan "Pembangunan Baru").
-   **Atomic Export**: Download hasil matching dalam format Excel yang sudah di-styling rapi.
-   **Secure Proxy**: Keamanan API Key terjamin dengan sistem proxy melalui backend.

## 🧠 Cara Kerja (How It Works)

Sistem ini menggunakan pendekatan tiga lapis untuk memastikan akurasi data yang maksimal:

1.  **Normalization & Abbreviation Handling**:
    Sistem membersihkan teks dari karakter khusus dan melakukan ekspansi singkatan teknis otomatis (misal: *Rehab* → *Rehabilitasi*, *DI* → *Daerah Irigasi*) berdasarkan kamus istilah Pekerjaan Umum.

2.  **Hybrid Semantic Retrieval**:
    Mencari kandidat pasangan menggunakan perpaduan dua algoritma:
    -   **Fuzzy Matching (60%)**: Menangani kesalahan penulisan (*typo*) dan urutan kata yang berbeda.
    -   **TF-IDF Cosine Similarity (40%)**: Menganalisis kemiripan konteks berdasarkan frekuensi kata penting.
    
3.  **AI Expert Verification (LLM)**:
    Kandidat terbaik hasil *Fuzzy* akan divalidasi oleh AI yang berperan sebagai *Ahli Perencana Wilayah*. AI mengecek apakah secara substansi teknis dua kegiatan tersebut memang sama (misal: membedakan antara "Pemeliharaan Jalan" dan "Peningkatan Jalan" yang seringkali mirip secara teks tapi berbeda secara anggaran).

## 🛠️ Tech Stack

### Backend
-   **FastAPI**: Framework web Python modern dan cepat.
-   **Pandas & OpenPyXL**: Pengolahan data dan spreadsheet.
-   **RapidFuzz**: String matching tingkat lanjut.
-   **OpenRouter API**: Integrasi LLM (DeepSeek, Gemini, dll).

### Frontend
-   **React + Vite**: Library UI dan build tool yang kilat.
-   **Framer Motion**: Animasi UI yang halus dan premium.
-   **Lucide React**: Icon set yang modern.
-   **Axios**: Penanganan request API.

---

## ⚙️ Panduan Instalasi

Pastikan Anda sudah menginstall **Python 3.10+** dan **Node.js 18+**.

### 1. Persiapan Backend
```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

Buat file `.env` di dalam folder `backend/`:
```env
API_KEY="isi_key_openrouter_anda"
END_POINT="https://openrouter.ai/api/v1/chat/completions"
AI_MODEL="deepseek/deepseek-v3"
```

### 2. Persiapan Frontend
```bash
cd frontend
npm install
```

---

## 🚀 Menjalankan Aplikasi

### Run Backend
```bash
cd backend
uvicorn main:app --reload
```
Backend akan berjalan di `http://localhost:8000`.

### Run Frontend
```bash
cd frontend
npm run dev
```
Buka browser di `http://localhost:5173`.

---

## 🌐 Deployment (VPS)

Proyek ini dilengkapi dengan **GitHub Actions** untuk deploy otomatis ke VPS via SSH. 

**Requirements untuk GitHub Secrets:**
- `SSH_HOST`: IP Address VPS.
- `SSH_USERNAME`: User login VPS.
- `SSH_KEY`: Private SSH Key.
- `TARGET_DIR`: Path folder aplikasi di VPS.

Cek file `.github/workflows/deploy.yml` untuk detail alur build dan swap-nya.

---

## 🛡️ Keamanan (Security)
-   **Zero Secret Leak**: API Key tidak pernah dikirim ke browser.
-   **Rate Limiting**: Disarankan memasang Nginx sebagai reverse proxy dengan rate limit di VPS.
-   **Internal Validation**: Validasi syntax dilakukan di level CI sebelum deploy.

## 📄 Lisensi
MIT License - Bebas digunakan untuk keperluan pengembangan internal maupun komersial.
