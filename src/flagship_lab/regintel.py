from __future__ import annotations

import math
import re
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .core import Database, append_audit_event, sha256_json


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for token in TOKEN_RE.findall(text):
        lowered = token.lower()
        if re.fullmatch(r"[\u4e00-\u9fff]+", lowered) and len(lowered) > 1:
            tokens.extend(lowered[i : i + 2] for i in range(len(lowered) - 1))
        else:
            tokens.append(lowered)
    return tokens


class RegIntelService:
    def __init__(self, db: Database):
        self.db = db

    def add_document(self, document_key: str, title: str, source_url: str, published_at: str, content: str) -> str:
        version_hash = sha256_json({"title": title, "published_at": published_at, "content": content})
        with self.db.connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO regulation_documents
                   (document_key,title,source_url,published_at,version_hash,content) VALUES (?,?,?,?,?,?)""",
                (document_key, title, source_url, published_at, version_hash, content),
            )
            append_audit_event(conn, "regintel", "DOCUMENT_VERSIONED", document_key, {"version_hash": version_hash})
        return version_hash

    def search(self, query: str, limit: int = 5) -> list[dict]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        with self.db.connect() as conn:
            rows = list(conn.execute("SELECT * FROM regulation_documents"))
        docs = [tokenize(row["title"] + " " + row["content"]) for row in rows]
        document_frequency = Counter(token for tokens in docs for token in set(tokens))
        scored = []
        for row, tokens in zip(rows, docs):
            counts = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                if counts[token]:
                    idf = math.log((len(rows) + 1) / (document_frequency[token] + 0.5)) + 1
                    score += (1 + math.log(counts[token])) * idf
            matched_query_terms = sum(1 for token in set(query_tokens) if counts[token])
            coverage = matched_query_terms / max(len(set(query_tokens)), 1)
            if score and coverage >= 0.5:
                snippet = self._best_snippet(row["content"], query_tokens)
                scored.append({
                    "document_key": row["document_key"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "published_at": row["published_at"],
                    "version_hash": row["version_hash"],
                    "score": round(score, 6),
                    "query_coverage": round(coverage, 6),
                    "snippet": snippet,
                })
        return sorted(scored, key=lambda x: (-x["score"], x["title"]))[:limit]

    def hybrid_search(self, query: str, limit: int = 5, lexical_weight: float = 0.55) -> list[dict]:
        if not 0 <= lexical_weight <= 1:
            raise ValueError("lexical_weight must be between 0 and 1")
        with self.db.connect() as conn:
            rows = list(conn.execute("SELECT * FROM regulation_documents ORDER BY id"))
        if not rows or not query.strip():
            return []
        lexical = {hit["version_hash"]: hit for hit in self.search(query, limit=len(rows))}
        lexical_max = max((hit["score"] for hit in lexical.values()), default=1.0)
        corpus = [row["title"] + " " + row["content"] for row in rows]
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1, sublinear_tf=True)
        matrix = vectorizer.fit_transform(corpus + [query])
        dense_scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()
        results = []
        for row, dense_score in zip(rows, dense_scores):
            lexical_hit = lexical.get(row["version_hash"])
            lexical_score = (lexical_hit["score"] / lexical_max) if lexical_hit else 0.0
            hybrid_score = lexical_weight * lexical_score + (1 - lexical_weight) * float(dense_score)
            if hybrid_score <= 0:
                continue
            results.append({
                "document_key": row["document_key"],
                "title": row["title"],
                "source_url": row["source_url"],
                "published_at": row["published_at"],
                "version_hash": row["version_hash"],
                "lexical_score": round(lexical_score, 6),
                "char_tfidf_score": round(float(dense_score), 6),
                "hybrid_score": round(hybrid_score, 6),
                "snippet": self._best_snippet(row["content"], tokenize(query)),
            })
        return sorted(results, key=lambda x: (-x["hybrid_score"], x["title"]))[:limit]

    def answer(self, query: str, minimum_score: float = 1.0) -> dict:
        hits = self.hybrid_search(query, limit=3)
        if not hits or hits[0]["hybrid_score"] < 0.12:
            return {"answer": "现有证据不足，拒绝生成结论。", "refused": True, "citations": []}
        answer = "根据已收录公开材料，可核验的信息包括：" + "；".join(hit["snippet"] for hit in hits)
        return {
            "answer": answer,
            "refused": False,
            "citations": [
                {k: hit[k] for k in ("title", "source_url", "published_at", "version_hash", "hybrid_score")}
                for hit in hits
            ],
        }

    def evaluate(self, cases: list[dict], k: int = 3) -> dict:
        if not cases:
            raise ValueError("evaluation cases cannot be empty")
        hits = 0
        reciprocal_rank = 0.0
        details = []
        for case in cases:
            relevant = set(case["relevant_keys"])
            ranked = [item["document_key"] for item in self.hybrid_search(case["query"], limit=k)]
            rank = next((index + 1 for index, key in enumerate(ranked) if key in relevant), None)
            hits += int(rank is not None)
            reciprocal_rank += 1 / rank if rank else 0
            details.append({"query": case["query"], "ranked": ranked, "first_relevant_rank": rank})
        return {
            "cases": len(cases),
            f"recall_at_{k}": round(hits / len(cases), 6),
            "mrr": round(reciprocal_rank / len(cases), 6),
            "details": details,
        }

    @staticmethod
    def _best_snippet(content: str, query_tokens: list[str], width: int = 140) -> str:
        lowered = content.lower()
        positions = [lowered.find(token) for token in query_tokens if lowered.find(token) >= 0]
        start = max(0, (min(positions) if positions else 0) - 30)
        return content[start : start + width].strip()
