#!/usr/bin/env python3
import argparse
import os
import sys
from typing import Dict, List

import requests
import yaml


def vprint(verbose: bool, *args, **kwargs):
    if verbose:
        print(*args, **kwargs)


def load_group_roles_yaml(url: str, verbose: bool = False) -> Dict:
    vprint(verbose, f"[HTTP] GET {url}")
    r = requests.get(url, timeout=10)
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    r.raise_for_status()
    return yaml.safe_load(r.text) or {}


def get_group(api_url: str, token: str, name: str, verbose: bool = False) -> Dict:
    headers = {"Authorization": f"token {token}"}
    url = f"{api_url}/groups/{name}"
    vprint(verbose, f"[HTTP] GET {url}")
    r = requests.get(url, headers=headers, timeout=10)
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def ensure_group(api_url: str, token: str, name: str, verbose: bool = False) -> None:
    headers = {"Authorization": f"token {token}"}
    url = f"{api_url}/groups/{name}"
    vprint(verbose, f"[HTTP] POST {url}")
    r = requests.post(url, headers=headers, timeout=10)
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    if r.status_code not in (201, 409):  # created or already exists
        r.raise_for_status()


def add_users_to_group(api_url: str, token: str, name: str, users: List[str], verbose: bool = False) -> None:
    if not users:
        return
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }
    url = f"{api_url}/groups/{name}/users"
    vprint(verbose, f"[HTTP] POST {url} users={users}")
    r = requests.post(
        url,
        headers=headers,
        json={"users": users},
        timeout=10,
    )
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    r.raise_for_status()


def remove_users_from_group(api_url: str, token: str, name: str, users: List[str], verbose: bool = False) -> None:
    if not users:
        return
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }
    url = f"{api_url}/groups/{name}/users"
    vprint(verbose, f"[HTTP] DELETE {url} users={users}")
    r = requests.delete(
        url,
        headers=headers,
        json={"users": users},
        timeout=10,
    )
    vprint(verbose, f"[HTTP] {r.status_code} {url}")
    r.raise_for_status()


def sync_membership(
    group_roles_url: str,
    api_url: str,
    token: str,
    prefix: str = "group-",
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    data = load_group_roles_yaml(group_roles_url, verbose=verbose)
    roles_cfg = data.get("roles", []) or []

    for r in roles_cfg:
        group_name = r.get("name")
        members = r.get("members", []) or []
        if not group_name or not group_name.startswith(prefix):
            continue

        desired_members = set(members)
        print(f"[SYNC] Group {group_name}: desired members = {sorted(desired_members)}")

        existing = get_group(api_url, token, group_name, verbose=verbose)
        if existing is None:
            print(f"[SYNC] Group {group_name} does not exist")
            existing_members = set()
            if dry_run:
                print(f"[DRY-RUN] Would create group {group_name}")
            else:
                print(f"[ACTION] Creating group {group_name}")
                ensure_group(api_url, token, group_name, verbose=verbose)
        else:
            existing_members = set(existing.get("users", []))
            print(f"[SYNC] Group {group_name}: existing members = {sorted(existing_members)}")

        to_add = sorted(desired_members - existing_members)
        to_remove = sorted(existing_members - desired_members)

        if dry_run:
            if to_add:
                print(f"[DRY-RUN] Would add to {group_name}: {to_add}")
            if to_remove:
                print(f"[DRY-RUN] Would remove from {group_name}: {to_remove}")
        else:
            if to_add:
                print(f"[ACTION] Adding to {group_name}: {to_add}")
                add_users_to_group(api_url, token, group_name, to_add, verbose=verbose)
            if to_remove:
                print(f"[ACTION] Removing from {group_name}: {to_remove}")
                remove_users_from_group(api_url, token, group_name, to_remove, verbose=verbose)


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser(
        description="Sync JupyterHub group membership from group-roles.yaml via the groups API."
    )
    p.add_argument(
        "--group-roles-url",
        required=True,
        help="URL to group-roles.yaml",
    )
    p.add_argument(
        "--api-url",
        required=True,
        help="JupyterHub base API URL, e.g. https://lobot.cs.queensu.ca/hub/api",
    )
    p.add_argument(
        "--token",
        help="JupyterHub API token. If omitted, uses JUPYTERHUB_API_TOKEN env var.",
    )
    p.add_argument(
        "--prefix",
        default="group-",
        help="Only sync groups whose role name starts with this prefix (default: group-)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't modify anything; just show what would be done",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose HTTP logging",
    )

    args = p.parse_args(argv)

    token = args.token or os.environ.get("JUPYTERHUB_API_TOKEN")
    if not token:
        print("ERROR: API token not provided. Use --token or set JUPYTERHUB_API_TOKEN.", file=sys.stderr)
        return 1

    api_url = args.api_url.rstrip("/")

    sync_membership(
        group_roles_url=args.group_roles_url,
        api_url=api_url,
        token=token,
        prefix=args.prefix,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
