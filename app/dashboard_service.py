from sqlalchemy.orm import Session
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from .database_utils import ConversationService
from .database import Message, Conversation
import statistics

class DashboardService:
    """Service for aggregating analytics data for dashboard visualization"""
    
    @staticmethod
    def get_analytics_data(db: Session, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get aggregated analytics data for dashboard"""
        try:
            # Get date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)
            
            # Get conversations in range
            conversations = ConversationService.get_user_conversations_since(db, user_id, start_date)
            
            if not conversations:
                return DashboardService._get_mock_data()
            
            # Get all messages from these conversations
            all_messages = []
            for conv in conversations:
                messages = ConversationService.get_conversation_messages(db, conv.id)
                all_messages.extend(messages)
            
            # Filter analyzed messages
            analyzed_messages = [msg for msg in all_messages if msg.analyzed and msg.role == 'user']
            
            if not analyzed_messages:
                return DashboardService._get_mock_data()
            
            # Calculate metrics
            sentiment_metrics = DashboardService._calculate_sentiment_metrics(analyzed_messages)
            weekly_reflections = DashboardService._get_weekly_reflections(conversations, analyzed_messages)
            insights = DashboardService._generate_insights(analyzed_messages)
            recommendations = DashboardService._generate_recommendations(analyzed_messages)
            
            return {
                "sentiment_metrics": sentiment_metrics,
                "weekly_reflections": weekly_reflections,
                "insights": insights,
                "recommendations": recommendations,
                "period_days": days,
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            # Fallback to mock data if anything fails
            return DashboardService._get_mock_data()
    
    @staticmethod
    def _calculate_sentiment_metrics(messages: List[Message]) -> Dict[str, Any]:
        """Calculate aggregated sentiment metrics"""
        stress_scores = [msg.stress_level for msg in messages if msg.stress_level is not None]
        energy_scores = [msg.energy_level for msg in messages if msg.energy_level is not None]
        satisfaction_scores = [msg.satisfaction_level for msg in messages if msg.satisfaction_level is not None]
        sentiment_scores = [msg.sentiment_score for msg in messages if msg.sentiment_score is not None]
        
        # Calculate happiness from sentiment (convert -5 to 5 range to 1 to 10)
        happiness_scores = [(score + 5) * 2 for score in sentiment_scores]
        
        return {
            "stress": {
                "value": round(statistics.mean(stress_scores), 1) if stress_scores else 3.2,
                "max": 10,
                "trend": DashboardService._calculate_trend(stress_scores),
                "color": "text-orange-500",
                "bgColor": "bg-orange-100"
            },
            "energy": {
                "value": round(statistics.mean(energy_scores), 1) if energy_scores else 7.1,
                "max": 10,
                "trend": DashboardService._calculate_trend(energy_scores),
                "color": "text-green-500",
                "bgColor": "bg-green-100"
            },
            "satisfaction": {
                "value": round(statistics.mean(satisfaction_scores), 1) if satisfaction_scores else 6.8,
                "max": 10,
                "trend": DashboardService._calculate_trend(satisfaction_scores),
                "color": "text-blue-500",
                "bgColor": "bg-blue-100"
            },
            "happiness": {
                "value": round(statistics.mean(happiness_scores), 1) if happiness_scores else 7.3,
                "max": 10,
                "trend": DashboardService._calculate_trend(happiness_scores),
                "color": "text-purple-500",
                "bgColor": "bg-purple-100"
            }
        }
    
    @staticmethod
    def _calculate_trend(scores: List[float]) -> float:
        """Calculate trend from a list of scores"""
        if len(scores) < 2:
            return 0.0
        
        # Compare recent half vs earlier half
        mid_point = len(scores) // 2
        recent_avg = statistics.mean(scores[mid_point:])
        earlier_avg = statistics.mean(scores[:mid_point])
        
        return round(recent_avg - earlier_avg, 1)
    
    @staticmethod
    def _get_weekly_reflections(conversations: List[Conversation], messages: List[Message]) -> List[Dict[str, Any]]:
        """Get weekly reflection summary"""
        reflections = []
        
        # Group by days
        for i in range(7):
            date = datetime.utcnow() - timedelta(days=i)
            day_messages = [msg for msg in messages if msg.timestamp.date() == date.date() and msg.role == 'user']
            
            if day_messages:
                avg_sentiment = statistics.mean([msg.sentiment_score for msg in day_messages if msg.sentiment_score is not None]) if day_messages else 0
                avg_energy = statistics.mean([msg.energy_level for msg in day_messages if msg.energy_level is not None]) if day_messages else 5
                
                sentiment_label = "positive" if avg_sentiment > 1 else "negative" if avg_sentiment < -1 else "neutral"
                
                # Extract key theme from message content
                key_theme = DashboardService._extract_key_theme(day_messages)
                
                reflections.append({
                    "date": "Today" if i == 0 else "Yesterday" if i == 1 else f"{i} days ago",
                    "sentiment": sentiment_label,
                    "key_theme": key_theme,
                    "energy_level": int(avg_energy) if avg_energy else 5
                })
            else:
                reflections.append({
                    "date": "Today" if i == 0 else "Yesterday" if i == 1 else f"{i} days ago",
                    "sentiment": "neutral",
                    "key_theme": "No reflections",
                    "energy_level": 5
                })
        
        return reflections[:3]  # Return only last 3 days
    
    @staticmethod
    def _extract_key_theme(messages: List[Message]) -> str:
        """Extract key theme from messages"""
        # Simple keyword analysis
        all_content = " ".join([msg.content.lower() for msg in messages])
        
        themes = {
            "work": ["work", "project", "meeting", "deadline", "task"],
            "productivity": ["productive", "focus", "accomplished", "completed"],
            "wellness": ["tired", "energy", "sleep", "health", "exercise"],
            "social": ["friends", "family", "social", "people", "team"],
            "learning": ["learn", "study", "read", "course", "skill"]
        }
        
        theme_scores = {}
        for theme, keywords in themes.items():
            score = sum(1 for keyword in keywords if keyword in all_content)
            if score > 0:
                theme_scores[theme] = score
        
        if theme_scores:
            top_theme = max(theme_scores, key=theme_scores.get)
            return f"{top_theme.capitalize()} focused day"
        
        return "Mixed activities"
    
    @staticmethod
    def _generate_insights(messages: List[Message]) -> List[Dict[str, Any]]:
        """Generate insights from analytics data"""
        insights = []
        
        # Analyze energy patterns
        energy_scores = [msg.energy_level for msg in messages if msg.energy_level is not None]
        if energy_scores:
            avg_energy = statistics.mean(energy_scores)
            if avg_energy > 7:
                insights.append({
                    "type": "energy",
                    "title": "Consistently high energy levels detected",
                    "description": f"Your average energy level is {avg_energy:.1f}/10, indicating good vitality",
                    "timeframe": "Recent data",
                    "actionable": True
                })
        
        # Analyze stress patterns
        stress_scores = [msg.stress_level for msg in messages if msg.stress_level is not None]
        if stress_scores:
            avg_stress = statistics.mean(stress_scores)
            if avg_stress > 6:
                insights.append({
                    "type": "stress",
                    "title": "Elevated stress levels observed",
                    "description": f"Your average stress level is {avg_stress:.1f}/10, consider stress management",
                    "timeframe": "Recent data", 
                    "actionable": True
                })
        
        # If no real insights, add a generic one
        if not insights:
            insights.append({
                "type": "productivity",
                "title": "Reflection data is building up",
                "description": "Continue using the reflection tool to gather more insights",
                "timeframe": "Ongoing",
                "actionable": False
            })
        
        return insights
    
    @staticmethod
    def _generate_recommendations(messages: List[Message]) -> List[Dict[str, Any]]:
        """Generate recommendations based on analytics"""
        recommendations = []
        
        # Analyze patterns for recommendations
        stress_scores = [msg.stress_level for msg in messages if msg.stress_level is not None]
        energy_scores = [msg.energy_level for msg in messages if msg.energy_level is not None]
        
        if stress_scores and statistics.mean(stress_scores) > 6:
            recommendations.append({
                "type": "wellness",
                "title": "Try stress reduction techniques",
                "description": "Based on your recent stress patterns",
                "action": "Set Reminder",
                "priority": "high",
                "category": "Wellness"
            })
        
        if energy_scores and statistics.mean(energy_scores) < 5:
            recommendations.append({
                "type": "wellness", 
                "title": "Focus on energy management",
                "description": "Consider reviewing your sleep and exercise habits",
                "action": "Schedule Review",
                "priority": "medium",
                "category": "Wellness"
            })
        
        # Default recommendation
        if not recommendations:
            recommendations.append({
                "type": "growth",
                "title": "Continue regular reflections",
                "description": "Keep building your self-awareness through regular check-ins",
                "action": "Schedule Now",
                "priority": "low", 
                "category": "Growth"
            })
        
        return recommendations
    
    @staticmethod
    def _get_mock_data() -> Dict[str, Any]:
        """Return mock data when no real data is available"""
        return {
            "sentiment_metrics": {
                "stress": {"value": 3.2, "max": 10, "trend": -0.3, "color": "text-orange-500", "bgColor": "bg-orange-100"},
                "energy": {"value": 7.1, "max": 10, "trend": 0.8, "color": "text-green-500", "bgColor": "bg-green-100"},
                "satisfaction": {"value": 6.8, "max": 10, "trend": 0.2, "color": "text-blue-500", "bgColor": "bg-blue-100"},
                "happiness": {"value": 7.3, "max": 10, "trend": 0.5, "color": "text-purple-500", "bgColor": "bg-purple-100"}
            },
            "weekly_reflections": [
                {"date": "Today", "sentiment": "positive", "key_theme": "Getting started with reflections", "energy_level": 8},
                {"date": "Yesterday", "sentiment": "neutral", "key_theme": "Building habits", "energy_level": 6},
                {"date": "2 days ago", "sentiment": "positive", "key_theme": "Learning new tools", "energy_level": 7}
            ],
            "insights": [
                {
                    "type": "productivity",
                    "title": "Start building your reflection data",
                    "description": "Use the reflection agent to begin tracking your patterns and insights",
                    "timeframe": "Getting started",
                    "actionable": True
                }
            ],
            "recommendations": [
                {
                    "type": "growth",
                    "title": "Begin daily reflections",
                    "description": "Start with 5-minute daily check-ins to build awareness",
                    "action": "Start Now",
                    "priority": "medium",
                    "category": "Growth"
                }
            ],
            "period_days": 30,
            "last_updated": datetime.utcnow().isoformat()
        }