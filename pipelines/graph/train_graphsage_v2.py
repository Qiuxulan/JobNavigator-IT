from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).parents[2]
MODEL_DIR = ROOT / "models" / "graphsage_v2"
REPORT_PATH = ROOT / "reports" / "graphsage_metrics_v2.json"
DSN = os.environ.get(
    "JOBNAV_POSTGRES_DSN",
    "postgresql://jobnav:jobnav@localhost:5432/jobnavigator",
)
MODEL_VERSION = os.environ.get("JOBNAV_GRAPH_MODEL_VERSION", "graphsage-v2")
EMBED_DIM = int(os.environ.get("JOBNAV_GRAPH_EMBED_DIM", "64"))
EPOCHS = int(os.environ.get("JOBNAV_GRAPH_EPOCHS", "60"))
LR = float(os.environ.get("JOBNAV_GRAPH_LR", "0.01"))
SEED = int(os.environ.get("JOBNAV_GRAPH_SEED", "42"))
RELATIONS = ("SKILL_PREREQ", "JOB_REQUIRES", "SKILL_HAS_RESOURCE")


@dataclass
class GraphDataset:
    node_keys: list[tuple[str, str]]
    node_types: list[str]
    features: torch.Tensor
    edge_index: torch.Tensor
    positive_edges: list[tuple[int, int]]


class SimpleSAGEConv(nn.Module):
    def __init__(self, in_dim: int, out_dim: int) -> None:
        super().__init__()
        self.linear = nn.Linear(in_dim * 2, out_dim)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        src, dst = edge_index
        agg = torch.zeros_like(x)
        agg.index_add_(0, dst, x[src])
        degree = torch.bincount(dst, minlength=x.size(0)).clamp(min=1).unsqueeze(1).to(x.dtype)
        return self.linear(torch.cat([x, agg / degree], dim=1))


class GraphSAGEEncoder(nn.Module):
    def __init__(self, in_dim: int, hidden_dim: int, out_dim: int) -> None:
        super().__init__()
        self.conv1 = SimpleSAGEConv(in_dim, hidden_dim)
        self.conv2 = SimpleSAGEConv(hidden_dim, out_dim)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(x, edge_index))
        x = F.dropout(x, p=0.15, training=self.training)
        x = self.conv2(x, edge_index)
        return F.normalize(x, p=2, dim=1)


def _set_seed() -> None:
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)


def _load_rows() -> tuple[list[tuple[str, str, list[float]]], list[tuple[str, str, str, str]]]:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT node_type, node_id, feature_vector FROM graph_nodes ORDER BY node_type, node_id")
            node_rows = cur.fetchall()
            cur.execute(
                """
                SELECT src_type, src_id, dst_type, dst_id
                FROM graph_edges
                WHERE relation = ANY(%s)
                """,
                (list(RELATIONS),),
            )
            edge_rows = cur.fetchall()
    return node_rows, edge_rows


def build_dataset() -> GraphDataset:
    node_rows, edge_rows = _load_rows()
    if not node_rows:
        raise RuntimeError("graph_nodes is empty. Run build_career_graph_v2 first.")

    node_keys = [(row[0], row[1]) for row in node_rows]
    node_types = [row[0] for row in node_rows]
    index_by_key = {key: index for index, key in enumerate(node_keys)}
    max_len = max(len(row[2] or []) for row in node_rows)
    features = []
    for _, _, vector in node_rows:
        row = list(vector or [])
        if len(row) < max_len:
            row += [0.0] * (max_len - len(row))
        features.append(row)
    features_tensor = torch.tensor(features, dtype=torch.float32)

    edges: list[tuple[int, int]] = []
    for src_type, src_id, dst_type, dst_id in edge_rows:
        src_key = (src_type, src_id)
        dst_key = (dst_type, dst_id)
        if src_key not in index_by_key or dst_key not in index_by_key:
            continue
        src_idx = index_by_key[src_key]
        dst_idx = index_by_key[dst_key]
        edges.append((src_idx, dst_idx))
        edges.append((dst_idx, src_idx))
    if not edges:
        raise RuntimeError("No graph edges found for GraphSAGE v2 training.")

    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous()
    positive_edges = list({tuple(sorted((src, dst))) for src, dst in edges if src != dst})
    return GraphDataset(node_keys=node_keys, node_types=node_types, features=features_tensor, edge_index=edge_index, positive_edges=positive_edges)


def _sample_negative_edges(node_count: int, positive_edges: set[tuple[int, int]], sample_size: int) -> list[tuple[int, int]]:
    negatives: set[tuple[int, int]] = set()
    attempts = 0
    while len(negatives) < sample_size and attempts < sample_size * 20:
        left = random.randrange(node_count)
        right = random.randrange(node_count)
        attempts += 1
        if left == right:
            continue
        key = tuple(sorted((left, right)))
        if key in positive_edges:
            continue
        negatives.add(key)
    return list(negatives)


