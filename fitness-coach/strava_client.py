#!/usr/bin/env python3
"""
Strava API client for fetching athlete activities.
"""
import requests
import json
import webbrowser
from datetime import datetime
from typing import List, Dict, Optional
import time

class StravaClient:
    """Client for interacting with Strava API."""

    AUTH_URL = "https://www.strava.com/oauth/authorize"
    TOKEN_URL = "https://www.strava.com/oauth/token"
    API_BASE = "https://www.strava.com/api/v3"

    def __init__(self, client_id: str, client_secret: str, access_token: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    def get_authorization_url(self, redirect_uri: str = "http://localhost:8000") -> str:
        """
        Generate the OAuth authorization URL.

        Args:
            redirect_uri: Where Strava will redirect after authorization

        Returns:
            Authorization URL to visit
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "read,activity:read_all"
        }

        query = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}?{query}"

    def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response with access_token and refresh_token
        """
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }

        response = requests.post(self.TOKEN_URL, data=payload)
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        return data

    def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh an expired access token.

        Args:
            refresh_token: Refresh token from previous authentication

        Returns:
            New token response
        """
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        response = requests.post(self.TOKEN_URL, data=payload)
        response.raise_for_status()

        data = response.json()
        self.access_token = data["access_token"]
        return data

    def get_athlete(self) -> Dict:
        """Get the authenticated athlete's profile."""
        return self._request("GET", "/athlete")

    def get_activities(
        self,
        before: Optional[int] = None,
        after: Optional[int] = None,
        page: int = 1,
        per_page: int = 30
    ) -> List[Dict]:
        """
        Get athlete's activities.

        Args:
            before: Timestamp to retrieve activities before
            after: Timestamp to retrieve activities after
            page: Page number
            per_page: Number of activities per page (max 200)

        Returns:
            List of activity dictionaries
        """
        params = {
            "page": page,
            "per_page": per_page
        }

        if before:
            params["before"] = before
        if after:
            params["after"] = after

        return self._request("GET", "/athlete/activities", params=params)

    def get_all_activities(
        self,
        after: Optional[datetime] = None,
        progress_callback=None
    ) -> List[Dict]:
        """
        Fetch all activities with pagination.

        Args:
            after: Only get activities after this date
            progress_callback: Function to call with progress updates

        Returns:
            List of all activities
        """
        all_activities = []
        page = 1
        per_page = 200  # Max allowed by Strava

        # Convert datetime to timestamp if provided
        after_timestamp = int(after.timestamp()) if after else None

        while True:
            if progress_callback:
                progress_callback(f"Fetching page {page}...")

            activities = self.get_activities(
                after=after_timestamp,
                page=page,
                per_page=per_page
            )

            if not activities:
                break

            all_activities.extend(activities)

            if progress_callback:
                progress_callback(f"Fetched {len(all_activities)} activities so far...")

            # Rate limiting: Strava allows 100 requests per 15 minutes
            if len(activities) < per_page:
                break

            page += 1
            time.sleep(0.5)  # Be nice to the API

        return all_activities

    def _request(self, method: str, endpoint: str, params=None, data=None) -> Dict:
        """
        Make an authenticated request to the Strava API.

        Args:
            method: HTTP method
            endpoint: API endpoint (e.g., '/athlete')
            params: Query parameters
            data: Request body

        Returns:
            JSON response
        """
        if not self.access_token:
            raise ValueError("No access token. Please authenticate first.")

        url = f"{self.API_BASE}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        response = requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=data
        )

        response.raise_for_status()
        return response.json()


def save_tokens(tokens: Dict, filename: str = ".strava_tokens.json"):
    """Save Strava tokens to a file."""
    with open(filename, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"✅ Tokens saved to {filename}")


def load_tokens(filename: str = ".strava_tokens.json") -> Optional[Dict]:
    """Load Strava tokens from a file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def authenticate_strava(client_id: str, client_secret: str) -> StravaClient:
    """
    Interactive Strava authentication flow.

    Args:
        client_id: Strava application client ID
        client_secret: Strava application client secret

    Returns:
        Authenticated StravaClient
    """
    # Try to load existing tokens
    tokens = load_tokens()

    if tokens and "access_token" in tokens:
        print("✅ Found existing Strava tokens")
        client = StravaClient(client_id, client_secret, tokens["access_token"])

        # Check if token is still valid by trying to get athlete
        try:
            athlete = client.get_athlete()
            print(f"✅ Authenticated as {athlete['firstname']} {athlete['lastname']}")
            return client
        except:
            print("⚠️  Token expired, refreshing...")
            if "refresh_token" in tokens:
                new_tokens = client.refresh_access_token(tokens["refresh_token"])
                save_tokens(new_tokens)
                # Fetch athlete info with the new token
                athlete = client.get_athlete()
                print(f"✅ Authenticated as {athlete['firstname']} {athlete['lastname']}")
                return client

    # New authentication required
    print("\n🔐 Strava Authentication Required")
    print("=" * 50)

    client = StravaClient(client_id, client_secret)
    auth_url = client.get_authorization_url()

    print("\n1. Opening browser for Strava authorization...")
    print(f"   If it doesn't open, visit: {auth_url}\n")

    webbrowser.open(auth_url)

    print("2. After authorizing, you'll be redirected to a URL like:")
    print("   http://localhost:8000/?code=XXXXX&scope=...")
    print()

    redirect_url = input("3. Paste the full redirect URL here: ").strip()

    # Extract code from URL
    if "code=" in redirect_url:
        code = redirect_url.split("code=")[1].split("&")[0]

        print("\n4. Exchanging code for access token...")
        tokens = client.exchange_code_for_token(code)
        save_tokens(tokens)

        athlete = client.get_athlete()
        print(f"✅ Successfully authenticated as {athlete['firstname']} {athlete['lastname']}")

        return client
    else:
        raise ValueError("Could not extract authorization code from URL")
