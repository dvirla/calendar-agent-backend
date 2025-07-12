from pydantic_ai import RunContext, Agent
from typing import Dict, Any
from datetime import timedelta
import pytz
from .base_agent import BaseAgent
from .agent_dataclasses import CalendarDependencies, AgentResponse
from pydantic import BaseModel
import logfire
from .config import LOGFIRE_TOKEN, MODEL_TEMPRATURE
import logging
from statistics import mean
from collections import defaultdict, Counter

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

logfire.configure(token=LOGFIRE_TOKEN, scrubbing=False)
logfire.instrument_pydantic_ai()


class InsightSection(BaseModel):
    """Structure for each insight section"""
    full_content: str
    summary: str

class StructuredInsights(BaseModel):
    """Structured output for insights"""
    goal_alignment: InsightSection
    energy_management: InsightSection
    time_allocation: InsightSection
    behavioral_trends: InsightSection

class InsightAgent(BaseAgent):
    """AI agent specialized in extracting behavioral insights from user data"""

    def __init__(self, calendar_service, user_id, user, db):
        self.calendar_service = calendar_service
        self.timezone = getattr(calendar_service, "timezone", pytz.UTC)
        
        system_prompt = f"""You are an insight extraction specialist. Current date/time: {self._get_current_time()}

        ## Core Purpose
        Extract actionable behavioral insights from user data across five key categories:
        
        **Productivity Patterns**: Identify when, where, and how the user is most/least effective
        **Goal Alignment**: Track progress and trajectory analysis toward stated objectives  
        **Energy Management**: Correlate activities with energy levels and mood patterns
        **Time Allocation**: Compare actual time use vs intended priorities
        **Behavioral Trends**: Detect emerging patterns in habits, decisions, and responses

        ## Analysis Approach
        1. **Data-Driven**: Base insights on quantitative patterns from calendar events and conversations
        2. **Pattern Recognition**: Identify recurring themes, anomalies, and trend changes
        3. **Contextual**: Consider time of day, day of week, duration, and frequency patterns
        4. **Actionable**: Provide specific, implementable recommendations
        5. **Longitudinal**: Track changes over time periods (daily, weekly, monthly)

        ## Available Tools
        - get_calendar_events: Access historical and upcoming events
        - get_events_for_date: Review specific day activities
        - search_calendar_events: Find patterns in event types
        - summarize_conversations: Analyze conversation patterns
        - analyze_productivity_patterns: Extract productivity insights
        - analyze_goal_alignment: Track goal progress
        - analyze_energy_patterns: Correlate activities with energy
        - analyze_time_allocation: Compare intended vs actual time use
        - analyze_behavioral_trends: Identify habit patterns

        Provide data-backed insights with specific metrics and actionable recommendations."""
        
        super().__init__(calendar_service, user_id, user, db, system_prompt)
        
        self.analysis_agent = Agent(
            self.model,
            deps_type=CalendarDependencies,
            output_type=StructuredInsights,
            model_settings={"temperature": MODEL_TEMPRATURE},
        )

        self._register_insight_tools()

    def _register_insight_tools(self):
        """Register insight-specific analysis tools"""

        @self.agent.tool
        async def analyze_productivity_patterns(
            ctx: RunContext[CalendarDependencies], days: int = 30
        ) -> Dict[str, Any]:
            """Analyze when, where, and how user is most/least productive"""
            try:
                events = ctx.deps.calendar_service.get_events(
                    days_ahead=0, days_back=days
                )
                
                if not events:
                    return {"message": f"No events found in the past {days} days"}

                # Analyze time patterns
                hour_productivity = defaultdict(list)
                day_productivity = defaultdict(list)
                meeting_types = Counter()
                duration_patterns = []
                
                for event in events:
                    start_time = self._get_timezone_aware_datetime(event.start_time)
                    end_time = self._get_timezone_aware_datetime(event.end_time)
                    duration = (end_time - start_time).total_seconds() / 3600
                    
                    hour_productivity[start_time.hour].append(duration)
                    day_productivity[start_time.strftime('%A')].append(duration)
                    duration_patterns.append(duration)
                    
                    # Categorize meeting types
                    title_lower = event.title.lower()
                    if any(word in title_lower for word in ['meeting', 'call', 'standup', 'sync']):
                        meeting_types['meetings'] += 1
                    elif any(word in title_lower for word in ['focus', 'work', 'coding', 'dev']):
                        meeting_types['focused_work'] += 1
                    elif any(word in title_lower for word in ['break', 'lunch', 'personal']):
                        meeting_types['breaks'] += 1
                    else:
                        meeting_types['other'] += 1

                # Calculate insights
                peak_hours = sorted(hour_productivity.items(), 
                                  key=lambda x: len(x[1]), reverse=True)[:3]
                most_productive_day = max(day_productivity.items(), 
                                        key=lambda x: len(x[1]))
                avg_meeting_duration = mean(duration_patterns) if duration_patterns else 0
                
                return {
                    "analysis_period": f"{days} days",
                    "total_events": len(events),
                    "peak_hours": [f"{hour}:00 ({len(events)} events)" 
                                 for hour, events in peak_hours],
                    "most_productive_day": f"{most_productive_day[0]} ({len(most_productive_day[1])} events)",
                    "meeting_distribution": dict(meeting_types),
                    "average_meeting_duration": round(avg_meeting_duration, 2),
                    "insights": self._generate_productivity_insights(
                        peak_hours, most_productive_day, meeting_types, avg_meeting_duration
                    )
                }

            except Exception as e:
                logger.error(f"Error analyzing productivity patterns: {str(e)}")
                return {"error": f"Could not analyze productivity patterns: {str(e)}"}

        @self.agent.tool
        async def analyze_goal_alignment(
            ctx: RunContext[CalendarDependencies], days: int = 30
        ) -> Dict[str, Any]:
            """Analyze progress toward stated goals and objectives"""
            try:
                events = ctx.deps.calendar_service.get_events(
                    days_ahead=0, days_back=days
                )
                
                if not events:
                    return {"message": f"No events found in the past {days} days"}

                # Categorize events by potential goals
                goal_categories = {
                    'professional_development': ['learn', 'training', 'course', 'skill', 'workshop'],
                    'project_work': ['project', 'dev', 'coding', 'build', 'implementation'],
                    'strategic_planning': ['strategy', 'planning', 'roadmap', 'vision', 'goal'],
                    'team_collaboration': ['team', 'standup', 'sync', 'collaboration', 'review'],
                    'personal_growth': ['personal', 'growth', 'reflection', 'coaching', 'mentor']
                }
                
                goal_time_allocation = defaultdict(float)
                goal_frequency = defaultdict(int)
                
                for event in events:
                    title_lower = event.title.lower()
                    description_lower = (event.description or '').lower()
                    duration = (event.end_time - event.start_time).total_seconds() / 3600
                    
                    for goal, keywords in goal_categories.items():
                        if any(keyword in title_lower or keyword in description_lower 
                               for keyword in keywords):
                            goal_time_allocation[goal] += duration
                            goal_frequency[goal] += 1

                total_time = sum(goal_time_allocation.values())
                goal_percentages = {goal: (time/total_time)*100 if total_time > 0 else 0 
                                  for goal, time in goal_time_allocation.items()}
                
                return {
                    "analysis_period": f"{days} days",
                    "total_goal_focused_time": round(total_time, 2),
                    "goal_time_allocation": {goal: round(time, 2) 
                                           for goal, time in goal_time_allocation.items()},
                    "goal_frequency": dict(goal_frequency),
                    "goal_percentages": {goal: round(pct, 1) 
                                       for goal, pct in goal_percentages.items()},
                    "insights": self._generate_goal_alignment_insights(
                        goal_time_allocation, goal_frequency, goal_percentages
                    )
                }

            except Exception as e:
                logger.error(f"Error analyzing goal alignment: {str(e)}")
                return {"error": f"Could not analyze goal alignment: {str(e)}"}

        @self.agent.tool
        async def analyze_time_allocation(
            ctx: RunContext[CalendarDependencies], days: int = 30
        ) -> Dict[str, Any]:
            """Compare actual time use vs intended priorities"""
            try:
                events = ctx.deps.calendar_service.get_events(
                    days_ahead=0, days_back=days
                )
                
                if not events:
                    return {"message": f"No events found in the past {days} days"}

                # Categorize time allocation
                time_categories = {
                    'deep_work': ['focus', 'coding', 'writing', 'analysis', 'development'],
                    'meetings': ['meeting', 'call', 'standup', 'sync', 'discussion'],
                    'administrative': ['admin', 'email', 'paperwork', 'filing', 'process'],
                    'learning': ['training', 'course', 'learning', 'study', 'research'],
                    'breaks': ['break', 'lunch', 'personal', 'rest']
                }
                
                category_time = defaultdict(float)
                daily_patterns = defaultdict(lambda: defaultdict(float))
                
                for event in events:
                    title_lower = event.title.lower()
                    duration = (event.end_time - event.start_time).total_seconds() / 3600
                    event_date = event.start_time.strftime('%Y-%m-%d')
                    
                    categorized = False
                    for category, keywords in time_categories.items():
                        if any(keyword in title_lower for keyword in keywords):
                            category_time[category] += duration
                            daily_patterns[event_date][category] += duration
                            categorized = True
                            break
                    
                    if not categorized:
                        category_time['other'] += duration
                        daily_patterns[event_date]['other'] += duration

                total_time = sum(category_time.values())
                time_percentages = {cat: (time/total_time)*100 if total_time > 0 else 0 
                                  for cat, time in category_time.items()}
                
                # Calculate daily averages
                num_days = len(daily_patterns)
                daily_averages = {cat: round(total_time/num_days, 2) if num_days > 0 else 0 
                                for cat, total_time in category_time.items()}
                
                return {
                    "analysis_period": f"{days} days",
                    "total_tracked_time": round(total_time, 2),
                    "time_allocation": {cat: round(time, 2) 
                                     for cat, time in category_time.items()},
                    "time_percentages": {cat: round(pct, 1) 
                                       for cat, pct in time_percentages.items()},
                    "daily_averages": daily_averages,
                    "insights": self._generate_time_allocation_insights(
                        category_time, time_percentages, daily_averages
                    )
                }

            except Exception as e:
                logger.error(f"Error analyzing time allocation: {str(e)}")
                return {"error": f"Could not analyze time allocation: {str(e)}"}

        @self.agent.tool
        async def analyze_behavioral_trends(
            ctx: RunContext[CalendarDependencies], days: int = 30
        ) -> Dict[str, Any]:
            """Identify emerging patterns in habits, decisions, and responses"""
            try:
                events = ctx.deps.calendar_service.get_events(
                    days_ahead=0, days_back=days
                )
                
                if not events:
                    return {"message": f"No events found in the past {days} days"}

                # Analyze weekly patterns
                weekly_patterns = defaultdict(lambda: defaultdict(int))
                event_timing = defaultdict(list)
                recurring_events = defaultdict(int)
                
                for event in events:
                    week_num = event.start_time.isocalendar()[1]
                    day_of_week = event.start_time.strftime('%A')
                    hour = event.start_time.hour
                    
                    weekly_patterns[week_num][day_of_week] += 1
                    event_timing[hour].append(event.title)
                    
                    # Check for recurring patterns
                    event_key = f"{event.title.lower()}_{day_of_week}_{hour}"
                    recurring_events[event_key] += 1

                # Identify trends
                consistent_patterns = {k: v for k, v in recurring_events.items() 
                                     if v >= 2}
                peak_activity_hours = sorted(event_timing.items(), 
                                           key=lambda x: len(x[1]), reverse=True)[:5]
                
                return {
                    "analysis_period": f"{days} days",
                    "total_events_analyzed": len(events),
                    "consistent_patterns": len(consistent_patterns),
                    "peak_activity_hours": [f"{hour}:00 ({len(events)} events)" 
                                          for hour, events in peak_activity_hours],
                    "recurring_events": {k: v for k, v in list(consistent_patterns.items())[:10]},
                    "insights": self._generate_behavioral_trends_insights(
                        weekly_patterns, consistent_patterns, peak_activity_hours
                    )
                }

            except Exception as e:
                logger.error(f"Error analyzing behavioral trends: {str(e)}")
                return {"error": f"Could not analyze behavioral trends: {str(e)}"}

    def _generate_productivity_insights(self, peak_hours, most_productive_day, meeting_types, avg_duration):
        """Generate insights from productivity analysis"""
        insights = []
        
        if peak_hours:
            top_hour = peak_hours[0][0]
            insights.append(f"Peak productivity occurs at {top_hour}:00 - consider scheduling important work during this time")
        
        if most_productive_day:
            insights.append(f"Most active day is {most_productive_day[0]} - plan key activities accordingly")
        
        if avg_duration > 2:
            insights.append(f"Average meeting duration is {avg_duration:.1f} hours - consider shorter, more focused sessions")
        
        meeting_ratio = meeting_types.get('meetings', 0) / sum(meeting_types.values()) if meeting_types else 0
        if meeting_ratio > 0.6:
            insights.append("High meeting density detected - consider blocking time for focused work")
        
        return insights

    def _generate_goal_alignment_insights(self, time_allocation, _frequency, percentages):
        """Generate insights from goal alignment analysis"""
        insights = []
        
        if not time_allocation:
            insights.append("No clear goal-oriented activities detected - consider defining specific objectives")
            return insights
        
        top_goal = max(time_allocation.items(), key=lambda x: x[1])
        insights.append(f"Most time invested in {top_goal[0]} ({top_goal[1]:.1f} hours)")
        
        if percentages.get('professional_development', 0) < 10:
            insights.append("Low professional development time - consider increasing learning activities")
        
        if percentages.get('strategic_planning', 0) < 5:
            insights.append("Limited strategic planning time - consider regular planning sessions")
        
        return insights

    def _generate_time_allocation_insights(self, _category_time, percentages, _daily_averages):
        """Generate insights from time allocation analysis"""
        insights = []
        
        deep_work_pct = percentages.get('deep_work', 0)
        meeting_pct = percentages.get('meetings', 0)
        
        if deep_work_pct < 20:
            insights.append("Low deep work time - consider blocking larger time chunks for focused work")
        
        if meeting_pct > 50:
            insights.append("High meeting load - evaluate meeting necessity and efficiency")
        
        if percentages.get('breaks', 0) < 5:
            insights.append("Insufficient break time - consider scheduling regular breaks for better productivity")
        
        return insights

    def _generate_behavioral_trends_insights(self, _weekly_patterns, consistent_patterns, peak_hours):
        """Generate insights from behavioral trends analysis"""
        insights = []
        
        if consistent_patterns:
            insights.append(f"Identified {len(consistent_patterns)} consistent behavioral patterns")
        
        if peak_hours:
            top_hour = peak_hours[0][0]
            insights.append(f"Consistent peak activity at {top_hour}:00 - leverage this natural rhythm")
        
        if len(consistent_patterns) < 3:
            insights.append("Limited routine consistency - consider establishing regular habits")
        
        return insights

    async def generate_comprehensive_insights(self, days: int = 30) -> Dict[str, Dict[str, str]]:
        """Generate comprehensive behavioral insights across all categories"""
        try:
            current_pending_actions = []
            deps = CalendarDependencies(
                calendar_service=self.calendar_service,
                user_id=self.user_id,
                user=self.user,
                db=self.db,
                pending_actions=current_pending_actions,
            )
            
            # Generate structured insights using Pydantic model
            comprehensive_prompt = f"""Analyze the past {days} days and generate comprehensive behavioral insights.

            For each of the four categories below, provide detailed analysis in the full_content field (2-3 paragraphs with specific metrics and actionable recommendations), and create a concise summary (1-2 sentences) that captures the key findings.

            Goal Alignment: Analyze progress toward objectives, time invested in goal-oriented activities, alignment between calendar activities and potential goals, and provide specific recommendations for better goal achievement.

            Energy Management: Analyze energy patterns throughout different times of day, correlation between activities and energy levels, identify peak performance periods, and provide specific recommendations for optimizing energy use.

            Time Allocation: Analyze how time is distributed across different activity types, compare intended vs actual time use, identify efficiency patterns, and provide specific recommendations for better time management.

            Behavioral Trends: Analyze emerging patterns in habits and decisions, consistency in routines and behaviors, changes in behavior over time, and provide specific recommendations for positive behavioral reinforcement.

            IMPORTANT: 
            - Provide specific, measurable recommendations with metrics where possible
            - Include time-based suggestions (e.g., "allocate 2 hours daily", "schedule at 9 AM")
            - Each summary should be 1-2 sentences maximum
            - Each full_content should be 2-3 detailed paragraphs
            - Use data from calendar events and conversation patterns to support insights"""
            
            result = await self.analysis_agent.run(comprehensive_prompt, deps=deps)
            structured_insights = result.output
            
            # Convert structured output to the expected dictionary format
            insights_dict = {
                'goal_alignment': {
                    'summary': structured_insights.goal_alignment.summary,
                    'full_content': structured_insights.goal_alignment.full_content
                },
                'energy_management': {
                    'summary': structured_insights.energy_management.summary,
                    'full_content': structured_insights.energy_management.full_content
                },
                'time_allocation': {
                    'summary': structured_insights.time_allocation.summary,
                    'full_content': structured_insights.time_allocation.full_content
                },
                'behavioral_trends': {
                    'summary': structured_insights.behavioral_trends.summary,
                    'full_content': structured_insights.behavioral_trends.full_content
                }
            }
            
            logger.info(f"Generated structured insights successfully")
            for key, value in insights_dict.items():
                logger.info(f"{key}: summary='{value['summary'][:50]}...', full_content='{value['full_content'][:50]}...'")
            
            return insights_dict
            
        except Exception as e:
            logger.error(f"Error generating insights: {str(e)}")
            error_section = {
                'summary': f"Error analyzing insights: {str(e)}",
                'full_content': f"Unable to generate insights due to: {str(e)}"
            }
            return {
                'goal_alignment': error_section,
                'energy_management': error_section,
                'time_allocation': error_section,
                'behavioral_trends': error_section
            }
    