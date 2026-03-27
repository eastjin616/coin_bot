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

def ask_agent(message: str) -> str:
    settings = get_settings()
    if not settings.groq_api_key:
        return "Groq API 키가 설정되지 않았습니다."

    llm = ChatGroq(
        api_key=settings.groq_api_key,
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0,
    )
    tools = [get_portfolio_tool, get_trade_history_tool, get_market_signal_tool]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=3)

    try:
        result = executor.invoke({"input": message})
        return result.get("output", "답변을 생성하지 못했습니다.")
    except Exception as e:
        logger.error(f"Agent 실행 오류: {e}")
        return f"오류가 발생했습니다: {str(e)}"
