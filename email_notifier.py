"""Email notification module"""
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from datetime import datetime


class EmailNotifier:
    """Send email notifications"""
    
    def __init__(self, smtp_server: Optional[str] = None, smtp_port: int = 587,
                 smtp_user: Optional[str] = None, smtp_password: Optional[str] = None,
                 from_email: Optional[str] = None):
        """
        Initialize email notifier
        
        Args:
            smtp_server: SMTP server (default: smtp.gmail.com)
            smtp_port: SMTP port (default: 587)
            smtp_user: SMTP username (from env: SMTP_USER)
            smtp_password: SMTP password (from env: SMTP_PASSWORD)
            from_email: From email address (from env: SMTP_FROM_EMAIL)
        """
        self.smtp_server = smtp_server or os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = smtp_port or int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = smtp_user or os.getenv("SMTP_USER")
        self.smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
        self.from_email = from_email or os.getenv("SMTP_FROM_EMAIL") or self.smtp_user
    
    def send_notification(self, to_email: str, subject: str, body: str, html_body: Optional[str] = None) -> bool:
        """
        Send email notification
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Plain text body
            html_body: Optional HTML body
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.smtp_user or not self.smtp_password:
            print("⚠️ SMTP credentials not configured, skipping email notification")
            return False
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Add plain text part
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Add HTML part if provided
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            print(f"✅ Email notification sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to send email notification: {e}")
            return False
    
    def send_shopping_complete_notification(self, to_email: str, cart_url: str = "https://www.ah.nl/mijnlijst") -> bool:
        """
        Send shopping completion notification
        
        Args:
            to_email: Recipient email address
            cart_url: Shopping cart URL
            
        Returns:
            True if sent successfully, False otherwise
        """
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        subject = "🛒 AH购物清单已完成 - 请完成付款"
        
        body = f"""
AH购物清单已完成！

时间: {current_time}

购物车已准备好，请访问以下链接完成付款：
{cart_url}

祝购物愉快！
        """.strip()
        
        html_body = f"""
        <html>
        <body>
            <h2>🛒 AH购物清单已完成</h2>
            <p><strong>时间:</strong> {current_time}</p>
            <p>购物车已准备好，请访问以下链接完成付款：</p>
            <p><a href="{cart_url}">{cart_url}</a></p>
            <p>祝购物愉快！</p>
        </body>
        </html>
        """
        
        return self.send_notification(to_email, subject, body, html_body)

