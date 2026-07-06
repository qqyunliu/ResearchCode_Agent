import re
from typing import Protocol

from app.llm.client import LlmClient

REWRITE_PROMPT = """Rewrite a Chinese code-search question as one concise line of English search keywords.
Preserve code identifiers, file names, API paths, and field names exactly.
Do not answer the question. Do not use Markdown or add explanations."""


class QueryRewriter(Protocol):
    def rewrite(self, query: str) -> str: ...


def contains_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", text) is not None


class LlmQueryRewriter:
    def __init__(self, llm: LlmClient) -> None:
        self.llm = llm

    def rewrite(self, query: str) -> str:
        original = query.strip()
        if not contains_cjk(original):
            return original
        try:
            rewritten = " ".join(
                self.llm.complete(REWRITE_PROMPT, original).split()
            )
            return rewritten or original
        except Exception:
            return original
