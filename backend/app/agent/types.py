from enum import Enum


class TaskType(str, Enum):
    CODE_QA = "CODE_QA"
    TRACE_CHAIN = "TRACE_CHAIN"
    CHANGE_PLAN = "CHANGE_PLAN"
