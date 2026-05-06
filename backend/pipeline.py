import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process
from unidecode import unidecode
import re
import time
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from scipy.sparse import csr_matrix

class FuzzyMatcherPipeline:
    def __init__(self, threshold=80, top_k=3, ai_validator=None):
        self.threshold = threshold
        self.top_k = top_k
        self.stop_words = ['pembangunan', 'pemeliharaan', 'rehabilitasi', 'peningkatan', 'pengadaan', 'jasa', 'konstruksi']
        self.abbreviations = self._load_abbreviations()
        self.ai_validator = ai_validator

    def _load_abbreviations(self):
        file_path = "abbreviation_map_pekerjaan_umum.csv"
        if not os.path.exists(file_path):
            print(f"Warning: {file_path} not found.")
            return []
        
        try:
            df = pd.read_csv(file_path)
            # Filter rows with valid regex and expansion
            df = df.dropna(subset=['regex_pattern', 'ekspansi_standar'])
            
            # Pre-compile regex for performance
            compiled = []
            for _, row in df.iterrows():
                try:
                    pattern = re.compile(row['regex_pattern'], flags=re.IGNORECASE)
                    compiled.append((pattern, row['ekspansi_standar'].lower()))
                except re.error:
                    continue
            return compiled
        except Exception as e:
            print(f"Error loading abbreviations: {e}")
            return []

    def normalize(self, text):
        if not isinstance(text, str):
            return ""
        # Unidecode and lower
        text = unidecode(text).lower()
        
        # Apply abbreviations using pre-compiled regex
        for pattern, expansion in self.abbreviations:
            text = pattern.sub(expansion, text)

        # Remove special characters
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def clean_for_blocking(self, text):
        # Remove common construction stop words for better blocking
        words = text.split()
        filtered = [w for w in words if w not in self.stop_words]
        return " ".join(filtered) if filtered else text

    def run(self, df_left, df_right, cols_left, cols_right, ai_config=None):
        start_time = time.time()
        
        # Ensure we have lists
        if isinstance(cols_left, str): cols_left = [cols_left]
        if isinstance(cols_right, str): cols_right = [cols_right]

        # Add temporary ID to preserve order and ensure 1:1 mapping
        df_left = df_left.copy()
        df_left['_row_id'] = range(len(df_left))
        
        # 1. Preprocessing
        print(f"Preprocessing with columns: {cols_left} vs {cols_right}...")
        
        def combine_cols(row, cols):
            return " ".join([self.normalize(str(row[c])) for c in cols if pd.notnull(row[c])])

        df_left['_norm'] = df_left.apply(lambda r: combine_cols(r, cols_left), axis=1)
        df_right_proc = df_right.copy()
        df_right_proc['_norm'] = df_right_proc.apply(lambda r: combine_cols(r, cols_right), axis=1)
        
        # 2. Exact Match (Pick first match to keep 1:1)
        print("Finding exact matches...")
        
        # Prepare right side for merge (drop duplicate norms to avoid row expansion)
        df_right_exact = df_right_proc.drop_duplicates('_norm').copy()
        df_right_exact.columns = [f"{c}_right" if c != '_norm' else c for c in df_right_exact.columns]
        
        df_left_merge = df_left.copy()
        df_left_merge.columns = [f"{c}_left" if c not in ['_norm', '_row_id'] else c for c in df_left_merge.columns]

        # Left join to keep all rows from A
        merged = pd.merge(df_left_merge, df_right_exact, on='_norm', how='left')
        
        # Identify rows that matched exactly
        matched_mask = merged['_norm_right'].notnull() if '_norm_right' in merged.columns else pd.Series([False]*len(merged))
        
        exact_matches = merged[matched_mask].copy()
        exact_matches['score'] = 100
        exact_matches['match_type'] = 'Exact'
        
        # 3. Fuzzy Match for remaining
        remaining_left_indices = merged[~matched_mask]['_row_id'].tolist()
        
        if not remaining_left_indices:
            final_df = exact_matches
        else:
            remaining_left = df_left[df_left['_row_id'].isin(remaining_left_indices)].copy()
            # We use all of B for fuzzy matching targets
            remaining_right = df_right_proc.copy()
            
            print(f"Fuzzy matching {len(remaining_left)} remaining rows...")
            
            fuzzy_results = []
            
            # 1. Initialize TF-IDF with Word-level vectorization (better for technical terms)
            vectorizer = TfidfVectorizer(
                analyzer='word',
                ngram_range=(1, 2), # Unigrams and Bigrams
                stop_words=self.stop_words,
                strip_accents='unicode'
            )
            
            # Fit on both tables
            corpus = pd.concat([remaining_left['_norm'], df_right_proc['_norm']])
            vectorizer.fit(corpus)
            
            matrix_a = vectorizer.transform(remaining_left['_norm'])
            matrix_b = vectorizer.transform(df_right_proc['_norm'])
            
            # Pre-calculate Cosine Similarity matrix
            from sklearn.metrics.pairwise import cosine_similarity
            print(f"Running Hybrid AI Retrieval (TF-IDF + Fuzzy) for {len(remaining_left)} rows...")
            
            choices = df_right_proc['_norm'].tolist()
            
            for i, (idx_a, row) in enumerate(remaining_left.iterrows()):
                query = row['_norm']
                
                # --- HYBRID RETRIEVAL ---
                # A. TF-IDF Cosine Similarity (Fast)
                cosine_scores = cosine_similarity(matrix_a[i], matrix_b).flatten()
                
                # B. Fuzzy Token Set Ratio (Accurate for word overlap)
                # We only run fuzzy on top 100 cosine candidates to keep it fast
                candidate_indices = np.argsort(cosine_scores)[::-1][:100]
                
                final_candidates = []
                for idx_b in candidate_indices:
                    # Combined Score: Average of Cosine (scaled to 100) and Fuzzy
                    f_score = fuzz.token_set_ratio(query, choices[idx_b])
                    c_score = int(cosine_scores[idx_b] * 100)
                    
                    # HYBRID CALCULATION
                    hybrid_score = (f_score * 0.6) + (c_score * 0.4)
                    
                    # HARDCODED THRESHOLD: We set this low (30) to ensure high recall.
                    # We don't want the initial filter to be strict.
                    if hybrid_score >= 30:
                        final_candidates.append({
                            'idx': idx_b,
                            'score': int(hybrid_score),
                            'c_score': c_score,
                            'f_score': f_score
                        })
                
                if final_candidates:
                    # Sort by hybrid score and take Top K for AI to judge
                    final_candidates = sorted(final_candidates, key=lambda x: x['score'], reverse=True)[:self.top_k]
                    
                    for cand in final_candidates:
                        row_right = df_right_proc.iloc[cand['idx']]
                        merged_row = {**{f"{k}_left": v for k, v in row.items() if not k.startswith('_')}, 
                                     **{f"{k}_right": v for k, v in row_right.items() if not k.startswith('_')}}
                        merged_row['score'] = cand['score']
                        merged_row['match_type'] = 'Semantic Candidate'
                        merged_row['_row_id'] = row['_row_id'] 
                        fuzzy_results.append(merged_row)
                else:
                    # No candidates found
                    merged_row = {f"{k}_left": v for k, v in row.items() if not k.startswith('_')}
                    merged_row['score'] = 0
                    merged_row['match_type'] = None
                    merged_row['_row_id'] = row['_row_id']
                    fuzzy_results.append(merged_row)
            
            fuzzy_df = pd.DataFrame(fuzzy_results)
            
    def run_ai_reranking(self, fuzzy_df, ai_config):
        """Separate method to run AI reranking on an existing candidate dataframe."""
        if not self.ai_validator or fuzzy_df.empty or ai_config is None:
            return fuzzy_df

        # Ensure AI columns exist with correct types
        for col in ['ai_score', 'ai_status', 'ai_reason']:
            if col not in fuzzy_df.columns:
                fuzzy_df[col] = 0.0 if col == 'ai_score' else '-'

        # We verify all semantic candidates that have a minimum retrieval score of 50
        to_verify = fuzzy_df[
            (fuzzy_df['match_type'].isin(['Semantic Candidate', 'AI Search Candidate'])) & 
            (fuzzy_df['score'] >= 50)
        ].copy()
        print(f"AI: Found {len(to_verify)} candidates (Score >= 50) for AI reranking.")
        
        if not to_verify.empty:
            records_to_ai = []
            for idx, row in to_verify.iterrows():
                sumber_a = {k.replace('_left', ''): v for k, v in row.items() if k.endswith('_left') and not k.startswith('_')}
                sumber_b = {k.replace('_right', ''): v for k, v in row.items() if k.endswith('_right') and not k.startswith('_')}
                
                records_to_ai.append({
                    "id": str(idx),
                    "sumber_a": sumber_a,
                    "sumber_b": sumber_b,
                    "skor_retrieval": row.get('score', 0)
                })
            
            # Process in parallel batches
            try:
                ai_results = self.ai_validator.validate_pairs(records_to_ai, config=ai_config)
            except Exception as e:
                print(f"AI batch error: {e}")
                ai_results = []
            
            # Map results back
            for res in ai_results:
                try:
                    idx = int(res['id'])
                    status = res.get('status', 'TIDAK_COCOK')
                    score_akhir = res.get('skor_akhir', 0)
                    alasan = res.get('alasan', '')
                    catatan = res.get('catatan_teknis', '')
                    
                    fuzzy_df.at[idx, 'ai_score'] = score_akhir
                    fuzzy_df.at[idx, 'ai_status'] = status
                    fuzzy_df.at[idx, 'ai_reason'] = f"{alasan} {catatan}".strip()
                except:
                    continue

        # SELECTION LOGIC: Pick the best candidate for each original row from A
        status_priority = {'COCOK': 3, 'PERLU_VERIFIKASI': 2, 'TIDAK_COCOK': 1, '-': 0, 'AI_TIMEOUT/ERROR': 0}
        fuzzy_df['priority'] = fuzzy_df['ai_status'].map(lambda x: status_priority.get(x, 0))
        
        # Sort: Priority > AI Score > Retrieval Score
        fuzzy_df = fuzzy_df.sort_values(
            ['_row_id', 'priority', 'ai_score', 'score'], 
            ascending=[True, False, False, False]
        )
        fuzzy_df = fuzzy_df.drop_duplicates(subset=['_row_id'], keep='first')
        
        # Update match_type for the winners
        def finalize_match_type(row):
            if row['ai_status'] == 'COCOK': return 'AI Verified'
            if row['ai_status'] == 'PERLU_VERIFIKASI': return 'AI Review Needed'
            if row['ai_status'] == 'TIDAK_COCOK': return 'AI Rejected'
            return 'AI Search Result'
        
        fuzzy_df['match_type'] = fuzzy_df.apply(finalize_match_type, axis=1)
        if 'priority' in fuzzy_df.columns:
            fuzzy_df = fuzzy_df.drop(columns=['priority'])
            
        return fuzzy_df

    def run(self, df_left, df_right, cols_left, cols_right, ai_config=None, use_ai=True):
        start_time = time.time()
        
        # Ensure we have lists
        if isinstance(cols_left, str): cols_left = [cols_left]
        if isinstance(cols_right, str): cols_right = [cols_right]

        # Add temporary ID to preserve order and ensure 1:1 mapping
        df_left = df_left.copy()
        df_left['_row_id'] = range(len(df_left))
        
        # 1. Preprocessing
        print(f"Preprocessing with columns: {cols_left} vs {cols_right}...")
        
        def combine_cols(row, cols):
            return " ".join([self.normalize(str(row[c])) for c in cols if pd.notnull(row[c])])

        df_left['_norm'] = df_left.apply(lambda r: combine_cols(r, cols_left), axis=1)
        df_right_proc = df_right.copy()
        df_right_proc['_norm'] = df_right_proc.apply(lambda r: combine_cols(r, cols_right), axis=1)
        
        # 2. Exact Match
        df_right_exact = df_right_proc.drop_duplicates('_norm').copy()
        df_right_exact.columns = [f"{c}_right" if c != '_norm' else c for c in df_right_exact.columns]
        df_left_merge = df_left.copy()
        df_left_merge.columns = [f"{c}_left" if c not in ['_norm', '_row_id'] else c for c in df_left_merge.columns]

        merged = pd.merge(df_left_merge, df_right_exact, on='_norm', how='left')
        matched_mask = merged['_norm_right'].notnull() if '_norm_right' in merged.columns else pd.Series([False]*len(merged))
        
        exact_matches = merged[matched_mask].copy()
        exact_matches['score'] = 100
        exact_matches['match_type'] = 'Exact Match'
        
        remaining_left = df_left[~df_left['_row_id'].isin(exact_matches['_row_id'])].copy()
        
        if remaining_left.empty:
            final_df = exact_matches
        else:
            # 3. Hybrid Semantic Retrieval
            fuzzy_results = []
            vectorizer = TfidfVectorizer(analyzer='word', ngram_range=(1, 2), stop_words=self.stop_words, strip_accents='unicode')
            corpus = pd.concat([remaining_left['_norm'], df_right_proc['_norm']])
            vectorizer.fit(corpus)
            
            matrix_a = vectorizer.transform(remaining_left['_norm'])
            matrix_b = vectorizer.transform(df_right_proc['_norm'])
            
            from sklearn.metrics.pairwise import cosine_similarity
            choices = df_right_proc['_norm'].tolist()
            
            for i, (idx_a, row) in enumerate(remaining_left.iterrows()):
                query = row['_norm']
                cosine_scores = cosine_similarity(matrix_a[i], matrix_b).flatten()
                candidate_indices = np.argsort(cosine_scores)[::-1][:100]
                
                final_candidates = []
                for idx_b in candidate_indices:
                    f_score = fuzz.token_set_ratio(query, choices[idx_b])
                    c_score = int(cosine_scores[idx_b] * 100)
                    hybrid_score = (f_score * 0.6) + (c_score * 0.4)
                    if hybrid_score >= 30:
                        final_candidates.append({'idx': idx_b, 'score': int(hybrid_score)})
                
                if final_candidates:
                    final_candidates = sorted(final_candidates, key=lambda x: x['score'], reverse=True)[:20]
                    for cand in final_candidates:
                        row_right = df_right_proc.iloc[cand['idx']]
                        merged_row = {**{f"{k}_left": v for k, v in row.items() if not k.startswith('_')}, 
                                     **{f"{k}_right": v for k, v in row_right.items() if not k.startswith('_')}}
                        merged_row['score'] = cand['score']
                        merged_row['match_type'] = 'Semantic Candidate'
                        merged_row['_row_id'] = row['_row_id'] 
                        fuzzy_results.append(merged_row)
                else:
                    merged_row = {f"{k}_left": v for k, v in row.items() if not k.startswith('_')}
                    merged_row['score'] = 0
                    merged_row['match_type'] = None
                    merged_row['_row_id'] = row['_row_id']
                    fuzzy_results.append(merged_row)
            
            fuzzy_df = pd.DataFrame(fuzzy_results)
            
            # Step 2: Return Top 5 candidates for Frontend to process
            if not fuzzy_df.empty:
                fuzzy_df = fuzzy_df.sort_values(['_row_id', 'score'], ascending=[True, False])
                fuzzy_df = fuzzy_df.groupby('_row_id').head(5).reset_index(drop=True)
                fuzzy_df['match_type'] = 'AI Search Candidate'
            
            # Initialize AI columns with empty values for display
            for col in ['ai_score', 'ai_status', 'ai_reason']:
                fuzzy_df[col] = 0 if col == 'ai_score' else '-'
                if col not in exact_matches.columns:
                    exact_matches[col] = '-' if col != 'ai_score' else 100
            
            exact_matches['match_type'] = 'Exact Match'
            final_df = pd.concat([exact_matches, fuzzy_df], ignore_index=True)
        
        final_df = final_df.sort_values('_row_id')
        # Keep _row_id for internal tracking (needed for Step 2 AI)
        cols_to_drop = [c for c in final_df.columns if '_norm' in c]
        final_df = final_df.drop(columns=cols_to_drop)
        return final_df