def _job_skill_pairs(dataset: GraphDataset) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    positive = set(dataset.positive_edges)
    for left, right in positive:
        left_type = dataset.node_types[left]
        right_type = dataset.node_types[right]
        if left_type == "job" and right_type == "skill":
            pairs.append((left, right))
        elif left_type == "skill" and right_type == "job":
            pairs.append((right, left))
    return pairs


def train(dataset: GraphDataset) -> tuple[GraphSAGEEncoder, dict[str, Any], np.ndarray]:
    _set_seed()
    model = GraphSAGEEncoder(dataset.features.size(1), max(64, EMBED_DIM * 2), EMBED_DIM)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    positive_set = set(dataset.positive_edges)
    job_skill_pairs = _job_skill_pairs(dataset)
    history = []

    for epoch in range(1, EPOCHS + 1):
        model.train()
        optimizer.zero_grad()
        embeddings = model(dataset.features, dataset.edge_index)

        pos_src = torch.tensor([src for src, _ in dataset.positive_edges], dtype=torch.long)
        pos_dst = torch.tensor([dst for _, dst in dataset.positive_edges], dtype=torch.long)
        pos_logits = (embeddings[pos_src] * embeddings[pos_dst]).sum(dim=1)
        pos_loss = F.binary_cross_entropy_with_logits(pos_logits, torch.ones_like(pos_logits))

        negatives = _sample_negative_edges(len(dataset.node_keys), positive_set, len(dataset.positive_edges))
        neg_src = torch.tensor([src for src, _ in negatives], dtype=torch.long)
        neg_dst = torch.tensor([dst for _, dst in negatives], dtype=torch.long)
        neg_logits = (embeddings[neg_src] * embeddings[neg_dst]).sum(dim=1)
        neg_loss = F.binary_cross_entropy_with_logits(neg_logits, torch.zeros_like(neg_logits))

        if job_skill_pairs:
            pairs = random.sample(job_skill_pairs, k=min(256, len(job_skill_pairs)))
            pair_src = torch.tensor([src for src, _ in pairs], dtype=torch.long)
            pair_dst = torch.tensor([dst for _, dst in pairs], dtype=torch.long)
            pair_loss = (1.0 - F.cosine_similarity(embeddings[pair_src], embeddings[pair_dst])).mean()
        else:
            pair_loss = torch.tensor(0.0)

        loss = pos_loss + neg_loss + 0.25 * pair_loss
        loss.backward()
        optimizer.step()

        history.append(
            {
                "epoch": epoch,
                "loss": round(float(loss.item()), 6),
                "positive_score": round(float(torch.sigmoid(pos_logits).mean().item()), 6),
                "negative_score": round(float(torch.sigmoid(neg_logits).mean().item()), 6),
            }
        )

    model.eval()
    with torch.no_grad():
        embeddings = model(dataset.features, dataset.edge_index).cpu().numpy()

    summary = {
        "model_version": MODEL_VERSION,
        "embedding_dim": EMBED_DIM,
        "epochs": EPOCHS,
        "learning_rate": LR,
        "node_count": len(dataset.node_keys),
        "edge_count": len(dataset.positive_edges),
        "history_tail": history[-10:],
        "final_loss": history[-1]["loss"],
    }
    return model, summary, embeddings


def save_outputs(dataset: GraphDataset, model: GraphSAGEEncoder, summary: dict[str, Any], embeddings: np.ndarray) -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "input_dim": dataset.features.size(1),
            "embedding_dim": EMBED_DIM,
            "model_version": MODEL_VERSION,
        },
        MODEL_DIR / "model.pt",
    )
    (MODEL_DIR / "node_index.json").write_text(
        json.dumps({f"{node_type}:{node_id}": idx for idx, (node_type, node_id) in enumerate(dataset.node_keys)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    np.save(MODEL_DIR / "embeddings.npy", embeddings)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM graphsage_embeddings WHERE model_version = %s", (MODEL_VERSION,))
            for (node_type, node_id), vector in zip(dataset.node_keys, embeddings):
                clean = [round(float(value), 6) for value in vector.tolist()]
                cur.execute(
                    """
                    INSERT INTO graphsage_embeddings (node_type, node_id, embedding, model_version, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (node_type, node_id, model_version) DO UPDATE SET
                      embedding = EXCLUDED.embedding,
                      updated_at = NOW();
                    """,
                    (node_type, node_id, clean, MODEL_VERSION),
                )
                cur.execute(
                    """
                    UPDATE graph_nodes
                    SET embedding_vector = %s, updated_at = NOW()
                    WHERE node_type = %s AND node_id = %s
                    """,
                    (clean, node_type, node_id),
                )
        conn.commit()


def main() -> None:
    dataset = build_dataset()
    model, summary, embeddings = train(dataset)
    save_outputs(dataset, model, summary, embeddings)
    print(json.dumps({"status": "ok", **summary, "model_dir": str(MODEL_DIR)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
