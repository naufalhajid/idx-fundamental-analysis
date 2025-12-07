#!/usr/bin/env bash

nvm use

cd "$(dirname "$0")/app/ui" || exit 1

bun install

bun run dev --open
