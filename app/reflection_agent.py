from pydantic_ai import RunContext, Agent
from typing import Dict, Any
from datetime import datetime, timedelta
import pytz
from .base_agent import BaseAgent
from .agent_dataclasses import CalendarDependencies
import logfire
from .config import LOGFIRE_TOKEN, MODEL_TEMPRATURE
import logging
from .agent_dataclasses import AgentResponse, CalendarDependencies


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logfire.configure(token=LOGFIRE_TOKEN, scrubbing=False)
logfire.instrument_pydantic_ai()


class ReflectionAgent(BaseAgent):
    """Reflection-focused AI agent for insights and personal growth"""

    def __init__(self, calendar_service, user_id, user, db):
        self.calendar_service = calendar_service
        self.timezone = getattr(calendar_service, "timezone", pytz.UTC)
        
        system_prompt = f"""You are a reflection and insights assistant. Current date/time: {self._get_current_time()}

        ## Core Purpose
        - **Analyze**: Review user's activities, conversations, and patterns
        - **Reflect**: Generate thoughtful questions and insights about productivity and well-being
        - **Guide**: Offer personalized suggestions for improvement and growth

        ## Rules
        1. Focus on meaningful insights, not just data summaries
        2. Ask thoughtful questions that promote self-reflection
        3. Connect patterns across different time periods
        4. Provide actionable suggestions for improvement
        5. Be empathetic and encouraging in tone

        ## Available Tools
        - get_calendar_events: Access historical and upcoming events
        - get_events_for_date: Review specific day activities
        - search_calendar_events: Find patterns in event types
        - summarize_conversations: Summarize recent conversations with insights

        Keep responses thoughtful and focused on personal growth."""
        
        super().__init__(calendar_service, user_id, user, db, system_prompt)
        
        self.summery_agent = Agent(
            self.model,
            deps_type=CalendarDependencies,
            output_type=AgentResponse,
            model_settings={"temperature": MODEL_TEMPRATURE},
        )

        self._register_reflection_tools()

    def _register_reflection_tools(self):
        """Register reflection-specific tools"""

        @self.agent.tool
        async def summarize_conversations(
            ctx: RunContext[CalendarDependencies], days: int = 7
        ) -> Dict[str, Any]:
            """Summarize user conversations using the agent"""
            try:
                from .database_utils import ConversationService

                period_ago = self._get_current_time() - timedelta(days=days)
                conversations = ConversationService.get_user_conversations_since(
                    ctx.deps.db, ctx.deps.user_id, period_ago
                )

                if not conversations:
                    return {
                        "message": f"No conversations found in the past {days} days to summarize"
                    }

                # Prepare conversation data for summarization
                conversation_data = []
                for conv in conversations:
                    messages = ConversationService.get_conversation_messages(
                        ctx.deps.db, conv.id
                    )
                    conversation_summary = {
                        "title": conv.title,
                        "created_at": conv.created_at.isoformat(),
                        "message_count": len(messages),
                        "messages": [
                            {
                                "role": msg.role,
                                "content": (
                                    msg.content[:200] + "..."
                                    if len(msg.content) > 200
                                    else msg.content
                                ),
                            }
                            for msg in messages[-10:]
                        ],  # Last 10 messages, truncated
                    }
                    conversation_data.append(conversation_summary)

                # Use the agent to create summaries
                summary_prompt = f"Analyze and summarize these {len(conversations)} conversations from the past {days} days. For each conversation, provide a concise summary highlighting key topics, decisions, and outcomes: {conversation_data}"
                deps = CalendarDependencies(
                    calendar_service=ctx.deps.calendar_service,
                    user_id=ctx.deps.user_id,
                    user=ctx.deps.user,
                    db=ctx.deps.db,
                    pending_actions=[],
                )
                result = await self.summery_agent.run(summary_prompt, deps=deps)
                return {
                    "period": f"Past {days} days",
                    "conversation_count": len(conversations),
                    "total_messages": sum(
                        len(
                            ConversationService.get_conversation_messages(
                                ctx.deps.db, conv.id
                            )
                        )
                        for conv in conversations
                    ),
                    "summary": result.output.message,
                }

            except Exception as e:
                logger.error(f"Error summarizing conversations: {str(e)}")
                return {"error": f"Could not summarize conversations: {str(e)}"}

    async def generate_weekly_insights(self) -> str:
        """Generate weekly insights and reflection prompts"""
        try:
            current_pending_actions = []
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                user_id=self.user_id,
                user=self.user,
                db=self.db,
                pending_actions=current_pending_actions,
            )
            result = await self.agent.run(
                "Create a comprehensive summery for every conversation in the last 7 days",
                deps=deps,
            )

            return result.output.message
        except Exception as e:
            return f"Error generating insights: {str(e)}"
