---
tags:
- sentence-transformers
- sentence-similarity
- feature-extraction
- generated_from_trainer
- dataset_size:303
- loss:MultipleNegativesRankingLoss
widget:
- source_sentence: 深度学习基础 深度学习 机器学习基础 deep learning neural networks tensorflow keras
    intermediate level5
  sentences:
  - Introduction to Deep Learning & Neural Networks with Keras coursera IBM | rating:4.8
  - Command Line Tools for Genomic Data Science coursera Johns Hopkins University
    | rating:4.9
  - Causal Inference coursera Columbia University | rating:4.5
- source_sentence: SQL基础 数据库  sql database mysql relational query beginner level1
  sentences:
  - 'Expressway to Data Science: Python Programming coursera University of Colorado
    Boulder | rating:4.5'
  - Learn SQL Basics for Data Science coursera University of California, Davis | rating:4.6
  - B站最好的提示词工程教程2025（全88集系统课） bilibili UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
- source_sentence: LangChain框架 LLM工程 大语言模型基础 Python基础 langchain llm framework python
    intermediate level8
  sentences:
  - Modern Regression Analysis in R coursera University of Colorado Boulder | rating:4.9
  - 2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI） bilibili UP:吴恩达Agent | 播放量256.5万；Agent专项最强资源；涵盖四大设计模式
  - Data Visualization with Python coursera IBM | rating:4.5
- source_sentence: 统计学基础 数据科学 NumPy科学计算 高等数学基础(线代/概率) statistics probability hypothesis
    testing statistical analysis intermediate level3
  sentences:
  - Linear Regression for Business Statistics coursera Rice University | rating:4.4
  - Statistical Analysis Fundamentals using Excel coursera IBM | rating:4.5
  - Python Basics coursera University of Michigan | rating:4.8
- source_sentence: Python基础 编程语言  python programming beginners tutorial basics beginner
    level1
  sentences:
  - Data Analysis and Interpretation coursera Wesleyan University | rating:4.7
  - Introduction to Python Programming coursera University of Pennsylvania | rating:4.6
  - 黑马程序员 Python Web开发 FastAPI从入门到实战 bilibili UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
pipeline_tag: sentence-similarity
library_name: sentence-transformers
---

# SentenceTransformer

