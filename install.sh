#!/usr/bin/env bash
# Armored Turtle Automated Filament Changer
#
# Copyright (C) 2024-2025 Armored Turtle
#
# This file may be distributed under the terms of the GNU GPLv3 license.

printer_config=$HOME/printer_data/config
klipperscreen_dir=$HOME/KlipperScreen
klipperscreen_conf_file=$printer_config/KlipperScreen.conf
afc_klipperscreen_path=$HOME/AFC-Klipper-Screen-Add-On
test_mode=False
min_version="v0.4.5"

function show_help() {
  echo "Usage: $0 [-p <printer_config>] [-k <klipperscreen_dir>] [-h]"
  echo "Options:"
  echo "  -p <printer_config>    Path to the printer configuration directory (default: $HOME/printer_data/config)"
  echo "  -k <klipperscreen_dir> Path to the KlipperScreen directory (default: $HOME/KlipperScreen)"
  echo "  -h                     Show this help message"
}

function checkKlipperscreen() {
  if [ ! -d "$klipperscreen_dir/.git" ]; then
    echo "[ERROR] KlipperScreen repository not found at $klipperscreen_dir."
    exit 1
  fi

  git -C "$klipperscreen_dir" fetch --tags

  local current_version
  current_version=$(git -C "$klipperscreen_dir" describe --tags --abbrev=0)

  if [[ "$(printf '%s\n' "$min_version" "$current_version" | sort -V | head -n1)" != "$min_version" ]]; then
    echo "[ERROR] KlipperScreen version $current_version is lower than the required $min_version."
    echo "[ERROR] Please update KlipperScreen to at least version $min_version"
    exit 1
  fi

  echo "[INFO] KlipperScreen version $current_version meets the minimum requirement of $min_version."
}

function checks() {
  if [ "$EUID" -eq 0 ]; then
    echo "[WARNING] This script must not be run as root!"
    exit 1
  fi
  if [ "$(sudo systemctl list-units --full -all -t service --no-legend | grep -F 'KlipperScreen.service')" ]; then
    printf "[INFO] KlipperScreen service found! Continuing...\n\n"
  else
    echo "[ERROR] KlipperScreen service not found, please install KlipperScreen first!"
    exit 1
  fi
  if [ ! -d "$klipperscreen_dir" ]; then
    echo "[ERROR] KlipperScreen directory is not installed or detected in $klipperscreen_dir."
    exit 1
  fi
  checkKlipperscreen
  if [ ! -f "$printer_config"/KlipperScreen.conf ]; then
    echo "[ERROR] KlipperScreen.conf is missing. Expected path: $printer_config/KlipperScreen.conf."
    exit 1
  fi
}

function clone_repo() {
  local afc_klipperscreen afc_klipperscreen_base
  afc_klipperscreen="$(dirname "${afc_klipperscreen_path}")"
  afc_klipperscreen_base="$(basename "${afc_klipperscreen_path}")"

  if [ ! -d "$afc_klipperscreen_path/.git" ]; then
    echo "[INFO] AFC-Klipper-Screen-Add-On not found, cloning..."
    if git -C "$afc_klipperscreen" clone https://github.com/ArmoredTurtle/AFC-Klipper-Screen-Add-On.git "$afc_klipperscreen_base"; then
      echo "[INFO] AFC-Klipper-Screen-Add-On cloned successfully."
    else
      echo "[ERROR] Failed to clone AFC-Klipper-Screen-Add-On."
      exit 1
    fi
  else
    echo "[INFO] AFC-Klipper-Screen-Add-On already exists, checking for updates..."
    cd "$afc_klipperscreen_path" || exit 1

    # Fetch latest changes
    git fetch origin

    local local_hash remote_hash base_hash
    local_hash=$(git rev-parse HEAD)
    remote_hash=$(git rev-parse origin/main)
    base_hash=$(git merge-base HEAD origin/main)

    if [[ "$local_hash" == "$remote_hash" ]]; then
      echo "[INFO] AFC-Klipper-Screen-Add-On is up to date."
    elif [[ "$local_hash" == "$base_hash" ]]; then
      echo "[INFO] Updates found. Pulling latest changes..."
      git pull --ff-only
    else
      echo "[WARN] Local changes detected. Skipping pull to avoid overwriting."
    fi
  fi
}

