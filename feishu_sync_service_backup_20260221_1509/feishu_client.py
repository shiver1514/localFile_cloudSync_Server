import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

BASE = "https://open.feishu.cn/open-apis"


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, user_token_file: str, timeout: int = 30):
        self.app_id = app_id or ""
        self.app_secret = app_secret or ""
        self.user_token_file = user_token_file or ""
        self.timeout = timeout

    def _load_user_tokens(self):
        if not self.user_token_file:
            return None
        p = Path(self.user_token_file)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def _save_user_tokens(self, data: dict):
        if not self.user_token_file:
            return
        p = Path(self.user_token_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _user_access_token(self):
        tokens = self._load_user_tokens()
        if not tokens:
            return None

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        created = int(tokens.get("created_at", 0))
        expires_in = int(tokens.get("expires_in", 7200))

        if not access_token:
            return None

        expire_at = created + max(expires_in - 300, 300) * 1000
        if created and int(time.time() * 1000) < expire_at:
            return access_token

        if not refresh_token or not self.app_id or not self.app_secret:
            return None

        res = requests.post(
            f"{BASE}/authen/v1/refresh_access_token",
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            },
            timeout=self.timeout,
        )
        data = res.json()
        if data.get("code") != 0:
            return None

        refreshed = data.get("data", {})
        refreshed["created_at"] = int(time.time() * 1000)
        self._save_user_tokens(refreshed)
        return refreshed.get("access_token")

    def _tenant_access_token(self):
        if not self.app_id or not self.app_secret:
            return None
        res = requests.post(
            f"{BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=self.timeout,
        )
        data = res.json()
        if data.get("code") != 0:
            return None
        return data.get("tenant_access_token")

    def get_access_token(self, priority=("user", "tenant")) -> Tuple[Optional[str], Optional[str]]:
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

    def _auth_headers(self, content_type: Optional[str] = "application/json"):
        token, token_type = self.get_access_token()
        if not token:
            raise RuntimeError("no_token")
        headers = {"Authorization": f"Bearer {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers, token_type

    def _check_data(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise RuntimeError("invalid_response")
        if payload.get("code", 0) != 0:
            raise RuntimeError(f"feishu_error: code={payload.get('code')} msg={payload.get('msg')}")
        return payload.get("data", {}) or {}

    def get_root_folder_token(self) -> str:
        headers, _ = self._auth_headers()
        res = requests.get(f"{BASE}/drive/explorer/v2/root_folder/meta", headers=headers, timeout=self.timeout)
        data = self._check_data(res.json())
        token = data.get("token")
        if not token:
            raise RuntimeError("root_folder_token_missing")
        return token

    def list_files(self, folder_token: Optional[str], page_size: int = 200, page_token: Optional[str] = None) -> Dict:
        headers, token_type = self._auth_headers()
        params = {"page_size": page_size}
        if folder_token:
            params["folder_token"] = folder_token
        if page_token:
            params["page_token"] = page_token

        res = requests.get(f"{BASE}/drive/v1/files", params=params, headers=headers, timeout=self.timeout)
        body = res.json()
        if body.get("code", 0) != 0:
            return {"ok": False, "token_type": token_type, "error": body}
        data = body.get("data", {}) or {}
        return {
            "ok": True,
            "token_type": token_type,
            "files": data.get("files", []) or [],
            "next_page_token": data.get("next_page_token") or data.get("page_token"),
        }

    def list_folder_once(self, folder_token: Optional[str]) -> List[dict]:
        page_token = None
        items: List[dict] = []
        while True:
            res = self.list_files(folder_token=folder_token, page_size=200, page_token=page_token)
            if not res.get("ok"):
                raise RuntimeError(f"list_files_failed: {res.get('error')}")
            items.extend(res.get("files", []))
            page_token = res.get("next_page_token")
            if not page_token:
                break
        return items

    def create_folder(self, name: str, folder_token: Optional[str]) -> str:
        headers, _ = self._auth_headers()
        parent = folder_token or self.get_root_folder_token()
        res = requests.post(
            f"{BASE}/drive/v1/files/create_folder",
            json={"name": name, "folder_token": parent},
            headers=headers,
            timeout=self.timeout,
        )
        data = self._check_data(res.json())
        token = data.get("token")
        if not token:
            raise RuntimeError("create_folder_no_token")
        return token

    def upload_file(self, local_path: str, folder_token: Optional[str], file_name: Optional[str] = None) -> dict:
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

        body = res.json()
        data = self._check_data(body)
        return {
            "token_type": token_type,
            "file_token": data.get("file_token") or data.get("token"),
            "revision_id": data.get("revision_id"),
        }

    def download_file(self, file_token: str, dest_path: str):
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

    def rename_file(self, file_token: str, new_name: str):
        headers, _ = self._auth_headers()
        res = requests.patch(
            f"{BASE}/drive/v1/files/{file_token}",
            json={"name": new_name},
            headers=headers,
            timeout=self.timeout,
        )
        self._check_data(res.json())

    def move_file(self, file_token: str, file_type: str, folder_token: Optional[str]):
        headers, _ = self._auth_headers()
        target = folder_token or self.get_root_folder_token()
        res = requests.post(
            f"{BASE}/drive/v1/files/{file_token}/move",
            json={"type": file_type or "file", "folder_token": target},
            headers=headers,
            timeout=self.timeout,
        )
        self._check_data(res.json())

    def delete_file(self, file_token: str, file_type: str):
        headers, _ = self._auth_headers()
        res = requests.delete(
            f"{BASE}/drive/v1/files/{file_token}",
            params={"type": file_type or "file"},
            headers=headers,
            timeout=self.timeout,
        )
        self._check_data(res.json())

    def get_file_meta(self, file_token: str) -> dict:
        headers, _ = self._auth_headers()
        res = requests.get(f"{BASE}/drive/v1/files/{file_token}", headers=headers, timeout=self.timeout)
        data = self._check_data(res.json())
        if "file" in data and isinstance(data["file"], dict):
            return data["file"]
        return data
