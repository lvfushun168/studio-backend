import os
import sys
from pathlib import Path

from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.account import Account


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from gemini_webapi import GeminiClient  # noqa: E402


class GeminiGateway:
    async def generate_images(
        self,
        account: Account,
        prompt: str,
        input_paths: list[str],
        out_dir: Path,
        model_name: str | None = None,
    ) -> list[str]:
        secure_1psid = decrypt_secret(account.secure_1psid_enc)
        secure_1psidts = decrypt_secret(account.secure_1psidts_enc)
        if not secure_1psid:
            raise ValueError("Missing __Secure-1PSID")

        client = GeminiClient(secure_1psid, secure_1psidts or None)
        await client.init(timeout=180, auto_close=False, auto_refresh=True, verbose=True)

        try:
            kwargs = {}
            kwargs["model"] = model_name or account.model_hint or settings.default_model
            response = await client.generate_content(
                prompt,
                files=input_paths or None,
                **kwargs,
            )

            out_dir.mkdir(parents=True, exist_ok=True)
            saved_paths: list[str] = []
            for index, image in enumerate(response.images, start=1):
                saved_path = await image.save(
                    path=str(out_dir),
                    filename=f"generated_{index}.png",
                    verbose=True,
                )
                saved_paths.append(saved_path)

            if not saved_paths:
                raise ValueError("Gemini did not return any images for this task.")

            return saved_paths
        finally:
            await client.close()
