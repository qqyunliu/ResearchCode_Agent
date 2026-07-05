from app.agent.types import TaskType

CHANGE_PLAN_KEYWORDS = (
    "add ",
    "adding ",
    "change ",
    "changing ",
    "modify",
    "modification",
    "which files need",
    "affected files",
    "impact",
    "risk",
    "新增",
    "增加",
    "修改",
    "改哪些",
    "需要改",
    "影响",
    "风险",
    "字段",
)

TRACE_CHAIN_KEYWORDS = (
    "come from",
    "comes from",
    "data flow",
    "call chain",
    "call relationship",
    "frontend backend",
    "front-end back-end",
    "trace",
    "数据从哪里",
    "数据来源",
    "调用链",
    "调用关系",
    "链路",
    "前后端",
    "追踪",
)

CODE_QA_KEYWORDS = (
    "where",
    "which file",
    "implemented",
    "implementation",
    "method",
    "class",
    "function",
    "在哪里",
    "哪个文件",
    "怎么实现",
    "方法",
    "函数",
    "类",
)


class SimpleAgentPlanner:
    def plan(self, question: str) -> TaskType:
        normalized = " ".join(question.casefold().split())
        if not normalized:
            raise ValueError("question must not be blank")

        if self._contains(normalized, CHANGE_PLAN_KEYWORDS):
            return TaskType.CHANGE_PLAN
        if self._contains(normalized, TRACE_CHAIN_KEYWORDS):
            return TaskType.TRACE_CHAIN
        if self._contains(normalized, CODE_QA_KEYWORDS):
            return TaskType.CODE_QA
        return TaskType.CODE_QA

    @staticmethod
    def _contains(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)
