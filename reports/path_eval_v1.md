# C部分 学习路径评估报告（三策略版）
生成日期：2026-06-01

## 三策略对比摘要 — RAG应用工程师 （RAG应用工程师（仅Python基础））

| 策略 | 步骤数 | 总学时 | 目标覆盖 | 平均难度 | 前3步技能顺序 |
|------|--------|--------|----------|----------|--------------|
| [最短路径] 快速通道 | 10步 | 215h | 100% | intermediate | FastAPI部署 → PyTorch框架 → NLP基础 |
| [最低难度] 由易到难 | 16步 | 460h | 100% | intermediate | 高等数学基础(线代/概率) → NumPy科学计算 → Pandas数据处理 |
| [最全覆盖] 系统学习 | 17步 | 480h | 100% | intermediate | 高等数学基础(线代/概率) → NumPy科学计算 → Pandas数据处理 |

> **选路说明**
> - **最短路径**：跳过理论基础直达应用层，步骤最少，适合有一定背景、追求速成的学习者
> - **最低难度**：完整前置链路，贪心优先选最简单的可学技能，适合零基础逐步进阶
> - **最全覆盖**：完整路径+扩展技能，含底层原理，适合追求系统掌握的学习者

## 目标岗位：RAG应用工程师  [最短路径] 快速通道

| 指标 | 数值 |
|------|------|
| 总学时 | **215h** |
| 学习步骤 | **10 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门1步 / 中级7步 / 进阶2步 |

**用户已有**：sk_git, sk_python_basic
**缺口技能**：文本Embedding, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, RAG工程化, 向量数据库

---

