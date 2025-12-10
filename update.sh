#!/bin/sh

BRANCH=$(git config -f .gitmodules submodule.src/core.branch)
cd src/core && git checkout $BRANCH && git pull && cd ../..
git add src/core
git commit -m "General: Update submodule corePY" || echo "No changes to commit"
git push
