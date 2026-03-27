# backend/ai/chat_agent.py
import logging
from langchain_groq import ChatGroq
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.prompts import ChatPromptTemplate
from backend.ai.agent_tools import get_portfolio_tool, get_trade_history_tool, get_market_signal_tool
from backend.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 coin_bot 투자 어시스턴트입니다.
사용자의 암호화폐 포트폴리오와 매매 내역을 조회할 수 있는 툴을 가지고 있습니다.
항상 한국어로 답변하세요. 숫자는 쉼표로 구분하고, 수익은 +/- 기호를 붙여 명확히 표시하세요.
모르는 정보는 툴로 조회한 뒤 답변하세요."""

MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

def ask_agent(message: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        return "Groq API 키가 설정되지 않았습니다."

    tools = [get_portfolio_tool, get_trade_history_tool, get_market_signal_tool]
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    last_error = None
    for model in MODELS:
        try:
            llm = ChatGroq(api_key=settings.groq_api_key, model=model, temperature=0)
            agent = create_tool_calling_agent(llm, tools, prompt)
            executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=3)
            result = executor.invoke({"input": message})
            logger.info(f"Chat agent 응답 완료 (모델: {model})")
            return result.get("output", "답변을 생성하지 못했습니다.")
        except Exception as e:
            logger.warning(f"Chat agent 모델 {model} 실패: {e}")
            last_error = e
            continue

    logger.error(f"모든 모델 실패: {last_error}")
    return "현재 AI 서비스가 일시적으로 불가합니다. 잠시 후 다시 시도해주세요."
