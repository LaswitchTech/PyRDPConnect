#!/bin/sh

cd src/core && git pull && cd ../..
git add src/core
git commit -m "General: Update submodule corePY" || echo "No changes to commit"
git push
