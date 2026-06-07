ALTER TABLE skills
  ADD COLUMN IF NOT EXISTS category TEXT,
  ADD COLUMN IF NOT EXISTS level INT,
  ADD COLUMN IF NOT EXISTS difficulty TEXT,
  ADD COLUMN IF NOT EXISTS hours_estimate INT,
  ADD COLUMN IF NOT EXISTS hot BOOLEAN DEFAULT FALSE;

ALTER TABLE learning_resources
  ADD COLUMN IF NOT EXISTS hours_estimate DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS note TEXT,
  ADD COLUMN IF NOT EXISTS language TEXT;

CREATE TABLE IF NOT EXISTS graph_nodes (
  node_type TEXT NOT NULL,
  node_id TEXT NOT NULL,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  feature_vector DOUBLE PRECISION[] DEFAULT '{}'::double precision[],
  embedding_vector DOUBLE PRECISION[] DEFAULT '{}'::double precision[],
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (node_type, node_id)
);

CREATE TABLE IF NOT EXISTS graphsage_embeddings (
  node_type TEXT NOT NULL,
  node_id TEXT NOT NULL,
  embedding DOUBLE PRECISION[] NOT NULL DEFAULT '{}'::double precision[],
  model_version TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT NOW(),
  PRIMARY KEY (node_type, node_id, model_version)
);

CREATE INDEX IF NOT EXISTS idx_graph_nodes_type_id ON graph_nodes(node_type, node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_relation ON graph_edges(relation);
CREATE INDEX IF NOT EXISTS idx_graphsage_embeddings_model ON graphsage_embeddings(model_version);
