import os
from typing import List
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from app.config import config

class WhatsAppService:
    def __init__(self):
        self.client = Client(config.TWILIO_SID, config.TWILIO_TOKEN)
        self.from_number = config.TWILIO_WHATSAPP_NUMBER

    async def send_text(self, to: str, body: str):
        """Send text message. Split if >1500 chars."""
        chunks = [body[i:i+config.MAX_MESSAGE_LENGTH] for i in range(0, len(body), config.MAX_MESSAGE_LENGTH)]
        for chunk in chunks:
            self.client.messages.create(
                from_=self.from_number,
                body=chunk,
                to=f"whatsapp:{to}"
            )

    async def send_image(self, to: str, image_path: str, caption: str = ""):
        """Send image with caption."""
        from twilio.base.exceptions import TwilioRestException
        try:
            # For MVP: use local file path with Twilio (needs public URL in prod)
            # In production, upload to S3/Cloudinary first
            media_url = await self._upload_image(image_path)
            self.client.messages.create(
                from_=self.from_number,
                media_url=[media_url],
                body=caption[:1000],
                to=f"whatsapp:{to}"
            )
        except TwilioRestException as e:
            # Fallback: send text with URL
            await self.send_text(to, f"📸 Preview: {caption}\n(Images require public URL hosting)")

    async def send_file(self, to: str, file_path: str, filename: str):
        """Send code file as document."""
        media_url = await self._upload_file(file_path)
        self.client.messages.create(
            from_=self.from_number,
            media_url=[media_url],
            to=f"whatsapp:{to}"
        )

    async def _upload_image(self, image_path: str) -> str:
        """Upload image to public URL."""
        filename = os.path.basename(image_path)
        return f"{config.BASE_URL}/static/{filename}"

    async def _upload_file(self, file_path: str) -> str:
        """Upload file to public URL."""
        filename = os.path.basename(file_path)
        return f"{config.BASE_URL}/static/{filename}"
