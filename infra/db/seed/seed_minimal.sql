INSERT INTO job_roles (job_id, title, fine_role, coarse_role, city, salary_min_k, salary_max_k, required_skills)
VALUES
('job_rag_001', 'RAG应用工程师', 'RAG应用工程师', 'AI工程师', '上海', 25, 45, '["Python", "LangChain", "RAG"]')
ON CONFLICT (job_id) DO NOTHING;

