import os
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from ..agents import AgentRegistry, AgentRunner
from ..agents.course_recommendation.agent import CourseRecommendationAgent
from ..agents.course_recommendation.tools import get_course_recommendation_tools
from ..agents.learning_assistant.agent import LearningAssistantAgent
from ..agents.script_automation.agent import (
    ScriptAutomationAgent,
    initialize_script_state,
)
from ..core.global_state import (
    get_calendar,
    get_draft_calendar,
    load_script_sandbox_config,
    save_script_sandbox_config,
    get_script_sandbox_dir,
)
from ..services.init_calendar.loader import (
    init_draft_calendar,
    save_calendar_to_file,
    save_draft_calendar_to_file,
)
from ..services.llm_config import LLMConfig
from .document_qa_api import router as document_qa_router

# Ensure credentials directory exists at startup
CREDENTIALS_DIR = Path(__file__).resolve().parents[2] / "credentials"
CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
from .routes.calendar import router as calendar_router
from .routes.chat import router as chat_router
from .routes.chat_sessions import router as chat_sessions_router
from .routes.course_recommendation import router as course_recommendation_router
from .routes.learning_assistant import router as learning_assistant_router
from .routes.script_automation import router as script_automation_router
from .routes.settings import router as settings_router
from .routes.credentials import router as credentials_router

warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module="openpyxl",
)

