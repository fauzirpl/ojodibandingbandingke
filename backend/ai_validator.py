import requests
import json
import os
import re
from typing import List, Dict

class AIValidator:
    def __init__(self, api_key: str, model: str = "deepseek/deepseek-v3"):
        self.api_key = api_key
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.system_prompt = """# PERSONA & KEAHLIAN
Kamu adalah Perencana Wilayah dan Kota Ahli Madya dengan spesialisasi
di bidang Pekerjaan Umum, mencakup tiga sub-bidang:
  - Sumber Daya Air (SDA): irigasi, drainase, embung, bendung,
    pengendalian banjir, air baku
  - Bina Marga (BM): jalan, jembatan, gorong-gorong, trotoar,
    manajemen lalu lintas
  - Cipta Karya (CK): sanitasi, air minum, persampahan, permukiman,
    bangunan gedung, ruang terbuka hijau, TPA, TPST, IPLT, IPAL, SPAM

# KONTEKS TUGAS
Kamu menerima daftar program/kegiatan/pekerjaan yang telah melewati pra-seleksi fuzzy matching.
Tugasmu adalah melakukan verifikasi pencocokan tingkat lanjut secara substantif.

# ATURAN KHUSUS DUPLIKAT
Di kolom [A] Kegiatan mungkin terdapat kegiatan yang duplikat (beberapa kandidat untuk satu input).
Tugasmu adalah menganalisis semua kandidat tersebut, namun prioritaskan/pilih yang lokasinya paling mirip dari segi provinsi dan kabupaten/kota sebagai hasil akhir.

# KRITERIA PENCOCOKAN (bobot substansi)
Evaluasi setiap pasangan berdasarkan:
  1. Kesamaan substansi teknis (50%) — apakah lingkup pekerjaan
     teknis yang dimaksud sama (mis. rehab saluran irigasi sekunder
     = pemeliharaan saluran irigasi sekunder → COCOK)
  2. Kesamaan lokasi (30%) — nama desa/kelurahan, kecamatan,
     ruas jalan, DI (Daerah Irigasi), atau nama badan air
  3. Kesesuaian bidang PU (20%) — pastikan tidak lintas sub-bidang
     (SDA ≠ BM ≠ CK kecuali ada alasan teknis)

# OUTPUT FORMAT (JSON array, tanpa teks lain)
[
  {
    "id": "string",
    "status": "COCOK" | "TIDAK_COCOK" | "PERLU_VERIFIKASI",
    "skor_akhir": 0.0,
    "alasan": "penjelasan singkat ≤2 kalimat teknis",
    "catatan_teknis": "opsional: perbedaan nomenklatur atau scope"
  }
]

# KETENTUAN PENTING
- Gunakan terminologi teknis PU yang lazim (SNI, Permen PUPR)
- Perbedaan nomenklatur yang lazim (mis. "rehab" vs "peningkatan")
  harus dianalisis substansinya, bukan hanya teksnya
- Jika lokasi ambigu (nama generik seperti "Sungai Besar"),
  tandai sebagai PERLU_VERIFIKASI
- Respons HANYA berisi JSON array, tidak ada teks preamble"""

    def _process_chunk(self, chunk: List[Dict], config: Dict = None) -> List[Dict]:
        """Internal helper to process a single batch of pairs."""
        custom_prompt = self.system_prompt
        if config and 'weights' in config:
            w = config['weights']
            custom_prompt += f"\n\n# CUSTOM CRITERIA WEIGHTS\nEvaluasi setiap pasangan berdasarkan bobot dinamis berikut:\n"
            custom_prompt += f"1. Kesamaan substansi teknis ({w.get('substansi', 40)}%)\n"
            custom_prompt += f"2. Kesamaan lokasi ({w.get('lokasi', 25)}%)\n"
            custom_prompt += f"3. Kesesuaian bidang PU ({w.get('bidang', 20)}%)\n"
            custom_prompt += f"4. Kesesuaian waktu & anggaran ({w.get('anggaran', 15)}%)\n"
            
        if config and 'mappings' in config:
            m = config['mappings']
            custom_prompt += f"\n\n# COLUMN CONTEXT MAPPING\nUntuk membantu analisis, gunakan pemetaan kolom berikut:\n"
            for key, cols in m.items():
                custom_prompt += f"- {key.capitalize()}: Merujuk pada kolom {', '.join(cols)}\n"

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": custom_prompt},
                {"role": "user", "content": json.dumps({"kandidat_pasangan": chunk}, ensure_ascii=False)}
            ],
            "temperature": 0.1,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fuzzysearch.app",
        }

        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                response = requests.post(self.url, headers=headers, data=json.dumps(data), timeout=120)
                response.raise_for_status()
                
                resp_json = response.json()
                if "choices" not in resp_json or not resp_json["choices"]:
                    raise ValueError(f"AI response missing choices: {resp_json}")
                    
                message = resp_json["choices"][0].get("message", {})
                content = message.get("content")
                
                if content is None:
                    # Some models return None if content is filtered or empty
                    raise ValueError("Respons AI kosong (None). Mungkin terkena filter konten.")
                
                # Robust JSON array extraction
                start_idx = content.find('[')
                end_idx = content.rfind(']')
                
                if start_idx != -1 and end_idx != -1:
                    json_str = content[start_idx:end_idx+1]
                    json_str = json_str.replace('\n', ' ').replace('\r', '')
                    # Fix trailing commas inside array and objects
                    json_str = re.sub(r',\s*\]', ']', json_str)
                    json_str = re.sub(r',\s*\}', '}', json_str)
                    return json.loads(json_str)
                
                raise ValueError(f"Tidak ditemukan array JSON. Konten Mentah: {content[:100]}...")
                
            except Exception as e:
                last_error = e
                print(f"Batch AI Gagal (Percobaan {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
        
        print(f"Batch AI Gagal Total setelah {max_retries} kali percobaan: {str(last_error)}")
        return [{"id": p['id'], "status": "ERROR", "skor_akhir": 0, "alasan": "AI gagal memberikan respons valid"} for p in chunk]

    def validate_pairs(self, pairs: List[Dict], config: Dict = None) -> List[Dict]:
        """
        Validates multiple pairs in parallel using batching.
        """
        if not pairs:
            return []

        # Batch size (adjust based on model token limits)
        batch_size = 5 
        chunks = [pairs[i:i + batch_size] for i in range(0, len(pairs), batch_size)]
        
        results = []
        from concurrent.futures import ThreadPoolExecutor
        
        print(f"AI: Processing {len(pairs)} pairs in {len(chunks)} parallel batches...")
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            # Map chunk processing to threads
            future_to_chunk = {executor.submit(self._process_chunk, chunk, config): chunk for chunk in chunks}
            
            for future in future_to_chunk:
                try:
                    batch_results = future.result()
                    if isinstance(batch_results, list):
                        results.extend(batch_results)
                except Exception as e:
                    print(f"Thread execution error: {e}")

        return results
