from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import joblib
import networkx as nx
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score


FEATURES = [
    "in_degree",
    "out_degree",
    "weighted_out",
    "unique_counterparties",
    "pagerank",
    "shared_account_count",
    "three_cycle_count",
    "night_activity_ratio",
]


@dataclass(frozen=True)
class TemporalDataset:
    x: np.ndarray
    y: np.ndarray
    months: np.ndarray
    entity_ids: np.ndarray
    feature_names: list[str]


def generate_temporal_graph_dataset(entities: int = 400, months: int = 12, seed: int = 20260811) -> TemporalDataset:
    if entities < 30 or months < 4:
        raise ValueError("dataset requires at least 30 entities and 4 months")
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    nodes = [f"ORG-{i:05d}" for i in range(entities)]
    latent_risk = {node: rng.random() < 0.05 for node in nodes}
    rows: list[list[float]] = []
    labels: list[int] = []
    time_values: list[int] = []
    entity_values: list[str] = []
    for month in range(1, months + 1):
        graph = nx.DiGraph()
        graph.add_nodes_from(nodes)
        cycle_counts = {node: 0 for node in nodes}
        for node in nodes:
            risky = latent_risk[node]
            edge_count = int(np_rng.poisson(2.0 + (5.0 if risky else 0.0)))
            for _ in range(edge_count):
                target = rng.choice(nodes)
                if target == node:
                    continue
                amount = float(np_rng.lognormal(mean=9.1 + (0.8 if risky else 0), sigma=0.8))
                if graph.has_edge(node, target):
                    graph[node][target]["weight"] += amount
                else:
                    graph.add_edge(node, target, weight=amount)
        risky_nodes = [node for node in nodes if latent_risk[node]]
        rng.shuffle(risky_nodes)
        for index in range(0, len(risky_nodes) - 2, 3):
            a, b, c = risky_nodes[index : index + 3]
            graph.add_edge(a, b, weight=250_000)
            graph.add_edge(b, c, weight=250_000)
            graph.add_edge(c, a, weight=250_000)
            cycle_counts[a] += 1
            cycle_counts[b] += 1
            cycle_counts[c] += 1
        pagerank = nx.pagerank(graph, weight="weight")
        for node in nodes:
            risky = latent_risk[node]
            outgoing = list(graph.out_edges(node, data=True))
            rows.append([
                float(graph.in_degree(node)),
                float(graph.out_degree(node)),
                float(sum(edge[2]["weight"] for edge in outgoing)),
                float(len({edge[1] for edge in outgoing})),
                float(pagerank[node]),
                float(np_rng.poisson(2.5 if risky else 0.15)),
                float(cycle_counts[node]),
                float(np.clip(np_rng.normal(0.58 if risky else 0.08, 0.08), 0, 1)),
            ])
            label_noise = rng.random() < 0.008
            labels.append(int(risky) ^ int(label_noise))
            time_values.append(month)
            entity_values.append(node)
    return TemporalDataset(
        np.asarray(rows), np.asarray(labels), np.asarray(time_values), np.asarray(entity_values), FEATURES.copy()
    )


def _population_stability_index(train: np.ndarray, test: np.ndarray, buckets: int = 10) -> float:
    edges = np.unique(np.quantile(train, np.linspace(0, 1, buckets + 1)))
    if len(edges) < 3:
        return 0.0
    edges[0], edges[-1] = -np.inf, np.inf
    train_share = np.histogram(train, bins=edges)[0].astype(float)
    test_share = np.histogram(test, bins=edges)[0].astype(float)
    train_share = np.clip(train_share / max(train_share.sum(), 1), 1e-6, None)
    test_share = np.clip(test_share / max(test_share.sum(), 1), 1e-6, None)
    return float(np.sum((test_share - train_share) * np.log(test_share / train_share)))


