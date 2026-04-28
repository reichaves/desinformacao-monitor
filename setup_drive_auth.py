"""
One-time setup script to obtain Google Drive OAuth 2.0 refresh token.

Run this script ONCE on your local machine to generate the credentials
needed for automated (headless) Drive uploads in GitHub Actions.

Usage:
    python setup_drive_auth.py

Prerequisites:
    1. Create an OAuth 2.0 "Desktop app" credential in Google Cloud Console
       (APIs & Services → Credentials → Create credentials → OAuth client ID → Desktop app)
    2. Set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET as env vars,
       OR enter them when prompted.

Output:
    Prints the three values to add as GitHub secrets:
        GOOGLE_DRIVE_CLIENT_ID
        GOOGLE_DRIVE_CLIENT_SECRET
        GOOGLE_DRIVE_REFRESH_TOKEN

Author: Abraji / reichaves
Date: 2026-04-28
Dependencies: google-auth-oauthlib
"""

import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Installing google-auth-oauthlib...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "google-auth-oauthlib"], check=True)
    from google_auth_oauthlib.flow import InstalledAppFlow

_SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    """Run the interactive OAuth flow and print the resulting credentials."""
    print("=" * 60)
    print("Google Drive OAuth Setup — Monitor de Desinformação")
    print("=" * 60)
    print()

    # Get credentials from env or prompt
    client_id = os.environ.get("GOOGLE_DRIVE_CLIENT_ID") or input(
        "Cole seu GOOGLE_DRIVE_CLIENT_ID (do Google Cloud Console): "
    ).strip()

    client_secret = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET") or input(
        "Cole seu GOOGLE_DRIVE_CLIENT_SECRET: "
    ).strip()

    if not client_id or not client_secret:
        print("\nERRO: client_id e client_secret são obrigatórios.")
        sys.exit(1)

    # Build client config dict (same format as downloaded JSON)
    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        }
    }

    print()
    print("Abrindo o navegador para autenticação Google...")
    print("Faça login com a conta que TEM a pasta do Drive.")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, scopes=_SCOPES)

    # Try localhost first; fall back to out-of-band if port is busy
    try:
        credentials = flow.run_local_server(port=0, prompt="consent")
    except Exception:
        credentials = flow.run_console()

    refresh_token = credentials.refresh_token
    if not refresh_token:
        print("\nERRO: Não foi possível obter o refresh token.")
        print("Tente novamente e certifique-se de clicar em 'Permitir'.")
        sys.exit(1)

    print()
    print("=" * 60)
    print("SUCESSO! Adicione os seguintes valores como GitHub Secrets:")
    print("=" * 60)
    print()
    print(f"GOOGLE_DRIVE_CLIENT_ID")
    print(f"  {client_id}")
    print()
    print(f"GOOGLE_DRIVE_CLIENT_SECRET")
    print(f"  {client_secret}")
    print()
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN")
    print(f"  {refresh_token}")
    print()
    print("Comandos gh CLI para adicionar direto ao GitHub:")
    print()
    print(f'gh secret set GOOGLE_DRIVE_CLIENT_ID --body "{client_id}" --repo reichaves/desinformacao-monitor')
    print(f'gh secret set GOOGLE_DRIVE_CLIENT_SECRET --body "{client_secret}" --repo reichaves/desinformacao-monitor')
    print(f'gh secret set GOOGLE_DRIVE_REFRESH_TOKEN --body "{refresh_token}" --repo reichaves/desinformacao-monitor')
    print()
    print("IMPORTANTE: Guarde o refresh token em local seguro.")
    print("NÃO commite esses valores no repositório.")


if __name__ == "__main__":
    main()
