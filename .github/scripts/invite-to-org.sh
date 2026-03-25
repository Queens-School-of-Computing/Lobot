#!/usr/bin/env bash

if [[ $# -ne 2 ]]
then
  echo 'Usage .github/scripts/invite-to-org.sh <org_name> <user_id>'
  exit 1
fi

org_name="$1"
user_id="$2"

resp=$(
  gh api "/orgs/${org_name}/invitations" \
    -F "invitee_id=${user_id}" \
    -f role=direct_member
)

if [[ $? -ne 0 ]]
then
  error_message=$(echo $resp | jq -r '.errors[].message')
  if [[ "$error_message" = "Invitee is already a part of this organization" ]]
  then
    echo "$error_message"
    exit 0
  fi

  echo $resp | jq
  exit 1
fi