def validate_entity_holdout(
    dataset: TemporalDataset,
    train_through_month: int = 8,
    holdout_fraction: float = 0.25,
    seed: int = 20260811,
) -> dict:
    if not 0.1 <= holdout_fraction <= 0.5:
        raise ValueError("holdout_fraction must be between 0.1 and 0.5")
    rng = random.Random(seed)
    labels_by_entity = {
        entity: int(dataset.y[dataset.entity_ids == entity].max()) for entity in np.unique(dataset.entity_ids)
    }
    risky = sorted(entity for entity, label in labels_by_entity.items() if label)
    normal = sorted(entity for entity, label in labels_by_entity.items() if not label)
    rng.shuffle(risky)
    rng.shuffle(normal)
    holdout = set(risky[: max(1, math.ceil(len(risky) * holdout_fraction))])
    holdout.update(normal[: max(1, math.ceil(len(normal) * holdout_fraction))])
    is_holdout = np.isin(dataset.entity_ids, list(holdout))
    train_mask = (dataset.months <= train_through_month) & ~is_holdout
    test_mask = (dataset.months > train_through_month) & is_holdout
    if len(np.unique(dataset.y[train_mask])) < 2 or len(np.unique(dataset.y[test_mask])) < 2:
        raise ValueError("entity holdout requires both classes in train and test")
    model = RandomForestClassifier(
        n_estimators=180,
        max_depth=8,
        min_samples_leaf=4,
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(dataset.x[train_mask], dataset.y[train_mask])
    probabilities = model.predict_proba(dataset.x[test_mask])[:, 1]
    y_test = dataset.y[test_mask]
    train_entities = set(dataset.entity_ids[train_mask])
    test_entities = set(dataset.entity_ids[test_mask])
    drift = [
        {
            "feature": feature,
            "psi": round(_population_stability_index(dataset.x[train_mask, idx], dataset.x[test_mask, idx]), 6),
        }
        for idx, feature in enumerate(dataset.feature_names)
    ]
    drift.sort(key=lambda item: -item["psi"])
    return {
        "protocol": "entity-disjoint temporal holdout/v1",
        "seed": seed,
        "holdout_fraction": holdout_fraction,
        "train_rows": int(train_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "train_entities": len(train_entities),
        "test_entities": len(test_entities),
        "entity_leakage_count": len(train_entities & test_entities),
        "average_precision": round(float(average_precision_score(y_test, probabilities)), 6),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 6),
        "feature_drift_psi": drift,
        "high_drift_features": [item["feature"] for item in drift if item["psi"] >= 0.25],
        "limitations": [
            "实体隔离降低了同一主体跨月份泄漏，但数据仍为固定种子生成的合成图。",
            "PSI仅用于数据分布监测，不证明因果关系或真实业务稳定性。",
        ],
    }


def train_temporal_baseline(
    dataset: TemporalDataset,
    train_through_month: int = 8,
    seed: int = 20260811,
) -> tuple[RandomForestClassifier, dict]:
    train_mask = dataset.months <= train_through_month
    test_mask = dataset.months > train_through_month
    if not train_mask.any() or not test_mask.any():
        raise ValueError("time split must contain train and test rows")
    model = RandomForestClassifier(
        n_estimators=180,
        max_depth=8,
        min_samples_leaf=4,
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=1,
    )
    model.fit(dataset.x[train_mask], dataset.y[train_mask])
    probabilities = model.predict_proba(dataset.x[test_mask])[:, 1]
    y_test = dataset.y[test_mask]
    cutoff_count = max(1, math.ceil(len(probabilities) * 0.05))
    ranked = np.argsort(-probabilities)
    top_mask = np.zeros(len(probabilities), dtype=bool)
    top_mask[ranked[:cutoff_count]] = True
    recall_at_top5 = float(y_test[top_mask].sum() / max(y_test.sum(), 1))
    threshold_predictions = probabilities >= 0.5
    importances = sorted(
        ({"feature": name, "importance": round(float(value), 6)} for name, value in zip(dataset.feature_names, model.feature_importances_)),
        key=lambda item: -item["importance"],
    )
    metrics = {
        "dataset": "synthetic_temporal_graph_v1",
        "seed": seed,
        "train_months": [int(dataset.months[train_mask].min()), int(dataset.months[train_mask].max())],
        "test_months": [int(dataset.months[test_mask].min()), int(dataset.months[test_mask].max())],
        "train_rows": int(train_mask.sum()),
        "test_rows": int(test_mask.sum()),
        "test_positive_rate": round(float(y_test.mean()), 6),
        "average_precision": round(float(average_precision_score(y_test, probabilities)), 6),
        "roc_auc": round(float(roc_auc_score(y_test, probabilities)), 6),
        "recall_at_top_5_percent": round(recall_at_top5, 6),
        "precision_at_threshold_0_5": round(float(precision_score(y_test, threshold_predictions, zero_division=0)), 6),
        "recall_at_threshold_0_5": round(float(recall_score(y_test, threshold_predictions, zero_division=0)), 6),
        "feature_importance": importances,
        "limitations": [
            "训练和测试数据均为固定规则生成的合成图，指标不能代表真实舞弊识别效果。",
            "标签由潜在风险和少量噪声生成，仍可能存在生成机制带来的可分性偏高。",
            "时间切分防止使用未来月份训练，但同一实体可跨月出现。",
        ],
    }
    return model, metrics


def save_model_artifacts(model: RandomForestClassifier, metrics: dict, output_dir: str | Path) -> dict:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    model_path = destination / "riskgraph-baseline.joblib"
    card_path = destination / "riskgraph-model-card.json"
    joblib.dump(model, model_path)
    card_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"model": str(model_path), "model_card": str(card_path)}
