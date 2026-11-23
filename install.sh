#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf 'Usage: %s [--codex] [--t3] [--with-hooks] [--with-heavy] [--dry-run]\n' "$0"
}

with_codex=false
with_heavy=false
with_hooks=false
with_t3=false
dry_run=false
for argument in "$@"; do
  case "$argument" in
    --codex) with_codex=true ;;
    --with-heavy) with_heavy=true ;;
    --with-hooks) with_hooks=true ;;
    --t3) with_t3=true; with_codex=true; with_hooks=true ;;
    --dry-run) dry_run=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; printf 'Unknown option: %s\n' "$argument" >&2; exit 2 ;;
  esac
done

# Resolve script links without GNU-only readlink options.
source_path=${BASH_SOURCE[0]}
while [[ -L "$source_path" ]]; do
  source_dir=$(cd -P "$(dirname "$source_path")" && pwd)
  source_path=$(readlink "$source_path")
  [[ "$source_path" == /* ]] || source_path="$source_dir/$source_path"
done
repo_dir=$(cd -P "$(dirname "$source_path")" && pwd)

case "${HOME:-}" in
  /*) ;;
  *) printf 'HOME must be an absolute path.\n' >&2; exit 1 ;;
esac
home_dir=${HOME%/}
[[ -n "$home_dir" ]] || home_dir=/
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required.\n' >&2
  exit 1
fi

sources=()
destinations=()
add_mapping() {
  sources+=("$repo_dir/$1")
  destinations+=("$home_dir/$2")
}

add_mapping instructions/CLAUDE.md .claude/CLAUDE.md
for agent in scout worker designer advisor reviewer; do
  add_mapping "agents/$agent.md" ".claude/agents/$agent.md"
done

shopt -s nullglob
skill_files=("$repo_dir"/skills/*/SKILL.md)
if [[ ${#skill_files[@]} -eq 0 ]]; then
  printf 'No skills found in %s/skills.\n' "$repo_dir" >&2
  exit 1
fi
for skill_file in "${skill_files[@]}"; do
  skill_dir=${skill_file%/SKILL.md}
  skill_name=${skill_dir##*/}
  add_mapping "skills/$skill_name" ".claude/skills/$skill_name"
  if $with_codex; then
    add_mapping "skills/$skill_name" ".agents/skills/$skill_name"
  fi
done
if $with_codex; then
  add_mapping instructions/CLAUDE.md .codex/AGENTS.md
fi
if $with_heavy; then
  add_mapping bin/heavy .local/bin/heavy
fi
if $with_t3; then
  add_mapping instructions/CLAUDE.md .t3/codex-home/AGENTS.md
fi
if $with_hooks; then
  for hook in background_job_guard.py orchestration_mode.py signin_handoff_check.py; do
    add_mapping "hooks/$hook" ".claude/hooks/$hook"
  done
  # Configuration is merged, not symlinked over an existing settings file.
  sources+=("$repo_dir/hooks/install_hooks.py" "$repo_dir/hooks/codex-hooks.json")
fi

# Validate every selected source and destination parent before changing HOME.
for source_item in "${sources[@]}"; do
  if [[ ! -e "$source_item" ]]; then
    printf 'Missing repo item: %s\n' "$source_item" >&2
    exit 1
  fi
done
for destination in "${destinations[@]}"; do
  parent=$(dirname "$destination")
  while :; do
    if [[ -L "$parent" ]]; then
      printf 'Refusing destination parent symlink: %s\n' "$parent" >&2
      exit 1
    fi
    if [[ -e "$parent" && ! -d "$parent" ]]; then
      printf 'Destination parent is not a directory: %s\n' "$parent" >&2
      exit 1
    fi
    [[ "$parent" != "$home_dir" && "$parent" != / ]] || break
    parent=$(dirname "$parent")
  done
done

# Validate all JSON and configuration parents before creating any links.
hook_flags=(--home "$home_dir" --repo "$repo_dir")
if $with_hooks; then
  $with_codex && hook_flags+=(--codex)
  $with_t3 && hook_flags+=(--t3)
  python3 "$repo_dir/hooks/install_hooks.py" "${hook_flags[@]}" --validate
fi

# os.replace replaces a destination symlink itself, including directory links.
move_item() {
  python3 -c 'import os, sys; os.replace(sys.argv[1], sys.argv[2])' "$1" "$2"
}

link_item() {
  local path=$1 target=$2 backup='' stamp counter=0 staging

  if [[ -L "$path" && "$(readlink "$path")" == "$target" ]]; then
    printf 'ok %s\n' "$path"
    return
  fi
  if $dry_run; then
    if [[ -e "$path" && ! -L "$path" ]]; then
      printf 'would back up %s to %s.bak-<UTC stamp>\n' "$path" "$path"
    fi
    printf 'would link %s -> %s\n' "$path" "$target"
    return
  fi

  mkdir -p "$(dirname "$path")"
  if [[ -e "$path" && ! -L "$path" ]]; then
    stamp=$(date -u +%Y%m%d-%H%M%S)
    backup="$path.bak-$stamp"
    while [[ -e "$backup" || -L "$backup" ]]; do
      counter=$((counter + 1))
      backup="$path.bak-$stamp-$counter"
    done
    move_item "$path" "$backup"
  fi

  staging=$(mktemp -d "${path}.link-XXXXXX") || {
    [[ -z "$backup" ]] || move_item "$backup" "$path"
    return 1
  }
  if ! ln -s "$target" "$staging/link" || ! move_item "$staging/link" "$path"; then
    rm -f "$staging/link"
    rmdir "$staging"
    [[ -z "$backup" ]] || move_item "$backup" "$path"
    return 1
  fi
  rmdir "$staging"

  if [[ -n "$backup" ]]; then
    printf 'linked %s (backup: %s)\n' "$path" "$backup"
  else
    printf 'linked %s\n' "$path"
  fi
}

for ((index = 0; index < ${#destinations[@]}; index++)); do
  link_item "${destinations[$index]}" "${sources[$index]}"
done
if $with_hooks; then
  $dry_run && hook_flags+=(--dry-run)
  python3 "$repo_dir/hooks/install_hooks.py" "${hook_flags[@]}"
fi
