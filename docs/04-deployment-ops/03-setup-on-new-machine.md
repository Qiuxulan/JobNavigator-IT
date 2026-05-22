# 新机器拉取与环境配置总手册（唯一入口）

本文件是**唯一**环境安装与运行说明。  
其他文档不再重复写安装命令，统一引用本文件。

---

## 1. 前置安装

在新电脑上先安装：

1. Git
2. Conda（Miniconda / Anaconda）
3. Docker Desktop（Windows 建议启用 WSL2）

检查是否成功：

```bash
git --version
conda --version
docker --version
docker compose version
```

---

## 2. 拉取项目

```bash
git clone <你的仓库地址>
cd JobNavigator-IT
```

---

## 3. 创建与更新 Python 环境

首次创建：

```bash
conda env create -f environment.yml
conda activate jobnavigator-it
```

已有同名环境时更新：

```bash
conda env update -f environment.yml --prune
conda activate jobnavigator-it
```

---

## 4. 本地运行（不使用 Docker）

1. 运行测试

```bash
pytest -q
```

2. 启动 API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

3. 打开接口文档

`http://localhost:8000/docs`

---

## 5. Docker 运行（联调用）

启动：

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build
```

查看状态：

```bash
docker compose -f infra/docker/docker-compose.yml ps
```

停止：

```bash
docker compose -f infra/docker/docker-compose.yml down
```

---

## 6. 常见问题

1. `docker: command not found`
: Docker 未安装或未启动

2. Docker 拉镜像失败（超时 / 连接失败）
: 检查网络与代理；必要时配置镜像源

3. `conda run` 临时文件冲突
: 建议先 `conda activate`，再直接执行命令

4. `pytest` 出现缓存权限警告
: 不影响主要结果；可手动删除 `.pytest_cache`

---

## 7. 提交前最低检查

1. `pytest -q` 通过
2. 能打开 `http://localhost:8000/docs`
3. `git status` 没有误提交本地数据/缓存/密钥

