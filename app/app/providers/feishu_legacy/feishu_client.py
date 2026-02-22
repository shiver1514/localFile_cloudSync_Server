import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, user_token_file: str, timeout: int = 30):
        self.app_id = app_id or ""
        self.app_secret = app_secret or ""
        self.user_token_file = user_token_file or ""
        self.timeout = timeout

    def _load_user_tokens(self) -> dict[str, Any] | None:
        if not self.user_token_file:
            return None
        p = Path(self.user_token_file)
        if not p.exists():
            return None
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
        return None

    def _save_user_tokens(self, data: dict[str, Any]) -> None:
        if not self.user_token_file:
            return
        p = Path(self.user_token_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_oauth_authorize_url(self, redirect_uri: str, state: str) -> str:
        if not self.app_id:
            raise RuntimeError("app_id_missing")
        if not redirect_uri:
            raise RuntimeError("redirect_uri_missing")
        if not state:
            raise RuntimeError("oauth_state_missing")
        query = urlencode(
            {
                "app_id": self.app_id,
                "redirect_uri": redirect_uri,
                "state": state,
            }
        )
        return f"https://open.feishu.cn/open-apis/authen/v1/index?{query}"

    def exchange_code_for_user_token(self, code: str) -> dict[str, Any]:
        if not self.app_id or not self.app_secret:
            raise RuntimeError("auth_incomplete")
        code_text = (code or "").strip()
        if not code_text:
            raise RuntimeError("oauth_code_missing")

        res = requests.post(
            f"{BASE}/authen/v1/access_token",
            json={
                "grant_type": "authorization_code",
                "code": code_text,
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            timeout=self.timeout,
        )
        token_data = self._check_data(res.json())
        token_data["created_at"] = int(time.time() * 1000)
        self._save_user_tokens(token_data)
        return token_data

    def _refresh_user_tokens(
        self,
        refresh_token: str,
        *,
        raise_on_error: bool = False,
    ) -> dict[str, Any] | None:
        refresh = (refresh_token or "").strip()
        if not refresh or not self.app_id or not self.app_secret:
            if raise_on_error:
                raise RuntimeError("refresh_token_missing_or_auth_incomplete")
            return None

        res = requests.post(
            f"{BASE}/authen/v1/refresh_access_token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            timeout=self.timeout,
        )
        payload_raw = res.json()
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        if payload.get("code") != 0:
            if raise_on_error:
                raise RuntimeError(f"refresh_token_failed: {payload.get('msg')}")
            return None

        refreshed_raw = payload.get("data", {}) or {}
        refreshed = refreshed_raw if isinstance(refreshed_raw, dict) else {}
        refreshed["created_at"] = int(time.time() * 1000)
        self._save_user_tokens(refreshed)
        return refreshed

    def refresh_user_access_token(self, force: bool = False) -> dict[str, Any]:
        tokens = self._load_user_tokens()
        if not tokens:
            raise RuntimeError("no_user_token_file_or_empty")

        if not force:
            access_token = tokens.get("access_token")
            created = int(tokens.get("created_at", 0))
            expires_in = int(tokens.get("expires_in", 7200))
            expire_at = created + max(expires_in - 300, 300) * 1000
            if access_token and created and int(time.time() * 1000) < expire_at:
                return tokens

        refreshed = self._refresh_user_tokens(tokens.get("refresh_token", ""), raise_on_error=True)
        if not refreshed or not refreshed.get("access_token"):
            raise RuntimeError("refresh_token_failed_no_access_token")
        return refreshed

    def _user_access_token(self) -> str | None:
        tokens = self._load_user_tokens()
        if not tokens:
            return None

        access_token_raw = tokens.get("access_token")
        refresh_token_raw = tokens.get("refresh_token")
        access_token = access_token_raw if isinstance(access_token_raw, str) and access_token_raw else None
        refresh_token = refresh_token_raw if isinstance(refresh_token_raw, str) else ""
        created = int(tokens.get("created_at", 0))
        expires_in = int(tokens.get("expires_in", 7200))

        if not access_token:
            return None

        expire_at = created + max(expires_in - 300, 300) * 1000
        if created and int(time.time() * 1000) < expire_at:
            return access_token

        refreshed = self._refresh_user_tokens(refresh_token, raise_on_error=False)
        if not refreshed:
            return None
        return refreshed.get("access_token")

    def _tenant_access_token(self) -> str | None:
        if not self.app_id or not self.app_secret:
            return None
        res = requests.post(
            f"{BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout,
        )
        data_raw = res.json()
        data = data_raw if isinstance(data_raw, dict) else {}
        if data.get("code") != 0:
            return None
        token = data.get("tenant_access_token")
        if isinstance(token, str) and token:
            return token
        return None

    def get_access_token(
        self,
        priority: tuple[str, ...] = ("user", "tenant"),
    ) -> tuple[str | None, str | None]:
        for mode in priority:
            if mode == "user":
                tok = self._user_access_token()
                if tok:
                    return tok, "user_access_token"
            elif mode == "tenant":
                tok = self._tenant_access_token()
                if tok:
                    return tok, "tenant_access_token"
        return None, None

    def _auth_headers(
        self,
        content_type: str | None = "application/json",
    ) -> tuple[dict[str, str], str | None]:
        token, token_type = self.get_access_token()
        if not token:
            raise RuntimeError("no_token")
        headers = {"Authorization": f"Bearer {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers, token_type

    def _check_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise RuntimeError("invalid_response")
        if payload.get("code", 0) != 0:
            raise RuntimeError(f"feishu_error: code={payload.get('code')} msg={payload.get('msg')}")
        data = payload.get("data", {}) or {}
        if not isinstance(data, dict):
            raise RuntimeError("invalid_response_data")
        return data

    def get_root_folder_token(self) -> str:
        headers, _ = self._auth_headers()
        res = requests.get(f"{BASE}/drive/explorer/v2/root_folder/meta", headers=headers, timeout=self.timeout)
        payload_raw = res.json()
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        data = self._check_data(payload)
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("root_folder_token_missing")
        return token

    def list_files(
        self,
        folder_token: str | None,
        page_size: int = 200,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        headers, token_type = self._auth_headers()
        params: dict[str, str | int] = {"page_size": page_size}
        if folder_token:
            params["folder_token"] = folder_token
        if page_token:
            params["page_token"] = page_token

        res = requests.get(f"{BASE}/drive/v1/files", params=params, headers=headers, timeout=self.timeout)
        body_raw = res.json()
        body = body_raw if isinstance(body_raw, dict) else {}
        if body.get("code", 0) != 0:
            return {"ok": False, "token_type": token_type, "error": body}
        data_raw = body.get("data", {}) or {}
        data = data_raw if isinstance(data_raw, dict) else {}
        files_raw = data.get("files", []) or []
        files = [item for item in files_raw if isinstance(item, dict)] if isinstance(files_raw, list) else []
        next_page_token_raw = data.get("next_page_token") or data.get("page_token")
        next_page_token = str(next_page_token_raw) if next_page_token_raw is not None else None
        return {
            "ok": True,
            "token_type": token_type,
            "files": files,
            "next_page_token": next_page_token,
        }

    def list_folder_once(self, folder_token: str | None) -> list[dict[str, Any]]:
        page_token: str | None = None
        items: list[dict[str, Any]] = []
        while True:
            res = self.list_files(folder_token=folder_token, page_size=200, page_token=page_token)
            if not res.get("ok"):
                raise RuntimeError(f"list_files_failed: {res.get('error')}")
            files = res.get("files", [])
            if isinstance(files, list):
                items.extend(item for item in files if isinstance(item, dict))
            next_page_token = res.get("next_page_token")
            page_token = str(next_page_token) if next_page_token is not None else None
            if not page_token:
                break
        return items

    def create_folder(self, name: str, folder_token: str | None) -> str:
        headers, _ = self._auth_headers()
        parent = folder_token or self.get_root_folder_token()
        res = requests.post(
            f"{BASE}/drive/v1/files/create_folder",
            json={"name": name, "folder_token": parent},
            headers=headers,
            timeout=self.timeout,
        )
        payload_raw = res.json()
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        data = self._check_data(payload)
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("create_folder_no_token")
        return token

    def upload_file(self, local_path: str, folder_token: str | None, file_name: str | None = None) -> dict[str, Any]:
        path = Path(local_path)
        if not path.exists() or not path.is_file():
            raise RuntimeError(f"local_file_not_found: {local_path}")

        token, token_type = self.get_access_token()
        if not token:
            raise RuntimeError("no_token")

        parent = folder_token or self.get_root_folder_token()
        name = file_name or path.name

        headers = {"Authorization": f"Bearer {token}"}
        with path.open("rb") as fp:
            files = {"file": (name, fp, "application/octet-stream")}
            data = {
                "file_name": name,
                "parent_type": "explorer",
                "parent_node": parent,
                "size": str(path.stat().st_size),
            }
            res = requests.post(
                f"{BASE}/drive/v1/files/upload_all",
                headers=headers,
                data=data,
                files=files,
                timeout=self.timeout,
            )

        body_raw = res.json()
        body = body_raw if isinstance(body_raw, dict) else {}
        data = self._check_data(body)
        return {
            "token_type": token_type,
            "file_token": data.get("file_token") or data.get("token"),
            "revision_id": data.get("revision_id"),
        }

    def download_file(self, file_token: str, dest_path: str) -> None:
        headers, _ = self._auth_headers(content_type=None)
        url = f"{BASE}/drive/v1/files/{file_token}/download"
        with requests.get(url, headers=headers, timeout=self.timeout, stream=True, allow_redirects=True) as res:
            if res.status_code >= 400:
                raise RuntimeError(f"download_failed_status_{res.status_code}")
            path = Path(dest_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as fp:
                for chunk in res.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fp.write(chunk)

    def rename_file(self, file_token: str, new_name: str) -> None:
        headers, _ = self._auth_headers()
        res = requests.patch(
            f"{BASE}/drive/v1/files/{file_token}",
            json={"name": new_name},
            headers=headers,
            timeout=self.timeout,
        )
        text = (res.text or "").strip()
        if res.status_code == 404 and "page not found" in text.lower():
            raise RuntimeError("rename_endpoint_not_available_drive_v1")
        if res.status_code >= 400:
            raise RuntimeError(f"rename_failed_status_{res.status_code}: {text[:200]}")
        try:
            payload = res.json()
        except Exception:
            # Some gateways return empty/boolean text on success.
            if text in {"", "true", "null"}:
                return
            raise RuntimeError(f"rename_failed_non_json_response: {text[:200]}")
        self._check_data(payload)

    def move_file(self, file_token: str, file_type: str, folder_token: str | None) -> None:
        headers, _ = self._auth_headers()
        target = folder_token or self.get_root_folder_token()
        res = requests.post(
            f"{BASE}/drive/v1/files/{file_token}/move",
            json={"type": file_type or "file", "folder_token": target},
            headers=headers,
            timeout=self.timeout,
        )
        self._check_data(res.json())

    def delete_file(self, file_token: str, file_type: str) -> None:
        headers, _ = self._auth_headers()
        res = requests.delete(
            f"{BASE}/drive/v1/files/{file_token}",
            params={"type": file_type or "file"},
            headers=headers,
            timeout=self.timeout,
        )
        self._check_data(res.json())

    def get_file_meta(self, file_token: str) -> dict[str, Any]:
        headers, _ = self._auth_headers()
        res = requests.get(f"{BASE}/drive/v1/metas/{file_token}", headers=headers, timeout=self.timeout)
        payload_raw = res.json()
        payload = payload_raw if isinstance(payload_raw, dict) else {}
        data = self._check_data(payload)
        if "file" in data and isinstance(data["file"], dict):
            return dict(data["file"])
        return data
