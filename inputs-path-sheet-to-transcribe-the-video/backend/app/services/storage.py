import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings
from app.services.encryption import decrypt_value, encrypt_value

_SHEET_HISTORY_LIMIT = 8


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def remember_sheet_history(
    history: list[dict[str, Any]],
    url: str,
    title: str = "",
    *,
    limit: int = _SHEET_HISTORY_LIMIT,
) -> list[dict[str, Any]]:
    """Move url to the front of recent history; keep unique entries only."""
    cleaned = (url or "").strip()
    if not cleaned:
        return list(history or [])
    label = (title or "").strip() or cleaned
    rest = [item for item in (history or []) if (item.get("url") or "").strip() != cleaned]
    return [{"url": cleaned, "title": label, "used_at": _now_iso()}, *rest][:limit]


class Storage:
    def __init__(self) -> None:
        settings = get_settings()
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.secret = settings.secret_key
        self.config_path = self.data_dir / "config.json"
        self.tokens_path = self.data_dir / "tokens.enc"
        self.uploads_dir = self.data_dir / "uploads"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, data: dict) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_admin_config(self) -> dict:
        raw = self._read_json(self.config_path)
        result: dict[str, Any] = {
            "sheet_url": None,
            "output_sheet_url": None,
            "docs_folder_id": None,
            "voice_output_dir": None,
        }
        if raw.get("sheet_url_enc"):
            try:
                result["sheet_url"] = decrypt_value(raw["sheet_url_enc"], self.secret)
            except Exception:
                result["sheet_url"] = None
        if raw.get("output_sheet_url_enc"):
            try:
                result["output_sheet_url"] = decrypt_value(raw["output_sheet_url_enc"], self.secret)
            except Exception:
                result["output_sheet_url"] = None
        result["docs_folder_id"] = raw.get("docs_folder_id")
        result["registry_owner_email"] = raw.get("registry_owner_email")
        result["output_doc_id"] = raw.get("output_doc_id")
        result["voice_output_dir"] = raw.get("voice_output_dir")
        return result

    def get_registry_sheet(self, email: str) -> Optional[str]:
        """Return the registry sheet URL for this Google account, if any."""
        if not email:
            return None
        raw = self._read_json(self.config_path)
        key = email.strip().lower()
        by_email = raw.get("sheets_by_email_enc", {})
        if key in by_email:
            try:
                return decrypt_value(by_email[key], self.secret)
            except Exception:
                pass
        owner = (raw.get("registry_owner_email") or "").strip().lower()
        if owner == key and raw.get("sheet_url_enc"):
            try:
                return decrypt_value(raw["sheet_url_enc"], self.secret)
            except Exception:
                pass
        return None

    def save_registry_sheet(self, email: str, sheet_url: str) -> None:
        """Save registry sheet URL for a specific Google account."""
        data = self._read_json(self.config_path)
        key = email.strip().lower()
        by_email = data.get("sheets_by_email_enc", {})
        by_email[key] = encrypt_value(sheet_url, self.secret)
        data["sheets_by_email_enc"] = by_email
        data["registry_owner_email"] = key
        data["sheet_url_enc"] = encrypt_value(sheet_url, self.secret)
        self._write_json(self.config_path, data)

    def save_admin_config(
        self,
        sheet_url: str,
        docs_folder_id: Optional[str] = None,
        output_sheet_url: Optional[str] = None,
        voice_output_dir: Optional[str] = None,
    ) -> None:
        data = self._read_json(self.config_path)
        data["sheet_url_enc"] = encrypt_value(sheet_url, self.secret)
        if output_sheet_url is not None:
            data["output_sheet_url_enc"] = encrypt_value(output_sheet_url, self.secret)
        if docs_folder_id is not None:
            data["docs_folder_id"] = docs_folder_id
        if voice_output_dir is not None:
            data["voice_output_dir"] = voice_output_dir
        self._write_json(self.config_path, data)

    def save_output_sheet_url(self, output_sheet_url: str) -> None:
        data = self._read_json(self.config_path)
        data["output_sheet_url_enc"] = encrypt_value(output_sheet_url, self.secret)
        self._write_json(self.config_path, data)

    def _decrypt_json_blob(self, blob: Optional[str]) -> Optional[dict]:
        if not blob:
            return None
        try:
            return json.loads(decrypt_value(blob, self.secret))
        except Exception:
            return None

    def get_sheet_session(self, email: str) -> dict[str, Any]:
        """Per-Google-account current sheets + recent URLs."""
        session = {
            "input_url": None,
            "output_url": None,
            "input_history": [],
            "output_history": [],
        }
        key = (email or "").strip().lower()
        raw = self._read_json(self.config_path)
        by_email = raw.get("sheet_sessions_enc") or {}
        if key and key in by_email:
            parsed = self._decrypt_json_blob(by_email[key])
            if isinstance(parsed, dict):
                session["input_url"] = (parsed.get("input_url") or "").strip() or None
                session["output_url"] = (parsed.get("output_url") or "").strip() or None
                session["input_history"] = list(parsed.get("input_history") or [])
                session["output_history"] = list(parsed.get("output_history") or [])

        # Seed from legacy admin config so existing setups keep working.
        cfg = self.get_admin_config()
        if not session["input_url"] and cfg.get("sheet_url"):
            session["input_url"] = cfg["sheet_url"]
            session["input_history"] = remember_sheet_history(
                session["input_history"], cfg["sheet_url"], "Input sheet"
            )
        if not session["output_url"] and cfg.get("output_sheet_url"):
            session["output_url"] = cfg["output_sheet_url"]
            session["output_history"] = remember_sheet_history(
                session["output_history"], cfg["output_sheet_url"], "Output sheet"
            )
        return session

    def save_sheet_session(self, email: str, session: dict[str, Any]) -> dict[str, Any]:
        key = (email or "").strip().lower()
        if not key:
            raise ValueError("Google email is required to save sheet session")
        payload = {
            "input_url": (session.get("input_url") or "").strip() or None,
            "output_url": (session.get("output_url") or "").strip() or None,
            "input_history": list(session.get("input_history") or []),
            "output_history": list(session.get("output_history") or []),
        }
        data = self._read_json(self.config_path)
        by_email = data.get("sheet_sessions_enc") or {}
        by_email[key] = encrypt_value(json.dumps(payload), self.secret)
        data["sheet_sessions_enc"] = by_email
        data["registry_owner_email"] = key
        if payload["input_url"]:
            data["sheet_url_enc"] = encrypt_value(payload["input_url"], self.secret)
        if payload["output_url"]:
            data["output_sheet_url_enc"] = encrypt_value(payload["output_url"], self.secret)
        self._write_json(self.config_path, data)
        return payload

    def remember_sheet(
        self,
        email: str,
        *,
        kind: str,
        url: str,
        title: str = "",
    ) -> dict[str, Any]:
        session = self.get_sheet_session(email)
        field = "input_url" if kind == "input" else "output_url"
        hist_field = "input_history" if kind == "input" else "output_history"
        session[field] = url.strip()
        session[hist_field] = remember_sheet_history(session[hist_field], url, title)
        return self.save_sheet_session(email, session)

    def save_voice_output_dir(self, path: str) -> None:
        data = self._read_json(self.config_path)
        data["voice_output_dir"] = path
        self._write_json(self.config_path, data)

    def save_output_doc_id(self, doc_id: str) -> None:
        data = self._read_json(self.config_path)
        data["output_doc_id"] = doc_id
        self._write_json(self.config_path, data)

    def is_admin_configured(self) -> bool:
        cfg = self.get_admin_config()
        return bool(cfg.get("sheet_url"))

    def is_output_sheet_configured(self) -> bool:
        if self.get_admin_config().get("output_sheet_url"):
            return True
        return bool(get_settings().output_sheet_url.strip())

    def save_google_tokens(self, tokens: dict) -> None:
        encrypted = encrypt_value(json.dumps(tokens), self.secret)
        self.tokens_path.write_text(encrypted, encoding="utf-8")

    def get_google_tokens(self) -> Optional[dict]:
        if not self.tokens_path.exists():
            return None
        try:
            decrypted = decrypt_value(self.tokens_path.read_text(encoding="utf-8"), self.secret)
            return json.loads(decrypted)
        except Exception:
            return None

    def clear_google_tokens(self) -> None:
        if self.tokens_path.exists():
            os.remove(self.tokens_path)

    def save_upload(self, upload_id: str, filename: str, content: bytes) -> str:
        dest = self.uploads_dir / f"{upload_id}_{filename}"
        dest.write_bytes(content)
        return str(dest)

    def partial_upload_path(self, upload_id: str, filename: str) -> Path:
        return self.uploads_dir / f"{upload_id}_{filename}.partial"

    def final_upload_path(self, upload_id: str, filename: str) -> Path:
        return self.uploads_dir / f"{upload_id}_{filename}"

    def init_partial_upload(self, upload_id: str, filename: str, total_size: int) -> Path:
        path = self.partial_upload_path(upload_id, filename)
        with open(path, "wb") as f:
            if total_size > 0:
                f.truncate(total_size)
        meta_path = self.uploads_dir / f"{upload_id}.json"
        meta_path.write_text(
            json.dumps({"filename": filename, "size": total_size}),
            encoding="utf-8",
        )
        return path

    def get_upload_session(self, upload_id: str) -> dict:
        meta_path = self.uploads_dir / f"{upload_id}.json"
        if not meta_path.exists():
            raise FileNotFoundError(upload_id)
        return json.loads(meta_path.read_text(encoding="utf-8"))

    def write_upload_chunk(self, upload_id: str, filename: str, offset: int, data: bytes) -> None:
        path = self.partial_upload_path(upload_id, filename)
        with open(path, "r+b") as f:
            f.seek(offset)
            f.write(data)

    def finalize_partial_upload(self, upload_id: str, filename: str) -> str:
        partial = self.partial_upload_path(upload_id, filename)
        final = self.final_upload_path(upload_id, filename)
        if final.exists():
            final.unlink()
        partial.rename(final)
        meta_path = self.uploads_dir / f"{upload_id}.json"
        if meta_path.exists():
            meta_path.unlink()
        return str(final)


storage = Storage()
