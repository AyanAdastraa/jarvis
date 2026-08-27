"""
WhatsApp Cloud API Client — Official Meta Graph API integration.

This module handles all outbound communication with Meta's WhatsApp Cloud API.
It NEVER makes real API calls when WHATSAPP_MOCK_MODE is enabled.

Protocol: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

import json
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any

import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


class WhatsAppAPIError(Exception):
    """Raised when the Meta Cloud API returns an error."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WhatsApp API Error ({status_code}): {detail}")


class WhatsAppClient:
    """
    Client for Meta's WhatsApp Cloud API.

    When mock_mode is True (the default), all send operations are logged
    locally but never hit Meta's servers. This allows full local testing
    without credentials or a phone number.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        phone_number_id: Optional[str] = None,
        api_version: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ):
        self.access_token = access_token or settings.whatsapp_access_token
        self.phone_number_id = phone_number_id or settings.whatsapp_phone_number_id
        self.api_version = api_version or settings.whatsapp_api_version
        self.mock_mode = mock_mode if mock_mode is not None else settings.whatsapp_mock_mode

        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

        if not self.mock_mode and not self.access_token:
            logger.warning("WhatsApp client initialized in LIVE mode without an access token.")

    def _mask_phone(self, phone: str) -> str:
        """Mask a phone number for safe logging: +12345678901 → +12***8901"""
        if len(phone) <= 6:
            return "***"
        return phone[:3] + "***" + phone[-4:]

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _send_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a request to Meta's WhatsApp Cloud API.

        In mock mode, logs the payload and returns a synthetic success response.
        In live mode, makes the actual HTTP POST.
        """
        recipient = payload.get("to", "unknown")
        masked = self._mask_phone(recipient)

        if self.mock_mode:
            logger.info(
                f"[MOCK] WhatsApp message to {masked}",
                extra={"mock": True, "message_type": payload.get("type", "unknown")},
            )
            return {
                "messaging_product": "whatsapp",
                "contacts": [{"wa_id": recipient}],
                "messages": [{"id": f"mock_msg_{id(payload)}"}],
                "mock": True,
            }

        # --- LIVE MODE ---
        if not self.access_token:
            raise WhatsAppAPIError(401, "No access token configured.")
        if not self.phone_number_id:
            raise WhatsAppAPIError(400, "No phone_number_id configured.")

        logger.info(f"Sending WhatsApp message to {masked}")

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    self.base_url,
                    headers=self._get_headers(),
                    json=payload,
                )

            if response.status_code >= 400:
                # Extract Meta's error detail safely without leaking secrets
                try:
                    error_body = response.json()
                    detail = error_body.get("error", {}).get("message", response.text[:200])
                except Exception:
                    detail = f"HTTP {response.status_code}"
                raise WhatsAppAPIError(response.status_code, detail)

            return response.json()

        except WhatsAppAPIError:
            raise
        except httpx.TimeoutException:
            raise WhatsAppAPIError(408, "Request to Meta API timed out.")
        except Exception as e:
            logger.error("Unexpected error sending WhatsApp message.", exc_info=True)
            raise WhatsAppAPIError(500, f"Transport error: {type(e).__name__}")

    def send_text_message(self, recipient_phone: str, text: str) -> Dict[str, Any]:
        """
        Send a plain text message to a WhatsApp user.

        Args:
            recipient_phone: Full phone number with country code (e.g. "+1234567890")
            text: Message text (max 4096 characters per WhatsApp limit)
        """
        # WhatsApp has a 4096 char limit on text messages
        if len(text) > 4096:
            text = text[:4090] + "\n[…]"

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        return self._send_request(payload)

    def send_document_message(
        self,
        recipient_phone: str,
        document_link: str,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a document to a WhatsApp user via URL link.

        For MVP, this sends a document by URL. Full media upload support
        (multipart binary to Meta's media endpoint) is a future enhancement.

        Args:
            recipient_phone: Full phone number with country code
            document_link: Publicly accessible URL of the document
            caption: Optional caption text
            filename: Optional display filename
        """
        document_data: Dict[str, Any] = {"link": document_link}
        if caption:
            document_data["caption"] = caption[:1024]  # Meta caption limit
        if filename:
            document_data["filename"] = filename

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_phone,
            "type": "document",
            "document": document_data,
        }

        return self._send_request(payload)

    def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """
        Mark a received message as read (blue ticks).
        """
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }

        if self.mock_mode:
            logger.info(f"[MOCK] Marked message {message_id} as read")
            return {"success": True, "mock": True}

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    self.base_url,
                    headers=self._get_headers(),
                    json=payload,
                )
            return response.json()
        except Exception:
            # Non-critical — don't crash if read receipt fails
            logger.warning("Failed to send read receipt.", exc_info=True)
            return {"success": False}
