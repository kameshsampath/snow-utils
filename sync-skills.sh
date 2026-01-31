#!/bin/bash
# Copyright 2026 Kamesh Sampath
# Generated with Cortex Code
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# sync-skills.sh - Sync CLI scripts to snow-utils-skills repo

SKILLS_REPO="${SKILLS_REPO:-$HOME/git/kameshsampath/snow-utils-skills}"
CORTEX_CONFIG="$HOME/.config/.snowflake/cortex"

if [ ! -d "$SKILLS_REPO" ]; then
    echo "Skills repo not found at $SKILLS_REPO"
    echo "Set SKILLS_REPO env var to the correct path"
    exit 1
fi

echo "Syncing scripts to $SKILLS_REPO..."

# Sync extvolume
cp extvolume.py "$SKILLS_REPO/snow-utils-volumes/scripts/"
cp snow_common.py "$SKILLS_REPO/snow-utils-volumes/scripts/"

# Sync pat (needs network.py and network_presets.py for imports)
cp pat.py "$SKILLS_REPO/snow-utils-pat/scripts/"
cp snow_common.py "$SKILLS_REPO/snow-utils-pat/scripts/"
cp network.py "$SKILLS_REPO/snow-utils-pat/scripts/"
cp network_presets.py "$SKILLS_REPO/snow-utils-pat/scripts/"

# Sync networks
cp network.py "$SKILLS_REPO/snow-utils-networks/scripts/"
cp network_presets.py "$SKILLS_REPO/snow-utils-networks/scripts/"
cp snow_common.py "$SKILLS_REPO/snow-utils-networks/scripts/"

echo "✓ Scripts synced"

# Reload skills if --reload flag is passed
if [ "$1" = "--reload" ]; then
    echo ""
    echo "Clearing CoCo cache..."
    rm -rf "$CORTEX_CONFIG/cache" 2>/dev/null
    echo "✓ Cache cleared"
    
    echo ""
    echo "Reloading skills..."
    cortex skill remove "$SKILLS_REPO/snow-utils-volumes" 2>/dev/null
    cortex skill remove "$SKILLS_REPO/snow-utils-pat" 2>/dev/null
    cortex skill remove "$SKILLS_REPO/snow-utils-networks" 2>/dev/null
    cortex skill add "$SKILLS_REPO/snow-utils-volumes"
    cortex skill add "$SKILLS_REPO/snow-utils-pat"
    cortex skill add "$SKILLS_REPO/snow-utils-networks"
    echo "✓ Skills reloaded"
    
    echo ""
    echo "⚠ Restart CoCo or start a new chat session for changes to take effect"
fi

echo ""
echo "Next steps:"
echo "  cd $SKILLS_REPO"
echo "  git diff"
echo "  git add -A && git commit -m 'Sync scripts from snow-bin-utils'"
echo "  git push"
if [ "$1" != "--reload" ]; then
    echo ""
    echo "To reload skills: ./sync-skills.sh --reload"
fi
