import React, { useState, useEffect } from 'react';
import axios from 'axios';
import {
  Upload, Play, Download, CheckCircle, FileText,
  AlertCircle, Loader2, Database, Brain, Sparkles,
  Search, CheckCircle2, PlusCircle, FileSpreadsheet,
  Zap, Settings, ArrowRightLeft, XCircle, Trash2
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? "http://localhost:8000" 
    : window.location.origin);

function App() {
  const [fileA, setFileA] = useState(null);
  const [fileB, setFileB] = useState(null);
  const [colsA, setColsA] = useState([]);
  const [colsB, setColsB] = useState([]);
  const [mappings, setMappings] = useState([{ a: '', b: '' }]);
  const [sessionA, setSessionA] = useState("");
  const [sessionB, setSessionB] = useState("");

  const [threshold, setThreshold] = useState(80);
  const [loadingPhase, setLoadingPhase] = useState(null); // null, 'search', 'ai'
  const [batchInfo, setBatchInfo] = useState(""); // Untuk info Batch 1/9
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [failedBatches, setFailedBatches] = useState([]); // Track failed rowIds for manual retry
  const [selectedExportCols, setSelectedExportCols] = useState([]);
  const [aiConfig, setAiConfig] = useState({
    weights: { substansi: 40, lokasi: 25, bidang: 20, anggaran: 15 },
    mappings: { substansi: [], lokasi: [], bidang: [], anggaran: [] }
  });
  const [useAi, setUseAi] = useState(false);
  const [isAiComplete, setIsAiComplete] = useState(false);
  const [progress, setProgress] = useState(0);
  const [aiSecret, setAiSecret] = useState({ key: '', model: '' });
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    axios.get(`${API_BASE}/config`).then(res => {
      setAiSecret({ key: '', model: res.data.ai_model }); // Key is now backend-only
    });

    // Check for existing session
    const savedResultId = localStorage.getItem('last_result_id');
    if (savedResultId) {
      axios.get(`${API_BASE}/get-result/${savedResultId}`)
        .then(res => {
          setResult(res.data);
          setIsAiComplete(res.data.is_ai_complete);
          if (res.data.export_cols) setSelectedExportCols(res.data.export_cols);
          if (res.data.ai_config) setAiConfig(res.data.ai_config);
        })
        .catch(() => {
          localStorage.removeItem('last_result_id');
        });
    }
  }, []);

  useEffect(() => {
    const aiCols = ['ai_score', 'ai_status', 'ai_reason'];
    if (useAi) {
      setSelectedExportCols(prev => [...new Set([...prev, ...aiCols])]);
    } else {
      setSelectedExportCols(prev => prev.filter(c => !aiCols.includes(c)));
    }
  }, [useAi]);

  const addMapping = () => setMappings([...mappings, { a: '', b: '' }]);
  const removeMapping = (index) => setMappings(mappings.filter((_, i) => i !== index));
  const updateMapping = (index, key, value) => {
    const next = [...mappings];
    next[index][key] = value;
    setMappings(next);
  };

  const loadResult = (id) => {
    setLoadingPhase('search');
    axios.get(`${API_BASE}/get-result/${id}`)
      .then(res => {
        setResult(res.data);
        setIsAiComplete(res.data.is_ai_complete);
        if (res.data.export_cols) setSelectedExportCols(res.data.export_cols);
        if (res.data.ai_config) setAiConfig(res.data.ai_config);
        if (res.data.mappings && res.data.mappings.length > 0) setMappings(res.data.mappings);
        localStorage.setItem('last_result_id', id);
        setShowHistory(false);
      })
      .catch(err => setError("Gagal memuat history: " + err.message))
      .finally(() => setLoadingPhase(null));
  };

  const fetchHistory = () => {
    axios.get(`${API_BASE}/list-results`)
      .then(res => setHistory(res.data))
      .catch(err => console.error("Gagal ambil history", err));
  };

  const deleteResult = (e, id) => {
    e.stopPropagation(); // Biar tidak trigger loadResult
    if (window.confirm("Hapus history ini secara permanen?")) {
      axios.delete(`${API_BASE}/delete-result/${id}`)
        .then(() => fetchHistory())
        .catch(err => alert("Gagal menghapus: " + err.message));
    }
  };

  useEffect(() => {
    const matchedCols = [];
    mappings.forEach(m => {
      if (m.a) matchedCols.push(`${m.a}_left`);
      if (m.b) matchedCols.push(`${m.b}_right`);
    });

    if (matchedCols.length > 0) {
      setSelectedExportCols(prev => {
        const next = [...prev];
        let changed = false;
        matchedCols.forEach(c => {
          if (!next.includes(c)) {
            next.push(c);
            changed = true;
          }
        });
        return changed ? next : prev;
      });
    }
  }, [mappings]);

  const handleUpload = (file, setCols, setSession, suffix) => {
    const formData = new FormData();
    formData.append('file', file);

    axios.post(`${API_BASE}/upload`, formData)
      .then(res => {
        setCols(res.data.columns);
        setSession(res.data.session_id);
        setSelectedExportCols(prev => [...new Set([...prev, 'score', 'match_type'])]);
      })
      .catch(err => setError("Gagal upload: " + err.message));
  };

  const startMatching = async () => {
    const validMappings = mappings.filter(m => m.a && m.b);
    if (!sessionA || !sessionB || validMappings.length === 0) {
      setError("Silakan pilih file dan tentukan minimal satu pasangan kolom.");
      return;
    }

    setLoadingPhase('search');
    setResult(null);
    setError(null);
    setIsAiComplete(false);

    const colsA = validMappings.map(m => m.a);
    const colsB = validMappings.map(m => m.b);

    const formData = new FormData();
    formData.append('session_left', sessionA);
    formData.append('session_right', sessionB);
    formData.append('cols_left', JSON.stringify(colsA));
    formData.append('cols_right', JSON.stringify(colsB));
    formData.append('mappings', JSON.stringify(validMappings));
    formData.append('threshold', threshold);
    formData.append('use_ai', 'false');

    if (selectedExportCols.length > 0) {
      formData.append('export_cols', JSON.stringify(selectedExportCols));
    }
    if (aiConfig) {
      formData.append('ai_config', JSON.stringify(aiConfig));
    }

    try {
      const res = await axios.post(`${API_BASE}/match`, formData);
      const matchData = res.data;

      // Set result so it's visible during AI processing
      setResult(matchData);
      localStorage.setItem('last_result_id', matchData.result_id);
      if (matchData.export_cols?.length > 0) setSelectedExportCols(matchData.export_cols);
      if (matchData.mappings?.length > 0) setMappings(matchData.mappings);

      setLoadingPhase(null);

      // ── Auto-trigger AI verification immediately ──
      await runAiVerification(null, matchData);

    } catch (err) {
      const msg = err.response?.data?.detail || err.message;
      setError("Gagal matching: " + msg);
      setLoadingPhase(null);
    }
  };

  // resultOverride: pre-loaded match data (when called right after startMatching)
  const runAiVerification = async (targetRowIds = null, resultOverride = null) => {
    const activeResult = resultOverride || result;
    if (!activeResult?.result_id) return;
    setLoadingPhase('ai');
    setProgress(0);
    setError(null);
    
    // Reset failed batches if this is a fresh run (not a retry)
    if (!targetRowIds) setFailedBatches([]);

    try {
      let candidates = activeResult.all_candidates || [];
      if (candidates.length === 0) {
        const fullRes = await axios.get(`${API_BASE}/all-candidates/${activeResult.result_id}`);
        candidates = fullRes.data;
        setResult(prev => ({ ...prev, all_candidates: candidates }));
      }

      const groups = {};
      candidates.forEach(c => {
        if (!groups[c._row_id]) groups[c._row_id] = [];
        groups[c._row_id].push(c);
      });

      const rowIds = targetRowIds || Object.keys(groups);
      const totalRows = rowIds.length;
      let processedRows = 0;
      let allProcessedData = [...candidates];

      const systemPrompt = `# PERSONA & KEAHLIAN
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
Hiraukan perkara anggaran dan volume

# ATURAN KHUSUS DUPLIKAT
Di kolom [A] Kegiatan mungkin terdapat kegiatan yang duplikat (beberapa kandidat untuk satu input).
Tugasmu adalah menganalisis semua kandidat tersebut, namun prioritaskan/pilih yang lokasinya paling mirip dari segi provinsi dan kabupaten/kota sebagai hasil akhir.

# KRITERIA PENCOCOKAN
Evaluasi setiap pasangan berdasarkan:
  1. Kesamaan substansi teknis (50%)
  2. Kesamaan lokasi (30%)
  3. Kesesuaian bidang PU (20%)

# OUTPUT FORMAT (JSON array saja)
[
  { "id": "string", "status": "COCOK" | "TIDAK_COCOK" | "PERLU_VERIFIKASI", "skor_akhir": 0.0, "alasan": "string" }
]`;

      const delay = (ms) => new Promise(res => setTimeout(res, ms));
      const batchSize = 5; 
      
      for (let i = 0; i < rowIds.length; i += batchSize) {
        const batchRowIds = rowIds.slice(i, i + batchSize);
        const batchPairs = [];

        batchRowIds.forEach(rid => {
          groups[rid].forEach((row, idx) => {
            const getCols = (suffix) => Object.fromEntries(Object.entries(row).filter(([k]) => k.endsWith(suffix)).map(([k, v]) => [k.replace(suffix, ''), v]));
            batchPairs.push({
              id: `${rid}|${idx}`,
              sumber_a: getCols('_left'),
              sumber_b: getCols('_right'),
              retrieval_score: row.score
            });
          });
        });

        const batchNum = Math.floor(i / batchSize) + 1;
        const totalBatches = Math.ceil(rowIds.length / batchSize);
        setBatchInfo(`Batch ${batchNum} / ${totalBatches}`);

        let success = false;
        let retries = 3;
        let responseData = null;

        while (retries > 0 && !success) {
          try {
            const formData = new FormData();
            formData.append('pairs', JSON.stringify(batchPairs));
            formData.append('ai_config', JSON.stringify(aiConfig));

            const response = await axios.post(`${API_BASE}/verify-chunk`, formData);
            
            if (response.data) {
              responseData = response.data; // Backend returns the list of results directly
              success = true;
            } else {
              retries--;
              if (retries > 0) await delay(2000 * (4-retries));
            }
          } catch (e) {
            retries--;
            if (retries > 0) await delay(2000 * (4-retries));
          }
        }

        if (!success) {
          console.error(`Batch ${batchNum} failed permanently.`);
          setFailedBatches(prev => [...new Set([...prev, ...batchRowIds])]);
          processedRows += batchRowIds.length;
          continue;
        }

        const aiResults = responseData; // Backend directly returns the array

        aiResults.forEach(aiRes => {
          const [rid, cidx] = aiRes.id.split('|');
          const targetRow = groups[rid][parseInt(cidx)];
          if (targetRow) {
            targetRow.ai_status = aiRes.status;
            targetRow.ai_score = aiRes.skor_akhir;
            targetRow.ai_reason = aiRes.alasan;
            // Successfully processed, remove from failed if it was there
            setFailedBatches(prev => prev.filter(fid => fid !== rid));
          }
        });

        processedRows += batchRowIds.length;
        setProgress(Math.round((processedRows / totalRows) * 100));
        setResult(prev => ({ ...prev, preview: allProcessedData.slice(0, 50) }));
        await delay(500);
      }

      // Re-run final selection
      const priority = { 'COCOK': 3, 'PERLU_VERIFIKASI': 2, 'TIDAK_COCOK': 1, '-': 0 };
      const finalPreview = [];
      const seenIds = new Set();

      [...allProcessedData].sort((a, b) => {
        if (a._row_id !== b._row_id) return a._row_id - b._row_id;
        const pA = priority[a.ai_status] || 0;
        const pB = priority[b.ai_status] || 0;
        if (pA !== pB) return pB - pA;
        return (b.ai_score || 0) - (a.ai_score || 0) || (b.score - a.score);
      }).forEach(c => {
        if (!seenIds.has(c._row_id)) {
          finalPreview.push(c);
          seenIds.add(c._row_id);
        }
      });

      setResult(prev => ({ ...prev, preview: finalPreview, is_ai_complete: true, all_candidates: allProcessedData }));
      setIsAiComplete(true);

      // Sync to backend for persistence
      const syncForm = new FormData();
      syncForm.append('data', JSON.stringify(allProcessedData));
      axios.post(`${API_BASE}/sync-result/${activeResult.result_id}`, syncForm);

    } catch (err) {
      console.error(err);
      setError("Gagal verifikasi AI: " + err.message);
    } finally {
      setLoadingPhase(null);
    }
  };


  const exportAiResults = async () => {
    if (!result?.preview || !isAiComplete) return;
    try {
      const formData = new FormData();
      formData.append('result_id', result.result_id);
      formData.append('data', JSON.stringify(result.preview));
      formData.append('columns', JSON.stringify(selectedExportCols));

      const response = await axios.post(`${API_BASE}/export-custom`, formData, {
        responseType: 'blob',
      });

      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'hasil_matching_ai_final.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError("Gagal ekspor hasil AI: " + err.message);
    }
  };

  const downloadInitialResult = async () => {
    if (!result?.result_id) return;
    try {
      const response = await axios.get(`${API_BASE}/download/${result.result_id}`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `preview_matching_${result.result_id.substring(0, 8)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err) {
      setError("Gagal mengunduh preview: " + err.message);
    }
  };

  const getScoreColor = (score) => {
    if (score >= 95) return 'score-high';
    if (score >= 80) return 'score-mid';
    return 'score-low';
  };

  return (
    <div className="container">
      {/* System Status Bar */}
      <div className="status-bar">
        <div style={{ display: 'flex', gap: '2rem' }}>
          <span>NODE: INFRA_MATCH_ST_4.0</span>
          <span>LATENCY: 12ms</span>
          <span>AUTH: [ ADMIN ]</span>
        </div>
        <div style={{ display: 'flex', gap: '1rem', color: 'var(--primary)' }}>
          <motion.span animate={{ opacity: [1, 0.4, 1] }} transition={{ repeat: Infinity, duration: 1.5 }}>
            ● SYSTEM_READY
          </motion.span>
          <span>{new Date().toLocaleTimeString()}</span>
        </div>
      </div>

      <div className="dashboard-grid">
        {/* Sidebar: Control Center */}
        <div className="sidebar">
          <div style={{ marginBottom: '1rem' }}>
            <h1 style={{ fontSize: '1.2rem', fontWeight: '800', color: '#fff', letterSpacing: '0.1em' }}>
              INFRA_SYNC_AI<span className="cursor-blink" />
            </h1>
          </div>

          {/* Session Manager Panel */}
          <div className="panel">
            <div className="panel-header">
              <Database size={16} />
              <span className="panel-title">Session Manager</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              <button 
                onClick={() => { setShowHistory(true); fetchHistory(); }}
                className="btn" 
                title="Buka History"
                style={{ 
                  flexDirection: 'column', 
                  height: '60px', 
                  fontSize: '0.65rem', 
                  background: 'rgba(56, 189, 248, 0.05)', 
                  border: '1px solid rgba(56, 189, 248, 0.2)',
                  color: 'var(--primary)'
                }}
              >
                <FileText size={18} style={{ marginBottom: '4px' }} />
                <span>HISTORY</span>
              </button>
              <button 
                onClick={() => { 
                  setResult(prev => prev ? { ...prev, preview: [], total_rows: 0, isCleared: true } : null);
                  localStorage.removeItem('last_result_id');
                }}
                className="btn" 
                title="Kosongkan Tabel"
                style={{ 
                  flexDirection: 'column', 
                  height: '60px', 
                  fontSize: '0.65rem', 
                  background: 'rgba(239, 68, 68, 0.05)', 
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  color: '#ef4444'
                }}
              >
                <Trash2 size={18} style={{ marginBottom: '4px' }} />
                <span>CLEAR</span>
              </button>
            </div>
          </div>

          {/* Upload Panel */}
          <div className="panel">
            <div className="panel-header">
              <Database size={16} />
              <span className="panel-title">Data Ingestion</span>
            </div>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div className="upload-box" onClick={() => document.getElementById('inputA').click()}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>SOURCE_A (MASTER)</div>
                <div style={{ fontSize: '0.75rem', fontWeight: '600' }}>{fileA ? fileA.name : "[ INJECT_A ]"}</div>
                <input id="inputA" type="file" hidden onChange={(e) => {
                  const file = e.target.files[0];
                  if (file) { setFileA(file); handleUpload(file, setColsA, setSessionA, 'left'); }
                }} />
              </div>

              <div className="upload-box" onClick={() => document.getElementById('inputB').click()}>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>SOURCE_B (TARGET)</div>
                <div style={{ fontSize: '0.75rem', fontWeight: '600' }}>{fileB ? fileB.name : "[ INJECT_B ]"}</div>
                <input id="inputB" type="file" hidden onChange={(e) => {
                  const file = e.target.files[0];
                  if (file) { setFileB(file); handleUpload(file, setColsB, setSessionB, 'right'); }
                }} />
              </div>
            </div>
          </div>

          {/* Mapping Panel */}
          {(colsA.length > 0 && colsB.length > 0) && (
            <div className="panel">
              <div className="panel-header">
                <Settings size={16} />
                <span className="panel-title">Logic Bridge</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {mappings.map((m, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    <select value={m.a} onChange={(e) => updateMapping(idx, 'a', e.target.value)} style={{ flex: 1 }}>
                      <option value="">SRC_A</option>
                      {colsA.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <ArrowRightLeft size={14} color="var(--primary)" />
                    <select value={m.b} onChange={(e) => updateMapping(idx, 'b', e.target.value)} style={{ flex: 1 }}>
                      <option value="">SRC_B</option>
                      {colsB.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    {mappings.length > 1 && (
                      <button 
                        onClick={() => removeMapping(idx)}
                        style={{ background: 'transparent', border: 'none', color: '#ef4444', padding: '4px', cursor: 'pointer' }}
                        title="Hapus relasi"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                ))}
                <button onClick={addMapping} className="btn" style={{ width: '100%', marginTop: '0.5rem' }}>
                  + Add Relation
                </button>
              </div>

              <button 
                onClick={startMatching} 
                disabled={loadingPhase || !sessionA || !sessionB}
                className="btn btn-primary"
                style={{ width: '100%', marginTop: '1.5rem', padding: '0.8rem' }}
              >
                {loadingPhase === 'search' ? '[ FUZZY MATCHING... ]' 
                  : loadingPhase === 'ai' ? '[ AI RANKING... ]'
                  : 'EXECUTE_PIPELINE'}
              </button>
            </div>
          )}

          {result && (
            <div className="panel">
              <div className="panel-header">
                <CheckCircle size={16} />
                <span className="panel-title">Export Config</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                {isAiComplete ? (
                  <button onClick={exportAiResults} className="btn btn-primary" style={{ gridColumn: 'span 2' }}>
                    FINAL_REPORT
                  </button>
                ) : (
                  <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {loadingPhase === 'ai' && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--primary)', textAlign: 'center', fontFamily: 'var(--font-mono)' }}>
                        AI RANKING {progress}% — {batchInfo}
                      </div>
                    )}
                    {failedBatches.length > 0 && (
                      <button 
                        onClick={() => runAiVerification(failedBatches)} 
                        disabled={loadingPhase === 'ai'} 
                        className="btn" 
                        style={{ background: '#7c2d12', color: '#fb923c', border: '1px solid #fb923c' }}
                      >
                        <AlertCircle size={16} />
                        <span>RETRY FAILED ({failedBatches.length})</span>
                      </button>
                    )}
                  </div>
                )}
                <button onClick={downloadInitialResult} className="btn" style={{ gridColumn: 'span 2' }}>
                  RAW_DUMP
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Main Content: Data Stream */}
        <div className="main-content">
          {result ? (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <div>
                  <h2 style={{ fontSize: '1.5rem', fontWeight: '800', letterSpacing: '0.05em' }}>DATA_STREAM_OUTPUT</h2>
                  <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Found {result.match_count} probable matches in cluster</p>
                </div>
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7rem', color: 'var(--primary)' }}>
                  RESULT_ID: {result.result_id.substring(0, 8)}...
                </div>
              </div>

              <div className="panel" style={{ padding: 0, overflow: 'hidden' }}>
                <table className="data-grid">
                  <thead>
                    <tr>
                      <th style={{ width: '100px' }}>VERDICT</th>
                      <th style={{ width: '80px' }}>CONF</th>
                      <th>MASTER_CLUSTER</th>
                      <th>TARGET_CLUSTER</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview.map((row, idx) => (
                      <tr key={idx}>
                        <td>
                          <span className={`status-badge ${
                            row.ai_status === 'COCOK' ? 'text-primary' : 
                            row.ai_status === 'PERLU_VERIFIKASI' ? 'text-accent' : 'text-muted'
                          }`}>
                            {row.ai_status || 'PENDING'}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontWeight: '700' }}>{row.score}%</td>
                        <td>
                          {Object.entries(row)
                            .filter(([k]) => k.endsWith('_left'))
                            .map(([k, v]) => (
                              <div key={k} style={{ fontSize: '0.75rem', marginBottom: '2px' }}>
                                <span style={{ color: '#64748b', marginRight: '4px' }}>{k.replace('_left', '')}:</span>
                                <span>{v}</span>
                              </div>
                            ))
                          }
                        </td>
                        <td>
                          {/* Render all B columns dynamically */}
                          {Object.entries(row)
                            .filter(([k]) => k.endsWith('_right') && !['_norm_right', 'score_right', 'match_type_right'].includes(k))
                            .map(([k, v]) => (
                              <div key={k} style={{ fontSize: '0.75rem', marginBottom: '4px', borderBottom: '1px solid #1e293b', paddingBottom: '2px' }}>
                                <span style={{ color: '#94a3b8', marginRight: '4px', fontWeight: '500' }}>
                                  {k.replace('_right', '')}:
                                </span> 
                                <span style={{ color: '#f1f5f9' }}>{v || <span style={{ color: '#475569' }}>-</span>}</span>
                              </div>
                            ))
                          }
                          {Object.keys(row).filter(k => k.endsWith('_right') && k !== '_norm_right').length === 0 && (
                            <span style={{ color: '#64748b', fontSize: '0.75rem', fontStyle: 'italic' }}>- No matching data -</span>
                          )}
                          {isAiComplete && row.ai_reason && (
                            <div style={{ marginTop: '0.5rem', fontSize: '0.7rem', color: 'var(--primary)', opacity: 0.7, fontStyle: 'italic' }}>
                              &gt;&gt; {row.ai_reason}
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>
          ) : (
            <div style={{ height: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', color: 'var(--border)' }}>
              <motion.div animate={{ opacity: [0.2, 0.5, 0.2] }} transition={{ repeat: Infinity, duration: 3 }}>
                <Zap size={64} />
                <p style={{ marginTop: '1rem', fontFamily: 'var(--font-mono)', letterSpacing: '0.2em' }}>AWAITING_INPUT_STREAM</p>
              </motion.div>
            </div>
          )}
        </div>
      </div>

      {/* Modern Terminal Loader */}
      <AnimatePresence>
        {loadingPhase && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            style={{ position: 'fixed', inset: 0, background: 'rgba(2, 4, 8, 0.98)', zIndex: 2000, display: 'flex', justifyContent: 'center', alignItems: 'center' }}
          >
            <div style={{ width: '400px', fontFamily: 'var(--font-mono)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', fontSize: '0.8rem' }}>
                <span className="text-primary">&gt; {loadingPhase.toUpperCase()}_ENGINE_ACTIVE</span>
                <span>{progress}%</span>
              </div>
              <div style={{ height: '2px', background: 'rgba(255,255,255,0.05)', position: 'relative', overflow: 'hidden' }}>
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: `${progress}%` }}
                  style={{ height: '100%', background: 'var(--primary)', boxShadow: '0 0 15px var(--primary)' }}
                />
              </div>
              <div style={{ marginTop: '1rem', fontSize: '0.7rem', color: '#4b5563', lineHeight: '1.5' }}>
                [ SYSTEM ] Analyzing semantic vectors...<br />
                [ ENGINE ] Cross-referencing data points...<br />
                [ AI ] {batchInfo || "Readying expert analysis layer..."}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* History Modal */}
      <AnimatePresence>
        {showHistory && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="modal-overlay"
            onClick={() => setShowHistory(false)}
            style={{ position: 'fixed', inset: 0, background: 'rgba(2, 4, 8, 0.85)', zIndex: 3000, display: 'flex', justifyContent: 'center', alignItems: 'center', padding: '2rem' }}
          >
            <motion.div 
              initial={{ scale: 0.9, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              className="panel"
              onClick={e => e.stopPropagation()}
              style={{ width: '100%', maxWidth: '600px', maxHeight: '80vh', overflowY: 'auto' }}
            >
              <div className="panel-header" style={{ position: 'sticky', top: 0, background: 'var(--panel-bg)', zIndex: 10 }}>
                <Database size={16} />
                <span className="panel-title">Matching History</span>
                <XCircle size={18} onClick={() => setShowHistory(false)} style={{ cursor: 'pointer', marginLeft: 'auto' }} />
              </div>
              
              <div style={{ padding: '1rem' }}>
                {history.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)' }}>Belum ada history tersimpan.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {history.map((item) => (
                      <div 
                        key={item.id} 
                        className="upload-box" 
                        style={{ 
                          textAlign: 'left', 
                          cursor: 'pointer', 
                          borderColor: result?.result_id === item.id ? 'var(--primary)' : 'var(--border)',
                          background: result?.result_id === item.id ? 'rgba(56, 189, 248, 0.05)' : 'transparent',
                          transition: 'all 0.2s ease'
                        }}
                        onClick={() => loadResult(item.id)}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: item.is_ai_complete ? 'var(--primary)' : '#4b5563' }} />
                            <span style={{ fontWeight: '700', color: '#fff', fontFamily: 'var(--font-mono)' }}>ID: {item.id.substring(0, 8)}</span>
                          </div>
                          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{new Date(item.date * 1000).toLocaleString()}</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            <span style={{ color: 'var(--primary)' }}>{item.match_count}</span> MATCHES_FOUND
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{ fontSize: '0.7rem', padding: '2px 8px', borderRadius: '4px', background: 'rgba(255,255,255,0.05)', color: item.is_ai_complete ? 'var(--primary)' : 'var(--text-muted)' }}>
                              {item.is_ai_complete ? 'AI_VERIFIED' : 'DRAFT_MODE'}
                            </div>
                            <button 
                              onClick={(e) => deleteResult(e, item.id)}
                              className="btn-icon" 
                              style={{ color: '#ef4444', padding: '4px', borderRadius: '4px', background: 'rgba(239, 68, 68, 0.1)' }}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default App;
