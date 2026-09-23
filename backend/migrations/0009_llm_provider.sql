-- 0009_llm_provider.sql：llm_config 增加 provider 字段，支持多家 LLM 厂商。
-- 默认 'openai'：所有走 /chat/completions 协议的服务（DeepSeek / SiliconFlow /
-- Qwen / Kimi / 智谱 / Ollama / OpenAI 自身 ...）。
-- 'anthropic'：Claude Messages API。
-- 'gemini'：Google Gemini generateContent API。
ALTER TABLE llm_config ADD COLUMN provider TEXT DEFAULT 'openai';