This is a [sentence-transformers](https://www.SBERT.net) model trained. It maps sentences & paragraphs to a 384-dimensional dense vector space and can be used for retrieval.

## Model Details

### Model Description
- **Model Type:** Sentence Transformer
<!-- - **Base model:** [Unknown](https://huggingface.co/unknown) -->
- **Maximum Sequence Length:** 128 tokens
- **Output Dimensionality:** 384 dimensions
- **Similarity Function:** Cosine Similarity
- **Supported Modality:** Text
<!-- - **Training Dataset:** Unknown -->
<!-- - **Language:** Unknown -->
<!-- - **License:** Unknown -->

### Model Sources

- **Documentation:** [Sentence Transformers Documentation](https://sbert.net)
- **Repository:** [Sentence Transformers on GitHub](https://github.com/huggingface/sentence-transformers)
- **Hugging Face:** [Sentence Transformers on Hugging Face](https://huggingface.co/models?library=sentence-transformers)

### Full Model Architecture

```
SentenceTransformer(
  (0): Transformer({'transformer_task': 'feature-extraction', 'modality_config': {'text': {'method': 'forward', 'method_output_name': 'last_hidden_state'}}, 'module_output_name': 'token_embeddings', 'architecture': 'BertModel'})
  (1): Pooling({'embedding_dimension': 384, 'pooling_mode': 'mean', 'include_prompt': True})
)
```

## Usage

### Direct Usage (Sentence Transformers)

First install the Sentence Transformers library:

```bash
pip install -U sentence-transformers
```
Then you can load this model and run inference.
```python
from sentence_transformers import SentenceTransformer

# Download from the 🤗 Hub
model = SentenceTransformer("sentence_transformers_model_id")
# Run inference
sentences = [
    'Python基础 编程语言  python programming beginners tutorial basics beginner level1',
    'Introduction to Python Programming coursera University of Pennsylvania | rating:4.6',
    'Data Analysis and Interpretation coursera Wesleyan University | rating:4.7',
]
embeddings = model.encode(sentences)
print(embeddings.shape)
# [3, 384]

# Get the similarity scores for the embeddings
similarities = model.similarity(embeddings, embeddings)
print(similarities)
# tensor([[1.0000, 0.6157, 0.3331],
#         [0.6157, 1.0000, 0.7418],
#         [0.3331, 0.7418, 1.0000]])
```
<!--
### Direct Usage (Transformers)

<details><summary>Click to see the direct usage in Transformers</summary>

</details>
-->

<!--
### Downstream Usage (Sentence Transformers)

You can finetune this model on your own dataset.

<details><summary>Click to expand</summary>

</details>
-->

<!--
### Out-of-Scope Use

*List how the model may foreseeably be misused and address what users ought not to do with the model.*
-->

<!--
## Bias, Risks and Limitations

*What are the known or foreseeable issues stemming from this model? You could also flag here known failure cases or weaknesses of the model.*
-->

<!--
### Recommendations

*What are recommendations with respect to the foreseeable issues? For example, filtering explicit content.*
-->

## Training Details

### Training Dataset

#### Unnamed Dataset

* Size: 303 training samples
* Columns: <code>anchor</code> and <code>positive</code>
* Approximate statistics based on the first 100 samples:
  |          | anchor                                                                             | positive                                                                           |
  |:---------|:-----------------------------------------------------------------------------------|:-----------------------------------------------------------------------------------|
  | type     | string                                                                             | string                                                                             |
  | modality | text                                                                               | text                                                                               |
  | details  | <ul><li>min: 28 tokens</li><li>mean: 36.79 tokens</li><li>max: 41 tokens</li></ul> | <ul><li>min: 14 tokens</li><li>mean: 24.52 tokens</li><li>max: 70 tokens</li></ul> |
* Samples:
  | anchor                                                                                                                                     | positive                                                                                                                                |
  |:-------------------------------------------------------------------------------------------------------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------|
  | <code>机器学习基础 机器学习 统计学基础 Pandas数据处理 NumPy科学计算 machine learning scikit-learn supervised regression classification intermediate level4</code> | <code>Machine Learning Algorithms: Supervised Learning Tip to Tail coursera Alberta Machine Intelligence Institute \| rating:3.7</code> |
  | <code>机器学习基础 机器学习 统计学基础 Pandas数据处理 NumPy科学计算 machine learning scikit-learn supervised regression classification intermediate level4</code> | <code>Unsupervised Learning, Recommenders, Reinforcement Learning coursera DeepLearning.AI \| rating:4.9</code>                         |
  | <code>机器学习基础 机器学习 统计学基础 Pandas数据处理 NumPy科学计算 machine learning scikit-learn supervised regression classification intermediate level4</code> | <code>Introduction to Data Science and scikit-learn in Python coursera LearnQuest \| rating:4.4</code>                                  |
* Loss: [<code>MultipleNegativesRankingLoss</code>](https://sbert.net/docs/package_reference/sentence_transformer/losses.html#multiplenegativesrankingloss) with these parameters:
  ```json
  {
      "scale": 20.0,
      "similarity_fct": "cos_sim",
      "gather_across_devices": false,
      "directions": [
          "query_to_doc"
      ],
      "partition_mode": "joint",
      "hardness_mode": null,
      "hardness_strength": 0.0
  }
  ```

### Training Hyperparameters
#### Non-Default Hyperparameters

- `per_device_train_batch_size`: 32
- `learning_rate`: 2e-05
- `warmup_steps`: 2

#### All Hyperparameters
<details><summary>Click to expand</summary>

- `per_device_train_batch_size`: 32
- `num_train_epochs`: 3
- `max_steps`: -1
- `learning_rate`: 2e-05
- `lr_scheduler_type`: linear
- `lr_scheduler_kwargs`: None
- `warmup_steps`: 2
- `optim`: adamw_torch_fused
- `optim_args`: None
- `weight_decay`: 0.0
- `adam_beta1`: 0.9
- `adam_beta2`: 0.999
- `adam_epsilon`: 1e-08
- `optim_target_modules`: None
- `gradient_accumulation_steps`: 1
- `average_tokens_across_devices`: True
- `max_grad_norm`: 1.0
- `label_smoothing_factor`: 0.0
- `bf16`: False
- `fp16`: False
- `bf16_full_eval`: False
- `fp16_full_eval`: False
- `tf32`: None
- `gradient_checkpointing`: False
- `gradient_checkpointing_kwargs`: None
- `torch_compile`: False
- `torch_compile_backend`: None
- `torch_compile_mode`: None
- `use_liger_kernel`: False
- `liger_kernel_config`: None
- `use_cache`: False
- `neftune_noise_alpha`: None
- `torch_empty_cache_steps`: None
- `auto_find_batch_size`: False
- `log_on_each_node`: True
- `logging_nan_inf_filter`: True
- `include_num_input_tokens_seen`: no
- `log_level`: passive
- `log_level_replica`: warning
- `disable_tqdm`: False
- `project`: huggingface
- `trackio_space_id`: None
- `trackio_bucket_id`: None
- `trackio_static_space_id`: None
- `per_device_eval_batch_size`: 8
- `prediction_loss_only`: True
- `eval_on_start`: False
- `eval_do_concat_batches`: True
- `eval_use_gather_object`: False
- `eval_accumulation_steps`: None
- `include_for_metrics`: []
- `batch_eval_metrics`: False
- `save_only_model`: False
- `save_on_each_node`: False
- `enable_jit_checkpoint`: False
- `push_to_hub`: False
- `hub_private_repo`: None
- `hub_model_id`: None
- `hub_strategy`: every_save
- `hub_always_push`: False
- `hub_revision`: None
- `load_best_model_at_end`: False
- `ignore_data_skip`: False
- `restore_callback_states_from_checkpoint`: False
- `full_determinism`: False
- `seed`: 42
- `data_seed`: None
- `use_cpu`: False
- `accelerator_config`: {'split_batches': False, 'dispatch_batches': None, 'even_batches': True, 'use_seedable_sampler': True, 'non_blocking': False, 'gradient_accumulation_kwargs': None}
- `parallelism_config`: None
- `dataloader_drop_last`: False
- `dataloader_num_workers`: 0
- `dataloader_pin_memory`: True
- `dataloader_persistent_workers`: False
- `dataloader_prefetch_factor`: None
- `remove_unused_columns`: True
- `label_names`: None
- `train_sampling_strategy`: random
- `length_column_name`: length
- `ddp_find_unused_parameters`: None
- `ddp_bucket_cap_mb`: None
- `ddp_broadcast_buffers`: False
- `ddp_static_graph`: None
- `ddp_backend`: None
- `ddp_timeout`: 1800
- `fsdp`: []
- `fsdp_config`: {'min_num_params': 0, 'xla': False, 'xla_fsdp_v2': False, 'xla_fsdp_grad_ckpt': False}
- `deepspeed`: None
- `debug`: []
- `skip_memory_metrics`: True
- `do_predict`: False
- `resume_from_checkpoint`: None
- `warmup_ratio`: None
- `local_rank`: -1
- `prompts`: None
- `batch_sampler`: batch_sampler
- `multi_dataset_batch_sampler`: proportional
- `router_mapping`: {}
- `learning_rate_mapping`: {}

</details>

### Training Logs
| Epoch | Step | Training Loss |
|:-----:|:----:|:-------------:|
| 1.0   | 10   | 2.5401        |
| 2.0   | 20   | 1.9802        |
| 3.0   | 30   | 1.8288        |


### Training Time
- **Training**: 1.8 minutes

### Framework Versions
- Python: 3.13.7
- Sentence Transformers: 5.5.1
- Transformers: 5.9.0
- PyTorch: 2.11.0+cpu
- Accelerate: 1.13.0
- Datasets: 4.8.5
- Tokenizers: 0.22.2

## Citation

### BibTeX

#### Sentence Transformers
```bibtex
@inproceedings{reimers-2019-sentence-bert,
    title = "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks",
    author = "Reimers, Nils and Gurevych, Iryna",
    booktitle = "Proceedings of the 2019 Conference on Empirical Methods in Natural Language Processing",
    month = "11",
    year = "2019",
    publisher = "Association for Computational Linguistics",
    url = "https://arxiv.org/abs/1908.10084",
}
```

#### MultipleNegativesRankingLoss
```bibtex
@misc{oord2019representationlearningcontrastivepredictive,
      title={Representation Learning with Contrastive Predictive Coding},
      author={Aaron van den Oord and Yazhe Li and Oriol Vinyals},
      year={2019},
      eprint={1807.03748},
      archivePrefix={arXiv},
      primaryClass={cs.LG},
      url={https://arxiv.org/abs/1807.03748},
}
```

<!--
## Glossary

*Clearly define terms in order to be accessible across audiences.*
-->

<!--
## Model Card Authors

*Lists the people who create the model card, providing recognition and accountability for the detailed work that goes into its construction.*
-->

<!--
## Model Card Contact

*Provides a way for people who have updates to the Model Card, suggestions, or questions, to contact the Model Card authors.*
-->