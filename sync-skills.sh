#!/bin/bash
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
cp extvolume.py "$SKILLS_REPO/iceberg-external-volume/scripts/"
cp snow_common.py "$SKILLS_REPO/iceberg-external-volume/scripts/"

# Sync pat
cp pat.py "$SKILLS_REPO/snowflake-pat/scripts/"
cp snow_common.py "$SKILLS_REPO/snowflake-pat/scripts/"

echo "✓ Scripts synced"

# Reload skills if --reload flag is passed
if [ "$1" = "--reload" ]; then
    echo ""
    echo "Clearing CoCo cache..."
    rm -rf "$CORTEX_CONFIG/cache" 2>/dev/null
    echo "✓ Cache cleared"
    
    echo ""
    echo "Reloading skills..."
    cortex skill remove "$SKILLS_REPO/iceberg-external-volume" 2>/dev/null
    cortex skill remove "$SKILLS_REPO/snowflake-pat" 2>/dev/null
    cortex skill add "$SKILLS_REPO/iceberg-external-volume"
    cortex skill add "$SKILLS_REPO/snowflake-pat"
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
