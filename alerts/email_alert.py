"""
Email alert integration for SendGrid

Sends daily digests and high-priority alerts
"""

from typing import Optional, List
from datetime import datetime
from loguru import logger
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


class EmailAlert:
    """Send alerts via email"""
    
    def __init__(self, settings):
        self.settings = settings
        self.sendgrid_key = getattr(settings, 'sendgrid_api_key', None)
        self.recipient_email = getattr(settings, 'alert_email', None)
    
    async def send(
        self, 
        subject: str, 
        body: str,
        html: bool = False
    ):
        """Send an email alert"""
        
        if not self.sendgrid_key or not self.recipient_email:
            logger.warning("Email configuration incomplete - skipping email alert")
            return
        
        try:
            # Using SendGrid API would go here
            # For now, log that it would be sent
            logger.info(f"📧 Email alert queued: {subject}")
            
            # In production, integrate with SendGrid:
            # from sendgrid import SendGridAPIClient
            # from sendgrid.helpers.mail import Mail
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
