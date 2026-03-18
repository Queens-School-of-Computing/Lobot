#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List

import requests
import yaml

GROUP_ROLES_URL_DEFAULT = (
    "https://raw.githubusercontent.com/Queens-School-of-Computing/Lobot/newcluster/group-roles.yaml"
)


def vprint(verbose: bool, *args, **kwargs):
    if verbose:
        print(*args, **kwargs)


def load_group_roles(url: str, verbose: bool = False) -> Dict:
    vprint(verbose, f"[HTTP] GET {url}")
    resp = requests.get(url, timeout=10)
    vprint(verbose, f"[HTTP] {resp.status_code} {url}")
    resp.raise_for_status()
    data = yaml.safe_load(resp.text) or {}
    return data


def user_exists(api_url: str, token: str, name: str, verbose: bool = False) -> bool:
    headers = {"Authorization": f"token {token}"}
    url = f"{api_url}/users/{name}"
    vprint(verbose, f"[HTTP] GET {url}")
    r = requests.get(url, headers=headers, timeout=10)
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    if r.status_code == 200:
        return True
    if r.status_code == 404:
        return False
    # Any other error is unexpected
    r.raise_for_status()
    return False  # unreachable


def create_user(api_url: str, token: str, name: str, verbose: bool = False) -> None:
    """
    Create a single Hub user via API (no admin flag).
    """
    headers = {"Authorization": f"token {token}"}
    url = f"{api_url}/users/{name}"
    vprint(verbose, f"[HTTP] POST {url}")
    r = requests.post(url, headers=headers, timeout=10)
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    if r.status_code not in (201, 409):
        # 201 = created, 409 = already exists (race)
        r.raise_for_status()


def ensure_group_users(
    api_url: str,
    token: str,
    group_roles_url: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> List[str]:
    """
    Ensure that each 'user' entry in group-roles.yaml exists as a Hub user.

    Returns a list of created usernames.
    """
    data = load_group_roles(group_roles_url, verbose=verbose)
    roles_cfg = data.get("roles", []) or []

    created: List[str] = []

    for r in roles_cfg:
        group_user = r.get("user")
        if not group_user:
            continue

        vprint(verbose, f"[CHECK] Ensuring group user '{group_user}' exists")

        if user_exists(api_url, token, group_user, verbose=verbose):
            print(f"[INFO] Group user {group_user} already exists")
            continue

        print(f"[INFO] Group user {group_user} does not exist")
        if dry_run:
            print(f"[DRY-RUN] Would create user {group_user}")
            continue

        print(f"[ACTION] Creating group user {group_user}")
        create_user(api_url, token, group_user, verbose=verbose)
        created.append(group_user)

    return created


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(
        description="Ensure group/collab users from group-roles.yaml exist in JupyterHub"
    )
    p.add_argument(
        "--api-url",
        required=True,
        help="JupyterHub base API URL, e.g. https://lobot.cs.queensu.ca/hub/api",
    )
    p.add_argument(
        "--token",
        help="Admin API token. If omitted, uses JUPYTERHUB_API_TOKEN env var.",
    )
    p.add_argument(
        "--group-roles-url",
        default=GROUP_ROLES_URL_DEFAULT,
        help=f"URL to group-roles.yaml (default: {GROUP_ROLES_URL_DEFAULT})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't create anything; just report what would be done",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging of HTTP requests and checks",
    )
    args = p.parse_args(argv)

    token = args.token or os.environ.get("JUPYTERHUB_API_TOKEN")
    if not token:
        print(
            "ERROR: API token not provided. Use --token or set JUPYTERHUB_API_TOKEN.",
            file=sys.stderr,
        )
        return 1

    api_url = args.api_url.rstrip("/")

    created = ensure_group_users(
        api_url=api_url,
        token=token,
        group_roles_url=args.group_roles_url,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print(f"[SUMMARY] Created users: {created}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
