"""Refresh once per workflow and persist the result without logging secrets."""
import os
import subprocess
import requests


def main():
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("IG_ACCESS_TOKEN repository secret is missing")
    try:
        response = requests.get("https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
        data = response.json()
    except (requests.RequestException, ValueError):
        print("Token refresh unavailable; publishing will validate the current token.")
        return
    if response.status_code != 200 or "access_token" not in data:
        print("Token was not refreshed; continuing with the current token.")
        return
    refreshed = data["access_token"]
    print(f"::add-mask::{refreshed}")
    with open(os.environ["GITHUB_ENV"], "a", encoding="utf-8") as env:
        env.write(f"IG_ACCESS_TOKEN={refreshed}\n")
    if refreshed == token:
        print("Existing token refreshed; the repository secret already contains the returned value.")
    elif os.environ.get("GH_TOKEN"):
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
            input=refreshed, text=True, check=True)
        print("Refreshed token saved to repository secret.")
    else:
        print("::warning::GH_PAT is missing. Refreshed token is available only for this run; repository secret was not updated.")


if __name__ == "__main__":
    main()
