# agent/client.py
import os

from openai import OpenAI


class ResilientLLMRouter:
    def __init__(self):
        self.local_client = OpenAI(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
            timeout=5.0  # 5-second timeout for local edge
        )
        self.cloud_client = None
        if os.getenv("OPENAI_API_KEY"):
            self.cloud_client = OpenAI(
                base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                api_key=os.getenv("OPENAI_API_KEY")
            )
        self.local_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        self.cloud_model = os.getenv("OPENAI_MODEL", "gpt-4o")

    def chat_with_fallback(self, messages: list) -> str:
        """Attempts local execution first; falls back to cloud on failure."""
        try:
            response = self.local_client.chat.completions.create(
                model=self.local_model,
                messages=messages,
                temperature=0.1
            )
        except Exception as local_err:
            if self.cloud_client is None:
                raise RuntimeError(f"Local Ollama failed ({local_err}) and no OPENAI_API_KEY configured for fallback.") from local_err
            print(f"[Fallback] Local failed ({local_err}). Falling back to {self.cloud_model}...")
            response = self.cloud_client.chat.completions.create(
                model=self.cloud_model,
                messages=messages,
                temperature=0.1
            )
        content = response.choices[0].message.content
        return content if content is not None else ""