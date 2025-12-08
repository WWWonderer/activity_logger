import io
import hashlib
from pathlib import Path
from typing import List, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from .config import SyncConfig, load_config
from .state import SyncState


class DriveSyncClient:
    def __init__(self, config: SyncConfig, log_dir: Path | str):
        self.config = config
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._service = None
        self.state = SyncState()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def upload_file(self, local_path: Path | str) -> None:
        """Create or update the remote copy of the given file."""
        local_path = Path(local_path)
        if not local_path.exists():
            return

        service = self._drive_service()
        remote_name = local_path.name
        media = MediaFileUpload(
            local_path.as_posix(),
            mimetype="application/octet-stream",
            resumable=True,
        )
        file_id = self._find_file_id(remote_name)
        metadata = {"name": remote_name, "parents": [self.config.folder_id]}

        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            service.files().create(body=metadata, media_body=media, fields="id").execute()

    def pull_remote_logs(self) -> List[Path]:
        """Download remote files that we do not have locally or that changed."""
        service = self._drive_service()
        files = self._list_remote_files(service)
        updated_paths: List[Path] = []

        for file_meta in files:
            file_id = file_meta["id"]
            file_name = file_meta["name"]
            remote_md5 = file_meta.get("md5Checksum")
            dest_path = self.log_dir / file_name

            if not self._should_download(file_id, remote_md5, dest_path):
                continue

            self._download_file(service, file_id, dest_path)
            self.state.update(file_id, {"md5": remote_md5, "name": file_name})
            updated_paths.append(dest_path)

        return updated_paths

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _drive_service(self):
        if self._service:
            return self._service
        creds = self._load_credentials()
        self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
        return self._service

    def _load_credentials(self) -> Credentials:
        token_path = self.config.token_path
        creds: Optional[Credentials] = None
        token_path.parent.mkdir(parents=True, exist_ok=True)
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(
                token_path.as_posix(), scopes=self.config.scopes
            )

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    token_path.write_text(creds.to_json(), encoding="utf-8")
                    return creds
                except RefreshError:
                    # Refresh token revoked/expired: drop it and re-auth.
                    print("[Drive Sync] Token revoked/expired; removing and reauthorizing.")
                    token_path.unlink(missing_ok=True)
                    creds = None
                except Exception as exc:
                    print(f"[Drive Sync] Token refresh failed: {exc}")
                    token_path.unlink(missing_ok=True)
                    creds = None

            flow = InstalledAppFlow.from_client_secrets_file(
                self.config.credentials_path.as_posix(),
                scopes=self.config.scopes,
            )
            creds = flow.run_local_server(port=0)
            token_path.write_text(creds.to_json(), encoding="utf-8")

        return creds

    def _find_file_id(self, name: str) -> Optional[str]:
        service = self._drive_service()
        query = (
            f"name = '{name}' and '{self.config.folder_id}' in parents and trashed = false"
        )
        response = service.files().list(
            q=query, spaces="drive", fields="files(id,name)", pageSize=1
        ).execute()
        files = response.get("files", [])
        if files:
            return files[0]["id"]
        return None

    def _list_remote_files(self, service) -> List[dict]:
        query = f"'{self.config.folder_id}' in parents and trashed = false"
        page_token = None
        results: List[dict] = []

        while True:
            response = service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, md5Checksum, modifiedTime)",
                pageSize=100,
                pageToken=page_token,
            ).execute()
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return results

    def _should_download(self, file_id: str, remote_md5: str | None, dest_path: Path) -> bool:
        state_entry = self.state.get(file_id)
        if state_entry and state_entry.get("md5") == remote_md5 and dest_path.exists():
            return False
        if remote_md5 and dest_path.exists():
            if _md5(dest_path) == remote_md5:
                return False
        return True

    def _download_file(self, service, file_id: str, dest_path: Path) -> None:
        request = service.files().get_media(fileId=file_id)
        fh = io.FileIO(dest_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def _md5(path: Path) -> str:
    hash_md5 = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_drive_sync_client(log_dir: Path | str):
    try:
        config = load_config()
    except FileNotFoundError:
        print("[Drive Sync] config.json not found under sync/. Skipping sync.")
        return None
    except ValueError as exc:
        print(f"[Drive Sync] Invalid config: {exc}")
        return None

    try:
        return DriveSyncClient(config, log_dir=log_dir)
    except Exception as exc:
        print(f"[Drive Sync] Unable to initialise Drive client: {exc}")
        return None