CALENDAR_PERSIST_PATH = Path(__file__).resolve().parents[2] / "resources" / "calendar.json"
HISTORIES_DIR = Path(__file__).resolve().parents[2] / "resources" / "histories"
DRAFT_PERSIST_PATH = (
    Path(__file__).resolve().parents[2] / "resources" / "draft_calendar.json"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()

    # ── Step 0: Ensure credentials directory exists ────────────
    # This must happen before any tool tries to read/write credential files.
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[API] Credentials directory ready: {CREDENTIALS_DIR}")

    # ── Step 1: Load persisted LLM config (overrides env vars) ──
    # ── Lazy import: SchedulerDemoAgent depends on playwright (heavy) ──
    from ..agents.scheduler.agent import SchedulerDemoAgent, initialize_demo_state
    
    llm_config = LLMConfig.get_instance()
    llm_config.load_persisted()

    # ── Step 1: Main calendar (must load before draft) ────────
    initialize_demo_state(calendar_path=CALENDAR_PERSIST_PATH)

    # ── Step 2: Restore dirty draft calendar if available ─────
    init_draft_calendar(
        calendar_path=CALENDAR_PERSIST_PATH,
        draft_path=DRAFT_PERSIST_PATH,
    )

    summary_trigger = int(os.getenv("AGENT_SUMMARY_TRIGGER", "36"))
    summary_keep = int(os.getenv("AGENT_SUMMARY_KEEP", "14"))

    # ── Step 3: Build the shared ChatModelProxy instance ──────
    # ChatModelProxy wraps a ChatOpenAI and supports hot-swapping the
    # inner model without recompiling agent graphs (see settings API).
    # If no API key is configured yet, use a placeholder so all
    # LangChain agents can be pre-compiled at startup.
    llm = llm_config.build_chat_model(tier="smart")
    if llm is None:
        from ..services.llm_config import ChatModelProxy
        inner = ChatOpenAI(
            model=llm_config.get_tier_model("smart"),
            api_key=SecretStr("placeholder"),
            base_url=llm_config.base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
            temperature=0,
        )
        llm = ChatModelProxy(inner)
        print("[API] No API key found — agents pre-compiled with placeholder credentials.")

    # ── Step 4: Initialize all agents (always, even without key) ──
    scheduler_history_path = HISTORIES_DIR / "scheduler_history.json"
    agent = SchedulerDemoAgent(
        llm,
        max_steps=10,
        summary_trigger=summary_trigger,
        summary_keep=summary_keep,
        history_path=scheduler_history_path,
    )
    AgentRegistry.register("scheduler", agent)
    history_count = len(agent.messages)
    print(f"[API] Scheduler Agent initialized ({history_count} history messages).")

    try:
        saved_dir = load_script_sandbox_config()
        if saved_dir:
            initialize_script_state(Path(saved_dir))
            print(f"[API] Script sandbox restored from config: {saved_dir}")
        else:
            initialize_script_state()
            print(f"[API] Script sandbox initialized (default).")
    except Exception as e:
        print(f"[API] WARNING: Script sandbox initialization failed: {e}")

    script_history_path = HISTORIES_DIR / "script_automation_history.json"
    try:
        script_agent = ScriptAutomationAgent(
            llm,
            max_steps=10,
            summary_trigger=summary_trigger,
            summary_keep=summary_keep,
            history_path=script_history_path,
        )
        AgentRegistry.register("script_automation", script_agent)
        history_count = len(script_agent.messages)
        print(f"[API] Script Automation Agent initialized ({history_count} history messages).")
    except Exception as e:
        print(f"[API] WARNING: Script Automation Agent initialization failed: {e}")

    try:
        la_agent = LearningAssistantAgent(llm, max_steps=8)
        AgentRegistry.register("learning_assistant", la_agent)
        print("[API] Learning assistant agent initialized successfully.")
    except Exception as e:
        print(f"[API] WARNING: Learning Assistant Agent initialization failed: {e}")

    try:
        course_tools = get_course_recommendation_tools()
        course_agent = CourseRecommendationAgent(
            llm,
            max_steps=8,
            tools=course_tools,
        )
        AgentRegistry.register("course_recommendation", course_agent)
        print(f"[API] Course recommendation agent initialized with {len(course_tools)} tools, max_steps=8.")
    except Exception as e:
        print(f"[API] WARNING: Course Recommendation Agent initialization failed: {e}")

    try:
        from ..services.document_qa import get_document_qa_service
        qa_service = get_document_qa_service()
        qa_service.load_index()
        print("[API] Document QA service initialized successfully.")
    except Exception as e:
        print(f"[API] WARNING: Document QA service failed to initialize: {e}")

    yield

    # ── Shutdown: persist state in order ──────────────────────
    # 1. Main calendar (already being done).
    calendar = get_calendar()
    if calendar is not None:
        save_calendar_to_file(calendar, CALENDAR_PERSIST_PATH)
        print(f"[API] Calendar saved to {CALENDAR_PERSIST_PATH}")

    # 2. Agent conversation histories.
    for name in AgentRegistry.list_agents():
        agent = AgentRegistry.get(name)
        if hasattr(agent, 'runner') and hasattr(agent.runner, 'messages'):
            path = HISTORIES_DIR / f"{name}_history.json"
            AgentRunner.save_history(agent.runner.messages, path)
            print(f"[API] {name} history saved ({len(agent.runner.messages)} messages).")

    # 3. Sandbox directory config.
    sandbox_dir = get_script_sandbox_dir()
    if sandbox_dir:
        save_script_sandbox_config(sandbox_dir)
        print(f"[API] Sandbox config saved: {sandbox_dir}")

    # 4. Draft calendar (saved last so main calendar is already on disk).
    draft = get_draft_calendar()
    if draft is not None:
        save_draft_calendar_to_file(draft, DRAFT_PERSIST_PATH)
        print(f"[API] Draft calendar saved to {DRAFT_PERSIST_PATH}")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Smart Campus Assistant API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(calendar_router)
    app.include_router(chat_router)
    app.include_router(chat_sessions_router)
    app.include_router(document_qa_router)
    app.include_router(learning_assistant_router)
    app.include_router(script_automation_router)
    app.include_router(course_recommendation_router)
    app.include_router(settings_router)
    app.include_router(credentials_router)

    @app.get("/api/health")
    def health_check():
        return {
            "status": "ok",
            "calendar_initialized": get_calendar() is not None,
            "draft_initialized": get_draft_calendar() is not None,
        }

    return app


app = create_app()
