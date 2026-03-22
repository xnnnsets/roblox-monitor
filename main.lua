local CONFIG_PATH = "../config.json"
local VERSION = "beta-2024.06.01"

local DEFAULT_CONFIG = {
  language = "id",
  package = "",
  package_mode = "auto",
  manual_packages = {},
  monitor_selection = "all",
  selected_packages = {},
  check_interval = 10,
  server_code = "",
  server_mode = "all",
  server_code_by_package = {},
  discord_webhook = "",
  afk_timeout_minutes = 20,
  clear_cache_mode = "target",
  auto_float = true,
  auto_grid = true,
  auto_float_grid = true,
  float_start_delay_seconds = 3,
  a10_launch_delay_seconds = 10,
  startup_grace_seconds = 45,
  multi_launch_delay_seconds = 30,
  float_orientation_mode = "system",
  grid_layout_preset = "compact",
  monitor_ui_mode = "live",
  log_check_every_cycles = 3,
  package_usernames = {},
  enable_immediate_launch = true,
  initial_launch_gap_seconds = 8,
  aggressive_username_detection = true,
  username_fetch_delay_seconds = 5,
}

local COLOR = {
  green = "\27[92m",
  red = "\27[91m",
  cyan = "\27[96m",
  reset = "\27[0m",
}

local DEVICE_PROFILE = { checked = false }
local RUNTIME_STATE = { monitor_compact = false, monitor_ui_mode = "safe", monitor_hotkeys_enabled = false }

