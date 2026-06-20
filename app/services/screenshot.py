import os
import io
import hashlib
from playwright.async_api import async_playwright
from PIL import Image
from app.config import config

class ScreenshotService:
    def __init__(self):
        self.viewport_mobile = config.SCREENSHOT_VIEWPORT_MOBILE
        self.viewport_desktop = config.SCREENSHOT_VIEWPORT_DESKTOP
        self.output_dir = config.SCREENSHOT_OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)

    async def capture(self, url: str, viewport: str = "mobile", full_page: bool = True) -> str:
        """Capture screenshot, compress, return file path."""
        vp = self.viewport_mobile if viewport == "mobile" else self.viewport_desktop

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport=vp)

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1500)  # Let animations settle

                screenshot = await page.screenshot(full_page=full_page)
            finally:
                await browser.close()

        # Compress for WhatsApp
        img = Image.open(io.BytesIO(screenshot))

        # Convert to RGB if necessary
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # Resize if too large
        max_dim = 1200
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Generate filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        output_path = os.path.join(self.output_dir, f"screenshot_{url_hash}.jpg")

        img.save(output_path, "JPEG", quality=75, optimize=True)

        return output_path

    async def capture_comparison(self, before_url: str, after_url: str, viewport: str = "mobile") -> str:
        """Capture side-by-side comparison."""
        before_path = await self.capture(before_url, viewport)
        after_path = await self.capture(after_url, viewport)

        # Combine images side by side
        before = Image.open(before_path)
        after = Image.open(after_path)

        total_width = before.width + after.width
        max_height = max(before.height, after.height)

        combined = Image.new("RGB", (total_width, max_height), (255, 255, 255))
        combined.paste(before, (0, 0))
        combined.paste(after, (before.width, 0))

        output_path = os.path.join(self.output_dir, f"comparison_{hashlib.md5(f'{before_url}{after_url}'.encode()).hexdigest()[:8]}.jpg")
        combined.save(output_path, "JPEG", quality=75)

        return output_path
