#!/bin/bash
# sync-skills.sh - Sync CLI scripts to snow-bin-skills repo

SKILLS_REPO="${SKILLS_REPO:-$HOME/git/kameshsampath/snow-utils-skills}"

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
echo ""
echo "Next steps:"
echo "  cd $SKILLS_REPO"
echo "  git diff"
echo "  git add -A && git commit -m 'Sync scripts from snow-bin-utils'"
echo "  git push"
