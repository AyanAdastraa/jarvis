import asyncio
from interfaces.whatsapp_client import WhatsAppClient

async def main():
    client = WhatsAppClient()
    try:
        # Send to the user's verified number
        response = client.send_text_message("918889430293", "Hello from JARVIS! Please reply to this message.")
        print("Success:", response)
    except Exception as e:
        print("Error:", str(e))

asyncio.run(main())
