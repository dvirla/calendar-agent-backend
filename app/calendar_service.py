import pickle
import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from typing import List, Optional
from .config import SCOPES, REDIRECT_URI
from .models import CalendarEvent

class GoogleCalendarService:
    def __init__(self):
        self.service = None
        self.credentials = None
    
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
    
    def get_events(self, days_ahead: int = 7) -> List[CalendarEvent]:
        """Get calendar events for the next N days"""
        if not self.service:
            if not self.load_credentials():
                raise Exception("No calendar credentials found")
        
        now = datetime.utcnow()
        time_max = now + timedelta(days=days_ahead)
        
        events_result = self.service.events().list(
            calendarId='primary',
            timeMin=now.isoformat() + 'Z',
            timeMax=time_max.isoformat() + 'Z',
            maxResults=50,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = []
        for event in events_result.get('items', []):
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            
            events.append(CalendarEvent(
                id=event['id'],
                title=event.get('summary', 'No Title'),
                start_time=datetime.fromisoformat(start.replace('Z', '+00:00')),
                end_time=datetime.fromisoformat(end.replace('Z', '+00:00')),
                description=event.get('description', ''),
                location=event.get('location', '')
            ))
        
        return events
    
    def create_event(self, event: CalendarEvent) -> str:
        """Create a new calendar event"""
        if not self.service:
            if not self.load_credentials():
                raise Exception("No calendar credentials found")
        
        event_body = {
            'summary': event.title,
            'start': {'dateTime': event.start_time.isoformat()},
            'end': {'dateTime': event.end_time.isoformat()},
            'description': event.description or '',
            'location': event.location or ''
        }
        
        created_event = self.service.events().insert(
            calendarId='primary',
            body=event_body
        ).execute()
        
        return created_event['id']