function link_icons() {
  local styles_dir="$klipperscreen_dir/styles"
  local icons_dir="$afc_klipperscreen_path/KlipperScreen/afc_icons"
  local icon

  if [ ! -d "$styles_dir" ]; then
    echo "[ERROR] Theme directory not found: $styles_dir"
    return 1
  fi

  if [ ! -d "$icons_dir" ]; then
    echo "[ERROR] Icons directory not found: $icons_dir"
    return 1
  fi

  echo "[INFO] Linking icons to all themes in: $styles_dir"

  shopt -s nullglob
  for theme_dir in "$styles_dir"/*/; do
    local theme_images_dir="$theme_dir/images"
    mkdir -p "$theme_images_dir"

    echo "[INFO] Linking icons to theme: $(basename "$theme_dir")"
    for icon in "$icons_dir"/*.svg "$icons_dir"/*.png; do
      ln -sf "$icon" "$theme_images_dir/"
    done
  done
  shopt -u nullglob

  echo "[INFO] Icons linked to all themes."
}

function install_files() {
  local exclude_paths exclude_file

  if [ ! -L "$printer_config/AFC_menu.conf" ]; then
    ln -s "$afc_klipperscreen_path/KlipperScreen/AFC_menu.conf" "$printer_config/AFC_menu.conf"
  fi
  if [ ! -L "$klipperscreen_dir/panels/AFC.py" ]; then
    ln -s "$afc_klipperscreen_path/KlipperScreen/AFC.py" "$klipperscreen_dir/panels/AFC.py"
  fi
  if [ ! -d "$klipperscreen_dir/afc_icons" ]; then
    ln -s "$afc_klipperscreen_path/KlipperScreen/afc_icons" "$klipperscreen_dir/afc_icons"
  fi

  exclude_paths=(
    "panels/AFC.py"
    "**/afc_icons"
  )
  exclude_file="$klipperscreen_dir/.git/info/exclude"

  for path in "${exclude_paths[@]}"; do
    if ! grep -Fxq "$path" "$exclude_file"; then
      echo "$path" >> "$exclude_file"
    fi
  done
}

function ensure_afc_config() {
  local klipperscreen_conf_file="$1"
  local include_line="[include AFC_menu.conf]"

  local line_num
  line_num=$(grep -n '^#~#' "$klipperscreen_conf_file" | cut -d: -f1 | head -n1)
  local insert_before=${line_num:-999999}

  local tmp_file
  tmp_file=$(mktemp)
  local has_include=false

  grep -Fxq "$include_line" "$klipperscreen_conf_file" && has_include=true

  local i=1
  while IFS= read -r line; do
    if [[ $i -eq $insert_before && $has_include == false ]]; then
      echo "$include_line" >> "$tmp_file"
    fi
    echo "$line" >> "$tmp_file"
    ((i++))
  done < "$klipperscreen_conf_file"

  if [[ "$insert_before" == "999999" && $has_include == false ]]; then
    echo "$include_line" >> "$tmp_file"
  fi

  mv "$tmp_file" "$klipperscreen_conf_file"
  echo "[INFO] Updated $klipperscreen_conf_file."
}

function uninstall() {
  local klipperscreen_conf_file="$1"
  local tmp_file
  tmp_file=$(mktemp)

  local in_block=false
  local preserve=false

  while IFS= read -r line || [[ -n "$line" ]]; do
    # If we hit the protected line, start preserving everything as-is
    if [[ "$line" == "#~# --- Do not edit below this line. This section is auto generated --- #~#" ]]; then
      preserve=true
    fi

    if $preserve; then
      echo "$line" >> "$tmp_file"
      continue
    fi

    # Skip the include line
    if [[ "$line" == "[include AFC_menu.conf]" ]]; then
      continue
    fi

    # Detect start of a new section: end skipping
    if $in_block && [[ "$line" =~ ^\[.*\] ]]; then
      in_block=false
    fi

    # If not in block, write line
    if ! $in_block; then
      echo "$line" >> "$tmp_file"
    fi
  done < "$klipperscreen_conf_file"

  mv "$tmp_file" "$klipperscreen_conf_file"
  echo "[INFO] Removed AFC KlipperScreen config from: $klipperscreen_conf_file"
  echo "[INFO] Uninstalling AFC-Klipper-Screen-Add-On..."
  rm -f "$printer_config/AFC_menu.conf"
  rm -f "$klipperscreen_dir/panels/AFC.py"
  rm -rf "$klipperscreen_dir/afc_icons"
  echo "[INFO] Uninstall complete."
  exit 0
}


while getopts "p:k:uth" arg; do
  case ${arg} in
  p)
    printer_config=$OPTARG ;;
  k)
    klipperscreen_dir=$OPTARG ;;
  u)
    uninstall=True ;;
  t)
    test_mode=True ;;
  h)
    show_help
    exit 0 ;;
  *) exit 1 ;;
  esac
done

main() {
  if [ "$uninstall" == "True" ]; then
    uninstall "$klipperscreen_conf_file"
  fi
  if [ $test_mode == "False" ]; then
    checks
    clone_repo
  fi
  install_files
  ensure_afc_config "$klipperscreen_conf_file"
  link_icons
  echo "[INFO] AFC-Klipper-Screen-Add-On installed successfully."
  echo "[INFO] Please restart KlipperScreen to apply changes."
}

main
