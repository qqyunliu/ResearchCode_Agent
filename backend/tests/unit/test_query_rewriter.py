from app.retrieval.query_rewriter import LlmQueryRewriter, contains_cjk


class FakeLlm:
    def __init__(self, result="alert list API controller", error=None):
        self.result, self.error, self.calls = result, error, []

    def complete(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if self.error:
            raise self.error
        return self.result


def test_detects_cjk_and_rewrites_chinese() -> None:
    llm = FakeLlm()
    assert contains_cjk("告警 API")
    assert not contains_cjk("alert API")
    assert LlmQueryRewriter(llm).rewrite("告警列表 API 在哪里？") == "alert list API controller"
    assert llm.calls[0][1] == "告警列表 API 在哪里？"


def test_english_bypasses_llm_and_failure_falls_back() -> None:
    llm = FakeLlm(error=RuntimeError())
    rewriter = LlmQueryRewriter(llm)
    assert rewriter.rewrite("alert API") == "alert API"
    assert rewriter.rewrite("告警 API") == "告警 API"
