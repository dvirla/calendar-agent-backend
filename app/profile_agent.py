from pydantic_ai import RunContext, Agent
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import json
import pytz
import logfire
import sys
import os
from .base_agent import BaseAgent
from .database_utils import UserProfileService
from .agent_dataclasses import CalendarDependencies, AgentResponse
from .config import MODEL_TEMPRATURE


class ProfileAgent(BaseAgent):
    """Profile-focused AI agent that manages user goals, preferences, and personal information"""
    
    def __init__(self, calendar_service, user_id, user, db):
        self.calendar_service = calendar_service
        self.user_id = user_id
        self.user = user
        self.db = db
        self.timezone = getattr(calendar_service, 'timezone', pytz.UTC)
        
        system_prompt = f"""You are a profile management assistant. Current date/time: {self._get_current_time()}

        ## Core Purpose
        - **Extract**: Parse user goals, preferences, and personal information from natural language
        - **Update**: Manage user profile data including goals, work preferences, and communication style
        - **Guide**: Help users set meaningful goals and preferences for better personalization
        - **Maintain**: Keep profile information current and relevant

        ## Available Tools
        - update_user_profile: Update user profile with extracted information
        - get_user_profile: Retrieve current user profile
        - delete_profile_field: Remove specific profile fields
        - suggest_profile_improvements: Suggest profile enhancements

        ## Profile Fields You Can Manage
        - short_term_goals: Goals for next 1-3 months
        - long_term_goals: Goals for 6+ months
        - work_preferences: Work style, peak hours, break frequency
        - personal_interests: Hobbies and interests
        - reflection_frequency: How often user wants reflections (daily/weekly/monthly)
        - reflection_focus_areas: What to focus on (productivity, wellness, growth)
        - communication_tone: Preferred tone (casual/professional/encouraging)
        - preferred_insights: Types of insights user wants

        ## Guidelines
        1. Be conversational and encouraging when discussing goals
        2. Ask clarifying questions to better understand user preferences
        3. Suggest specific, actionable goals
        4. Respect user privacy and only store what they explicitly share
        5. Help users refine vague goals into specific, measurable ones

        Keep responses helpful and focused on improving their personal productivity and growth."""
        
        super().__init__(calendar_service, user_id, user, db, system_prompt)
        self._register_profile_tools()
    
    def _register_profile_tools(self):
        """Register profile-specific tools"""
        
        @self.agent.tool
        async def update_user_profile(
            ctx: RunContext[CalendarDependencies], 
            profile_data: Dict[str, Any]
        ) -> Dict[str, Any]:
            """Update user profile with new information
            
            Args:
                profile_data: Dictionary containing profile fields to update
                
            Returns:
                Success status and updated profile summary
            """
            try:
                updated_profile = UserProfileService.update_user_profile(
                    ctx.deps.db, 
                    ctx.deps.user_id, 
                    profile_data
                )
                
                if updated_profile:
                    return {
                        "success": True,
                        "message": "Profile updated successfully!",
                        "updated_fields": list(profile_data.keys()),
                        "profile_summary": self._format_profile_summary(updated_profile)
                    }
                else:
                    return {
                        "success": False,
                        "message": "Failed to update profile",
                        "error": "Could not save profile changes"
                    }
                    
            except Exception as e:
                logfire.error(f"Error updating profile: {e}")
                return {
                    "success": False,
                    "message": "Error updating profile",
                    "error": str(e)
                }
        
        @self.agent.tool
        async def get_user_profile(
            ctx: RunContext[CalendarDependencies]
        ) -> Dict[str, Any]:
            """Get current user profile
            
            Returns:
                Current user profile data
            """
            try:
                profile = UserProfileService.get_user_profile(ctx.deps.db, ctx.deps.user_id)
                
                if profile:
                    return {
                        "success": True,
                        "profile": {
                            "short_term_goals": profile.short_term_goals or [],
                            "long_term_goals": profile.long_term_goals or [],
                            "work_preferences": profile.work_preferences or {},
                            "personal_interests": profile.personal_interests or [],
                            "reflection_frequency": profile.reflection_frequency,
                            "reflection_focus_areas": profile.reflection_focus_areas or [],
                            "communication_tone": profile.communication_tone,
                            "preferred_insights": profile.preferred_insights or []
                        }
                    }
                else:
                    return {
                        "success": True,
                        "profile": None,
                        "message": "No profile found. Let's create one! Tell me about your goals and preferences."
                    }
                    
            except Exception as e:
                logfire.error(f"Error getting profile: {e}")
                return {
                    "success": False,
                    "message": "Error retrieving profile",
                    "error": str(e)
                }
        
        @self.agent.tool 
        async def extract_profile_from_text(
            ctx: RunContext[CalendarDependencies],
            message: str
        ) -> Dict[str, Any]:
            """Extract profile information from natural language text
            
            Args:
                message: User's natural language message about goals/preferences
                
            Returns:
                Extracted profile data in structured format
            """
            try:
                # Use a specialized extraction agent
                extraction_agent = Agent(
                    self.model,
                    system_prompt="""Extract profile information from text and return as JSON.
                    
                    Return format:
                    {
                        "short_term_goals": ["goal1", "goal2"],
                        "long_term_goals": ["goal1", "goal2"],
                        "work_preferences": {"peak_hours": "morning", "work_style": "focused"},
                        "personal_interests": ["interest1", "interest2"],
                        "reflection_frequency": "weekly",
                        "reflection_focus_areas": ["productivity", "wellness"],
                        "communication_tone": "professional",
                        "preferred_insights": ["time_management", "goal_progress"]
                    }
                    
                    Only include fields mentioned in the text. Return valid JSON only.""",
                    model_settings={"temperature": 0.1}
                )
                
                result = await extraction_agent.run(message)
                
                try:
                    extracted_data = json.loads(result.output)
                    return {
                        "success": True,
                        "extracted_data": extracted_data,
                        "message": "Successfully extracted profile information"
                    }
                except json.JSONDecodeError:
                    # Fallback to basic extraction
                    return {
                        "success": True,
                        "extracted_data": self._extract_basic_goals(message),
                        "message": "Extracted basic profile information"
                    }
                    
            except Exception as e:
                logfire.error(f"Error extracting profile: {e}")
                return {
                    "success": False,
                    "message": "Error extracting profile information",
                    "error": str(e)
                }
        
        @self.agent.tool
        async def suggest_profile_improvements(
            ctx: RunContext[CalendarDependencies]
        ) -> Dict[str, Any]:
            """Suggest improvements to user's current profile
            
            Returns:
                Suggestions for profile enhancements
            """
            try:
                profile = UserProfileService.get_user_profile(ctx.deps.db, ctx.deps.user_id)
                suggestions = []
                
                if not profile:
                    return {
                        "suggestions": [
                            "Create a profile by sharing your goals and preferences",
                            "Tell me about your short-term goals (next 1-3 months)",
                            "Share your work preferences (peak hours, work style)",
                            "Let me know your communication preferences"
                        ]
                    }
                
                # Analyze profile completeness and suggest improvements
                if not profile.short_term_goals:
                    suggestions.append("Add some short-term goals to focus your next few months")
                
                if not profile.long_term_goals:
                    suggestions.append("Consider setting long-term goals (6+ months) for bigger aspirations")
                
                if not profile.work_preferences:
                    suggestions.append("Share your work preferences to get better scheduling suggestions")
                
                if not profile.personal_interests:
                    suggestions.append("Add personal interests to make reflections more meaningful")
                
                if profile.reflection_frequency == "weekly" and not profile.reflection_focus_areas:
                    suggestions.append("Specify areas to focus on in your reflections (productivity, wellness, growth)")
                
                # Check for vague goals
                all_goals = (profile.short_term_goals or []) + (profile.long_term_goals or [])
                vague_indicators = ["better", "more", "improve", "try to"]
                
                for goal in all_goals:
                    if any(indicator in goal.lower() for indicator in vague_indicators):
                        suggestions.append(f"Make this goal more specific: '{goal}' - add measurable targets or deadlines")
                        break
                
                if not suggestions:
                    suggestions.append("Your profile looks complete! Consider reviewing and updating it periodically.")
                
                return {
                    "success": True,
                    "suggestions": suggestions
                }
                
            except Exception as e:
                logfire.error(f"Error generating suggestions: {e}")
                return {
                    "success": False,
                    "message": "Error generating suggestions",
                    "error": str(e)
                }
    
    def _extract_basic_goals(self, message: str) -> Dict[str, Any]:
        """Fallback method to extract basic goals from message"""
        profile_data = {}
        
        # Simple keyword extraction
        goal_keywords = ["want to", "goal", "trying to", "working on", "planning to", "hope to"]
        
        for keyword in goal_keywords:
            if keyword in message.lower():
                # Extract the part after the keyword as a goal
                parts = message.lower().split(keyword, 1)
                if len(parts) > 1:
                    goal = parts[1].strip().split('.')[0].strip()  # Take until first period
                    if len(goal) > 5 and len(goal) < 100:  # Reasonable length
                        profile_data["short_term_goals"] = [goal.capitalize()]
                        break
        
        # Extract work preferences
        if any(word in message.lower() for word in ["morning person", "early bird"]):
            profile_data["work_preferences"] = {"peak_hours": "morning"}
        elif any(word in message.lower() for word in ["night owl", "evening"]):
            profile_data["work_preferences"] = {"peak_hours": "evening"}
        
        # Extract communication tone
        if any(word in message.lower() for word in ["casual", "informal"]):
            profile_data["communication_tone"] = "casual"
        elif any(word in message.lower() for word in ["professional", "formal"]):
            profile_data["communication_tone"] = "professional"
        
        return profile_data
    
    def _format_profile_summary(self, profile) -> str:
        """Format profile summary for user feedback"""
        summary_parts = []
        
        if profile.short_term_goals:
            summary_parts.append(f"Short-term goals: {', '.join(profile.short_term_goals)}")
        
        if profile.long_term_goals:
            summary_parts.append(f"Long-term goals: {', '.join(profile.long_term_goals)}")
            
        if profile.work_preferences:
            prefs = []
            for key, value in profile.work_preferences.items():
                prefs.append(f"{key}: {value}")
            if prefs:
                summary_parts.append(f"Work preferences: {', '.join(prefs)}")
        
        if profile.communication_tone:
            summary_parts.append(f"Communication tone: {profile.communication_tone}")
            
        if profile.reflection_frequency:
            summary_parts.append(f"Reflection frequency: {profile.reflection_frequency}")
        
        return "; ".join(summary_parts) if summary_parts else "Profile updated"