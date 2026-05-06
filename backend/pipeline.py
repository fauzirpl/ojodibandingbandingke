import pandas as pd
import numpy as np
from rapidfuzz import fuzz
from unidecode import unidecode
import re
import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def sanitize_col(c):
    """Replace special characters in column names with underscores."""
    s = str(c).strip()
    # Preserve leading _ for internal cols
    if s.startswith('_'):
        return s
    return re.sub(r'[^a-zA-Z0-9_]', '_', s)


class FuzzyMatcherPipeline:
    def __init__(self, threshold=30, top_k=3, ai_validator=None):
        self.threshold = threshold
        self.top_k = top_k
        self.stop_words = ['pembangunan', 'pemeliharaan', 'rehabilitasi', 'peningkatan',
                           'pengadaan', 'jasa', 'konstruksi']
        self.abbreviations = self._load_abbreviations()
        self.ai_validator = ai_validator

    def _load_abbreviations(self):
        file_path = "abbreviation_map_pekerjaan_umum.csv"
        if not os.path.exists(file_path):
            return []
        try:
            df = pd.read_csv(file_path)
            df = df.dropna(subset=['regex_pattern', 'ekspansi_standar'])
            compiled = []
            for _, row in df.iterrows():
                try:
                    pattern = re.compile(row['regex_pattern'], flags=re.IGNORECASE)
                    compiled.append((pattern, row['ekspansi_standar'].lower()))
                except Exception:
                    continue
            return compiled
        except Exception:
            return []

    def normalize(self, text):
        if not isinstance(text, str):
            return ""
        text = unidecode(text).lower()
        for pattern, expansion in self.abbreviations:
            text = pattern.sub(expansion, text)
        text = re.sub(r'[^a-z0-9\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _build_row_right(self, base_row_dict, df_right_row, score, match_type):
        """Build a result row with _left and _right columns."""
        new_row = {k: v for k, v in base_row_dict.items()
                   if k.endswith('_left') or k == '_row_id'}
        for k, v in df_right_row.items():
            if k != '_norm':
                new_row[f"{k}_right"] = v
        new_row['score'] = score
        new_row['match_type'] = match_type
        return new_row

    def run(self, df_left, df_right, cols_left, cols_right, ai_config=None, use_ai=False):
        # ── 1. Sanitize columns ────────────────────────────────────────────────
        df_left = df_left.copy()
        df_left.rename(columns={c: sanitize_col(c) for c in df_left.columns}, inplace=True)
        cols_left = [sanitize_col(c) for c in cols_left]
        df_left['_row_id'] = range(len(df_left))

        df_right = df_right.copy()
        df_right.rename(columns={c: sanitize_col(c) for c in df_right.columns}, inplace=True)
        cols_right = [sanitize_col(c) for c in cols_right]

        # ── 2. Normalization ───────────────────────────────────────────────────
        def combine_cols(row, cols):
            parts = []
            for c in cols:
                if c in row and pd.notnull(row[c]):
                    parts.append(self.normalize(str(row[c])))
            return " ".join(parts)

        df_left['_norm'] = df_left.apply(lambda r: combine_cols(r, cols_left), axis=1)
        df_right['_norm'] = df_right.apply(lambda r: combine_cols(r, cols_right), axis=1)

        print(f"DEBUG run: A rows={len(df_left)}, B rows={len(df_right)}")
        print(f"DEBUG run: cols_left_sanitized={cols_left}")
        print(f"DEBUG run: cols_right_sanitized={cols_right}")
        print(f"DEBUG run: df_left cols={df_left.columns.tolist()}")
        print(f"DEBUG run: df_right cols={df_right.columns.tolist()}")
        
        # Check all requested cols actually exist
        missing_left = [c for c in cols_left if c not in df_left.columns]
        missing_right = [c for c in cols_right if c not in df_right.columns]
        if missing_left:
            print(f"WARNING: cols_left not found in df_left: {missing_left}")
            cols_left = [c for c in cols_left if c in df_left.columns]
        if missing_right:
            print(f"WARNING: cols_right not found in df_right: {missing_right}")
            cols_right = [c for c in cols_right if c in df_right.columns]

        df_left['_norm'] = df_left.apply(lambda r: combine_cols(r, cols_left), axis=1)
        df_right['_norm'] = df_right.apply(lambda r: combine_cols(r, cols_right), axis=1)

        print(f"DEBUG run: sample A norm='{df_left['_norm'].iloc[0]}'")
        print(f"DEBUG run: sample B norm='{df_right['_norm'].iloc[0]}'")

        # ── 3. Exact Match ─────────────────────────────────────────────────────
        df_right_exact = df_right.drop_duplicates('_norm').copy()
        df_right_exact.columns = [
            f"{c}_right" if c != '_norm' else c for c in df_right_exact.columns
        ]
        df_left_prep = df_left.copy()
        df_left_prep.columns = [
            f"{c}_left" if c not in ['_norm', '_row_id'] else c
            for c in df_left_prep.columns
        ]

        merged = pd.merge(df_left_prep, df_right_exact, on='_norm', how='left')

        right_cols_in_merged = [c for c in merged.columns if c.endswith('_right')]
        if right_cols_in_merged:
            exact_matched_mask = merged[right_cols_in_merged[0]].notnull()
        else:
            exact_matched_mask = pd.Series([False] * len(merged), index=merged.index)

        exact_df = merged[exact_matched_mask].copy()
        exact_df['score'] = 100
        exact_df['match_type'] = 'Exact Match'

        remaining_left = merged[~exact_matched_mask].copy()
        print(f"DEBUG run: exact={exact_matched_mask.sum()}, remaining={len(remaining_left)}")

        # ── 4. Fuzzy / Semantic Match ──────────────────────────────────────────
        if remaining_left.empty:
            final_results = exact_df
        else:
            fuzzy_results = []
            has_vectorizer = False
            matrix_a = matrix_b = None

            try:
                vectorizer = TfidfVectorizer(
                    analyzer='word', ngram_range=(1, 2),
                    stop_words=self.stop_words,
                    strip_accents='unicode', min_df=1
                )
                corpus = pd.concat([remaining_left['_norm'], df_right['_norm']])
                vectorizer.fit(corpus)
                matrix_a = vectorizer.transform(remaining_left['_norm'])
                matrix_b = vectorizer.transform(df_right['_norm'])
                has_vectorizer = True
                print(f"DEBUG TF-IDF OK, vocab={len(vectorizer.vocabulary_)}")
            except Exception as tfidf_err:
                print(f"DEBUG TF-IDF FAILED: {tfidf_err}")

            choices = df_right['_norm'].tolist()

            for i, (idx, row) in enumerate(remaining_left.iterrows()):
                query = row['_norm']
                candidates = []

                # Primary: TF-IDF + Cosine + Fuzzy hybrid
                if has_vectorizer and query:
                    try:
                        cosine_scores = cosine_similarity(matrix_a[i], matrix_b).flatten()
                        candidate_indices = np.argsort(cosine_scores)[::-1][:50]
                        for idx_b in candidate_indices:
                            f_score = fuzz.token_set_ratio(query, choices[idx_b])
                            c_score = int(cosine_scores[idx_b] * 100)
                            hybrid_score = (f_score * 0.6) + (c_score * 0.4)
                            if hybrid_score >= self.threshold:
                                candidates.append({'idx': idx_b, 'score': int(hybrid_score)})
                    except Exception as e:
                        print(f"DEBUG cosine error row {i}: {e}")

                # Fallback: ALWAYS return top-K even if below threshold
                # This prevents null values in TARGET_CLUSTER
                if not candidates:
                    all_scores = []
                    for idx_b, choice in enumerate(choices):
                        f_score = fuzz.token_set_ratio(query, choice) if query else 0
                        all_scores.append({'idx': idx_b, 'score': f_score})
                    all_scores.sort(key=lambda x: x['score'], reverse=True)
                    # Take top-K even if score is low — let AI reranking sort it out
                    candidates = all_scores[:self.top_k]
                    if candidates:
                        print(f"DEBUG fallback row {i}: best_score={candidates[0]['score']}")

                # Build result rows
                base = row.to_dict()
                if candidates:
                    for cand in candidates:
                        row_right = df_right.iloc[cand['idx']]
                        fuzzy_results.append(
                            self._build_row_right(base, row_right, cand['score'], 'Semantic Candidate')
                        )
                else:
                    # Absolutely no data (empty query)
                    new_row = {k: v for k, v in base.items() if k.endswith('_left') or k == '_row_id'}
                    new_row['score'] = 0
                    new_row['match_type'] = None
                    fuzzy_results.append(new_row)

            fuzzy_df = pd.DataFrame(fuzzy_results)
            final_results = pd.concat([exact_df, fuzzy_df], ignore_index=True)

        # ── 5. Cleanup ─────────────────────────────────────────────────────────
        for col in ['ai_score', 'ai_status', 'ai_reason']:
            if col not in final_results.columns:
                final_results[col] = 0 if col == 'ai_score' else '-'

        final_results = final_results.drop(
            columns=[c for c in final_results.columns if c.startswith('_norm')],
            errors='ignore'
        )
        return final_results.sort_values(['_row_id', 'score'], ascending=[True, False])

    def run_ai_reranking(self, df, ai_config):
        if not self.ai_validator or df.empty or ai_config is None:
            return (df.sort_values(['_row_id', 'score'], ascending=[True, False])
                    .drop_duplicates('_row_id'))

        to_verify = df[df['score'] >= 50].copy()
        if not to_verify.empty:
            records = []
            for idx, row in to_verify.iterrows():
                s_a = {k.replace('_left', ''): v for k, v in row.items() if k.endswith('_left')}
                s_b = {k.replace('_right', ''): v for k, v in row.items() if k.endswith('_right')}
                records.append({"id": str(idx), "sumber_a": s_a, "sumber_b": s_b})

            ai_results = self.ai_validator.validate_pairs(records, config=ai_config)
            for res in ai_results:
                try:
                    idx = int(res['id'])
                    df.at[idx, 'ai_score'] = res.get('skor_akhir', 0)
                    df.at[idx, 'ai_status'] = res.get('status', 'TIDAK_COCOK')
                    df.at[idx, 'ai_reason'] = (
                        f"{res.get('alasan', '')} {res.get('catatan_teknis', '')}".strip()
                    )
                except Exception:
                    continue

        if 'ai_status' not in df.columns:
            df['ai_status'] = '-'

        status_priority = {'COCOK': 3, 'PERLU_VERIFIKASI': 2, 'TIDAK_COCOK': 1, '-': 0}
        df['priority'] = df['ai_status'].map(lambda x: status_priority.get(x, 0))
        df = df.sort_values(
            ['_row_id', 'priority', 'ai_score', 'score'],
            ascending=[True, False, False, False]
        )
        df = df.drop_duplicates(subset=['_row_id'], keep='first')

        def finalize_type(row):
            if row['ai_status'] == 'COCOK':
                return 'AI Verified'
            if row['ai_status'] == 'PERLU_VERIFIKASI':
                return 'AI Review'
            if row['ai_status'] == 'TIDAK_COCOK':
                return 'AI Rejected'
            return row.get('match_type', '')

        df['match_type'] = df.apply(finalize_type, axis=1)
        return df.drop(columns=['priority'], errors='ignore')
