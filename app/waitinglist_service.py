# app/waitinglist_service.py
import os
import json
import re
import hashlib
import socket
import logging
from datetime import datetime, timezone
from typing import Dict, Any
import gspread
from google.oauth2.service_account import Credentials
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class WaitlistManager:
    def __init__(self):
        logger.info("Initializing WaitlistManager")
        try:
            self.client = self._init_google_sheets()
            self.sheet = self.client.open_by_key(self._get_spreadsheet_id()).worksheet(self._get_sheet_name())
            self._ensure_headers()
            logger.info("WaitlistManager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WaitlistManager: {str(e)}")
            raise
    
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
        logger.info("Initializing Google Sheets client")
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        
        try:
            # Try to use environment variables first, fallback to service account file
            if self._has_service_account_env_vars():
                logger.info("Using service account from environment variables")
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
                logger.info(f"Using service account file: {service_account_file}")
                creds = Credentials.from_service_account_file(service_account_file, scopes=scopes)
            
            client = gspread.authorize(creds)
            logger.info("Google Sheets client initialized successfully")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets client: {str(e)}")
            raise
    
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
        logger.info(f"Validating email: {email}")
        
        # Basic format validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            logger.warning(f"Email format validation failed for: {email}")
            return {'valid': False, 'error': 'Invalid email format'}
        
        # Extract domain
        domain = email.split('@')[1]
        logger.info(f"Validating domain: {domain}")
        
        # Check if domain has MX record
        try:
            socket.getaddrinfo(domain, None)
            logger.info(f"Email validation successful for: {email}")
            return {'valid': True}
        except socket.gaierror as e:
            logger.warning(f"Domain validation failed for {domain}: {str(e)}")
            return {'valid': False, 'error': 'Invalid email domain'}
    
    def _hash_email(self, email: str) -> str:
        """Create hash of email for duplicate checking"""
        return hashlib.sha256(email.lower().encode()).hexdigest()[:16]
    
    def check_existing_signup(self, email: str) -> bool:
        """Check if email already exists in waitlist"""
        logger.info(f"Checking for existing signup: {email}")
        email_hash = self._hash_email(email)
        try:
            cell = self.sheet.find(email_hash, in_column=13)
            exists = cell is not None
            logger.info(f"Existing signup check for {email}: {'exists' if exists else 'not found'}")
            return exists
        except Exception as e:
            logger.error(f"Error checking existing signup for {email}: {str(e)}")
            return False
    
    def add_to_waitlist(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Add new signup to waitlist"""
        email = data.get('email', 'unknown')
        logger.info(f"Starting waitlist registration for: {email}")
        
        try:
            # Validate email
            email_validation = self._validate_email(data['email'])
            if not email_validation['valid']:
                logger.warning(f"Email validation failed for {email}: {email_validation['error']}")
                return {'success': False, 'error': email_validation['error']}
            
            # Check for existing signup
            if self.check_existing_signup(data['email']):
                logger.warning(f"Duplicate signup attempt for: {email}")
                return {'success': False, 'error': 'Email already on waitlist'}
            
            # Get current count for position
            logger.info(f"Getting current waitlist position for: {email}")
            all_values = self.sheet.get_all_values()
            position = len(all_values)  # This includes header row
            logger.info(f"Assigning position {position} to: {email}")
            
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
            logger.info(f"Adding {email} to waitlist spreadsheet")
            self.sheet.append_row(row_data)
            logger.info(f"Successfully added {email} to spreadsheet at position {position}")
            
            # Send confirmation email - fail entire process if email fails
            logger.info(f"Sending confirmation email to: {email}")
            email_result = self.send_confirmation_email(data['email'], data['name'], 127 + position)
            if not email_result['success']:
                logger.error(f"Email sending failed for {email}, removing from waitlist: {email_result['error']}")
                # Remove the row we just added since email failed
                self.sheet.delete_rows(len(self.sheet.get_all_values()))
                return {'success': False, 'error': f'Registration failed: {email_result["error"]}'}
            
            logger.info(f"Successfully completed waitlist registration for: {email}")
            return {
                'success': True, 
                'position': position,
                'message': 'Successfully added to waitlist and confirmation email sent'
            }
        except Exception as e:
            logger.error(f"Unexpected error during waitlist registration for {email}: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def send_confirmation_email(self, email: str, name: str, position: int) -> Dict[str, Any]:
        """Send confirmation email with proper error handling"""
        logger.info(f"Starting confirmation email send to: {email}")
        
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.privateemail.com')
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            sender_email = 'support@memomindai.com'
            sender_password = os.getenv('EMAIL_PASSWORD')
            
            logger.info(f"Email config - Server: {smtp_server}, Port: {smtp_port}, Sender: {sender_email}")
            
            if not sender_password:
                logger.error("Email password not configured")
                return {'success': False, 'error': 'Email password not configured'}

            message = MIMEMultipart("alternative")
            message["From"] = f"MemoMind AI Team <{sender_email}>"
            message["To"] = email
            message["Subject"] = "🚀 Welcome to MemoMind AI - You're In!"

            # Create both plain text and HTML versions
            text_body = f"""🚀 WELCOME TO MEMOMIND AI - YOU'RE IN! 🚀

    Hi {name}! 👋

    Thank you for joining the MemoMind AI waitlist. You're position #{position} in line to access the AI-powered calendar assistant that will transform how you work, reflect, and achieve your goals.

    ✅ YOU'RE IN! ✅
    Position #{position} • Early Access Secured

    ═══════════════════════════════════════════════════════════════

    WHAT HAPPENS NEXT?

    📧 We'll keep you updated on our launch progress
    🎯 You'll get exclusive early access before our public release (Q2 2025)  
    🏆 Be among the first 1,000 users to experience AI-driven productivity optimization

    ═══════════════════════════════════════════════════════════════

    WHY YOU MADE THE RIGHT CHOICE

    Most professionals lose 40% of their productive time to poor scheduling. MemoMind AI doesn't just organize your calendar—it analyzes your patterns, provides performance insights, and guides daily reflections to help you work smarter and achieve work-life balance.

    Key Benefits:
    🧠 AI-Powered Insights | 📊 Performance Analytics | ⚖️ Work-Life Balance

    ═══════════════════════════════════════════════════════════════

    STAY CONNECTED

    Visit our website: https://memomindai.com
    Questions? Just reply to this email—we read every message! 💬

    ═══════════════════════════════════════════════════════════════

    We're building something special, and having ambitious professionals like you on this journey means everything to us.

    Here's to optimizing your performance and achieving your biggest goals! 🎯

    Best regards,
    The MemoMind AI Team

    P.S. Keep an eye on your inbox—we'll be sharing exclusive updates and productivity insights as we get closer to launch.

    ---
    MemoMind AI - AI-Powered Calendar Optimization & Performance Insights
    Website: https://memomindai.com
    """
            html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Welcome to MemoMind AI</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        
        <!-- Header -->
        <div style="text-align: center; margin-bottom: 30px; padding: 20px; background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); border-radius: 12px;">
            <h1 style="color: white; margin: 0; font-size: 24px; font-weight: bold;">🚀 Welcome to MemoMind AI!</h1>
            <p style="color: #e0e7ff; margin: 10px 0 0 0; font-size: 16px;">You're officially on the waitlist</p>
        </div>

        <!-- Main Content -->
        <div style="background: #f8fafc; padding: 25px; border-radius: 12px; margin-bottom: 20px;">
            <h2 style="color: #1e293b; margin-top: 0;">Hi {name}! 👋</h2>
            
            <p style="font-size: 16px; margin-bottom: 20px;">
                Thank you for joining the MemoMind AI waitlist. <strong>You're position #{position}</strong> in line to access the AI-powered calendar assistant that will transform how you work, reflect, and achieve your goals.
            </p>

            <!-- Status Box -->
            <div style="background: white; border: 2px solid #10b981; border-radius: 8px; padding: 15px; margin: 20px 0; text-align: center;">
                <div style="color: #10b981; font-weight: bold; font-size: 18px;">✅ You're In!</div>
                <div style="color: #6b7280; font-size: 14px; margin-top: 5px;">Position #{position} • Early Access Secured</div>
            </div>
        </div>

        <!-- What's Next Section -->
        <div style="margin-bottom: 25px;">
            <h3 style="color: #1e293b; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px;">What happens next?</h3>
            <ul style="padding-left: 0; list-style: none;">
                <li style="padding: 8px 0; border-left: 3px solid #3b82f6; padding-left: 12px; margin-bottom: 8px;">
                    📧 We'll keep you updated on our launch progress
                </li>
                <li style="padding: 8px 0; border-left: 3px solid #8b5cf6; padding-left: 12px; margin-bottom: 8px;">
                    🎯 You'll get exclusive early access before our public release (Q4 2025)
                </li>
                <li style="padding: 8px 0; border-left: 3px solid #10b981; padding-left: 12px; margin-bottom: 8px;">
                    🏆 Be among the first 1,000 users to experience AI-driven productivity optimization
                </li>
            </ul>
        </div>

        <!-- Value Proposition -->
        <div style="background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%); padding: 20px; border-radius: 12px; margin-bottom: 25px;">
            <h3 style="color: #1e293b; margin-top: 0;">Why you made the right choice</h3>
            <p style="margin-bottom: 15px;">
                Most professionals lose <strong>40% of their productive time</strong> to poor scheduling. MemoMind AI doesn't just organize your calendar—it analyzes your patterns, provides performance insights, and guides daily reflections to help you work smarter and achieve work-life balance.
            </p>
            
            <!-- Key Benefits -->
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 15px;">
                <span style="background: #dbeafe; color: #1e40af; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">🧠 AI-Powered Insights</span>
                <span style="background: #f3e8ff; color: #7c3aed; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">📊 Performance Analytics</span>
                <span style="background: #dcfce7; color: #166534; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 500;">⚖️ Work-Life Balance</span>
            </div>
        </div>

        <!-- Call to Action -->
        <div style="text-align: center; margin: 30px 0;">
            <p style="color: #6b7280; margin-bottom: 15px;">Stay connected with us:</p>
            <div style="margin-bottom: 20px;">
                <a href="https://memomindai.com" style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); color: white; padding: 12px 24px; text-decoration: none; border-radius: 25px; font-weight: 500; margin: 0 5px;">Visit Our Website</a>
            </div>
            <p style="color: #6b7280; font-size: 14px;">
                Questions? Just reply to this email—we read every message! 💬
            </p>
        </div>

        <!-- Closing -->
        <div style="background: #1e293b; color: white; padding: 20px; border-radius: 12px; text-align: center;">
            <p style="margin: 0; font-size: 16px;">
                We're building something special, and having ambitious professionals like you on this journey means everything to us.
            </p>
            <p style="margin: 15px 0 0 0; font-weight: bold; font-size: 18px; background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                Here's to optimizing your performance and achieving your biggest goals! 🎯
            </p>
        </div>

        <!-- Footer -->
        <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #6b7280; font-size: 12px;">
            <p style="margin: 0;">
                <strong>MemoMind AI</strong> - AI-Powered Calendar Optimization & Performance Insights<br>
                <a href="https://memomindai.com" style="color: #3b82f6; text-decoration: none;">memomindai.com</a>
            </p>
            <p style="margin: 10px 0 0 0; font-style: italic;">
                P.S. Keep an eye on your inbox—we'll be sharing exclusive updates and productivity insights as we get closer to launch.
            </p>
        </div>
    </body>
    </html>
    """

            # Attach both versions
            part1 = MIMEText(text_body, "plain")
            part2 = MIMEText(html_body, "html")
            
            message.attach(part1)
            message.attach(part2)

            logger.info(f"Connecting to SMTP server {smtp_server}:{smtp_port}")
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                logger.info("Starting TLS connection")
                server.starttls()
                logger.info("Authenticating with SMTP server")
                server.login(sender_email, sender_password)
                logger.info(f"Sending email to: {email}")
                server.send_message(message)
                
            logger.info(f"Confirmation email sent successfully to: {email}")
            return {'success': True, 'message': 'Confirmation email sent'}
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed for {email}: {str(e)}")
            return {'success': False, 'error': 'Email authentication failed'}
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"SMTP recipients refused for {email}: {str(e)}")
            return {'success': False, 'error': 'Invalid recipient email address'}
        except smtplib.SMTPServerDisconnected as e:
            logger.error(f"SMTP server disconnected for {email}: {str(e)}")
            return {'success': False, 'error': 'Email server connection failed'}
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error for {email}: {str(e)}")
            return {'success': False, 'error': f'SMTP error: {str(e)}'}
        except Exception as e:
            logger.error(f"Unexpected error sending email to {email}: {str(e)}")
            return {'success': False, 'error': f'Email sending failed: {str(e)}'}
    
    def get_waitlist_stats(self) -> Dict[str, Any]:
        """Get waitlist statistics including total count, role breakdown, and last signup"""
        logger.info("Starting waitlist stats calculation")
        
        try:
            # Get all data from the sheet
            logger.info("Fetching all data from waitlist spreadsheet")
            all_values = self.sheet.get_all_values()
            logger.info(f"Retrieved {len(all_values)} rows from spreadsheet")
            
            # Skip header row
            if len(all_values) <= 1:
                logger.info("No data rows found in waitlist (only header or empty)")
                return {
                    'total': 0,
                    'roles': {},
                    'last_signup': None,
                    'error': None
                }
            
            data_rows = all_values[1:]  # Skip header
            logger.info(f"Processing {len(data_rows)} data rows")
            
            # Count total active signups
            total = len(data_rows)
            
            # Count roles breakdown
            roles = {}
            last_signup_timestamp = None
            
            for i, row in enumerate(data_rows):
                if len(row) >= 8:  # Ensure we have enough columns
                    # Role is in column 7 (0-indexed)
                    role = row[7] if row[7] else 'Unknown'
                    roles[role] = roles.get(role, 0) + 1
                    
                    # Timestamp is in column 0
                    if row[0] and (not last_signup_timestamp or row[0] > last_signup_timestamp):
                        last_signup_timestamp = row[0]
                else:
                    logger.warning(f"Row {i+2} has insufficient columns ({len(row)}), skipping role analysis")
            
            logger.info(f"Waitlist stats calculated - Total: {total}, Roles: {len(roles)}, Last signup: {last_signup_timestamp}")
            
            return {
                'total': total,
                'roles': roles,
                'last_signup': last_signup_timestamp,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Error calculating waitlist stats: {str(e)}")
            return {
                'total': 0,
                'roles': {},
                'last_signup': None,
                'error': str(e)
            }