### Step 1. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 2. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 3. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 4. 文本Embedding [中级]
- 分类：NLP　学时：15h　难度：intermediate
- 推荐资源：
  - [什么是词嵌入 Word Embedding算法（含Word2Vec/CBOW/Skip-gram）](https://www.bilibili.com/video/BV1sw411S7i1/) `bilibili` UP:小黑黑讲AI | 播放量7.8万；Embedding基础原理；NLP入门必备
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [Product Recommender System: OpenAI Text Embedding](https://www.coursera.org/search?query=Product+Recommender+System:+OpenAI+Text+Embedding) `coursera` Coursera Project Network | rating:5.0

### Step 5. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 6. 向量数据库 [中级]
- 分类：数据库　学时：15h　难度：intermediate
- 推荐资源：
  - [Retrieval-Augmented Generation (RAG) with Embeddings & Vector Databases](https://www.coursera.org/search?query=Retrieval-Augmented+Generation+(RAG)+with+Embeddings+&+Vector+Databases) `coursera` Scrimba | rating:4.8
  - [Vector Databases: from Embeddings to Applications](https://www.coursera.org/search?query=Vector+Databases:+from+Embeddings+to+Applications) `coursera` DeepLearning.AI | rating:4.3
  - [Milvus/Qdrant/Weaviate/Pinecone/FAISS/Chroma向量数据库横评](https://www.bilibili.com/video/BV1zi1vByEjg/) `bilibili` UP:小天老师的AI大课堂 | 播放量1.5万；全面横评6款主流向量数据库

### Step 7. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 8. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 9. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 10. RAG工程化 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2025年公认最好的大模型RAG教程（吴恩达进阶版附课件）](https://www.bilibili.com/video/BV1QRbnzTEyK/) `bilibili` UP:吴恩达深度学习 | 播放量10.8万；高级RAG专项：句子窗口/Agentic RAG/知识图谱
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [支持多种向量数据库的100%本地化知识库 Milvus+ChatOllama](https://www.bilibili.com/video/BV1af421o79z/) `bilibili` UP:五里墩茶社 | 播放量32.3万；实操演示Milvus接入；适合工程实战


---

## 目标岗位：RAG应用工程师  [最低难度] 由易到难

| 指标 | 数值 |
|------|------|
| 总学时 | **460h** |
| 学习步骤 | **16 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门4步 / 中级10步 / 进阶2步 |

**用户已有**：sk_git, sk_python_basic
**缺口技能**：文本Embedding, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, RAG工程化, 向量数据库

---

### Step 1. 高等数学基础(线代/概率) [入门]
- 分类：数学基础　学时：60h　难度：beginner
- 推荐资源：
  - [Mathematics for Machine Learning: Linear Algebra](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning:+Linear+Algebra) `coursera` Imperial College London | rating:4.7
  - [Mathematics for Machine Learning](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning) `coursera` Imperial College London | rating:4.6
  - [Linear Algebra for Machine Learning and Data Science](https://www.coursera.org/search?query=Linear+Algebra+for+Machine+Learning+and+Data+Science) `coursera` DeepLearning.AI | rating:4.6

### Step 2. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 3. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 4. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 5. 统计学基础 [中级]
- 分类：数据科学　学时：40h　难度：intermediate
- 推荐资源：
  - [Introduction to Statistical Analysis:  Hypothesis Testing](https://www.coursera.org/search?query=Introduction+to+Statistical+Analysis:++Hypothesis+Testing) `coursera` SAS | rating:4.5
  - [Introduction to Statistics](https://www.coursera.org/search?query=Introduction+to+Statistics) `coursera` Stanford University | rating:4.6
  - [Statistics Foundations](https://www.coursera.org/search?query=Statistics+Foundations) `coursera` Meta | rating:4.8

### Step 6. 机器学习基础 [中级]
- 分类：机器学习　学时：60h　难度：intermediate
- 推荐资源：
  - [Introduction to Machine Learning: Supervised Learning](https://www.coursera.org/search?query=Introduction+to+Machine+Learning:+Supervised+Learning) `coursera` University of Colorado Boulder | rating:4.5
  - [Machine Learning Algorithms: Supervised Learning Tip to Tail](https://www.coursera.org/search?query=Machine+Learning+Algorithms:+Supervised+Learning+Tip+to+Tail) `coursera` Alberta Machine Intelligence Institute | rating:3.7
  - [Scikit-Learn For Machine Learning Classification Problems](https://www.coursera.org/search?query=Scikit-Learn+For+Machine+Learning+Classification+Problems) `coursera` Coursera Project Network | rating:4.4

### Step 7. 深度学习基础 [中级]
- 分类：深度学习　学时：50h　难度：intermediate
- 推荐资源：
  - [Introduction to Deep Learning & Neural Networks with Keras](https://www.coursera.org/search?query=Introduction+to+Deep+Learning+&+Neural+Networks+with+Keras) `coursera` IBM | rating:4.8
  - [Introduction to Deep Learning](https://www.coursera.org/search?query=Introduction+to+Deep+Learning) `coursera` University of Colorado Boulder | rating:4.5
  - [Introduction to Deep Learning for Computer Vision](https://www.coursera.org/search?query=Introduction+to+Deep+Learning+for+Computer+Vision) `coursera` MathWorks | rating:4.3

### Step 8. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 9. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 10. 文本Embedding [中级]
- 分类：NLP　学时：15h　难度：intermediate
- 推荐资源：
  - [什么是词嵌入 Word Embedding算法（含Word2Vec/CBOW/Skip-gram）](https://www.bilibili.com/video/BV1sw411S7i1/) `bilibili` UP:小黑黑讲AI | 播放量7.8万；Embedding基础原理；NLP入门必备
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [Product Recommender System: OpenAI Text Embedding](https://www.coursera.org/search?query=Product+Recommender+System:+OpenAI+Text+Embedding) `coursera` Coursera Project Network | rating:5.0

### Step 11. 向量数据库 [中级]
- 分类：数据库　学时：15h　难度：intermediate
- 推荐资源：
  - [Retrieval-Augmented Generation (RAG) with Embeddings & Vector Databases](https://www.coursera.org/search?query=Retrieval-Augmented+Generation+(RAG)+with+Embeddings+&+Vector+Databases) `coursera` Scrimba | rating:4.8
  - [Vector Databases: from Embeddings to Applications](https://www.coursera.org/search?query=Vector+Databases:+from+Embeddings+to+Applications) `coursera` DeepLearning.AI | rating:4.3
  - [Milvus/Qdrant/Weaviate/Pinecone/FAISS/Chroma向量数据库横评](https://www.bilibili.com/video/BV1zi1vByEjg/) `bilibili` UP:小天老师的AI大课堂 | 播放量1.5万；全面横评6款主流向量数据库

### Step 12. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 13. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 14. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 15. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 16. RAG工程化 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2025年公认最好的大模型RAG教程（吴恩达进阶版附课件）](https://www.bilibili.com/video/BV1QRbnzTEyK/) `bilibili` UP:吴恩达深度学习 | 播放量10.8万；高级RAG专项：句子窗口/Agentic RAG/知识图谱
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [支持多种向量数据库的100%本地化知识库 Milvus+ChatOllama](https://www.bilibili.com/video/BV1af421o79z/) `bilibili` UP:五里墩茶社 | 播放量32.3万；实操演示Milvus接入；适合工程实战


---

## 目标岗位：RAG应用工程师  [最全覆盖] 系统学习

| 指标 | 数值 |
|------|------|
| 总学时 | **480h** |
| 学习步骤 | **17 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门4步 / 中级10步 / 进阶3步 |

**用户已有**：sk_git, sk_python_basic
**缺口技能**：文本Embedding, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, RAG工程化, 向量数据库

---

### Step 1. 高等数学基础(线代/概率) [入门]
- 分类：数学基础　学时：60h　难度：beginner
- 推荐资源：
  - [Mathematics for Machine Learning: Linear Algebra](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning:+Linear+Algebra) `coursera` Imperial College London | rating:4.7
  - [Mathematics for Machine Learning](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning) `coursera` Imperial College London | rating:4.6
  - [Linear Algebra for Machine Learning and Data Science](https://www.coursera.org/search?query=Linear+Algebra+for+Machine+Learning+and+Data+Science) `coursera` DeepLearning.AI | rating:4.6

### Step 2. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 3. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 4. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 5. 统计学基础 [中级]
- 分类：数据科学　学时：40h　难度：intermediate
- 推荐资源：
  - [Introduction to Statistical Analysis:  Hypothesis Testing](https://www.coursera.org/search?query=Introduction+to+Statistical+Analysis:++Hypothesis+Testing) `coursera` SAS | rating:4.5
  - [Introduction to Statistics](https://www.coursera.org/search?query=Introduction+to+Statistics) `coursera` Stanford University | rating:4.6
  - [Statistics Foundations](https://www.coursera.org/search?query=Statistics+Foundations) `coursera` Meta | rating:4.8

### Step 6. 机器学习基础 [中级]
- 分类：机器学习　学时：60h　难度：intermediate
- 推荐资源：
  - [Introduction to Machine Learning: Supervised Learning](https://www.coursera.org/search?query=Introduction+to+Machine+Learning:+Supervised+Learning) `coursera` University of Colorado Boulder | rating:4.5
  - [Machine Learning Algorithms: Supervised Learning Tip to Tail](https://www.coursera.org/search?query=Machine+Learning+Algorithms:+Supervised+Learning+Tip+to+Tail) `coursera` Alberta Machine Intelligence Institute | rating:3.7
  - [Scikit-Learn For Machine Learning Classification Problems](https://www.coursera.org/search?query=Scikit-Learn+For+Machine+Learning+Classification+Problems) `coursera` Coursera Project Network | rating:4.4

### Step 7. 深度学习基础 [中级]
- 分类：深度学习　学时：50h　难度：intermediate
- 推荐资源：
  - [Introduction to Deep Learning & Neural Networks with Keras](https://www.coursera.org/search?query=Introduction+to+Deep+Learning+&+Neural+Networks+with+Keras) `coursera` IBM | rating:4.8
  - [Introduction to Deep Learning](https://www.coursera.org/search?query=Introduction+to+Deep+Learning) `coursera` University of Colorado Boulder | rating:4.5
  - [Introduction to Deep Learning for Computer Vision](https://www.coursera.org/search?query=Introduction+to+Deep+Learning+for+Computer+Vision) `coursera` MathWorks | rating:4.3

### Step 8. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 9. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 10. 文本Embedding [中级]
- 分类：NLP　学时：15h　难度：intermediate
- 推荐资源：
  - [什么是词嵌入 Word Embedding算法（含Word2Vec/CBOW/Skip-gram）](https://www.bilibili.com/video/BV1sw411S7i1/) `bilibili` UP:小黑黑讲AI | 播放量7.8万；Embedding基础原理；NLP入门必备
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [Product Recommender System: OpenAI Text Embedding](https://www.coursera.org/search?query=Product+Recommender+System:+OpenAI+Text+Embedding) `coursera` Coursera Project Network | rating:5.0

### Step 11. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 12. 向量数据库 [中级]
- 分类：数据库　学时：15h　难度：intermediate
- 推荐资源：
  - [Retrieval-Augmented Generation (RAG) with Embeddings & Vector Databases](https://www.coursera.org/search?query=Retrieval-Augmented+Generation+(RAG)+with+Embeddings+&+Vector+Databases) `coursera` Scrimba | rating:4.8
  - [Vector Databases: from Embeddings to Applications](https://www.coursera.org/search?query=Vector+Databases:+from+Embeddings+to+Applications) `coursera` DeepLearning.AI | rating:4.3
  - [Milvus/Qdrant/Weaviate/Pinecone/FAISS/Chroma向量数据库横评](https://www.bilibili.com/video/BV1zi1vByEjg/) `bilibili` UP:小天老师的AI大课堂 | 播放量1.5万；全面横评6款主流向量数据库

### Step 13. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 14. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 15. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 16. 大模型微调LoRA/QLoRA [进阶]
- 分类：LLM　学时：20h　难度：advanced
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 17. RAG工程化 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2025年公认最好的大模型RAG教程（吴恩达进阶版附课件）](https://www.bilibili.com/video/BV1QRbnzTEyK/) `bilibili` UP:吴恩达深度学习 | 播放量10.8万；高级RAG专项：句子窗口/Agentic RAG/知识图谱
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [支持多种向量数据库的100%本地化知识库 Milvus+ChatOllama](https://www.bilibili.com/video/BV1af421o79z/) `bilibili` UP:五里墩茶社 | 播放量32.3万；实操演示Milvus接入；适合工程实战


---

## 三策略对比摘要 — Agent应用工程师 （Agent应用工程师（有ML/DL基础））

| 策略 | 步骤数 | 总学时 | 目标覆盖 | 平均难度 | 前3步技能顺序 |
|------|--------|--------|----------|----------|--------------|
| [最短路径] 快速通道 | 9步 | 195h | 100% | intermediate | FastAPI部署 → PyTorch框架 → NLP基础 |
| [最低难度] 由易到难 (≡最短) | 9步 | 195h | 100% | intermediate | FastAPI部署 → PyTorch框架 → NLP基础 |
| [最全覆盖] 系统学习 | 12步 | 250h | 100% | intermediate | FastAPI部署 → PyTorch框架 → NLP基础 |

> **选路说明**
> - **最短路径**：跳过理论基础直达应用层，步骤最少，适合有一定背景、追求速成的学习者
> - **最低难度**：完整前置链路，贪心优先选最简单的可学技能，适合零基础逐步进阶
> - **最全覆盖**：完整路径+扩展技能，含底层原理，适合追求系统掌握的学习者
>
> *(注：该场景下最短路径与最低难度路径完全等效，见下方说明)*
> 等效原因：该岗位无需跳过理论基础（FAST_TRACK_SKIP=空集），
> 或用户已有技能覆盖了快速通道的跳过项，两条路径所需技能集合完全一致。

## 目标岗位：Agent应用工程师  [最短路径] 快速通道

| 指标 | 数值 |
|------|------|
| 总学时 | **195h** |
| 学习步骤 | **9 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门1步 / 中级5步 / 进阶3步 |

**用户已有**：sk_dl_basic, sk_git, sk_ml_basic, sk_numpy, sk_pandas, sk_python_basic
**缺口技能**：Agent架构设计, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, Tool Use/Function Calling

---

### Step 1. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 2. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 3. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 4. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 5. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 6. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 7. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 8. Agent架构设计 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 播放量256.5万；Agent专项最强资源；涵盖四大设计模式
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 9. Tool Use/Function Calling [进阶]
- 分类：LLM工程　学时：10h　难度：advanced
- 推荐资源：
  - [GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents) `github` stars:22236 | 50+ tutorials including Tool Use & Function Calling patterns
  - [AgentGuide](https://github.com/adongwanai/AgentGuide) `github` stars:5259 | 含Function Calling实战 + LangGraph Tool Use
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 含Tool Use/Function Calling设计模式讲解


---

## 目标岗位：Agent应用工程师  [最低难度] 由易到难

| 指标 | 数值 |
|------|------|
| 总学时 | **195h** |
| 学习步骤 | **9 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门1步 / 中级5步 / 进阶3步 |

**用户已有**：sk_dl_basic, sk_git, sk_ml_basic, sk_numpy, sk_pandas, sk_python_basic
**缺口技能**：Agent架构设计, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, Tool Use/Function Calling

---

### Step 1. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 2. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 3. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 4. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 5. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 6. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 7. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 8. Agent架构设计 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 播放量256.5万；Agent专项最强资源；涵盖四大设计模式
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 9. Tool Use/Function Calling [进阶]
- 分类：LLM工程　学时：10h　难度：advanced
- 推荐资源：
  - [GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents) `github` stars:22236 | 50+ tutorials including Tool Use & Function Calling patterns
  - [AgentGuide](https://github.com/adongwanai/AgentGuide) `github` stars:5259 | 含Function Calling实战 + LangGraph Tool Use
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 含Tool Use/Function Calling设计模式讲解


---

## 目标岗位：Agent应用工程师  [最全覆盖] 系统学习

| 指标 | 数值 |
|------|------|
| 总学时 | **250h** |
| 学习步骤 | **12 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门1步 / 中级7步 / 进阶4步 |

**用户已有**：sk_dl_basic, sk_git, sk_ml_basic, sk_numpy, sk_pandas, sk_python_basic
**缺口技能**：Agent架构设计, FastAPI部署, LangChain框架, 大语言模型基础, Prompt Engineering, Tool Use/Function Calling

---

### Step 1. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 2. PyTorch框架 [中级]
- 分类：深度学习　学时：30h　难度：intermediate
- 推荐资源：
  - [吴恩达大模型教程 DeepLearning.ai（中英双语附课件代码）](https://www.bilibili.com/video/BV1Bq421A74G/) `bilibili` UP:吴恩达机器学习 | 播放量248.3万；吴恩达官方课程中文版
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 3. NLP基础 [中级]
- 分类：NLP　学时：40h　难度：intermediate
- 推荐资源：
  - [nlp-tutorial](https://github.com/graykode/nlp-tutorial) `github` stars:14897 | graykode/nlp-tutorial
  - [Natural Language Processing in Microsoft Azure](https://www.coursera.org/search?query=Natural+Language+Processing+in+Microsoft+Azure) `coursera` Microsoft | rating:4.7
  - [Gen AI Foundational Models for NLP & Language Understanding](https://www.coursera.org/search?query=Gen+AI+Foundational+Models+for+NLP+&+Language+Understanding) `coursera` IBM | rating:4.6

### Step 4. 文本Embedding [中级]
- 分类：NLP　学时：15h　难度：intermediate
- 推荐资源：
  - [什么是词嵌入 Word Embedding算法（含Word2Vec/CBOW/Skip-gram）](https://www.bilibili.com/video/BV1sw411S7i1/) `bilibili` UP:小黑黑讲AI | 播放量7.8万；Embedding基础原理；NLP入门必备
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [Product Recommender System: OpenAI Text Embedding](https://www.coursera.org/search?query=Product+Recommender+System:+OpenAI+Text+Embedding) `coursera` Coursera Project Network | rating:5.0

### Step 5. Transformer架构 [进阶]
- 分类：NLP　学时：25h　难度：advanced
- 推荐资源：
  - [AI技术全栈教程：PyTorch+Transformer+大模型+RAG+Agent（卢菁）](https://www.bilibili.com/video/BV1YM411y7EP/) `bilibili` UP:卢菁博士_北大AI博士后 | 播放量147.6万；全栈课程；PyTorch/Transformer/RAG/Agent均覆盖
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [大模型训练全流程+微调实战（北大博士后卢菁）](https://www.bilibili.com/video/BV1V3BPYiEwW/) `bilibili` UP:人工智能AI大模型课程 | 播放量65.1万；LoRA/量化/vLLM实战；进阶必看

### Step 6. 向量数据库 [中级]
- 分类：数据库　学时：15h　难度：intermediate
- 推荐资源：
  - [Retrieval-Augmented Generation (RAG) with Embeddings & Vector Databases](https://www.coursera.org/search?query=Retrieval-Augmented+Generation+(RAG)+with+Embeddings+&+Vector+Databases) `coursera` Scrimba | rating:4.8
  - [Vector Databases: from Embeddings to Applications](https://www.coursera.org/search?query=Vector+Databases:+from+Embeddings+to+Applications) `coursera` DeepLearning.AI | rating:4.3
  - [Milvus/Qdrant/Weaviate/Pinecone/FAISS/Chroma向量数据库横评](https://www.bilibili.com/video/BV1zi1vByEjg/) `bilibili` UP:小天老师的AI大课堂 | 播放量1.5万；全面横评6款主流向量数据库

### Step 7. 大语言模型基础 [中级]
- 分类：LLM　学时：20h　难度：intermediate
- 推荐资源：
  - [Large Language Model Operations (LLMOps)](https://www.coursera.org/search?query=Large+Language+Model+Operations+(LLMOps)) `coursera` Duke University | rating:4.5
  - [【2026最新】台大李宏毅《生成式AI导论》LLM大模型零基础全套](https://www.bilibili.com/video/BV1a6j1z6En9/) `bilibili` UP:AI大模型课堂在线 | 播放量395.8万；学院派权威课程；覆盖LLM原理到应用
  - [【吴恩达】Claude Code全套教程，大模型入门到进阶](https://www.bilibili.com/video/BV1RSFUzVEAG/) `bilibili` UP:吴恩达的AI课 | 播放量42.4万；Claude Code工具使用；LLM工程化参考

### Step 8. Prompt Engineering [入门]
- 分类：LLM　学时：10h　难度：beginner
- 推荐资源：
  - [Generative AI: Prompt Engineering Basics](https://www.coursera.org/search?query=Generative+AI:+Prompt+Engineering+Basics) `coursera` IBM | rating:4.8
  - [Prompt Engineering Generative AI for Marketing & Advertising](https://www.coursera.org/search?query=Prompt+Engineering+Generative+AI+for+Marketing+&+Advertising) `coursera` Coursera Project Network | rating:4.7
  - [Prompt Engineering for Web Developers](https://www.coursera.org/search?query=Prompt+Engineering+for+Web+Developers) `coursera` Scrimba | rating:4.5

### Step 9. LangChain框架 [中级]
- 分类：LLM工程　学时：20h　难度：intermediate
- 推荐资源：
  - [B站最好的提示词工程教程2025（全88集系统课）](https://www.bilibili.com/video/BV19psRzpEPX/) `bilibili` UP:大模型学习教程 | 播放量21.7万；超大体量系统课；含Agent/RAG/LoRA
  - [【全748集】B站最全AI大模型零基础全套教程2025最新版](https://www.bilibili.com/video/BV1uNk1YxEJQ/) `bilibili` UP:大模型官方课程 | 播放量363.8万；体量极大适合系统学习
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 10. Agent架构设计 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 播放量256.5万；Agent专项最强资源；涵盖四大设计模式
  - [大模型全栈开发：RAG+Agent+MCP+Transformer+Qwen3+DeepSeek](https://www.bilibili.com/video/BV1p4pezGEWb/) `bilibili` UP:AI大模型基地 | 播放量100.4万；最新2026版；含MCP/A2A协议实战
  - [【全网炸裂】3天速通大模型：Prompt/LangChain/RAG/Agent/微调](https://www.bilibili.com/video/BV1hy5YzaErV/) `bilibili` UP:大模型-- | 播放量484.8万；覆盖最全；推荐首选入门合集

### Step 11. RAG工程化 [进阶]
- 分类：LLM工程　学时：25h　难度：advanced
- 推荐资源：
  - [2025年公认最好的大模型RAG教程（吴恩达进阶版附课件）](https://www.bilibili.com/video/BV1QRbnzTEyK/) `bilibili` UP:吴恩达深度学习 | 播放量10.8万；高级RAG专项：句子窗口/Agentic RAG/知识图谱
  - [15分钟弄懂Token和Embedding：详解LLM与RAG的数据处理机制](https://www.bilibili.com/video/BV1oNv8BPE2m/) `bilibili` UP:隔壁的程序员老王 | 播放量42.2万；强烈推荐；15分钟讲清楚Embedding核心概念
  - [支持多种向量数据库的100%本地化知识库 Milvus+ChatOllama](https://www.bilibili.com/video/BV1af421o79z/) `bilibili` UP:五里墩茶社 | 播放量32.3万；实操演示Milvus接入；适合工程实战

### Step 12. Tool Use/Function Calling [进阶]
- 分类：LLM工程　学时：10h　难度：advanced
- 推荐资源：
  - [GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents) `github` stars:22236 | 50+ tutorials including Tool Use & Function Calling patterns
  - [AgentGuide](https://github.com/adongwanai/AgentGuide) `github` stars:5259 | 含Function Calling实战 + LangGraph Tool Use
  - [2026年公认最好的AI Agent智能体教程（吴恩达Agentic AI）](https://www.bilibili.com/video/BV1DfrdByE2H/) `bilibili` UP:吴恩达Agent | 含Tool Use/Function Calling设计模式讲解


---

## 三策略对比摘要 — 数据分析师 （数据分析师（零基础））

| 策略 | 步骤数 | 总学时 | 目标覆盖 | 平均难度 | 前3步技能顺序 |
|------|--------|--------|----------|----------|--------------|
| [最短路径] 快速通道 | 10步 | 262h | 100% | beginner | 高等数学基础(线代/概率) → Python基础 → SQL基础 |
| [最低难度] 由易到难 | 10步 | 262h | 100% | beginner | 高等数学基础(线代/概率) → Python基础 → SQL基础 |
| [最全覆盖] 系统学习 | 12步 | 352h | 100% | beginner | 高等数学基础(线代/概率) → Python基础 → SQL基础 |

> **选路说明**
> - **最短路径**：跳过理论基础直达应用层，步骤最少，适合有一定背景、追求速成的学习者
> - **最低难度**：完整前置链路，贪心优先选最简单的可学技能，适合零基础逐步进阶
> - **最全覆盖**：完整路径+扩展技能，含底层原理，适合追求系统掌握的学习者

## 目标岗位：数据分析师  [最短路径] 快速通道

| 指标 | 数值 |
|------|------|
| 总学时 | **262h** |
| 学习步骤 | **10 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **beginner** |
| 难度分布 | 入门7步 / 中级3步 / 进阶0步 |

**用户已有**：零基础
**缺口技能**：A/B测试, 数据可视化Matplotlib, NumPy科学计算, Pandas数据处理, Python基础, SQL高级查询, SQL基础, 统计学基础, Tableau/PowerBI

---

### Step 1. 高等数学基础(线代/概率) [入门]
- 分类：数学基础　学时：60h　难度：beginner
- 推荐资源：
  - [Mathematics for Machine Learning: Linear Algebra](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning:+Linear+Algebra) `coursera` Imperial College London | rating:4.7
  - [Mathematics for Machine Learning](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning) `coursera` Imperial College London | rating:4.6
  - [Linear Algebra for Machine Learning and Data Science](https://www.coursera.org/search?query=Linear+Algebra+for+Machine+Learning+and+Data+Science) `coursera` DeepLearning.AI | rating:4.6

### Step 2. Python基础 [入门]
- 分类：编程语言　学时：40h　难度：beginner
- 推荐资源：
  - [Python Programming Fundamentals](https://www.coursera.org/search?query=Python+Programming+Fundamentals) `coursera` Duke University | rating:4.7
  - [Python Basics](https://www.coursera.org/search?query=Python+Basics) `coursera` University of Michigan | rating:4.8
  - [Introduction to Python Programming](https://www.coursera.org/search?query=Introduction+to+Python+Programming) `coursera` University of Pennsylvania | rating:4.6

### Step 3. SQL基础 [入门]
- 分类：数据库　学时：20h　难度：beginner
- 推荐资源：
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Database Management Essentials](https://www.coursera.org/search?query=Database+Management+Essentials) `coursera` University of Colorado System | rating:4.8
  - [Relational Database Support for Data Warehouses](https://www.coursera.org/search?query=Relational+Database+Support+for+Data+Warehouses) `coursera` University of Colorado System | rating:4.8

### Step 4. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 5. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 6. Tableau/PowerBI [入门]
- 分类：数据可视化　学时：20h　难度：beginner
- 推荐资源：
  - [Foundations of Business Intelligence](https://www.coursera.org/search?query=Foundations+of+Business+Intelligence) `coursera` Google | rating:4.8
  - [Business intelligence and data warehousing](https://www.coursera.org/search?query=Business+intelligence+and+data+warehousing) `coursera` Universidad Nacional Autónoma de México | rating:4.1
  - [Business Intelligence Concepts, Tools, and Applications](https://www.coursera.org/search?query=Business+Intelligence+Concepts,+Tools,+and+Applications) `coursera` University of Colorado System | rating:4.3

### Step 7. SQL高级查询 [中级]
- 分类：数据库　学时：20h　难度：intermediate
- 推荐资源：
  - [SQL进阶教程：窗口函数/子查询/性能优化全解析](https://search.bilibili.com/all?keyword=SQL进阶+窗口函数+数据分析) `bilibili` B站搜索补充资源 | 推荐搜索: SQL进阶 窗口函数 数据分析
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Web Applications for Everybody](https://www.coursera.org/search?query=Web+Applications+for+Everybody) `coursera` University of Michigan ★4.7 | 含SQL/MySQL/关系数据库/数据建模

### Step 8. 统计学基础 [中级]
- 分类：数据科学　学时：40h　难度：intermediate
- 推荐资源：
  - [Introduction to Statistical Analysis:  Hypothesis Testing](https://www.coursera.org/search?query=Introduction+to+Statistical+Analysis:++Hypothesis+Testing) `coursera` SAS | rating:4.5
  - [Introduction to Statistics](https://www.coursera.org/search?query=Introduction+to+Statistics) `coursera` Stanford University | rating:4.6
  - [Statistics Foundations](https://www.coursera.org/search?query=Statistics+Foundations) `coursera` Meta | rating:4.8

### Step 9. 数据可视化Matplotlib [入门]
- 分类：数据可视化　学时：12h　难度：beginner
- 推荐资源：
  - [Data Visualization with Python](https://www.coursera.org/search?query=Data+Visualization+with+Python) `coursera` Duke University | rating:4.9

### Step 10. A/B测试 [中级]
- 分类：数据科学　学时：15h　难度：intermediate
- 推荐资源：
  - [Design of Experiments](https://www.coursera.org/search?query=Design+of+Experiments) `coursera` Arizona State University | rating:4.7
  - [ANOVA and Experimental Design](https://www.coursera.org/search?query=ANOVA+and+Experimental+Design) `coursera` University of Colorado Boulder | rating:3.7
  - [Data Wrangling, Analysis and AB Testing with SQL](https://www.coursera.org/search?query=Data+Wrangling,+Analysis+and+AB+Testing+with+SQL) `coursera` University of California, Davis | rating:4.7


---

## 目标岗位：数据分析师  [最低难度] 由易到难

| 指标 | 数值 |
|------|------|
| 总学时 | **262h** |
| 学习步骤 | **10 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **beginner** |
| 难度分布 | 入门7步 / 中级3步 / 进阶0步 |

**用户已有**：零基础
**缺口技能**：A/B测试, 数据可视化Matplotlib, NumPy科学计算, Pandas数据处理, Python基础, SQL高级查询, SQL基础, 统计学基础, Tableau/PowerBI

---

### Step 1. 高等数学基础(线代/概率) [入门]
- 分类：数学基础　学时：60h　难度：beginner
- 推荐资源：
  - [Mathematics for Machine Learning: Linear Algebra](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning:+Linear+Algebra) `coursera` Imperial College London | rating:4.7
  - [Mathematics for Machine Learning](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning) `coursera` Imperial College London | rating:4.6
  - [Linear Algebra for Machine Learning and Data Science](https://www.coursera.org/search?query=Linear+Algebra+for+Machine+Learning+and+Data+Science) `coursera` DeepLearning.AI | rating:4.6

### Step 2. Python基础 [入门]
- 分类：编程语言　学时：40h　难度：beginner
- 推荐资源：
  - [Python Programming Fundamentals](https://www.coursera.org/search?query=Python+Programming+Fundamentals) `coursera` Duke University | rating:4.7
  - [Python Basics](https://www.coursera.org/search?query=Python+Basics) `coursera` University of Michigan | rating:4.8
  - [Introduction to Python Programming](https://www.coursera.org/search?query=Introduction+to+Python+Programming) `coursera` University of Pennsylvania | rating:4.6

### Step 3. SQL基础 [入门]
- 分类：数据库　学时：20h　难度：beginner
- 推荐资源：
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Database Management Essentials](https://www.coursera.org/search?query=Database+Management+Essentials) `coursera` University of Colorado System | rating:4.8
  - [Relational Database Support for Data Warehouses](https://www.coursera.org/search?query=Relational+Database+Support+for+Data+Warehouses) `coursera` University of Colorado System | rating:4.8

### Step 4. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 5. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 6. 数据可视化Matplotlib [入门]
- 分类：数据可视化　学时：12h　难度：beginner
- 推荐资源：
  - [Data Visualization with Python](https://www.coursera.org/search?query=Data+Visualization+with+Python) `coursera` Duke University | rating:4.9

### Step 7. Tableau/PowerBI [入门]
- 分类：数据可视化　学时：20h　难度：beginner
- 推荐资源：
  - [Foundations of Business Intelligence](https://www.coursera.org/search?query=Foundations+of+Business+Intelligence) `coursera` Google | rating:4.8
  - [Business intelligence and data warehousing](https://www.coursera.org/search?query=Business+intelligence+and+data+warehousing) `coursera` Universidad Nacional Autónoma de México | rating:4.1
  - [Business Intelligence Concepts, Tools, and Applications](https://www.coursera.org/search?query=Business+Intelligence+Concepts,+Tools,+and+Applications) `coursera` University of Colorado System | rating:4.3

### Step 8. SQL高级查询 [中级]
- 分类：数据库　学时：20h　难度：intermediate
- 推荐资源：
  - [SQL进阶教程：窗口函数/子查询/性能优化全解析](https://search.bilibili.com/all?keyword=SQL进阶+窗口函数+数据分析) `bilibili` B站搜索补充资源 | 推荐搜索: SQL进阶 窗口函数 数据分析
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Web Applications for Everybody](https://www.coursera.org/search?query=Web+Applications+for+Everybody) `coursera` University of Michigan ★4.7 | 含SQL/MySQL/关系数据库/数据建模

### Step 9. 统计学基础 [中级]
- 分类：数据科学　学时：40h　难度：intermediate
- 推荐资源：
  - [Introduction to Statistical Analysis:  Hypothesis Testing](https://www.coursera.org/search?query=Introduction+to+Statistical+Analysis:++Hypothesis+Testing) `coursera` SAS | rating:4.5
  - [Introduction to Statistics](https://www.coursera.org/search?query=Introduction+to+Statistics) `coursera` Stanford University | rating:4.6
  - [Statistics Foundations](https://www.coursera.org/search?query=Statistics+Foundations) `coursera` Meta | rating:4.8

### Step 10. A/B测试 [中级]
- 分类：数据科学　学时：15h　难度：intermediate
- 推荐资源：
  - [Design of Experiments](https://www.coursera.org/search?query=Design+of+Experiments) `coursera` Arizona State University | rating:4.7
  - [ANOVA and Experimental Design](https://www.coursera.org/search?query=ANOVA+and+Experimental+Design) `coursera` University of Colorado Boulder | rating:3.7
  - [Data Wrangling, Analysis and AB Testing with SQL](https://www.coursera.org/search?query=Data+Wrangling,+Analysis+and+AB+Testing+with+SQL) `coursera` University of California, Davis | rating:4.7


---

## 目标岗位：数据分析师  [最全覆盖] 系统学习

| 指标 | 数值 |
|------|------|
| 总学时 | **352h** |
| 学习步骤 | **12 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **beginner** |
| 难度分布 | 入门8步 / 中级4步 / 进阶0步 |

**用户已有**：零基础
**缺口技能**：A/B测试, 数据可视化Matplotlib, NumPy科学计算, Pandas数据处理, Python基础, SQL高级查询, SQL基础, 统计学基础, Tableau/PowerBI

---

### Step 1. 高等数学基础(线代/概率) [入门]
- 分类：数学基础　学时：60h　难度：beginner
- 推荐资源：
  - [Mathematics for Machine Learning: Linear Algebra](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning:+Linear+Algebra) `coursera` Imperial College London | rating:4.7
  - [Mathematics for Machine Learning](https://www.coursera.org/search?query=Mathematics+for+Machine+Learning) `coursera` Imperial College London | rating:4.6
  - [Linear Algebra for Machine Learning and Data Science](https://www.coursera.org/search?query=Linear+Algebra+for+Machine+Learning+and+Data+Science) `coursera` DeepLearning.AI | rating:4.6

### Step 2. Python基础 [入门]
- 分类：编程语言　学时：40h　难度：beginner
- 推荐资源：
  - [Python Programming Fundamentals](https://www.coursera.org/search?query=Python+Programming+Fundamentals) `coursera` Duke University | rating:4.7
  - [Python Basics](https://www.coursera.org/search?query=Python+Basics) `coursera` University of Michigan | rating:4.8
  - [Introduction to Python Programming](https://www.coursera.org/search?query=Introduction+to+Python+Programming) `coursera` University of Pennsylvania | rating:4.6

### Step 3. SQL基础 [入门]
- 分类：数据库　学时：20h　难度：beginner
- 推荐资源：
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Database Management Essentials](https://www.coursera.org/search?query=Database+Management+Essentials) `coursera` University of Colorado System | rating:4.8
  - [Relational Database Support for Data Warehouses](https://www.coursera.org/search?query=Relational+Database+Support+for+Data+Warehouses) `coursera` University of Colorado System | rating:4.8

### Step 4. 数据结构与算法 [入门]
- 分类：计算机基础　学时：30h　难度：beginner
- 推荐资源：
  - [Foundations of Data Structures and Algorithms](https://www.coursera.org/search?query=Foundations+of+Data+Structures+and+Algorithms) `coursera` University of Colorado Boulder | rating:4.6
  - [Data Structures and Algorithms](https://www.coursera.org/search?query=Data+Structures+and+Algorithms) `coursera` University of California San Diego | rating:4.6
  - [leetcode-notes](https://github.com/datawhalechina/leetcode-notes) `github` stars:1110 | datawhalechina/leetcode-notes

### Step 5. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 6. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 7. Tableau/PowerBI [入门]
- 分类：数据可视化　学时：20h　难度：beginner
- 推荐资源：
  - [Foundations of Business Intelligence](https://www.coursera.org/search?query=Foundations+of+Business+Intelligence) `coursera` Google | rating:4.8
  - [Business intelligence and data warehousing](https://www.coursera.org/search?query=Business+intelligence+and+data+warehousing) `coursera` Universidad Nacional Autónoma de México | rating:4.1
  - [Business Intelligence Concepts, Tools, and Applications](https://www.coursera.org/search?query=Business+Intelligence+Concepts,+Tools,+and+Applications) `coursera` University of Colorado System | rating:4.3

### Step 8. SQL高级查询 [中级]
- 分类：数据库　学时：20h　难度：intermediate
- 推荐资源：
  - [SQL进阶教程：窗口函数/子查询/性能优化全解析](https://search.bilibili.com/all?keyword=SQL进阶+窗口函数+数据分析) `bilibili` B站搜索补充资源 | 推荐搜索: SQL进阶 窗口函数 数据分析
  - [Database Architecture, Scale, and NoSQL with Elasticsearch](https://www.coursera.org/search?query=Database+Architecture,+Scale,+and+NoSQL+with+Elasticsearch) `coursera` University of Michigan | rating:4.1
  - [Web Applications for Everybody](https://www.coursera.org/search?query=Web+Applications+for+Everybody) `coursera` University of Michigan ★4.7 | 含SQL/MySQL/关系数据库/数据建模

### Step 9. 统计学基础 [中级]
- 分类：数据科学　学时：40h　难度：intermediate
- 推荐资源：
  - [Introduction to Statistical Analysis:  Hypothesis Testing](https://www.coursera.org/search?query=Introduction+to+Statistical+Analysis:++Hypothesis+Testing) `coursera` SAS | rating:4.5
  - [Introduction to Statistics](https://www.coursera.org/search?query=Introduction+to+Statistics) `coursera` Stanford University | rating:4.6
  - [Statistics Foundations](https://www.coursera.org/search?query=Statistics+Foundations) `coursera` Meta | rating:4.8

### Step 10. 数据可视化Matplotlib [入门]
- 分类：数据可视化　学时：12h　难度：beginner
- 推荐资源：
  - [Data Visualization with Python](https://www.coursera.org/search?query=Data+Visualization+with+Python) `coursera` Duke University | rating:4.9

### Step 11. A/B测试 [中级]
- 分类：数据科学　学时：15h　难度：intermediate
- 推荐资源：
  - [Design of Experiments](https://www.coursera.org/search?query=Design+of+Experiments) `coursera` Arizona State University | rating:4.7
  - [ANOVA and Experimental Design](https://www.coursera.org/search?query=ANOVA+and+Experimental+Design) `coursera` University of Colorado Boulder | rating:3.7
  - [Data Wrangling, Analysis and AB Testing with SQL](https://www.coursera.org/search?query=Data+Wrangling,+Analysis+and+AB+Testing+with+SQL) `coursera` University of California, Davis | rating:4.7

### Step 12. 机器学习基础 [中级]
- 分类：机器学习　学时：60h　难度：intermediate
- 推荐资源：
  - [Introduction to Machine Learning: Supervised Learning](https://www.coursera.org/search?query=Introduction+to+Machine+Learning:+Supervised+Learning) `coursera` University of Colorado Boulder | rating:4.5
  - [Machine Learning Algorithms: Supervised Learning Tip to Tail](https://www.coursera.org/search?query=Machine+Learning+Algorithms:+Supervised+Learning+Tip+to+Tail) `coursera` Alberta Machine Intelligence Institute | rating:3.7
  - [Scikit-Learn For Machine Learning Classification Problems](https://www.coursera.org/search?query=Scikit-Learn+For+Machine+Learning+Classification+Problems) `coursera` Coursera Project Network | rating:4.4


---

## 三策略对比摘要 — 后端工程师 （后端工程师（有Python+SQL））

| 策略 | 步骤数 | 总学时 | 目标覆盖 | 平均难度 | 前3步技能顺序 |
|------|--------|--------|----------|----------|--------------|
| [最短路径] 快速通道 | 4步 | 53h | 100% | intermediate | Git版本控制 → Linux基础 → FastAPI部署 |
| [最低难度] 由易到难 | 4步 | 53h | 100% | intermediate | Git版本控制 → Linux基础 → Docker容器化 |
| [最全覆盖] 系统学习 | 7步 | 118h | 100% | beginner | Git版本控制 → Linux基础 → 数据结构与算法 |

> **选路说明**
> - **最短路径**：跳过理论基础直达应用层，步骤最少，适合有一定背景、追求速成的学习者
> - **最低难度**：完整前置链路，贪心优先选最简单的可学技能，适合零基础逐步进阶
> - **最全覆盖**：完整路径+扩展技能，含底层原理，适合追求系统掌握的学习者

## 目标岗位：后端工程师  [最短路径] 快速通道

| 指标 | 数值 |
|------|------|
| 总学时 | **53h** |
| 学习步骤 | **4 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门2步 / 中级2步 / 进阶0步 |

**用户已有**：sk_python_basic, sk_sql_basic
**缺口技能**：Docker容器化, FastAPI部署, Git版本控制, Linux基础

---

### Step 1. Git版本控制 [入门]
- 分类：工程工具　学时：8h　难度：beginner
- 推荐资源：
  - [Version Control with Git](https://www.coursera.org/search?query=Version+Control+with+Git) `coursera` Atlassian | rating:4.7
  - [【推荐搜索】B站搜索 Git教程 版本控制](https://search.bilibili.com/all?keyword=Git+版本控制+教程) `bilibili` 当前资源库暂无Git专项，推荐B站搜索黑马程序员Git教程
  - [Getting Started with Git and GitHub](https://www.coursera.org/search?query=Getting+Started+with+Git+and+GitHub) `coursera` IBM | rating:4.6

### Step 2. Linux基础 [入门]
- 分类：工程工具　学时：15h　难度：beginner
- 推荐资源：
  - [Hands-on Introduction to Linux Commands and Shell Scripting](https://www.coursera.org/search?query=Hands-on+Introduction+to+Linux+Commands+and+Shell+Scripting) `coursera` IBM | rating:4.6
  - [Linux Basics: The Command Line Interface - 6](https://www.coursera.org/search?query=Linux+Basics:+The+Command+Line+Interface+-+6) `coursera` Dartmouth College | rating:4.6
  - [Command Line Tools for Genomic Data Science](https://www.coursera.org/search?query=Command+Line+Tools+for+Genomic+Data+Science) `coursera` Johns Hopkins University | rating:4.9

### Step 3. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 4. Docker容器化 [中级]
- 分类：工程工具　学时：15h　难度：intermediate
- 推荐资源：
  - [Docker从入门到实战：容器化部署全流程教程](https://search.bilibili.com/all?keyword=Docker入门+容器化+部署) `bilibili` B站搜索补充资源 | 推荐搜索: Docker入门 容器化 K8s
  - [Docker for Beginners with Hands-on labs](https://www.coursera.org/search?query=Docker+for+Beginners+with+Hands-on+labs) `coursera` KodeKloud | rating:4.6
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容


---

## 目标岗位：后端工程师  [最低难度] 由易到难

| 指标 | 数值 |
|------|------|
| 总学时 | **53h** |
| 学习步骤 | **4 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **intermediate** |
| 难度分布 | 入门2步 / 中级2步 / 进阶0步 |

**用户已有**：sk_python_basic, sk_sql_basic
**缺口技能**：Docker容器化, FastAPI部署, Git版本控制, Linux基础

---

### Step 1. Git版本控制 [入门]
- 分类：工程工具　学时：8h　难度：beginner
- 推荐资源：
  - [Version Control with Git](https://www.coursera.org/search?query=Version+Control+with+Git) `coursera` Atlassian | rating:4.7
  - [【推荐搜索】B站搜索 Git教程 版本控制](https://search.bilibili.com/all?keyword=Git+版本控制+教程) `bilibili` 当前资源库暂无Git专项，推荐B站搜索黑马程序员Git教程
  - [Getting Started with Git and GitHub](https://www.coursera.org/search?query=Getting+Started+with+Git+and+GitHub) `coursera` IBM | rating:4.6

### Step 2. Linux基础 [入门]
- 分类：工程工具　学时：15h　难度：beginner
- 推荐资源：
  - [Hands-on Introduction to Linux Commands and Shell Scripting](https://www.coursera.org/search?query=Hands-on+Introduction+to+Linux+Commands+and+Shell+Scripting) `coursera` IBM | rating:4.6
  - [Linux Basics: The Command Line Interface - 6](https://www.coursera.org/search?query=Linux+Basics:+The+Command+Line+Interface+-+6) `coursera` Dartmouth College | rating:4.6
  - [Command Line Tools for Genomic Data Science](https://www.coursera.org/search?query=Command+Line+Tools+for+Genomic+Data+Science) `coursera` Johns Hopkins University | rating:4.9

### Step 3. Docker容器化 [中级]
- 分类：工程工具　学时：15h　难度：intermediate
- 推荐资源：
  - [Docker从入门到实战：容器化部署全流程教程](https://search.bilibili.com/all?keyword=Docker入门+容器化+部署) `bilibili` B站搜索补充资源 | 推荐搜索: Docker入门 容器化 K8s
  - [Docker for Beginners with Hands-on labs](https://www.coursera.org/search?query=Docker+for+Beginners+with+Hands-on+labs) `coursera` KodeKloud | rating:4.6
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容

### Step 4. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发


---

## 目标岗位：后端工程师  [最全覆盖] 系统学习

| 指标 | 数值 |
|------|------|
| 总学时 | **118h** |
| 学习步骤 | **7 步** |
| 目标技能覆盖 | **100%** |
| 平均难度 | **beginner** |
| 难度分布 | 入门5步 / 中级2步 / 进阶0步 |

**用户已有**：sk_python_basic, sk_sql_basic
**缺口技能**：Docker容器化, FastAPI部署, Git版本控制, Linux基础

---

### Step 1. Git版本控制 [入门]
- 分类：工程工具　学时：8h　难度：beginner
- 推荐资源：
  - [Version Control with Git](https://www.coursera.org/search?query=Version+Control+with+Git) `coursera` Atlassian | rating:4.7
  - [【推荐搜索】B站搜索 Git教程 版本控制](https://search.bilibili.com/all?keyword=Git+版本控制+教程) `bilibili` 当前资源库暂无Git专项，推荐B站搜索黑马程序员Git教程
  - [Getting Started with Git and GitHub](https://www.coursera.org/search?query=Getting+Started+with+Git+and+GitHub) `coursera` IBM | rating:4.6

### Step 2. Linux基础 [入门]
- 分类：工程工具　学时：15h　难度：beginner
- 推荐资源：
  - [Hands-on Introduction to Linux Commands and Shell Scripting](https://www.coursera.org/search?query=Hands-on+Introduction+to+Linux+Commands+and+Shell+Scripting) `coursera` IBM | rating:4.6
  - [Linux Basics: The Command Line Interface - 6](https://www.coursera.org/search?query=Linux+Basics:+The+Command+Line+Interface+-+6) `coursera` Dartmouth College | rating:4.6
  - [Command Line Tools for Genomic Data Science](https://www.coursera.org/search?query=Command+Line+Tools+for+Genomic+Data+Science) `coursera` Johns Hopkins University | rating:4.9

### Step 3. 数据结构与算法 [入门]
- 分类：计算机基础　学时：30h　难度：beginner
- 推荐资源：
  - [Foundations of Data Structures and Algorithms](https://www.coursera.org/search?query=Foundations+of+Data+Structures+and+Algorithms) `coursera` University of Colorado Boulder | rating:4.6
  - [Data Structures and Algorithms](https://www.coursera.org/search?query=Data+Structures+and+Algorithms) `coursera` University of California San Diego | rating:4.6
  - [leetcode-notes](https://github.com/datawhalechina/leetcode-notes) `github` stars:1110 | datawhalechina/leetcode-notes

### Step 4. NumPy科学计算 [入门]
- 分类：数据处理　学时：15h　难度：beginner
- 推荐资源：
  - [Data Science with NumPy, Sets, and Dictionaries](https://www.coursera.org/search?query=Data+Science+with+NumPy,+Sets,+and+Dictionaries) `coursera` Duke University | rating:2.9
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程

### Step 5. Pandas数据处理 [入门]
- 分类：数据处理　学时：20h　难度：beginner
- 推荐资源：
  - [Data Analysis in Python: Using Pandas DataFrames](https://www.coursera.org/search?query=Data+Analysis+in+Python:+Using+Pandas+DataFrames) `coursera` Coursera Project Network | rating:4.5
  - [data-science-complete-tutorial](https://github.com/edyoda/data-science-complete-tutorial) `github` stars:1822 | 含Pandas/NumPy/Matplotlib完整数据科学教程
  - [BiteSize Python: NumPy and Pandas](https://www.coursera.org/search?query=BiteSize+Python:+NumPy+and+Pandas) `coursera` University of Colorado Boulder | rating:4.8

### Step 6. FastAPI部署 [中级]
- 分类：后端工程　学时：15h　难度：intermediate
- 推荐资源：
  - [黑马程序员 Python Web开发 FastAPI从入门到实战](https://www.bilibili.com/video/BV1zV2QBtE39/) `bilibili` UP:黑马程序员 | 播放量82.5万；FastAPI最强中文课；含实战项目+AI问答功能；首选推荐
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容
  - [从0到1学习FastAPI框架的所有知识点（慕课网官方）](https://www.bilibili.com/video/BV1iN411X72b/) `bilibili` UP:慕课网官方账号 | 播放量14.6万；慕课网系统课；高性能API服务开发

### Step 7. Docker容器化 [中级]
- 分类：工程工具　学时：15h　难度：intermediate
- 推荐资源：
  - [Docker从入门到实战：容器化部署全流程教程](https://search.bilibili.com/all?keyword=Docker入门+容器化+部署) `bilibili` B站搜索补充资源 | 推荐搜索: Docker入门 容器化 K8s
  - [Docker for Beginners with Hands-on labs](https://www.coursera.org/search?query=Docker+for+Beginners+with+Hands-on+labs) `coursera` KodeKloud | rating:4.6
  - [尚学堂 FastAPI框架入门教程从0到1快速上手](https://www.bilibili.com/video/BV1eKpizeEnb/) `bilibili` UP:尚学堂官方 | 播放量14.2万；含ORM/中间件/DDD架构进阶内容


---
