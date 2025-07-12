from pydantic_ai import RunContext, Agent
from typing import Dict, Any
from datetime import timedelta
import pytz
from .base_agent import BaseAgent
from .agent_dataclasses import CalendarDependencies, AgentResponse
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
            output_type=AgentResponse,
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
            
            # Generate all insights in a single request to avoid hitting request limits
            comprehensive_prompt = f"""Generate a comprehensive behavioral insight report for the past {days} days.
            
            For each category below, provide BOTH a brief summary (1-2 sentences) AND detailed full content (2-3 paragraphs).
            Format your response exactly as shown with clear section headers and subsections:

            ## Goal Alignment
            ### Summary
            [Brief 1-2 sentence summary of goal alignment insights]
            
            ### Full Content
            [Detailed 2-3 paragraph analysis covering:
            - Progress toward stated objectives
            - Time invested in goal-oriented activities  
            - Alignment between calendar activities and potential goals
            - Specific recommendations for better goal achievement with metrics]
            
            ## Energy Management
            ### Summary
            [Brief 1-2 sentence summary of energy management insights]
            
            ### Full Content
            [Detailed 2-3 paragraph analysis covering:
            - Energy levels throughout different times of day
            - Correlation between activities and energy patterns
            - Peak performance periods
            - Specific recommendations for optimizing energy use with timing]
            
            ## Time Allocation
            ### Summary
            [Brief 1-2 sentence summary of time allocation insights]
            
            ### Full Content
            [Detailed 2-3 paragraph analysis covering:
            - How time is distributed across different activity types
            - Comparison of intended vs actual time use
            - Time efficiency patterns
            - Specific recommendations for better time management with breakdowns]
            
            ## Behavioral Trends
            ### Summary
            [Brief 1-2 sentence summary of behavioral trends insights]
            
            ### Full Content
            [Detailed 2-3 paragraph analysis covering:
            - Emerging patterns in habits and decisions
            - Consistency in routines and behaviors  
            - Changes in behavior over time
            - Specific recommendations for positive behavioral reinforcement]
            
            Provide specific, actionable recommendations with metrics where possible."""
            
            result = await self.agent.run(comprehensive_prompt, deps=deps)
            response_text = result.output.message
            
            # Parse the response to extract each section with summary and full content
            insights = self._parse_structured_response_with_summary(response_text)
            
            return insights
            
        except Exception as e:
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
    
    def _parse_structured_response_with_summary(self, response_text: str) -> Dict[str, Dict[str, str]]:
        """Parse the structured response into separate insight categories with summary and full content"""
        insights = {
            'goal_alignment': {'summary': '', 'full_content': ''},
            'energy_management': {'summary': '', 'full_content': ''},
            'time_allocation': {'summary': '', 'full_content': ''},
            'behavioral_trends': {'summary': '', 'full_content': ''}
        }
        
        # Split response by main section headers (##)
        main_sections = response_text.split('##')
        
        for section in main_sections:
            section = section.strip()
            if not section:
                continue
                
            # Extract section header
            lines = section.split('\n', 1)
            if len(lines) < 2:
                continue
                
            header = lines[0].strip().lower()
            section_content = lines[1].strip()
            
            # Determine which insight category this is
            category_key = None
            if 'goal alignment' in header:
                category_key = 'goal_alignment'
            elif 'energy management' in header:
                category_key = 'energy_management'
            elif 'time allocation' in header:
                category_key = 'time_allocation'
            elif 'behavioral trends' in header:
                category_key = 'behavioral_trends'
            
            if not category_key:
                continue
                
            # Parse summary and full content subsections
            subsections = section_content.split('###')
            
            for subsection in subsections:
                subsection = subsection.strip()
                if not subsection:
                    continue
                    
                sub_lines = subsection.split('\n', 1)
                if len(sub_lines) < 2:
                    continue
                    
                sub_header = sub_lines[0].strip().lower()
                sub_content = sub_lines[1].strip()
                
                if 'summary' in sub_header:
                    insights[category_key]['summary'] = sub_content
                elif 'full content' in sub_header:
                    insights[category_key]['full_content'] = sub_content
        
        # Fallback: if parsing fails, use the entire response for each section
        if not any(section['summary'] or section['full_content'] for section in insights.values()):
            fallback_content = response_text[:200] + "..." if len(response_text) > 200 else response_text
            fallback_section = {
                'summary': fallback_content,
                'full_content': response_text
            }
            for key in insights:
                insights[key] = fallback_section.copy()
        
        return insights
    
    def _parse_structured_response(self, response_text: str) -> Dict[str, str]:
        """Legacy method - parse the structured response into separate insight categories"""
        insights = {
            'goal_alignment': '',
            'energy_management': '',
            'time_allocation': '',
            'behavioral_trends': ''
        }
        
        # Split response by section headers
        sections = response_text.split('##')
        
        for section in sections:
            section = section.strip()
            if not section:
                continue
                
            lines = section.split('\n', 1)
            if len(lines) < 2:
                continue
                
            header = lines[0].strip().lower()
            content = lines[1].strip()
            
            if 'goal alignment' in header:
                insights['goal_alignment'] = content
            elif 'energy management' in header:
                insights['energy_management'] = content
            elif 'time allocation' in header:
                insights['time_allocation'] = content
            elif 'behavioral trends' in header:
                insights['behavioral_trends'] = content
        
        # Fallback: if parsing fails, distribute content evenly
        if not any(insights.values()):
            insights = {
                'goal_alignment': response_text[:len(response_text)//4],
                'energy_management': response_text[len(response_text)//4:len(response_text)//2],
                'time_allocation': response_text[len(response_text)//2:3*len(response_text)//4],
                'behavioral_trends': response_text[3*len(response_text)//4:]
            }
        
        return insights