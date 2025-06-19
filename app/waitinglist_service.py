# app/waitinglist_service.py
import os
import json
import re
import hashlib
import socket
from datetime import datetime, timezone
from typing import Dict, Any
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class WaitlistManager:
    def __init__(self):
        self.client = self._init_google_sheets()
        self.sheet = self.client.open_by_key(self._get_spreadsheet_id()).worksheet(self._get_sheet_name())
        self._ensure_headers()
    
    def _get_spreadsheet_id(self):
        """Get spreadsheet ID from environment or use default"""
        return os.getenv('WAITLIST_SPREADSHEET_ID', '1-Qbkc3nXD1wicRTKjpAVwnV_OLorS0DIfQJrtqtzuVA')
    
    def _get_sheet_name(self):
        """Get sheet name from environment or use default"""
        return os.getenv('WAITLIST_SHEET_NAME', 'Waitlist')
    
    def _get_service_account_file(self):
        """Get service account file path"""
        return os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service_account.json')
    
    def _has_service_account_env_vars(self):
        """Check if all required service account environment variables are set"""
        required_vars = [
            'GOOGLE_PROJECT_ID',
            'GOOGLE_PRIVATE_KEY_ID', 
            'GOOGLE_PRIVATE_KEY',
            'GOOGLE_CLIENT_EMAIL',
            'GOOGLE_CLIENT_ID'
        ]
        return all(os.getenv(var) for var in required_vars)
    
    def _init_google_sheets(self):
        """Initialize Google Sheets client"""
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        
        # Try to use environment variables first, fallback to service account file
        if self._has_service_account_env_vars():
            service_account_info = {
                "type": "service_account",
                "project_id": os.getenv('GOOGLE_PROJECT_ID'),
                "private_key_id": os.getenv('GOOGLE_PRIVATE_KEY_ID'),
                "private_key": os.getenv('GOOGLE_PRIVATE_KEY').replace('\\n', '\n'),
                "client_email": os.getenv('GOOGLE_CLIENT_EMAIL'),
                "client_id": os.getenv('SERVICE_GOOGLE_CLIENT_ID'),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv('GOOGLE_CLIENT_EMAIL').replace('@', '%40')}",
                "universe_domain": "googleapis.com"
            }
            creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        else:
            service_account_file = self._get_service_account_file()
            creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
        
        return gspread.authorize(creds)
    
    def _ensure_headers(self):
        """Ensure the spreadsheet has proper headers"""
        headers = self.sheet.row_values(1)
        expected_headers = [
            'Timestamp', 'Email', 'Name', 'Interested Features', 'Primary Usage',
            'Scheduling Frustration', 'Current Calendar Tool', 'Role/Profession', 
            'Company', 'Referral Source', 'UTM Source', 'Timezone',
            'Email Hash', 'Position', 'Status'
        ]
        
        if headers != expected_headers:
            self.sheet.update('A1:O1', [expected_headers])
    
    def _validate_email(self, email: str) -> Dict[str, Any]:
        """Validate email format and domain"""
        # Basic format validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return {'valid': False, 'error': 'Invalid email format'}
        
        # Extract domain
        domain = email.split('@')[1]
        
        # Check if domain has MX record
        try:
            socket.getaddrinfo(domain, None)
            return {'valid': True}
        except socket.gaierror:
            return {'valid': False, 'error': 'Invalid email domain'}
    
    def _hash_email(self, email: str) -> str:
        """Create hash of email for duplicate checking"""
        return hashlib.sha256(email.lower().encode()).hexdigest()[:16]
    
    def check_existing_signup(self, email: str) -> bool:
        """Check if email already exists in waitlist"""
        email_hash = self._hash_email(email)
        try:
            cell = self.sheet.find(email_hash, in_column=13)
            return cell is not None
        except:
            return False
    
    def add_to_waitlist(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add new signup to waitlist"""
        # Validate email
        email_validation = self._validate_email(data['email'])
        if not email_validation['valid']:
            return {'success': False, 'error': email_validation['error']}
        
        # Check for existing signup
        if self.check_existing_signup(data['email']):
            return {'success': False, 'error': 'Email already on waitlist'}
        
        # Get current count for position
        all_values = self.sheet.get_all_values()
        position = len(all_values)  # This includes header row
        
        # Prepare row data
        row_data = [
            data.get('timestamp', datetime.now(timezone.utc).isoformat()),
            data['email'],
            data['name'],
            data['interestedFeatures'],
            data['primaryUsage'],
            data['schedulingFrustration'],
            data['currentCalendarTool'],
            data['roleProfession'],
            data.get('company', ''),
            data.get('referralSource', ''),
            data.get('utmSource', ''),
            data.get('timezone', ''),
            self._hash_email(data['email']),
            position,
            'active'
        ]
        
        # Append to sheet
        try:
            self.sheet.append_row(row_data)
            
            # Send confirmation email - fail entire process if email fails
            email_result = self.send_confirmation_email(data['email'], data['name'], 127 + position)
            if not email_result['success']:
                # Remove the row we just added since email failed
                self.sheet.delete_rows(len(self.sheet.get_all_values()))
                return {'success': False, 'error': f'Registration failed: {email_result["error"]}'}
            
            return {
                'success': True, 
                'position': position,
                'message': 'Successfully added to waitlist and confirmation email sent'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_waitlist_stats(self) -> Dict[str, Any]:
        """Get statistics about the waitlist"""
        try:
            all_values = self.sheet.get_all_values()[1:]  # Skip header
            
            if not all_values:
                return {'total': 0, 'roles': {}}
            
            total = len(all_values)
            
            # Count by role/profession
            roles = {}
            for row in all_values:
                if len(row) > 7:  # Ensure row has role/profession data
                    role = row[7]  # Role/Profession is now column 8 (index 7)
                    roles[role] = roles.get(role, 0) + 1
            
            return {
                'total': total,
                'roles': roles,
                'last_signup': all_values[-1][0] if all_values else None
            }
        except Exception as e:
            return {'error': str(e)}
    
    def send_confirmation_email(self, email: str, name: str, position: int) -> Dict[str, Any]:
        """Send confirmation email with proper error handling"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.privateemail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            sender_email = 'support@memomindai.com'
            sender_password = os.getenv('EMAIL_PASSWORD')
            
            if not sender_password:
                return {'success': False, 'error': 'Email password not configured'}

            message = MIMEMultipart()
            message["From"] = sender_email
            message["To"] = email
            message["Subject"] = "Welcome to MemoMind AI Waitlist"

            body = f"""Hi {name},

Thank you for joining our waitlist! You're #{position} in line.

Best regards,
MemoMind AI Team"""
            message.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(message)
                
            return {'success': True, 'message': 'Confirmation email sent'}
            
        except smtplib.SMTPAuthenticationError:
            return {'success': False, 'error': 'Email authentication failed'}
        except smtplib.SMTPRecipientsRefused:
            return {'success': False, 'error': 'Invalid recipient email address'}
        except smtplib.SMTPServerDisconnected:
            return {'success': False, 'error': 'Email server connection failed'}
        except Exception as e:
            return {'success': False, 'error': f'Email sending failed: {str(e)}'}