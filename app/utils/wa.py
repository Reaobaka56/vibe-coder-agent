def normalise_wa(raw: str) -> str:
    """Normalize Twilio WhatsApp numbers for stable session and DB keys."""
    return (raw or "").replace("whatsapp:", "").strip()
