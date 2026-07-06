from functools import partial

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import (
    get_agent_planner,
    get_embedding_service,
    get_graph_context_builder,
    get_llm_client,
    get_rag_context_builder,
    get_vector_store,
    get_query_rewriter,
)
from app.agent.executor import AgentExecutor
from app.agent.planner import SimpleAgentPlanner
from app.agent.tool_registry import ToolRegistry
from app.graph.query_service import GraphQueryService
from app.llm.client import LlmClient
from app.rag.context_builder import RagContextBuilder
from app.rag.graph_context_builder import GraphContextBuilder
from app.rag.graph_retriever import GraphRagRetriever
from app.retrieval.embedding_service import EmbeddingService
from app.retrieval.hybrid_search import HybridSearchService
from app.retrieval.keyword_search import KeywordSearchService
from app.retrieval.vector_store import QdrantVectorStore
from app.retrieval.query_rewriter import LlmQueryRewriter
from app.schemas.agent import (
    AgentChatRequest,
    AgentChatResponse,
    CodeQaRequest,
    CodeQaResponse,
    ConversationRead,
    TraceRequest,
    TraceResponse,
)
from app.services.agent_chat_service import AgentChatService
from app.services.change_plan_service import ChangePlanService
from app.services.code_qa_service import CodeQaService
from app.services.conversation_service import ConversationService
from app.services.trace_service import TraceService

router = APIRouter()


def get_conversation_service(
    session: Session = Depends(get_session),
) -> ConversationService:
    return ConversationService(session)


def get_code_qa_service(
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    context_builder: RagContextBuilder = Depends(get_rag_context_builder),
    llm: LlmClient = Depends(get_llm_client),
    rewriter: LlmQueryRewriter = Depends(get_query_rewriter),
) -> CodeQaService:
    search = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
        rewriter=rewriter,
    )
    return CodeQaService(
        search=search,
        context_builder=context_builder,
        llm=llm,
    )


@router.post("/code-qa", response_model=CodeQaResponse)
def answer_code_question(
    data: CodeQaRequest,
    service: CodeQaService = Depends(get_code_qa_service),
) -> CodeQaResponse:
    return service.answer(
        project_id=data.project_id,
        question=data.question,
        limit=data.limit,
    )


def get_trace_service(
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    context_builder: GraphContextBuilder = Depends(
        get_graph_context_builder
    ),
    llm: LlmClient = Depends(get_llm_client),
    rewriter: LlmQueryRewriter = Depends(get_query_rewriter),
) -> TraceService:
    search = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
        rewriter=rewriter,
    )
    graph = GraphQueryService(session)
    return TraceService(
        retriever=GraphRagRetriever(search=search, graph=graph),
        graph=graph,
        context_builder=context_builder,
        llm=llm,
    )


@router.post("/trace", response_model=TraceResponse)
def trace_code_chain(
    data: TraceRequest,
    service: TraceService = Depends(get_trace_service),
) -> TraceResponse:
    return service.answer(
        data.project_id,
        data.question,
        limit=data.limit,
        max_depth=data.max_depth,
    )


def get_agent_chat_service(
    session: Session = Depends(get_session),
    embeddings: EmbeddingService = Depends(get_embedding_service),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
    rag_context_builder: RagContextBuilder = Depends(
        get_rag_context_builder
    ),
    graph_context_builder: GraphContextBuilder = Depends(
        get_graph_context_builder
    ),
    llm: LlmClient = Depends(get_llm_client),
    planner: SimpleAgentPlanner = Depends(get_agent_planner),
    rewriter: LlmQueryRewriter = Depends(get_query_rewriter),
) -> AgentChatService:
    search = HybridSearchService(
        embeddings=embeddings,
        vector_store=vector_store,
        keyword_search=KeywordSearchService(session),
        rewriter=rewriter,
    )
    graph = GraphQueryService(session)
    code_qa = CodeQaService(
        search=search,
        context_builder=rag_context_builder,
        llm=llm,
    )
    trace = TraceService(
        retriever=GraphRagRetriever(search=search, graph=graph),
        graph=graph,
        context_builder=graph_context_builder,
        llm=llm,
    )
    change_plan = ChangePlanService(
        search=search,
        graph=graph,
        context_builder=graph_context_builder,
        llm=llm,
    )
    tools = ToolRegistry()
    tools.register("hybrid_search", search.search)
    tools.register("graph_search", graph.traverse)
    tools.register(
        "read_entity",
        partial(
            graph.traverse,
            max_depth=0,
            relation_types=None,
        ),
    )
    tools.register("get_related_entities", graph.expand_entities)
    return AgentChatService(
        planner=planner,
        executor=AgentExecutor(
            code_qa=code_qa,
            trace=trace,
            change_plan=change_plan,
        ),
        conversations=ConversationService(session),
        tools=tools,
    )


@router.post("/chat", response_model=AgentChatResponse)
def answer_agent_chat(
    data: AgentChatRequest,
    service: AgentChatService = Depends(get_agent_chat_service),
) -> AgentChatResponse:
    return service.answer(
        project_id=data.project_id,
        question=data.question,
        conversation_id=data.conversation_id,
        limit=data.limit,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationRead,
)
def read_agent_conversation(
    conversation_id: int,
    project_id: int,
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationRead:
    conversation = service.get_for_project(conversation_id, project_id)
    return ConversationRead.from_model(conversation)