local function shell_quote(value)
  value = tostring(value or "")
  return "'" .. value:gsub("'", [['"'"']]) .. "'"
end

local function trim(value)
  return (tostring(value or ""):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function split_lines(text)
  local out = {}
  text = tostring(text or "")
  for line in text:gmatch("([^\n]*)\n?") do
    if line == "" and #out > 0 and out[#out] == "" then
      break
    end
    out[#out + 1] = line
  end
  return out
end

local function short_code(value, limit)
  value = trim(value)
  limit = limit or 10
  if value == "" then
    return "-"
  end
  if #value <= limit then
    return value
  end
  return value:sub(1, limit) .. "..."
end

local function short_text(text, width)
  text = tostring(text or "")
  width = math.max(1, tonumber(width) or 1)
  if #text <= width then
    return text
  end
  if width <= 3 then
    return text:sub(1, width)
  end
  return text:sub(1, width - 3) .. "..."
end

local function run_capture(command)
  local marker = "__EXIT_CODE__:"
  local wrapped = command .. "; printf '\n" .. marker .. "%s' \"$?\""
  local handle = io.popen(wrapped .. " 2>&1")
  if not handle then
    return 1, "failed to spawn command"
  end
  local output = handle:read("*a") or ""
  handle:close()
  local code = tonumber(output:match(marker .. "(%d+)%s*$")) or 1
  output = output:gsub("\n?" .. marker .. "%d+%s*$", "")
  return code, trim(output)
end

local function run_cmd(command)
  return run_capture("sh -c " .. shell_quote(command) .. " </dev/null")
end

local function run_su(command)
  return run_capture("su -c " .. shell_quote(command) .. " </dev/null")
end

local function term_cols()
  local _, output = run_cmd("command -v tput >/dev/null 2>&1 && tput cols || echo 80")
  return tonumber(trim(output)) or 80
end

local function file_exists(path)
  local handle = io.open(path, "r")
  if handle then
    handle:close()
    return true
  end
  return false
end

local function clear_screen()
  os.execute("clear")
end

local function sleep_seconds(seconds)
  seconds = tonumber(seconds) or 0
  if seconds <= 0 then
    return
  end
  run_cmd("sleep " .. shell_quote(tostring(seconds)))
end

local function tr(lang, id_text, en_text)
  if lang == "en" then
    return en_text
  end
  return id_text
end

local function say(lang, id_text, en_text)
  io.write(tr(lang, id_text, en_text) .. "\n")
end

local function print_brand_logo()
  print("==========================================")
  print("               XNNNSETS")
  print("==========================================")
end

local function print_header(lang, subtitle_id, subtitle_en)
  clear_screen()
  print_brand_logo()
  if subtitle_id or subtitle_en then
    print(" " .. tr(lang, subtitle_id or "", subtitle_en or ""))
  else
    if lang == "en" then
      print(" ROBLOX MONITOR CONTROL CENTER")
    else
      print(" PUSAT KONTROL ROBLOX MONITOR")
    end
  end
  print("==========================================")
end

local function clear_terminal_line()
  io.write("\r\27[2K")
end

local function monitor_write_status(text)
  clear_terminal_line()
  io.write(text)
  io.flush()
end

local function runtime_log(message, important)
  if RUNTIME_STATE.monitor_compact and not important then
    return
  end
  if RUNTIME_STATE.monitor_compact then
    clear_terminal_line()
  end
  print(message)
end

local function setup_monitor_hotkeys()
  local code, stty_state = run_cmd("stty -g < /dev/tty 2>/dev/null")
  if code ~= 0 or trim(stty_state) == "" then
    RUNTIME_STATE.monitor_hotkeys_enabled = false
    return nil
  end
  run_cmd("stty -icanon -echo min 0 time 0 susp undef < /dev/tty 2>/dev/null || true")
  RUNTIME_STATE.monitor_hotkeys_enabled = true
  return trim(stty_state)
end

local function restore_monitor_hotkeys(stty_state)
  RUNTIME_STATE.monitor_hotkeys_enabled = false
  if not stty_state or stty_state == "" then
    return
  end
  run_cmd("stty " .. shell_quote(stty_state) .. " < /dev/tty 2>/dev/null || true")
end

local function poll_monitor_control_key()
  if not RUNTIME_STATE.monitor_hotkeys_enabled then
    return nil
  end
  local ok, key = pcall(function()
    return io.stdin:read(1)
  end)
  if not ok then
    return nil
  end
  key = tostring(key or "")
  if key == "" then
    return nil
  end
  local lower = key:lower()
  if lower == "q" then
    return "quit"
  end
  if lower == "s" or key == string.char(26) then
    return "stop"
  end
  return nil
end

local function monitor_sleep_with_control(seconds)
  local total = math.max(0, tonumber(seconds) or 0)
  if total <= 0 then
    return poll_monitor_control_key()
  end
  local step = 0.2
  local elapsed = 0
  while elapsed < total do
    local command = poll_monitor_control_key()
    if command then
      return command
    end
    local wait_time = math.min(step, total - elapsed)
    sleep_seconds(wait_time)
    elapsed = elapsed + wait_time
  end
  return poll_monitor_control_key()
end

local json = {}

local function decode_error(str, idx, msg)
  error(string.format("JSON decode error at position %d: %s", idx, msg))
end

local function skip_ws(str, idx)
  local _, next_idx = str:find("^[ \n\r\t]*", idx)
  return (next_idx or idx - 1) + 1
end

local function parse_string(str, idx)
  idx = idx + 1
  local result = {}
  local i = idx
  while i <= #str do
    local c = str:sub(i, i)
    if c == '"' then
      result[#result + 1] = str:sub(idx, i - 1)
      return table.concat(result), i + 1
    elseif c == "\\" then
      result[#result + 1] = str:sub(idx, i - 1)
      local esc = str:sub(i + 1, i + 1)
      local map = {
        ['"'] = '"', ['\\'] = '\\', ['/'] = '/', b = '\b', f = '\f', n = '\n', r = '\r', t = '\t'
      }
      if esc == "u" then
        local hex = str:sub(i + 2, i + 5)
        if not hex:match("^%x%x%x%x$") then
          decode_error(str, i, "invalid unicode escape")
        end
        local code = tonumber(hex, 16)
        if code < 128 then
          result[#result + 1] = string.char(code)
        else
          result[#result + 1] = utf8.char(code)
        end
        i = i + 6
      elseif map[esc] then
        result[#result + 1] = map[esc]
        i = i + 2
      else
        decode_error(str, i, "invalid escape character")
      end
      idx = i
    else
      i = i + 1
    end
  end
  decode_error(str, idx, "unterminated string")
end

local parse_value

local function parse_array(str, idx)
  idx = idx + 1
  local result = {}
  idx = skip_ws(str, idx)
  if str:sub(idx, idx) == "]" then
    return result, idx + 1
  end
  while true do
    local value
    value, idx = parse_value(str, idx)
    result[#result + 1] = value
    idx = skip_ws(str, idx)
    local c = str:sub(idx, idx)
    if c == "]" then
      return result, idx + 1
    elseif c ~= "," then
      decode_error(str, idx, "expected ']' or ','")
    end
    idx = skip_ws(str, idx + 1)
  end
end

local function parse_object(str, idx)
  idx = idx + 1
  local result = {}
  idx = skip_ws(str, idx)
  if str:sub(idx, idx) == "}" then
    return result, idx + 1
  end
  while true do
    if str:sub(idx, idx) ~= '"' then
      decode_error(str, idx, "expected string key")
    end
    local key
    key, idx = parse_string(str, idx)
    idx = skip_ws(str, idx)
    if str:sub(idx, idx) ~= ":" then
      decode_error(str, idx, "expected ':'")
    end
    idx = skip_ws(str, idx + 1)
    local value
    value, idx = parse_value(str, idx)
    result[key] = value
    idx = skip_ws(str, idx)
    local c = str:sub(idx, idx)
    if c == "}" then
      return result, idx + 1
    elseif c ~= "," then
      decode_error(str, idx, "expected '}' or ','")
    end
    idx = skip_ws(str, idx + 1)
  end
end

local function parse_number(str, idx)
  local num = str:match("^-?%d+%.?%d*[eE]?[+-]?%d*", idx)
  if not num or num == "" then
    decode_error(str, idx, "invalid number")
  end
  return tonumber(num), idx + #num
end

parse_value = function(str, idx)
  idx = skip_ws(str, idx)
  local c = str:sub(idx, idx)
  if c == '"' then
    return parse_string(str, idx)
  elseif c == "{" then
    return parse_object(str, idx)
  elseif c == "[" then
    return parse_array(str, idx)
  elseif c == "-" or c:match("%d") then
    return parse_number(str, idx)
  elseif str:sub(idx, idx + 3) == "true" then
    return true, idx + 4
  elseif str:sub(idx, idx + 4) == "false" then
    return false, idx + 5
  elseif str:sub(idx, idx + 3) == "null" then
    return nil, idx + 4
  end
  decode_error(str, idx, "unexpected character '" .. c .. "'")
end

function json.decode(str)
  local value, idx = parse_value(str, 1)
  idx = skip_ws(str, idx)
  if idx <= #str then
    decode_error(str, idx, "trailing garbage")
  end
  return value
end

local function is_array(tbl)
  if type(tbl) ~= "table" then
    return false
  end
  local count = 0
  local max_index = 0
  for key, _ in pairs(tbl) do
    if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then
      return false
    end
    count = count + 1
    if key > max_index then
      max_index = key
    end
  end
  return max_index == count
end

local function escape_string(str)
  local replacements = {
    ['\\'] = '\\\\', ['"'] = '\\"', ['\b'] = '\\b', ['\f'] = '\\f',
    ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t'
  }
  return str:gsub('[\\"\b\f\n\r\t]', replacements)
end

local function encode_value(value, indent, level)
  local vtype = type(value)
  if vtype == "nil" then
    return "null"
  elseif vtype == "boolean" then
    return value and "true" or "false"
  elseif vtype == "number" then
    return tostring(value)
  elseif vtype == "string" then
    return '"' .. escape_string(value) .. '"'
  elseif vtype == "table" then
    local next_level = level + 1
    local pad = string.rep(indent, level)
    local inner = string.rep(indent, next_level)
    if is_array(value) then
      if #value == 0 then
        return "[]"
      end
      local items = {}
      for i = 1, #value do
        items[#items + 1] = inner .. encode_value(value[i], indent, next_level)
      end
      return "[\n" .. table.concat(items, ",\n") .. "\n" .. pad .. "]"
    end
    local keys = {}
    for key, _ in pairs(value) do
      keys[#keys + 1] = key
    end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    if #keys == 0 then
      return "{}"
    end
    local items = {}
    for _, key in ipairs(keys) do
      items[#items + 1] = inner .. '"' .. escape_string(tostring(key)) .. '": ' .. encode_value(value[key], indent, next_level)
    end
    return "{\n" .. table.concat(items, ",\n") .. "\n" .. pad .. "}"
  end
  error("unsupported JSON type: " .. vtype)
end

function json.encode(value)
  return encode_value(value, "  ", 0)
end

local function read_file(path)
  local handle = io.open(path, "r")
  if not handle then
    return nil
  end
  local data = handle:read("*a")
  handle:close()
  return data
end

local function write_file(path, data)
  local handle = assert(io.open(path, "w"))
  handle:write(data)
  handle:close()
end

local function deepcopy(value)
  if type(value) ~= "table" then
    return value
  end
  local out = {}
  for k, v in pairs(value) do
    out[k] = deepcopy(v)
  end
  return out
end

local function normalize_packages(items)
  local seen, out = {}, {}
  for _, item in ipairs(items or {}) do
    local pkg = trim(item)
    if pkg ~= "" and not seen[pkg] then
      seen[pkg] = true
      out[#out + 1] = pkg
    end
  end
  return out
end

local function load_config()
  local config = deepcopy(DEFAULT_CONFIG)
  if file_exists(CONFIG_PATH) then
    local ok, parsed = pcall(json.decode, read_file(CONFIG_PATH) or "{}")
    if ok and type(parsed) == "table" then
      for key, value in pairs(parsed) do
        config[key] = value
      end
    end
  end
  if config.auto_float == nil then
    config.auto_float = not not config.auto_float_grid
  end
  if config.auto_grid == nil then
    config.auto_grid = not not config.auto_float_grid
  end
  config.manual_packages = normalize_packages(config.manual_packages or {})
  config.selected_packages = normalize_packages(config.selected_packages or {})
  config.server_code_by_package = type(config.server_code_by_package) == "table" and config.server_code_by_package or {}
  config.package_usernames = type(config.package_usernames) == "table" and config.package_usernames or {}
  if config.float_orientation_mode ~= "system" and config.float_orientation_mode ~= "landscape" and config.float_orientation_mode ~= "portrait" then
    config.float_orientation_mode = "system"
  end
  if config.monitor_ui_mode ~= "live" and config.monitor_ui_mode ~= "safe" then
    config.monitor_ui_mode = "safe"
  end
  config.log_check_every_cycles = math.max(1, tonumber(config.log_check_every_cycles) or 3)
  if config.enable_immediate_launch == nil then config.enable_immediate_launch = true end
  if config.aggressive_username_detection == nil then config.aggressive_username_detection = true end
  config.initial_launch_gap_seconds = math.max(1, tonumber(config.initial_launch_gap_seconds) or 8)
  config.username_fetch_delay_seconds = math.max(0, tonumber(config.username_fetch_delay_seconds) or 5)
  return config
end

local function save_config(config)
  config.manual_packages = normalize_packages(config.manual_packages or {})
  config.selected_packages = normalize_packages(config.selected_packages or {})
  config.auto_float = not not config.auto_float
  config.auto_grid = not not config.auto_grid
  config.auto_float_grid = config.auto_float and config.auto_grid
  config.server_code_by_package = type(config.server_code_by_package) == "table" and config.server_code_by_package or {}
  config.package_usernames = type(config.package_usernames) == "table" and config.package_usernames or {}
  if config.float_orientation_mode ~= "system" and config.float_orientation_mode ~= "landscape" and config.float_orientation_mode ~= "portrait" then
    config.float_orientation_mode = "system"
  end
  if config.monitor_ui_mode ~= "live" and config.monitor_ui_mode ~= "safe" then
    config.monitor_ui_mode = "safe"
  end
  config.log_check_every_cycles = math.max(1, tonumber(config.log_check_every_cycles) or 3)
  config.enable_immediate_launch = not not config.enable_immediate_launch
  config.aggressive_username_detection = not not config.aggressive_username_detection
  write_file(CONFIG_PATH, json.encode(config) .. "\n")
end

local function prompt(label, default)
  if default ~= nil and tostring(default) ~= "" then
    io.write(string.format("%s [%s]: ", label, tostring(default)))
  else
    io.write(label .. ": ")
  end
  local value = io.read("*l") or ""
  value = trim(value)
  if value == "" and default ~= nil then
    return tostring(default)
  end
  return value
end

local function prompt_menu(lang, options, default)
  while true do
    local raw = prompt(tr(lang, "Pilihan", "Choice"), default)
    for _, item in ipairs(options) do
      if raw == item then
        return raw
      end
    end
    print(tr(lang, "Pilihan tidak valid.", "Invalid choice."))
  end
end

local function prompt_bool(lang, label_id, label_en, default)
  local default_text = default and "y" or "n"
  while true do
    local raw = prompt(tr(lang, label_id, label_en), default_text):lower()
    if raw == "y" or raw == "yes" or raw == "1" then
      return true
    elseif raw == "n" or raw == "no" or raw == "0" then
      return false
    end
    print(tr(lang, "Pilih y/n.", "Use y/n."))
  end
end

local function prompt_int(lang, label_id, label_en, default, min_value)
  min_value = min_value or 0
  while true do
    local raw = prompt(tr(lang, label_id, label_en), default)
    local value = tonumber(raw)
    if value and math.floor(value) == value and value >= min_value then
      return value
    end
    print(tr(lang, "Input angka tidak valid.", "Invalid number input."))
  end
end

local function prompt_float(lang, label_id, label_en, default, min_value)
  min_value = min_value or 0
  while true do
    local raw = prompt(tr(lang, label_id, label_en), default)
    local value = tonumber(raw)
    if value and value >= min_value then
      return value
    end
    print(tr(lang, "Input angka tidak valid.", "Invalid number input."))
  end
end

local function parse_server_code(raw)
  raw = trim(raw)
  if raw == "" then
    return ""
  end
  local code = raw:match("[?&]code=([^&#]+)")
  if code then
    return code
  end
  code = raw:match("([A-Fa-f0-9][A-Fa-f0-9]+)")
  if code and #code == 32 then
    return code
  end
  return raw
end

local function collect_packages_from_output(output)
  local items = {}
  for _, line in ipairs(split_lines(output)) do
    local pkg = trim(line:gsub("^package:", ""))
    if pkg ~= "" then
      items[#items + 1] = pkg
    end
  end
  return normalize_packages(items)
end

local function scan_packages()
  local commands = {
    { source = "pm", command = "pm list packages 2>/dev/null | grep -i roblox" },
    { source = "cmd", command = "cmd package list packages 2>/dev/null | grep -i roblox" },
    { source = "pm-all", command = "pm list packages -3 2>/dev/null | grep -Ei 'roblox|com\\.roblox'" },
  }
  for _, item in ipairs(commands) do
    local _, output = run_cmd(item.command)
    local packages = collect_packages_from_output(output)
    if #packages > 0 then
      return packages, item.source
    end
  end
  return {}, "none"
end

local function print_scan_result(lang, packages, source)
  print(tr(lang, "Hasil scanner package:", "Scanner package result:"))
  print(" source : " .. tostring(source or "-"))
  if #packages == 0 then
    print(" count  : 0")
    print(tr(lang, " tidak ada package Roblox terdeteksi", " no Roblox package detected"))
    return
  end
  print(" count  : " .. tostring(#packages))
  for index, pkg in ipairs(packages) do
    print(string.format(" %d. %s", index, pkg))
  end
end

local function resolve_source_packages(config)
  local auto_packages = select(1, scan_packages())
  local manual_packages = normalize_packages(config.manual_packages or {})
  local legacy_package = trim(config.package or "")
  if legacy_package ~= "" then
    manual_packages[#manual_packages + 1] = legacy_package
    manual_packages = normalize_packages(manual_packages)
  end
  if config.package_mode == "manual" then
    return (#manual_packages > 0) and manual_packages or auto_packages
  end
  return (#auto_packages > 0) and auto_packages or manual_packages
end

local function resolve_target_packages(config)
  local source = resolve_source_packages(config)
  local selected = normalize_packages(config.selected_packages or {})
  if config.monitor_selection == "selected" and #selected > 0 then
    local ordered, seen = {}, {}
    for _, pkg in ipairs(source) do
      for _, want in ipairs(selected) do
        if pkg == want and not seen[pkg] then
          ordered[#ordered + 1] = pkg
          seen[pkg] = true
        end
      end
    end
    for _, pkg in ipairs(selected) do
      if not seen[pkg] then
        ordered[#ordered + 1] = pkg
      end
    end
    return normalize_packages(ordered)
  end
  return source
end

local function resolve_cache_packages(config)
  if tostring(config.clear_cache_mode or "target") == "all" then
    return resolve_source_packages(config)
  end
  return resolve_target_packages(config)
end

local function get_package_label(package, config)
  local username = trim((config.package_usernames or {})[package] or "")
  if username ~= "" and username ~= "unknown" then
    return package .. " (" .. username .. ")"
  end
  return package
end

local function choose_packages_interactive(lang, available, current_selected)
  if #available == 0 then
    print(tr(lang, "Tidak ada package Roblox terdeteksi.", "No Roblox packages detected."))
    return {}
  end
  print(tr(lang, "Pilih package (pisahkan koma, contoh: 1,3)", "Choose packages (comma-separated, example: 1,3)"))
  local selected_map = {}
  for _, pkg in ipairs(current_selected or {}) do selected_map[pkg] = true end
  for i, pkg in ipairs(available) do
    local marker = selected_map[pkg] and "*" or " "
    print(string.format(" %d. [%s] %s", i, marker, pkg))
  end
  local raw = prompt(tr(lang, "Pilihan", "Choice"), "")
  if trim(raw) == "" then
    return current_selected or {}
  end
  local chosen = {}
  for part in raw:gmatch("[^,]+") do
    local idx = tonumber(trim(part))
    if idx and available[idx] then
      chosen[#chosen + 1] = available[idx]
    end
  end
  return normalize_packages(chosen)
end

local function collect_manual_packages(lang, existing)
  local packages = normalize_packages(existing or {})
  print(tr(lang, "Input package satu per baris. Enter kosong jika selesai.", "Input one package per line. Empty Enter to finish."))
  while true do
    local raw = prompt(tr(lang, "Paket", "Package"), "")
    if trim(raw) == "" then
      break
    end
    local additions = {}
    for part in raw:gmatch("[^,]+") do
      additions[#additions + 1] = trim(part)
    end
    for _, pkg in ipairs(additions) do
      packages[#packages + 1] = pkg
    end
    packages = normalize_packages(packages)
  end
  return packages
end

local function configure_monitor_selection(config, lang, available)
  if #available == 0 then
    config.monitor_selection = "all"
    config.selected_packages = {}
    return
  end
  print(tr(lang, "Pilih target monitor Roblox:", "Choose Roblox monitor targets:"))
  print("1. " .. tr(lang, "Buka semua package", "Open all packages"))
  print("2. " .. tr(lang, "Pilih package tertentu", "Choose selected packages"))
  local default_mode = (config.monitor_selection == "selected") and "2" or "1"
  local choice = prompt_menu(lang, {"1", "2"}, default_mode)
  if choice == "2" then
    config.monitor_selection = "selected"
    config.selected_packages = choose_packages_interactive(lang, available, config.selected_packages or {})
  else
    config.monitor_selection = "all"
    config.selected_packages = {}
  end
end

local function configure_server_settings(config, lang, available)
  print("1. " .. tr(lang, "Satu private server untuk semua package", "One private server for all packages"))
  print("2. " .. tr(lang, "Private server berbeda per package", "Different private server per package"))
  local default_mode = (config.server_mode == "per_package") and "2" or "1"
  local choice = prompt_menu(lang, {"1", "2"}, default_mode)
  if choice == "1" then
    config.server_mode = "all"
    config.server_code = parse_server_code(prompt(tr(lang, "Masukkan private server link / game link / server code", "Enter private server link / game link / server code"), config.server_code or ""))
    return
  end
  config.server_mode = "per_package"
  config.server_code_by_package = type(config.server_code_by_package) == "table" and config.server_code_by_package or {}
  for _, pkg in ipairs(available) do
    local key = get_package_label(pkg, config) .. " server link/code"
    config.server_code_by_package[pkg] = parse_server_code(prompt(key, config.server_code_by_package[pkg] or ""))
  end
  config.server_code = parse_server_code(prompt(tr(lang, "Server code global fallback", "Global fallback server code"), config.server_code or ""))
end

local function configure_cache_mode(config, lang)
  print("1. " .. tr(lang, "Clear cache semua package Roblox", "Clear cache all Roblox packages"))
  print("2. " .. tr(lang, "Clear cache package target monitor", "Clear cache monitor target packages"))
  local choice = prompt_menu(lang, {"1", "2"}, (config.clear_cache_mode == "all") and "1" or "2")
  config.clear_cache_mode = (choice == "1") and "all" or "target"
end

local function configure_float_orientation(config, lang)
  print("1. " .. tr(lang, "Ikuti orientasi sistem", "Follow system orientation"))
  print("2. " .. tr(lang, "Landscape layout", "Landscape layout"))
  print("3. " .. tr(lang, "Portrait layout", "Portrait layout"))
  local default_mode = ({system = "1", landscape = "2", portrait = "3"})[config.float_orientation_mode] or "1"
  local choice = prompt_menu(lang, {"1", "2", "3"}, default_mode)
  config.float_orientation_mode = ({["1"] = "system", ["2"] = "landscape", ["3"] = "portrait"})[choice]
end

local function configure_grid_preset(config, lang)
  print("1. balanced")
  print("2. compact")
  print("3. ultra-compact")
  print("4. wide")
  local default_mode = ({balanced = "1", compact = "2", ["ultra-compact"] = "3", wide = "4"})[config.grid_layout_preset] or "1"
  local choice = prompt_menu(lang, {"1", "2", "3", "4"}, default_mode)
  config.grid_layout_preset = ({["1"] = "balanced", ["2"] = "compact", ["3"] = "ultra-compact", ["4"] = "wide"})[choice]
end

local function configure_monitor_ui_mode(config, lang)
  print("1. " .. tr(lang, "Safe (stabil untuk device sensitif)", "Safe (stable for sensitive devices)"))
  print("2. " .. tr(lang, "Live snapshot (lebih detail)", "Live snapshot (more detailed)"))
  local default_mode = (config.monitor_ui_mode == "live") and "2" or "1"
  local choice = prompt_menu(lang, {"1", "2"}, default_mode)
  config.monitor_ui_mode = (choice == "2") and "live" or "safe"
end

local function print_config_body(config, lang)
  print("[PACKAGE]")
  print(" mode         : " .. tostring(config.package_mode))
  print(" monitor      : " .. tostring(config.monitor_selection))
  print(" selected     : " .. (#(config.selected_packages or {}) > 0 and table.concat(config.selected_packages, ", ") or "-"))
  print("\n[PRIVATE SERVER]")
  print(" mode         : " .. tostring(config.server_mode))
  print(" fallback     : " .. short_code(config.server_code or "", 12))
  print("\n[GRID / FLOAT]")
  print(" auto float   : " .. tostring(config.auto_float))
  print(" auto grid    : " .. tostring(config.auto_grid))
  print(" orientation  : " .. tostring(config.float_orientation_mode or "system"))
  print(" grid preset  : " .. (config.auto_grid and tostring(config.grid_layout_preset) or "-"))
  print(" start delay  : " .. (config.auto_float and (tostring(config.float_start_delay_seconds) .. "s") or "-"))
  print(" launch delay : " .. tostring(config.multi_launch_delay_seconds) .. "s")
  print(" monitor ui   : " .. tostring(config.monitor_ui_mode))
  print("\n[OTHER]")
  print(" check interval : " .. tostring(config.check_interval) .. "s")
  print(" log check cyc  : " .. tostring(config.log_check_every_cycles))
  print(" afk timeout    : " .. tostring(config.afk_timeout_minutes) .. " min")
  print(" clear cache    : " .. tostring(config.clear_cache_mode))
  print("\n[MONITOR BEHAVIOR]")
  print(" immediate launch : " .. tostring(config.enable_immediate_launch ~= false))
  print(" initial gap      : " .. tostring(config.initial_launch_gap_seconds or 8) .. "s")
  print(" aggressive user  : " .. tostring(config.aggressive_username_detection ~= false))
  print(" username delay   : " .. tostring(config.username_fetch_delay_seconds or 5) .. "s")
end

local function show_config_overview(config, lang)
  print_header(lang, "LIHAT KONFIGURASI", "VIEW CONFIG")
  print_config_body(config, lang)
  prompt(tr(lang, "Tekan Enter untuk kembali", "Press Enter to go back"), "")
end

local function show_config_summary(config, lang)
  print_header(lang, "PREVIEW CONFIG", "CONFIG PREVIEW")
  print_config_body(config, lang)
  local raw = prompt(tr(lang, "Simpan setting ini? (y/n)", "Save these settings? (y/n)"), "y")
  return raw == "" or raw:lower() == "y" or raw:lower() == "yes" or raw == "1"
end

local function quick_setup(config, lang)
  print_header(lang, "SETUP CONFIGURATION", "SETUP CONFIGURATION")
  print("1. " .. tr(lang, "Auto scanner package app Roblox", "Auto scanner Roblox app package"))
  print("2. " .. tr(lang, "Manual input app Roblox package", "Manual input Roblox app package"))
  local mode_choice = prompt_menu(lang, {"1", "2"}, (config.package_mode == "manual") and "2" or "1")
  local available = {}
  if mode_choice == "2" then
    config.package_mode = "manual"
    config.manual_packages = collect_manual_packages(lang, config.manual_packages or {})
    available = normalize_packages(config.manual_packages)
  else
    config.package_mode = "auto"
    local scan_source
    available, scan_source = scan_packages()
    print_scan_result(lang, available, scan_source)
    if #available == 0 then
      config.package_mode = "manual"
      print(tr(lang, "Scanner kosong, pindah ke input manual.", "Scanner returned empty, switching to manual input."))
      config.manual_packages = collect_manual_packages(lang, config.manual_packages or {})
      available = normalize_packages(config.manual_packages)
    end
  end
  configure_monitor_selection(config, lang, available)
  configure_server_settings(config, lang, available)
  configure_cache_mode(config, lang)
  config.discord_webhook = prompt(tr(lang, "Discord webhook (opsional)", "Discord webhook (optional)"), config.discord_webhook or "")
  config.check_interval = prompt_int(lang, "Check interval (detik)", "Check interval (seconds)", config.check_interval or 10, 1)
  config.afk_timeout_minutes = prompt_float(lang, "AFK timeout (menit)", "AFK timeout (minutes)", config.afk_timeout_minutes or 20, 0.1)
  config.auto_float = prompt_bool(lang, "Auto float/freeform? (y/n)", "Auto float/freeform? (y/n)", config.auto_float)
  if config.auto_float then
    config.float_start_delay_seconds = prompt_int(lang, "Float start delay (detik)", "Float start delay (seconds)", config.float_start_delay_seconds or 3, 0)
  end
  config.auto_grid = prompt_bool(lang, "Auto grid resize? (y/n)", "Auto grid resize? (y/n)", config.auto_grid)
  config.multi_launch_delay_seconds = prompt_int(lang, "Jeda buka antar app (detik)", "Delay between app launches (seconds)", config.multi_launch_delay_seconds or 30, 0)
  config.log_check_every_cycles = prompt_int(lang, "Cek log setiap berapa siklus", "Check logs every how many cycles", config.log_check_every_cycles or 3, 1)
  configure_monitor_ui_mode(config, lang)
  configure_float_orientation(config, lang)
  if config.auto_grid then
    configure_grid_preset(config, lang)
  end
  if not show_config_summary(config, lang) then
    os.exit(0)
  end
  return config
end

local function package_management_menu(config, lang)
  while true do
    print_header(lang, "KELOLA PACKAGE", "PACKAGE MANAGEMENT")
    print("1. " .. tr(lang, "Mode AUTO scanner", "AUTO scanner mode"))
    print("2. " .. tr(lang, "Mode MANUAL input", "MANUAL input mode"))
    print("3. " .. tr(lang, "Tambah paket manual", "Add manual package"))
    print("4. " .. tr(lang, "Hapus paket manual", "Remove manual package"))
    print("0. " .. tr(lang, "Kembali", "Back"))
    local choice = prompt_menu(lang, {"1", "2", "3", "4", "0"}, "0")
    if choice == "1" then
      config.package_mode = "auto"
    elseif choice == "2" then
      config.package_mode = "manual"
    elseif choice == "3" then
      config.manual_packages = collect_manual_packages(lang, config.manual_packages or {})
    elseif choice == "4" then
      for i, pkg in ipairs(config.manual_packages or {}) do
        print(string.format(" %d. %s", i, pkg))
      end
      local idx = tonumber(prompt(tr(lang, "Pilih nomor", "Choose number"), ""))
      if idx and config.manual_packages[idx] then
        table.remove(config.manual_packages, idx)
      end
    else
      break
    end
  end
end

local function edit_config(config, lang)
  while true do
    print_header(lang, "UBAH KONFIGURASI", "EDIT CONFIG")
    local menu_items = {}
    local function add_item(label, action)
      menu_items[#menu_items + 1] = { label = label, action = action }
      print(string.format("%d. %s", #menu_items, label))
    end

    add_item(tr(lang, "Lihat config sekarang", "View current config"), function()
      show_config_overview(config, lang)
    end)
    add_item(tr(lang, "Private server", "Private server"), function()
      configure_server_settings(config, lang, resolve_source_packages(config))
    end)
    add_item(tr(lang, "Kelola package", "Manage packages"), function()
      package_management_menu(config, lang)
    end)
    add_item(tr(lang, "Pilih package monitor", "Choose monitor targets"), function()
      configure_monitor_selection(config, lang, resolve_source_packages(config))
    end)
    add_item(tr(lang, "Mode clear cache", "Clear cache mode"), function()
      configure_cache_mode(config, lang)
    end)
    add_item(tr(lang, "Discord webhook", "Discord webhook"), function()
      config.discord_webhook = prompt("Discord webhook", config.discord_webhook or "")
    end)
    add_item(tr(lang, "Check interval", "Check interval"), function()
      config.check_interval = prompt_int(lang, "Check interval (detik)", "Check interval (seconds)", config.check_interval or 10, 1)
    end)
    add_item(tr(lang, "AFK timeout", "AFK timeout"), function()
      config.afk_timeout_minutes = prompt_float(lang, "AFK timeout (menit)", "AFK timeout (minutes)", config.afk_timeout_minutes or 20, 0.1)
    end)
    add_item(tr(lang, "Auto float/freeform", "Auto float/freeform"), function()
      config.auto_float = prompt_bool(lang, "Auto float/freeform? (y/n)", "Auto float/freeform? (y/n)", config.auto_float)
    end)
    add_item(tr(lang, "Auto grid resize", "Auto grid resize"), function()
      config.auto_grid = prompt_bool(lang, "Auto grid resize? (y/n)", "Auto grid resize? (y/n)", config.auto_grid)
    end)
    if config.auto_float then
      add_item(tr(lang, "Float start delay", "Float start delay"), function()
        config.float_start_delay_seconds = prompt_int(lang, "Float start delay (detik)", "Float start delay (seconds)", config.float_start_delay_seconds or 3, 0)
      end)
    end
    add_item(tr(lang, "Jeda buka antar app", "Delay between app launches"), function()
      config.multi_launch_delay_seconds = prompt_int(lang, "Jeda buka antar app (detik)", "Delay between app launches (seconds)", config.multi_launch_delay_seconds or 30, 0)
    end)
    add_item(tr(lang, "Cek log tiap N siklus", "Check logs every N cycles"), function()
      config.log_check_every_cycles = prompt_int(lang, "Cek log setiap berapa siklus", "Check logs every how many cycles", config.log_check_every_cycles or 3, 1)
    end)
    add_item(tr(lang, "Mode output monitor", "Monitor output mode"), function()
      configure_monitor_ui_mode(config, lang)
    end)
    add_item(tr(lang, "Orientasi float/grid", "Float/grid orientation"), function()
      configure_float_orientation(config, lang)
    end)
    if config.auto_grid then
      add_item(tr(lang, "Preset layout grid", "Grid layout preset"), function()
        configure_grid_preset(config, lang)
      end)
    end
    add_item(tr(lang, "Launch app langsung saat mulai", "Launch missing apps immediately on start"), function()
      config.enable_immediate_launch = prompt_bool(lang, "Launch app langsung saat mulai? (y/n)", "Launch missing apps immediately on start? (y/n)", config.enable_immediate_launch ~= false)
    end)
    add_item(tr(lang, "Jeda antar launch awal", "Gap between initial launches"), function()
      config.initial_launch_gap_seconds = prompt_int(lang, "Jeda antar launch awal (detik)", "Gap between initial launches (seconds)", config.initial_launch_gap_seconds or 8, 1)
    end)
    add_item(tr(lang, "Deteksi username agresif", "Aggressive username detection"), function()
      config.aggressive_username_detection = prompt_bool(lang, "Deteksi username agresif? (y/n)", "Aggressive username detection? (y/n)", config.aggressive_username_detection ~= false)
    end)
    add_item(tr(lang, "Jeda fetch username (s)", "Username fetch delay (s)"), function()
      config.username_fetch_delay_seconds = prompt_int(lang, "Jeda fetch username setelah join (detik)", "Username fetch delay after join (seconds)", config.username_fetch_delay_seconds or 5, 0)
    end)
    add_item(tr(lang, "Simpan dan keluar", "Save and exit"), function()
      if show_config_summary(config, lang) then
        save_config(config)
      end
      return "exit"
    end)

    print("0. " .. tr(lang, "Batal", "Cancel"))
    local options = {"0"}
    for index = 1, #menu_items do
      options[#options + 1] = tostring(index)
    end
    local choice = prompt_menu(lang, options, "0")
    if choice == "0" then
      return config
    end
    local result = menu_items[tonumber(choice)].action()
    if result == "exit" then
      return config
    end
  end
end

local function get_memory_info()
  local data = read_file("/proc/meminfo") or ""
  local total = tonumber(data:match("MemTotal:%s+(%d+)")) or 0
  local free = tonumber(data:match("MemAvailable:%s+(%d+)")) or 0
  total = math.floor(total / 1024)
  free = math.floor(free / 1024)
  local pct = (total > 0) and math.floor((free / total) * 100) or 0
  return total, free, pct
end

local function check_root_permission()
  local code, output = run_su("id")
  return code == 0 and output:find("uid=0") ~= nil
end

local function get_device_profile()
  if DEVICE_PROFILE.checked then
    return DEVICE_PROFILE
  end
  DEVICE_PROFILE.checked = true
  local _, sdk_out = run_cmd("getprop ro.build.version.sdk")
  DEVICE_PROFILE.sdk = tonumber(trim(sdk_out)) or 0
  local width, height = 1080, 2400
  local _, size_out = run_su("wm size 2>/dev/null")
  local last_w, last_h
  for w, h in size_out:gmatch("(%d+)x(%d+)") do
    last_w, last_h = tonumber(w), tonumber(h)
  end
  if last_w and last_h then
    width, height = last_w, last_h
  end
  DEVICE_PROFILE.width = width
  DEVICE_PROFILE.height = height
  local density = 0
  local _, density_out = run_su("wm density 2>/dev/null")
  for value in density_out:gmatch("(%d+)") do
    density = tonumber(value) or density
  end
  if density == 0 then
    local _, prop = run_cmd("getprop ro.sf.lcd_density")
    density = tonumber(trim(prop)) or 420
  end
  DEVICE_PROFILE.density = density
  DEVICE_PROFILE.scale = math.max(1.0, density / 160.0)
  DEVICE_PROFILE.safe_inset_x = math.max(16, math.floor(10 * DEVICE_PROFILE.scale), math.floor(width / 48))
  DEVICE_PROFILE.safe_inset_y = math.max(20, math.floor(14 * DEVICE_PROFILE.scale), math.floor(height / 50))
  return DEVICE_PROFILE
end

local function extract_task_id(text)
  text = tostring(text or "")
  local patterns = {
    "[Tt]ask%s+id[:%s]+([1-9]%d*)",
    "mTaskId%s*=%s*([1-9]%d*)",
    "taskId=([1-9]%d*)",
    "Task%{[^#\n]*#([1-9]%d*)",
    "TaskRecord%{[^#\n]*#([1-9]%d*)",
    "\bid=(%d+)\b",
  }
  for _, pattern in ipairs(patterns) do
    local match = text:match(pattern)
    if match then
      return tonumber(match)
    end
  end
  return nil
end

local function find_task_id(package)
  local commands = {
    "dumpsys activity activities 2>/dev/null",
    "dumpsys activity recents 2>/dev/null",
    "cmd activity tasks 2>/dev/null",
    "am task list 2>/dev/null",
    "dumpsys window windows 2>/dev/null",
  }
  for _, cmd in ipairs(commands) do
    local _, output = run_su(cmd)
    local lines = split_lines(output)
    for idx, line in ipairs(lines) do
      if line:find(package, 1, true) then
        local id = extract_task_id(line)
        if id then
          return id
        end
        local start_idx = math.max(1, idx - 12)
        local end_idx = math.min(#lines, idx + 12)
        local context_lines = {}
        for i = start_idx, end_idx do
          context_lines[#context_lines + 1] = lines[i]
        end
        id = extract_task_id(table.concat(context_lines, "\n"))
        if id then
          return id
        end
      end
    end
  end
  return nil
end

local function find_task_candidates(package)
  local commands = {
    "dumpsys activity activities 2>/dev/null",
    "dumpsys activity recents 2>/dev/null",
    "dumpsys window windows 2>/dev/null",
    "cmd activity tasks 2>/dev/null",
    "am task list 2>/dev/null",
    "dumpsys activity top 2>/dev/null",
  }
  local seen, ids = {}, {}
  local function push(id)
    if id and not seen[id] then
      seen[id] = true
      ids[#ids + 1] = id
    end
  end
  for _, cmd in ipairs(commands) do
    local _, output = run_su(cmd)
    local lines = split_lines(output)
    for idx, line in ipairs(lines) do
      if line:find(package, 1, true) then
        push(extract_task_id(line))
        local start_idx = math.max(1, idx - 12)
        local end_idx = math.min(#lines, idx + 12)
        local context_lines = {}
        for i = start_idx, end_idx do
          context_lines[#context_lines + 1] = lines[i]
        end
        push(extract_task_id(table.concat(context_lines, "\n")))
      end
    end
  end
  push(find_task_id(package))
  return ids
end

local function clamp_bounds(left, top, right, bottom, safe_left, safe_top, safe_right, safe_bottom, min_w, min_h)
  left = math.max(safe_left, math.min(left, safe_right - min_w))
  top = math.max(safe_top, math.min(top, safe_bottom - min_h))
  right = math.min(safe_right, math.max(right, left + min_w))
  bottom = math.min(safe_bottom, math.max(bottom, top + min_h))
  return math.floor(left), math.floor(top), math.floor(right), math.floor(bottom)
end

local function get_grid_bounds(index, total, width, height, config)
  local profile = get_device_profile()
  local scale = profile.scale
  local edge_x = profile.safe_inset_x
  local edge_y = profile.safe_inset_y
  local orientation = tostring(config.float_orientation_mode or "system")
  -- If explicitly locked to landscape but wm size still gives portrait dims, swap them
  if orientation == "landscape" and width < height then
    width, height = height, width
  elseif orientation == "portrait" and width > height then
    width, height = height, width
  end
  local gap = math.max(8, math.floor(6 * scale), math.floor(math.min(width, height) / 120))
  local safe_left = edge_x
  local safe_right = width - edge_x
  local safe_top = math.max(58, edge_y + math.floor(10 * scale))
  local safe_bottom = height - math.max(12, edge_y)
  local is_landscape = (orientation == "landscape") or (orientation == "system" and width > height)
  local dock_ratio = is_landscape and 0.40 or 0.32
  local preset = tostring(config.grid_layout_preset or "balanced")
  if profile.sdk >= 34 then
    dock_ratio = is_landscape and 0.36 or 0.30
  end
  if preset == "wide" then
    dock_ratio = dock_ratio + 0.04
  elseif preset == "ultra-compact" then
    dock_ratio = dock_ratio - 0.03
  end
  dock_ratio = math.max(0.26, math.min(0.56, dock_ratio))
  local available_total_w = math.max(240, safe_right - safe_left)
  local available_total_h = math.max(260, safe_bottom - safe_top)
  local dock_width = math.max(math.floor(220 * scale), math.floor(available_total_w * dock_ratio))
  dock_width = math.min(available_total_w, dock_width)
  local dock_left = safe_right - dock_width
  local available_w = math.max(180, dock_width - (gap * 2))
  local available_h = math.max(220, available_total_h - gap)

  local max_w, max_h, min_w, min_h, cols
  if preset == "ultra-compact" then
    max_w = is_landscape and 160 or 135
    max_h = is_landscape and 155 or 170
    min_w = is_landscape and 90 or 85
    min_h = is_landscape and 110 or 115
    cols = is_landscape and ((total >= 12) and 5 or (total >= 6) and 4 or 3) or ((total >= 8) and 4 or (total >= 3) and 3 or 2)
  elseif preset == "compact" then
    max_w = is_landscape and 225 or 175
    max_h = is_landscape and 190 or 210
    min_w = is_landscape and 105 or 98
    min_h = is_landscape and 125 or 130
    cols = is_landscape and ((total >= 8) and 4 or (total >= 4) and 3 or 2) or ((total >= 6) and 3 or (total > 1) and 2 or 1)
  elseif preset == "wide" then
    max_w = is_landscape and 370 or 275
    max_h = is_landscape and 285 or 315
    min_w = is_landscape and 150 or 130
    min_h = is_landscape and 165 or 175
    cols = is_landscape and ((total >= 7) and 3 or (total >= 3) and 2 or 1) or ((total >= 4) and 2 or 1)
  else
    max_w = is_landscape and 280 or 210
    max_h = is_landscape and 220 or 250
    min_w = is_landscape and 120 or 110
    min_h = is_landscape and 140 or 145
    cols = is_landscape and ((total >= 10) and 4 or (total >= 4) and 3 or 2) or ((total >= 7) and 3 or (total > 1) and 2 or 1)
  end
  cols = math.max(1, math.min(cols, total))
  local rows = math.max(1, math.ceil(total / cols))
  local cell_w = math.max(min_w, math.min(math.floor((available_w - gap * (cols - 1)) / cols), max_w))
  local cell_h = math.max(min_h, math.min(math.floor((available_h - gap * (rows - 1)) / rows), max_h))
  local row = math.floor(index / cols)
  local col = index % cols
  local used_w = cols * cell_w + (cols - 1) * gap
  local start_x = safe_right - used_w
  local min_left = is_landscape and safe_left or (dock_left + gap)
  if start_x < min_left then start_x = min_left end
  local left = start_x + col * (cell_w + gap)
  local top = safe_top + row * (cell_h + gap)
  local right = math.min(safe_right, left + cell_w)
  local bottom = math.min(safe_bottom, top + cell_h)
  return clamp_bounds(left, top, right, bottom, safe_left, safe_top, safe_right, safe_bottom, math.max(math.floor(76 * scale), math.floor(width / 11)), math.max(math.floor(92 * scale), math.floor(height / 11)))
end

local function try_apply_float(task_id, left, top, right, bottom, config)
  local commands = {}
  if config.auto_grid then
    commands[#commands + 1] = string.format("am task resize %d %d %d %d %d", task_id, left, top, right, bottom)
  end
  if #commands == 0 then
    return true
  end
  local success = false
  for _, cmd in ipairs(commands) do
    local code, output = run_su(cmd)
    local low = output:lower()
    if code == 0 and not low:find("error", 1, true) and not low:find("unknown", 1, true) and not low:find("exception", 1, true) then
      success = true
      break
    end
  end
  return success
end

local function apply_float_grid(package, grid_index, grid_total, config, task_id_hint, is_android_10)
  if not config.auto_float and not config.auto_grid then
    return false
  end

  if is_android_10 then
    runtime_log("[*] [A10] Taskbar mode aktif: skip auto float/grid command", false)
    return true
  end

  if config.auto_float then
    run_su("settings put global enable_freeform_support 1")
    run_su("settings put global force_resizable_activities 1")
    run_su("settings put global enable_non_resizable_multi_window 1")
  end

  sleep_seconds(config.float_start_delay_seconds or 3)
  local profile = get_device_profile()
  local pass_delays = {0.0, 0.7, 1.3, 2.2}
  if (profile.sdk or 0) >= 34 then
    pass_delays[#pass_delays + 1] = 3.2
  end

  local candidates, seen = {}, {}
  local function add_candidate(task_id)
    if task_id and not seen[task_id] then
      seen[task_id] = true
      candidates[#candidates + 1] = task_id
    end
  end
  add_candidate(task_id_hint)

  local last_left, last_top, last_right, last_bottom = 0, 0, 0, 0
  if is_android_10 and config.auto_float then
    runtime_log("[*] [A10] Applying float via post-launch task move", false)
  end

  for _, extra_delay in ipairs(pass_delays) do
    if extra_delay > 0 then
      sleep_seconds(extra_delay)
    end

    local width, height = get_device_profile().width, get_device_profile().height
    local left, top, right, bottom = get_grid_bounds(grid_index, grid_total, width, height, config)
    last_left, last_top, last_right, last_bottom = left, top, right, bottom

    for _, task_id in ipairs(find_task_candidates(package)) do
      add_candidate(task_id)
    end

    for _, task_id in ipairs(candidates) do
      if is_android_10 and config.auto_float then
        local move_cmd = "am task move-task " .. task_id .. " 2 true"
        local code, output = run_su(move_cmd)
        local low = tostring(output or ""):lower()
        if code == 0 and not low:find("error", 1, true) and not low:find("unknown", 1, true) and not low:find("exception", 1, true) then
          if not config.auto_grid or try_apply_float(task_id, left, top, right, bottom, config) then
            runtime_log(string.format("[v] Float/grid applied: %s -> [%d,%d,%d,%d]", package, left, top, right, bottom), true)
            return true
          end
        end
      end

      if try_apply_float(task_id, left, top, right, bottom, config) then
        runtime_log(string.format("[v] Float/grid applied: %s -> [%d,%d,%d,%d]", package, left, top, right, bottom), true)
        return true
      end
    end
  end

  local hint = (#candidates > 0) and (" candidates=" .. table.concat(candidates, ",")) or ""
  runtime_log(string.format("[!] Float gagal untuk %s.%s", package, hint), true)
  if config.auto_grid then
    runtime_log(string.format("[!] Grid target terakhir: [%d,%d,%d,%d]", last_left, last_top, last_right, last_bottom), true)
  end
  return false
end

local function get_activity_name(package)
  local function normalize_activity(raw)
    raw = trim(raw)
    if raw == "" then
      return nil
    end
    if raw:find("/", 1, true) then
      local pkg, cls = raw:match("^([^/]+)/(.+)$")
      if not cls then
        return nil
      end
      if cls:sub(1, 1) == "." then
        return pkg .. cls
      end
      return cls
    end
    if raw:sub(1, 1) == "." then
      return package .. raw
    end
    if raw:find("%.", 1, true) then
      return raw
    end
    return package .. "." .. raw
  end

  local candidates, seen = {}, {}
  local function push(raw)
    local activity = normalize_activity(raw)
    if activity and activity ~= "" and not seen[activity] then
      seen[activity] = true
      candidates[#candidates + 1] = activity
    end
  end

  local queries = {
    "cmd package resolve-activity --brief --user 0 " .. package .. " 2>/dev/null",
    "cmd package resolve-activity --brief " .. package .. " 2>/dev/null",
    "pm resolve-activity --brief " .. package .. " 2>/dev/null",
    "pm dump " .. package .. " 2>/dev/null | grep -E 'android.intent.action.MAIN|android.intent.category.LAUNCHER' -A1 | grep 'cmp=' | head -3",
  }

  for _, cmd in ipairs(queries) do
    local _, output = run_su(cmd)
    for _, line in ipairs(split_lines(output)) do
      local cmp = line:match("cmp=([^%s]+)")
      if cmp then
        push(cmp)
      else
        local component = trim(line:match("([%w%._]+/[%w%._$]+)$") or "")
        if component ~= "" then
          push(component)
        end
      end
    end
  end

  push("com.roblox.client.ActivityNativeMain")
  push("com.roblox.client.RobloxActivity")
  push(package .. ".ActivityNativeMain")
  push(package .. ".RobloxActivity")

  for _, activity in ipairs(candidates) do
    local quoted_component = shell_quote(package .. "/" .. activity)
    local _, check_output = run_su("pm dump " .. package .. " 2>/dev/null | grep -F " .. quoted_component .. " | head -1")
    if trim(check_output) ~= "" then
      return activity
    end
  end

  return "com.roblox.client.ActivityNativeMain"
end

local function get_deeplink_activity(package)
  local _, output = run_su("pm dump " .. package .. " 2>/dev/null | grep -A3 'roblox:'")
  local activity = output:match(package:gsub("([%%%-%+%?%[%]%(%)%.%*%^%$])", "%%%1") .. "/%.?([A-Za-z0-9_.]+)")
  if activity then
    if not activity:find("%.") then
      return "com.roblox.client." .. activity
    end
    return activity
  end
  return nil
end

local function get_roblox_username(package, config, aggressive)
  local function valid(name)
    name = trim(name or "")
    if name == "" then
      return nil
    end
    if name:lower() == "unknown" then
      return nil
    end
    if #name < 3 or #name > 30 then
      return nil
    end
    if not name:match("^[A-Za-z0-9_.-]+$") then
      return nil
    end
    if name:lower():find("roblox", 1, true) then
      return nil
    end
    return name
  end

  local function extract_username(text)
    text = tostring(text or "")
    local patterns = {
      '"[Uu]ser[Nn]ame"%s*[:=]%s*"([A-Za-z0-9_.-]+)"',
      '"[Pp]layer[Nn]ame"%s*[:=]%s*"([A-Za-z0-9_.-]+)"',
      '"[Dd]isplay[Nn]ame"%s*[:=]%s*"([A-Za-z0-9_.-]+)"',
      '[Uu]ser[Nn]ame["%s=:>]+([A-Za-z0-9_.-]+)',
      '[Pp]layer[Nn]ame["%s=:>]+([A-Za-z0-9_.-]+)',
      '[Dd]isplay[Nn]ame["%s=:>]+([A-Za-z0-9_.-]+)',
      'name="[Uu]ser[Nn]ame"[^>]*>([^<]+)<',
      'name="[Pp]layer[Nn]ame"[^>]*>([^<]+)<',
      'name="[Dd]isplay[Nn]ame"[^>]*>([^<]+)<',
    }
    for _, pattern in ipairs(patterns) do
      local found = valid(text:match(pattern))
      if found then
        return found
      end
    end
    return nil
  end

  local cached = nil
  if type(config) == "table" and type(config.package_usernames) == "table" then
    cached = valid(config.package_usernames[package])
  end

  local attempts = aggressive and 3 or 1
  for attempt = 1, attempts do
    local _, logcat = run_su("logcat -d -t 1200 2>/dev/null | grep -Ei 'username|playername|displayname|" .. package .. "|roblox' | tail -260")
    local name = extract_username(logcat)
    if name then
      return name
    end

    if aggressive then
      local prefs_cmd = "for f in /data/data/" .. package .. "/shared_prefs/*.xml; do [ -f \"$f\" ] && cat \"$f\"; done 2>/dev/null | grep -Ei 'username|playername|displayname' | head -20"
      local _, prefs = run_su(prefs_cmd)
      name = extract_username(prefs)
      if name then
        return name
      end
      if attempt < attempts then
        sleep_seconds(1)
      end
    end
  end

  return cached or "unknown"
end

local function print_monitor_banner(lang, targets, config)
  print_brand_logo()
  print(tr(lang, "MONITOR DIMULAI", "MONITOR STARTED"))
  print(" targets      : " .. tostring(#targets))
  print(" interval     : " .. tostring(config.check_interval or 10) .. "s")
  print(" auto float   : " .. tostring(config.auto_float))
  print(" auto grid    : " .. tostring(config.auto_grid))
  print("================================================")
  for index, pkg in ipairs(targets) do
    print(string.format(" %d. %s", index, pkg))
  end
  print("================================================")
end

local function print_a10_taskbar_guide(lang)
  print("================================================")
  say(lang, "[A10 GUIDE] Aktifkan Taskbar dahulu:", "[A10 GUIDE] Enable Taskbar first:")
  say(lang, "  1) Freeform window support = ON", "  1) Freeform window support = ON")
  say(lang, "  2) Always save window sizes for apps = ON", "  2) Always save window sizes for apps = ON")
  say(lang, "  3) Always open apps in new windows = ON", "  3) Always open apps in new windows = ON")
  say(lang, "  4) Default window size = Half screen", "  4) Default window size = Half screen")
  say(lang, "Setelah itu monitor akan pakai: monkey -> tunggu -> deeplink https", "After that monitor will use: monkey -> wait -> https deeplink")
  print("================================================")
end

local function save_username_cache(config, usernames)
  local changed = false
  for pkg, name in pairs(usernames) do
    if name ~= "unknown" and trim(name) ~= "" then
      if config.package_usernames[pkg] ~= name then
        config.package_usernames[pkg] = name
        changed = true
      end
    end
  end
  if changed then
    save_config(config)
  end
end

local function is_package_running(package)
  local code, output = run_su("pidof " .. package .. " 2>/dev/null")
  local pid = trim(output)
  if code == 0 and pid ~= "" then
    return pid, true
  end
  local ps_cmd = "ps -A 2>/dev/null | grep -F '" .. package .. "' | grep -v grep | awk '{print $2}' | head -5"
  local _, ps_output = run_su(ps_cmd)
  ps_output = trim(ps_output)
  return ps_output, ps_output ~= ""
end

local function kill_roblox(package)
  runtime_log("[!] Restarting " .. package .. " & cleaning logs...", true)
  run_su("am force-stop " .. package)
  run_su("logcat -c")
end

local function is_launch_success(code, output)
  local low = tostring(output or ""):lower()
  return code == 0
    and not low:find("error:", 1, true)
    and not low:find("unknown option", 1, true)
    and not low:find("exception", 1, true)
end

-- Lock/reinforce system rotation so monkey launch doesn't reset it.
-- orientation_mode: "landscape" | "portrait" | "system" (no-op)
local function apply_rotation_lock(orientation_mode)
  if orientation_mode == "landscape" then
    run_su("settings put system accelerometer_rotation 0")
    run_su("settings put system user_rotation 1")
  elseif orientation_mode == "portrait" then
    run_su("settings put system accelerometer_rotation 0")
    run_su("settings put system user_rotation 0")
  end
  -- "system" = respect user/rotation-control-app setting, don't override
end

local function apply_initial_rotation(config)
  -- Always apply rotation lock BEFORE cache clear, regardless of auto_float/auto_grid
  -- This ensures rotation is locked before system events can reset it
  local orientation = tostring(config.float_orientation_mode or "system")
  if orientation == "system" then
    -- No forced rotation; system will use device setting or rotation control app
    return
  end
  -- Force rotation to landscape or portrait
  apply_rotation_lock(orientation)
  runtime_log(string.format("[*] Initial rotation lock applied: %s", orientation), true)
end

local function join_server(package, activity_name, grid_index, grid_total, config)
  local server_code = config.server_code
  if config.server_mode == "per_package" and type(config.server_code_by_package) == "table" and trim(config.server_code_by_package[package] or "") ~= "" then
    server_code = config.server_code_by_package[package]
  end
  local https_link = "https://www.roblox.com/share?code=" .. tostring(server_code or "") .. "&type=Server"
  local roblox_link = "roblox://navigation/share_links?code=" .. tostring(server_code or "") .. "&type=Server"
  runtime_log("[+] Joining server code: " .. short_code(server_code, 10), false)
  runtime_log("[+] Package: " .. package, false)
  local resolved = get_deeplink_activity(package)
  if resolved then
    runtime_log("[*] Deeplink activity ditemukan: " .. resolved, false)
  end

  local profile = get_device_profile()
  local sdk = profile.sdk or 30
  local is_android_10 = sdk < 31

  if is_android_10 then
    local orient = tostring(config.float_orientation_mode or "system")
    if config.auto_float then
      -- Float ON: launch via ActivitySplash with --windowingMode 5 (freeform)
      runtime_log("[*] [A10] Float ON: am start --windowingMode 5 --activity-clear-top", true)
      -- Re-lock rotation BEFORE launch so monkey/am start can't flip it
      apply_rotation_lock(orient)
      local splash = package .. "/.startup.ActivitySplash"
      local a10_float_cmds = {
        "am start -n '" .. splash .. "' -a android.intent.action.VIEW -d '" .. https_link .. "' --windowingMode 5 -f 0x10000000 --activity-clear-top",
        "am start -n '" .. splash .. "' --windowingMode 5 -f 0x10000000 --activity-clear-top",
      }
      local launched, task_id_hint, need_deeplink = false, nil, false
      for i, cmd in ipairs(a10_float_cmds) do
        local code, output = run_su(cmd)
        if is_launch_success(code, output) then
          launched = true
          task_id_hint = extract_task_id(output)
          if i == 2 then need_deeplink = true end
          runtime_log("[v] [A10] Float launched - " .. (i == 1 and "splash+deeplink" or "splash only"), true)
          break
        end
      end
      if launched and need_deeplink then
        sleep_seconds(math.max(3, tonumber(config.a10_launch_delay_seconds) or 10))
        run_su("am start -a android.intent.action.VIEW -d '" .. https_link .. "' " .. package)
      elseif not launched then
        run_su("am start -a android.intent.action.VIEW -d '" .. https_link .. "' " .. package)
      end
      -- Re-lock after deeplink fires (Roblox app may request portrait internally)
      apply_rotation_lock(orient)
      sleep_seconds(0.5)
      apply_float_grid(package, grid_index, grid_total, config, task_id_hint, true)
      return
    else
      -- Float OFF: Taskbar method (monkey -> wait -> deeplink)
      runtime_log("[*] [A10] Float OFF: Taskbar flow (monkey -> wait -> deeplink)", true)
      local monkey_cmd = "monkey -p '" .. package .. "' -c android.intent.category.LAUNCHER 1"
      -- Lock rotation BEFORE monkey so HOME intent doesn't break orientation
      apply_rotation_lock(orient)
      run_su(monkey_cmd)
      -- Re-lock immediately after monkey (HOME screen may reset rotation)
      apply_rotation_lock(orient)
      sleep_seconds(math.max(3, tonumber(config.a10_launch_delay_seconds) or 10))
      local a10_commands = {
        "am start -a android.intent.action.VIEW -d '" .. https_link .. "' " .. package,
        "am start -a android.intent.action.VIEW -d '" .. https_link .. "' -p '" .. package .. "'",
        "am start -a android.intent.action.VIEW -d '" .. roblox_link .. "' " .. package,
      }
      local launched, task_id_hint = false, nil
      for _, cmd in ipairs(a10_commands) do
        local code, output = run_su(cmd)
        if is_launch_success(code, output) then
          launched = true
          task_id_hint = extract_task_id(output)
          runtime_log("[v] [A10] Launched via Taskbar flow", true)
          break
        end
      end
      if not launched then
        run_su("am start -a android.intent.action.VIEW -d '" .. https_link .. "' " .. package)
      end
      -- Final re-lock: Roblox can request portrait orientation during startup
      apply_rotation_lock(orient)
      sleep_seconds(0.5)
      apply_float_grid(package, grid_index, grid_total, config, task_id_hint, true)
      return
    end
  end

  local activities = {}
  local function add_activity(name)
    if name and name ~= "" then
      for _, existing in ipairs(activities) do
        if existing == name then return end
      end
      if not name:lower():find("splash", 1, true) then
        activities[#activities + 1] = name
      end
    end
  end
  add_activity(activity_name)
  add_activity("com.roblox.client.ActivityNativeMain")
  add_activity(package .. ".ActivityNativeMain")
  add_activity("com.roblox.client.RobloxActivity")
  add_activity(resolved)

  local launch_bounds = ""
  if config.auto_grid then
    local left, top, right, bottom = get_grid_bounds(grid_index, grid_total, profile.width, profile.height, config)
    launch_bounds = string.format("%d,%d,%d,%d", left, top, right, bottom)
  end

  local launched, task_id_hint = false, nil
  local primary_commands = {
    "am start -a android.intent.action.VIEW -d '" .. https_link .. "' -p '" .. package .. "' --windowingMode 5 --activity-clear-task",
    "am start -a android.intent.action.VIEW -d '" .. https_link .. "' -p '" .. package .. "' --windowingMode 5",
    "am start -a android.intent.action.VIEW -d '" .. https_link .. "' -p '" .. package .. "'",
  }
  for _, cmd in ipairs(primary_commands) do
    local code, output = run_su(cmd)
    if is_launch_success(code, output) then
      launched = true
      task_id_hint = extract_task_id(output)
      runtime_log("[v] Launched via A12+/A16 primary flow", true)
      break
    end
  end

  if not launched then
    runtime_log("[*] [A12+] Fallback ke flow activity-based (monitor.py style)", false)
  end

  for _, activity in ipairs(activities) do
    if launched then
      break
    end
    runtime_log("[*] Trying: -n " .. package .. "/" .. activity, false)
    runtime_log("[*] [A12+] Launch with bounds/float pre-applied", false)

    local commands = {}
    if config.auto_float then
      if config.auto_grid and launch_bounds ~= "" then
        commands[#commands + 1] = "am start --windowingMode 5 --activity-launch-bounds " .. launch_bounds .. " -n '" .. package .. "/" .. activity .. "' -a android.intent.action.VIEW -d '" .. https_link .. "'"
      end
      commands[#commands + 1] = "am start --windowingMode 5 -n '" .. package .. "/" .. activity .. "' -a android.intent.action.VIEW -d '" .. https_link .. "'"
    elseif config.auto_grid and launch_bounds ~= "" then
      commands[#commands + 1] = "am start --activity-launch-bounds " .. launch_bounds .. " -n '" .. package .. "/" .. activity .. "' -a android.intent.action.VIEW -d '" .. https_link .. "'"
    end
    commands[#commands + 1] = "am start -n '" .. package .. "/" .. activity .. "' -a android.intent.action.VIEW -d '" .. https_link .. "'"
    commands[#commands + 1] = "am start -n '" .. package .. "/" .. activity .. "' -a android.intent.action.VIEW -d '" .. roblox_link .. "'"

    for _, cmd in ipairs(commands) do
      local code, output = run_su(cmd)
      if is_launch_success(code, output) then
        launched = true
        task_id_hint = extract_task_id(output)
        runtime_log("[v] Launched via " .. activity, true)
        break
      end
    end
  end
  if not launched then
    run_su("am start -a android.intent.action.VIEW -d '" .. https_link .. "' -p '" .. package .. "'")
  end

  sleep_seconds(0.5)
  apply_float_grid(package, grid_index, grid_total, config, task_id_hint, false)
end

local function read_recent_roblox_logs(config)
  local lines = math.max(200, math.min(tonumber(config.log_scan_lines or 800) or 800, 1500))
  local _, output = run_su("logcat -d -t " .. tostring(lines) .. " 2>/dev/null | grep -Ei 'Roblox  :|rbx\\.|com\\.roblox\\.client' | tail -250")
  return output
end

local function check_game_status(config)
  local logs = read_recent_roblox_logs(config)
  if trim(logs) == "" then
    return false, nil, false
  end
  -- Disconnect code 276 = kicked dari server, tidak rejoin ulang
  if logs:match("Sending disconnect with reason:%s*276") then
    return true, "Disconnect kode 276 (kicked dari server)", true
  end
  local patterns = {
    {"Sending disconnect with reason:%s*277", "Disconnect reason 277"},
    {"Sending disconnect with reason:%s*26%d", "AFK disconnect"},
    {"Sending disconnect with reason:%s*279", "Disconnect reason 279"},
    {"Sending disconnect with reason:%s*27%d"},
    {"Lost connection with reason%s*:%s*Lost connection to the game server", "Lost connection to game server"},
    {"%[FLog::Network%]%s+Connection lost", "Connection lost"},
    {"ID_CONNECTION_LOST", "ID_CONNECTION_LOST"},
    {"AckTimeout", "AckTimeout"},
    {"SignalRCoreError.*Disconnected", "SignalR disconnected"},
    {"Session Transition FSM:%s*Error Occurred", "Session transition error"},
  }
  for _, item in ipairs(patterns) do
    if logs:match(item[1]) then
      return true, item[2], false
    end
  end
  return false, nil, false
end

local function render_monitor_snapshot(packages_info, memory_info, check_count)
  local _, free, pct = table.unpack(memory_info)
  -- Total box width capped to terminal, min 34
  local total_w = math.max(34, math.min(term_cols(), 58))
  -- left_w + right_w + 3 = total_w
  local left_w  = math.floor((total_w - 3) * 0.57)
  local right_w = (total_w - 3) - left_w
  local full_inner = total_w - 2  -- header rows without divider

  local function pad(s, w, align)
    s = tostring(s or "")
    if #s > w then return s:sub(1, w - 1) .. "~" end
    local sp = w - #s
    if align == "center" then
      local lp = math.floor(sp / 2)
      return string.rep(" ", lp) .. s .. string.rep(" ", sp - lp)
    elseif align == "right" then
      return string.rep(" ", sp) .. s
    end
    return s .. string.rep(" ", sp)
  end

  local function row_full(s)  return "\xe2\x95\x91" .. pad(s, full_inner, "center") .. "\xe2\x95\x91" end
  local function row(l, r)    return "\xe2\x95\x91" .. pad(l, left_w) .. "\xe2\x95\x91" .. pad(r, right_w) .. "\xe2\x95\x91" end
  local function hline(lc, mc, rc)
    return lc .. string.rep("\xe2\x95\x90", left_w) .. mc .. string.rep("\xe2\x95\x90", right_w) .. rc
  end
  local function htop()
    return "\xe2\x95\x94" .. string.rep("\xe2\x95\x90", full_inner) .. "\xe2\x95\x97"
  end
  local function hbot()
    return "\xe2\x95\x9a" .. string.rep("\xe2\x95\x90", left_w) .. "\xe2\x95\xa9" .. string.rep("\xe2\x95\x90", right_w) .. "\xe2\x95\x9d"
  end

  local out = {}
  local function push(s) out[#out + 1] = s end

  -- Brand header
  push(htop())
  push(row_full("X  N  N  N  S  E  T  S"))
  push(row_full("v" .. VERSION))

  -- Column headers
  push(hline("\xe2\x95\xa0", "\xe2\x95\xa6", "\xe2\x95\xa3"))
  push(row(" PACKAGE", " STATUS"))
  push(hline("\xe2\x95\xa0", "\xe2\x95\xac", "\xe2\x95\xa3"))

  -- One row per package (2 lines: name | username + status)
  local n = #packages_info
  local online_count = 0
  for idx, info in ipairs(packages_info) do
    local pkg, username, running = info[1], info[2], info[3]
    if running then online_count = online_count + 1 end
    local short_pkg  = " " .. pkg:gsub("com%.roblox%.", "rblx.")
    local user_str   = (username and username ~= "unknown" and username ~= "") and username or "unknown"
    local status_str = running and " ONLINE" or " OFFLINE"
    push(row(short_pkg, ""))
    push(row(" (" .. user_str .. ")", status_str))
    if idx < n then
      push(hline("\xe2\x95\xa0", "\xe2\x95\xac", "\xe2\x95\xa3"))
    end
  end

  -- Footer: system info
  push(hline("\xe2\x95\xa0", "\xe2\x95\xac", "\xe2\x95\xa3"))
  push(row(" System Memory", string.format(" [%d/%d]", online_count, n)))
  push(row(string.format(" Free: %dMB", free), string.format(" (%d%%)", pct)))
  push(row(" " .. os.date("%H:%M:%S"), " Checking"))
  push(hbot())

  return table.concat(out, "\n")
end

local function render_monitor_safe_line(packages_info, memory_info, loop_count)
  local _, free, pct = table.unpack(memory_info)
  local running_count = 0
  local parts = {}
  for _, info in ipairs(packages_info) do
    local pkg, username, running = info[1], info[2], info[3]
    if running then running_count = running_count + 1 end
    local short_pkg = pkg:gsub("com%.roblox%.", "rblx.")
    local user_str  = (username and username ~= "unknown" and username ~= "") and username or "?"
    local mark = running and "\xe2\x97\x8f" or "\xe2\x97\x8b"  -- ● or ○
    parts[#parts + 1] = short_pkg .. "(" .. user_str .. ")" .. mark
  end
  local pkg_summary = table.concat(parts, " ")
  local status = string.format("[%s] %d/%d ONLINE RAM:%dMB(%d%%) | %s",
    os.date("%H:%M"), running_count, #packages_info, free, pct, pkg_summary)
  return short_text(status, math.max(40, term_cols()))
end

local function clear_cache_and_kill_targets(config, lang)
  -- Apply rotation FIRST before clearing cache, so system doesn't reset rotation during cache clear
  apply_initial_rotation(config)
  
  local targets = resolve_cache_packages(config)
  if #targets == 0 then
    say(lang, "[!] Tidak ada package target yang terkonfigurasi/terdeteksi.", "[!] No target package configured/detected.")
    return
  end
  for _, pkg in ipairs(targets) do
    print(string.format("[*] %s: %s", tr(lang, "Membersihkan", "Cleaning"), pkg))
    run_su("am force-stop " .. pkg)
    run_su("rm -rf /data/data/" .. pkg .. "/cache/* /data/data/" .. pkg .. "/code_cache/* 2>/dev/null")
  end
end

local function run_monitor(config, lang)
  if not check_root_permission() then
    say(lang, "[!] Akses root ditolak", "[!] Root access denied")
    return 1
  end
  clear_screen()
  clear_cache_and_kill_targets(config, lang)
  run_cmd("command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock")
  local monitor_stty_state = setup_monitor_hotkeys()
  local function monitor_cleanup(exit_message)
    restore_monitor_hotkeys(monitor_stty_state)
    run_cmd("command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock")
    if RUNTIME_STATE.monitor_compact then
      clear_terminal_line()
      print("")
    end
    if exit_message and exit_message ~= "" then
      runtime_log(exit_message, true)
    end
  end

  local function consume_monitor_command(command)
    if command == "quit" then
      monitor_cleanup(tr(lang,
        "[*] Hotkey q terdeteksi, keluar dari script.",
        "[*] Hotkey q detected, quitting script."))
      return "quit"
    elseif command == "stop" then
      monitor_cleanup(tr(lang,
        "[*] Hotkey s/Ctrl+Z terdeteksi, stop monitor dan kembali ke menu.",
        "[*] Hotkey s/Ctrl+Z detected, stopping monitor and returning to menu."))
      return "menu"
    end
    return nil
  end

  runtime_log(tr(lang,
    "[HOTKEY] q=keluar script | s=stop monitor ke menu | Ctrl+Z=stop monitor",
    "[HOTKEY] q=quit script | s=stop monitor to menu | Ctrl+Z=stop monitor"), true)

  local installed = select(1, scan_packages())
  local targets = resolve_target_packages(config)
  if #targets == 0 then targets = installed end
  if #targets == 0 then targets = {"com.roblox.client"} end
  local profile = get_device_profile()
  local is_android_10 = (profile.sdk or 30) < 31
  print_monitor_banner(lang, targets, config)
  if is_android_10 then
    if not config.auto_float then
      print_a10_taskbar_guide(lang)
    else
      print("[*] [A10] Float mode ON — pakai am start --windowingMode 5 (tanpa Taskbar)")
    end
  end
  local activity_map, usernames = {}, {}
  for _, pkg in ipairs(targets) do
    activity_map[pkg] = get_activity_name(pkg)
    usernames[pkg] = get_roblox_username(pkg, config, false)
  end
  save_username_cache(config, usernames)
  run_su("logcat -c")
  local early_cmd = monitor_sleep_with_control(1)
  local early_result = consume_monitor_command(early_cmd)
  if early_result then
    return early_result
  end
  local pkg_state = {}
  local grid_index_map = {}
  for i, pkg in ipairs(targets) do
    pkg_state[pkg] = {join_time = os.time(), last_activity = os.time()}
    grid_index_map[pkg] = i - 1
  end
  local grid_total = #targets
  local initial_missing = {}
  for _, pkg in ipairs(targets) do
    local _, running = is_package_running(pkg)
    if running then
      apply_float_grid(pkg, grid_index_map[pkg], grid_total, config, nil, is_android_10)
    else
      initial_missing[#initial_missing + 1] = pkg
    end
  end

  if #initial_missing > 0 and (config.enable_immediate_launch ~= false) then
    runtime_log(string.format("[*] Initial launch: %d app belum jalan, launch langsung...", #initial_missing), true)
    local initial_gap = math.max(1, tonumber(config.initial_launch_gap_seconds) or 8)
    local username_delay = math.max(0, tonumber(config.username_fetch_delay_seconds) or 5)
    local use_aggressive = (config.aggressive_username_detection ~= false)
    for index, pkg in ipairs(initial_missing) do
      join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total, config)
      pkg_state[pkg] = {join_time = os.time(), last_activity = os.time()}
      if username_delay > 0 then
        local cmd = monitor_sleep_with_control(username_delay)
        local result = consume_monitor_command(cmd)
        if result then
          return result
        end
      end
      usernames[pkg] = get_roblox_username(pkg, config, use_aggressive)
      save_username_cache(config, {[pkg] = usernames[pkg]})
      if index < #initial_missing then
        local cmd = monitor_sleep_with_control(initial_gap)
        local result = consume_monitor_command(cmd)
        if result then
          return result
        end
      end
    end
  end

  local check_count = 0
  local loop_count = 0
  local last_snapshot = nil
  local last_safe_line = nil
  local ui_mode = (config.monitor_ui_mode == "live") and "live" or "safe"
  RUNTIME_STATE.monitor_ui_mode = ui_mode
  RUNTIME_STATE.monitor_compact = (ui_mode == "safe")
  local log_check_every_cycles = math.max(1, tonumber(config.log_check_every_cycles) or 3)
  local startup_grace_seconds = math.max(10, tonumber(config.startup_grace_seconds) or 45)
  if ui_mode == "safe" then
    print("")
  end
  while true do
    local cmd_start = poll_monitor_control_key()
    local start_result = consume_monitor_command(cmd_start)
    if start_result then
      return start_result
    end

    loop_count = loop_count + 1
    check_count = (check_count % math.max(1, #targets)) + 1
    local packages_info = {}
    for _, pkg in ipairs(targets) do
      local _, running = is_package_running(pkg)
      packages_info[#packages_info + 1] = {pkg, usernames[pkg] or "unknown", running}
    end
    local memory_info = {get_memory_info()}
    if ui_mode == "live" then
      local snapshot = render_monitor_snapshot(packages_info, memory_info, check_count)
      if snapshot ~= last_snapshot then
        clear_screen()
        print(snapshot)
        last_snapshot = snapshot
      end
    else
      local safe_line = render_monitor_safe_line(packages_info, memory_info, loop_count)
      if safe_line ~= last_safe_line then
        monitor_write_status(safe_line)
        last_safe_line = safe_line
      end
    end
    local crashed, crashed_pkgs = {}, {}
    for _, info in ipairs(packages_info) do
      local pkg = info[1]
      local running = info[3]
      if running then
        pkg_state[pkg].last_activity = os.time()
      else
        local age = os.time() - (pkg_state[pkg].join_time or 0)
        if age >= startup_grace_seconds then
          crashed_pkgs[#crashed_pkgs + 1] = pkg
        end
      end
    end
    for i, pkg in ipairs(crashed_pkgs) do
      crashed[pkg] = true
      runtime_log(string.format("[%s] %s Crash/Mati", os.date("%H:%M:%S"), pkg), true)
      kill_roblox(pkg)
      join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total, config)
      pkg_state[pkg] = {join_time = os.time(), last_activity = os.time()}
      local _ud1 = math.max(0, tonumber(config.username_fetch_delay_seconds) or 5)
      if _ud1 > 0 then
        local cmd = monitor_sleep_with_control(_ud1)
        local result = consume_monitor_command(cmd)
        if result then
          return result
        end
      end
      usernames[pkg] = get_roblox_username(pkg, config, config.aggressive_username_detection ~= false)
      save_username_cache(config, {[pkg] = usernames[pkg]})
      last_snapshot = nil
      last_safe_line = nil
      if i < #crashed_pkgs then
        local cmd = monitor_sleep_with_control(config.multi_launch_delay_seconds or 30)
        local result = consume_monitor_command(cmd)
        if result then
          return result
        end
      end
    end
    local is_error, reason, skip_rejoin = false, nil, false
    if (loop_count % log_check_every_cycles) == 0 then
      is_error, reason, skip_rejoin = check_game_status(config)
    end
    if is_error then
      if skip_rejoin then
        runtime_log(string.format("[%s] [!] %s - tidak rejoin otomatis.", os.date("%H:%M:%S"), reason or "skip"), true)
        run_su("logcat -c")  -- bersihkan log agar tidak re-trigger
      else
        for _, info in ipairs(packages_info) do
          local pkg, _, running = info[1], info[2], info[3]
          if running and not crashed[pkg] then
            runtime_log(string.format("[%s] Error: %s [%s]", os.date("%H:%M:%S"), reason or "unknown", pkg), true)
            kill_roblox(pkg)
            join_server(pkg, activity_map[pkg], grid_index_map[pkg], grid_total, config)
            pkg_state[pkg] = {join_time = os.time(), last_activity = os.time()}
            local _ud2 = math.max(0, tonumber(config.username_fetch_delay_seconds) or 5)
            if _ud2 > 0 then
              local cmd = monitor_sleep_with_control(_ud2)
              local result = consume_monitor_command(cmd)
              if result then
                return result
              end
            end
            usernames[pkg] = get_roblox_username(pkg, config, config.aggressive_username_detection ~= false)
            save_username_cache(config, {[pkg] = usernames[pkg]})
            last_snapshot = nil
            last_safe_line = nil
            break
          end
        end
      end
    end
    local cmd_wait = monitor_sleep_with_control(config.check_interval or 10)
    local wait_result = consume_monitor_command(cmd_wait)
    if wait_result then
      return wait_result
    end
  end
end

local function setup_boot_autorun(lang)
  local boot_dir = os.getenv("HOME") .. "/.termux/boot"
  run_cmd("mkdir -p " .. shell_quote(boot_dir))
  local path = boot_dir .. "/roblox-monitor.sh"
  local _, cwd = run_cmd("pwd")
  local repo_dir = trim(cwd)
  local script = {
    "#!/data/data/com.termux/files/usr/bin/sh",
    "LOG_FILE=\"$HOME/.termux/boot/roblox-monitor.log\"",
    "while [ \"$(getprop sys.boot_completed 2>/dev/null)\" != \"1\" ]; do sleep 2; done",
    "sleep 20",
    "cd " .. shell_quote(repo_dir),
    "if [ -x ./start.sh ]; then",
    "  nohup ./start.sh --autorun >> \"$LOG_FILE\" 2>&1 &",
    "else",
    "  echo \"[!] start.sh tidak ditemukan / tidak executable\" >> \"$LOG_FILE\"",
    "fi",
  }
  write_file(path, table.concat(script, "\n") .. "\n")
  run_cmd("chmod +x " .. shell_quote(path))
  clear_screen()
  say(lang, "[v] Boot script dibuat: " .. path, "[v] Boot script created: " .. path)
  say(lang, "[*] Wajib install app Termux:Boot dan buka 1x setelah install.", "[*] You must install Termux:Boot app and open it once after install.")
  say(lang, "[*] Log autorun: ~/.termux/boot/roblox-monitor.log", "[*] Autorun log: ~/.termux/boot/roblox-monitor.log")
end

local function remove_boot_autorun(lang)
  local path = os.getenv("HOME") .. "/.termux/boot/roblox-monitor.sh"
  os.remove(path)
  say(lang, "[v] Boot script dihapus.", "[v] Boot script removed.")
end

local function misc_menu(config, lang)
  while true do
    print_header(lang)
    print("1. " .. tr(lang, "Setup auto jalan setelah reboot", "Setup auto exec after reboot"))
    print("2. " .. tr(lang, "Nonaktifkan auto jalan setelah reboot", "Disable auto exec after reboot"))
    print("3. " .. tr(lang, "Update repo (git pull)", "Update repo (git pull)"))
    print("0. " .. tr(lang, "Kembali", "Back"))
    local choice = prompt_menu(lang, {"1","2","3","0"}, "0")
    if choice == "1" then
      setup_boot_autorun(lang)
    elseif choice == "2" then
      remove_boot_autorun(lang)
    elseif choice == "3" then
      run_cmd("git pull")
    else
      return
    end
    prompt(tr(lang, "Tekan Enter", "Press Enter"), "")
  end
end

local function pick_language(current)
  print_header(current or "id", "PILIH BAHASA", "CHOOSE LANGUAGE")
  print("1. Indonesia")
  print("2. English")
  local raw = prompt("Choice", "1")
  if raw == "2" then
    return "en"
  end
  return "id"
end

local function main_menu(config)
  local lang = config.language or "id"
  while true do
    print_header(lang)
    if lang == "en" then
      print("1. Setup configuration (First Run Needed)")
      print("2. Edit config")
      print("3. Optimize + Launch Apps")
      print("4. Misc")
      print("0. Exit")
    else
      print("1. Setup configuration (Wajib First Run)")
      print("2. Ubah konfigurasi")
      print("3. Optimalkan + Buka Aplikasi")
      print("4. Lainnya")
      print("0. Keluar")
    end
    local choice = prompt_menu(lang, {"1","2","3","4","0"}, "0")
    if choice == "1" then
      config = quick_setup(config, lang)
      save_config(config)
    elseif choice == "2" then
      config = edit_config(config, lang)
      save_config(config)
    elseif choice == "3" then
      save_config(config)
      clear_screen()
      local monitor_result = run_monitor(config, lang)
      if monitor_result == "quit" then
        return
      end
    elseif choice == "4" then
      misc_menu(config, lang)
    else
      return
    end
  end
end

local args = {...}
local options = { mode = nil, lang = nil, autorun = false }
local i = 1
while i <= #args do
  local arg = args[i]
  if arg == "--mode" then
    i = i + 1
    options.mode = args[i]
  elseif arg == "--lang" then
    i = i + 1
    options.lang = args[i]
  elseif arg:match("^%-%-lang=") then
    options.lang = arg:match("^%-%-lang=(.+)$")
  elseif arg == "--autorun" then
    options.autorun = true
  end
  i = i + 1
end

local config = load_config()
if options.lang == "en" or options.lang == "id" then
  config.language = options.lang
elseif not options.autorun and not options.mode then
  config.language = pick_language(config.language)
end

if not check_root_permission() then
  local lang = (options.lang == "en" or options.lang == "id") and options.lang or (config.language or "id")
  os.execute("clear")
  say(lang,
    "[!] Script ini butuh akses root (su). Pastikan device sudah root dan Termux diberi izin superuser, lalu jalankan ulang.",
    "[!] This script requires root access (su). Make sure the device is rooted and Termux has superuser permission, then run it again.")
  os.exit(1)
end

if options.mode == "setup" then
  config = quick_setup(config, config.language)
  save_config(config)
  os.exit(0)
elseif options.mode == "edit" then
  config = edit_config(config, config.language)
  save_config(config)
  os.exit(0)
elseif options.mode == "get-target-packages" then
  for _, pkg in ipairs(resolve_target_packages(config)) do
    print(pkg)
  end
  os.exit(0)
elseif options.mode == "get-cache-packages" then
  for _, pkg in ipairs(resolve_cache_packages(config)) do
    print(pkg)
  end
  os.exit(0)
elseif options.mode == "monitor" or options.autorun then
  save_config(config)
  os.exit(run_monitor(config, config.language) or 0)
else
  save_config(config)
  main_menu(config)
end