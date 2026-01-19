#!/bin/bash
# Mental Models API cURL examples for documentation.

BANK_ID="my-agent"
BASE_URL="${HINDSIGHT_API_URL:-http://localhost:8080}"

# [docs:mm-set-mission]
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mission" \
  -H "Content-Type: application/json" \
  -d '{"mission": "Be a PM for the engineering team, tracking sprint progress and team capacity"}'
# [/docs:mm-set-mission]


# [docs:mm-list]
# List all
curl "$BASE_URL/v1/default/banks/my-agent/mental-models"

# Filter by subtype
curl "$BASE_URL/v1/default/banks/my-agent/mental-models?subtype=structural"

# Filter by tags
curl "$BASE_URL/v1/default/banks/my-agent/mental-models?tags=user_alice&tags_match=any"
# [/docs:mm-list]


# [docs:mm-get]
curl "$BASE_URL/v1/default/banks/my-agent/mental-models/alice"
# [/docs:mm-get]


# [docs:mm-create]
# Create pinned model
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Product Roadmap",
    "description": "Track product priorities and feature decisions",
    "tags": ["project_alpha"]
  }'

# Create directive
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Response Guidelines",
    "subtype": "directive",
    "tags": ["user_alice"],
    "observations": [
      {"title": "Always respond in French", "content": "All responses must be in French"}
    ]
  }'
# [/docs:mm-create]


# [docs:mm-delete]
curl -X DELETE "$BASE_URL/v1/default/banks/my-agent/mental-models/old-model"
# [/docs:mm-delete]


# [docs:mm-refresh]
# Refresh all
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models/refresh"

# Refresh only structural
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models/refresh" \
  -H "Content-Type: application/json" \
  -d '{"subtype": "structural"}'

# With tags
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models/refresh" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["user_alice"]}'
# [/docs:mm-refresh]


# [docs:mm-refresh-single]
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models/alice/refresh"
# [/docs:mm-refresh-single]


# [docs:mm-versions]
# List versions
curl "$BASE_URL/v1/default/banks/my-agent/mental-models/alice/versions"

# Get specific version
curl "$BASE_URL/v1/default/banks/my-agent/mental-models/alice/versions/2"
# [/docs:mm-versions]


# [docs:mm-tags-refresh]
curl -X POST "$BASE_URL/v1/default/banks/my-agent/mental-models/refresh" \
  -H "Content-Type: application/json" \
  -d '{"tags": ["user_alice"]}'
# [/docs:mm-tags-refresh]


# [docs:mm-tags-filter]
# Filter by tags
curl "$BASE_URL/v1/default/banks/my-agent/mental-models?tags=user_alice&tags_match=any"

# Multiple tags with all match
curl "$BASE_URL/v1/default/banks/my-agent/mental-models?tags=user_alice,project_alpha&tags_match=all"
# [/docs:mm-tags-filter]
