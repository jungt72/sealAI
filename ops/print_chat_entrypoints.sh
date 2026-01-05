#!/usr/bin/env bash
set -euo pipefail

rg -n --hidden --follow "ChatScreen|ChatContainer|DashboardClient" frontend/src/app -S
rg -n --hidden --follow "app/chat|app/dashboard" frontend/src/app -S
rg -n --hidden --follow "useChatSseV2|/api/chat" frontend/src -S
