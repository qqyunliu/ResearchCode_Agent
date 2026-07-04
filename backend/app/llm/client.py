from typing import Any, Protocol


class LlmClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class OpenAICompatibleLlmClient:
    def __init__(
        self,
        model: str,
        api_key: str | None,
        *,
        base_url: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("RCA_LLM_API_KEY is required")
        self.model = model
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, base_url=base_url)
        self.client = client

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        completion = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("LLM returned an empty response")
        return str(content)
