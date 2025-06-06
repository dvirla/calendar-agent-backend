import pickle
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from typing import List, Optional
from .config import SCOPES, REDIRECT_URI
from .models import CalendarEvent

class GoogleCalendarService:
    def __init__(self):
        self.service = None
        self.credentials = None
        # Start with UTC, but will be updated based on calendar settings
        self.timezone = pytz.UTC
        self._timezone_detected = False
    
    def get_auth_url(self) -> str:
        """Generate Google OAuth authorization URL"""
        flow = Flow.from_client_secrets_file(
            'credentials.json', 
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        return auth_url
    
    def handle_oauth_callback(self, code: str) -> dict:
        """Handle OAuth callback and store credentials"""
        flow = Flow.from_client_secrets_file(
            'credentials.json',
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI
        )
        flow.fetch_token(code=code)
        
        # Save credentials
        self.credentials = flow.credentials
        with open('token.pickle', 'wb') as token:
            pickle.dump(self.credentials, token)
        
        return {"status": "success", "message": "Calendar connected successfully"}
    
    def load_credentials(self) -> bool:
        """Load saved credentials"""
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                self.credentials = pickle.load(token)
            
            # Refresh if expired
            if self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                with open('token.pickle', 'wb') as token:
                    pickle.dump(self.credentials, token)
            
            self.service = build('calendar', 'v3', credentials=self.credentials)
            return True
        return False
    
    def _detect_calendar_timezone(self):
        """Detect and set timezone from calendar settings"""
        if not self.service or self._timezone_detected:
            return
        
        try:
            # Get calendar settings to determine timezone
            calendar_info = self.service.calendars().get(calendarId='primary').execute()
            timezone_id = calendar_info.get('timeZone', 'UTC')
            
            # Update service timezone
            self.timezone = pytz.timezone(timezone_id)
            self._timezone_detected = True
            print(f"Calendar timezone detected: {timezone_id}")
            
        except Exception as e:
            print(f"Could not detect calendar timezone, using UTC: {e}")
            self.timezone = pytz.UTC
            self._timezone_detected = True
    
    def _ensure_timezone_aware(self, dt: datetime) -> datetime:
        """Ensure datetime is timezone-aware, defaulting to service timezone"""
        if dt.tzinfo is None:
            return self.timezone.localize(dt)
        return dt.astimezone(self.timezone)
    
    def _parse_datetime_with_timezone(self, dt_string: str, fallback_timezone: str = None) -> datetime:
        """Parse datetime string and handle timezone information from Google Calendar"""
        try:
            # Handle ISO format with timezone
            if 'T' in dt_string:
                if dt_string.endswith('Z'):
                    # UTC timezone
                    dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
                else:
                    # Has timezone info
                    dt = datetime.fromisoformat(dt_string)
                
                # Convert to calendar's timezone
                return dt.astimezone(self.timezone)
            else:
                # Date-only format (all-day events)
                date_obj = datetime.fromisoformat(dt_string).date()
                dt = datetime.combine(date_obj, datetime.min.time())
                return self.timezone.localize(dt)
        except Exception:
            # Fallback parsing
            dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
            return self._ensure_timezone_aware(dt)
    
    def get_events(self, days_ahead: int = 7) -> List[CalendarEvent]:
        """Get calendar events for the next N days"""
        if not self.service:
            if not self.load_credentials():
                raise Exception("No calendar credentials found")
        
        # Detect timezone from calendar settings
        self._detect_calendar_timezone()
        
        # Use timezone-aware datetime for API calls
        now = datetime.now(self.timezone)
        time_max = now + timedelta(days=days_ahead)
        
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse and ensure timezone consistency
            start_dt = self._parse_datetime_with_timezone(start)
            end_dt = self._parse_datetime_with_timezone(end)
            
            events.append(CalendarEvent(
                id=event['id'],
                title=event.get('summary', 'No Title'),
                start_time=self._ensure_timezone_aware(start_dt),
                end_time=self._ensure_timezone_aware(end_dt),
                description=event.get('description', ''),
                location=event.get('location', '')
            ))
        
        return events
    
    def create_event(self, event: CalendarEvent) -> str:
        """Create a new calendar event"""
        if not self.service:
            if not self.load_credentials():
                raise Exception("No calendar credentials found")
        
        # Ensure timezone consistency for event creation
        start_time = self._ensure_timezone_aware(event.start_time)
        end_time = self._ensure_timezone_aware(event.end_time)
        
        event_body = {
            'summary': event.title,
            'start': {'dateTime': start_time.isoformat()},
            'end': {'dateTime': end_time.isoformat()},
            'description': event.description or '',
            'location': event.location or ''
        }
        
        created_event = self.service.events().insert(
            calendarId='primary',
            body=event_body
        ).execute()
        
        return created_event['id']