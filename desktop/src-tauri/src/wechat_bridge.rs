//! WeChat (Weixin) connection bridge for the desktop workbench.
//!
//! SztuCode does not speak the WeChat protocol. The conversation is carried by
//! the OpenClaw Weixin channel plugin (`openclaw-weixin`); this module only
//! drives that plugin through the `openclaw` CLI and mirrors the result into
//! the connection panel:
//!
//! * it starts `openclaw channels login --channel openclaw-weixin`, keeps the
//!   process alive so the user can scan, and captures the terminal QR code plus
//!   the fallback link from its stdout;
//! * it reads the plugin's account index to decide whether a scan succeeded;
//! * it stores the session the conversation is bound to in
//!   `~/.sztu/wechat-bridge.json`, which the ACP bridge reads back through
//!   `py-runtime/src/sztu_code/core/wechat/binding.py`.
//!
//! The CLI is launched through a real `node.exe` running `openclaw.mjs` when
//! both can be found. A launcher that is itself a bare `node` shim (no `.exe`
//! suffix) makes OpenClaw's internal re-spawn fail, which is why `openclaw` can
//! print `--version` yet never produce a login QR.

use std::{
    io::{BufRead, BufReader},
    path::{Path, PathBuf},
    process::{Child, Command as StdCommand, Stdio},
    sync::{Arc, Mutex as StdMutex},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use serde::{Deserialize, Serialize};
use tauri::State;

/// Channel id of the OpenClaw Weixin plugin.
pub const DEFAULT_CHANNEL: &str = "openclaw-weixin";
/// How long a pending login is considered scannable.
const LOGIN_TTL_SECS: u64 = 300;
/// How long `wechat_login_start` waits for the QR before giving up.
const QR_WAIT: Duration = Duration::from_secs(25);
/// Characters used by terminal QR renderers.
const QR_BLOCK_CHARS: [char; 5] = ['█', '▀', '▄', '▌', '▐'];
/// Markers the plugin prints once the scan has been confirmed.
const CONNECTED_MARKERS: [&str; 8] = [
    "登录成功",
    "连接成功",
    "扫码成功",
    "已成功连接",
    "login successful",
    "connected successfully",
    "scan succeeded",
    "authenticated",
];

// ---------------------------------------------------------------------------
// Front-end contract (mirrors desktop/src/services/wechat-bridge.ts)
// ---------------------------------------------------------------------------

#[derive(Serialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct WeChatStatus {
    pub state: &'static str,
    pub account: Option<String>,
    pub bound_session_id: Option<String>,
    /// Last failure worth showing in the panel, e.g. a broken OpenClaw install.
    pub last_error: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Default)]
#[serde(rename_all = "camelCase")]
pub struct WeChatLoginTicket {
    /// Terminal QR code (rendered as monospace text) or an image URL.
    pub qr: String,
    /// Fallback link printed next to the QR, for clients that cannot scan text.
    pub link: Option<String>,
    pub expires_at: Option<String>,
}

// ---------------------------------------------------------------------------
// Persisted state (~/.sztu/wechat-bridge.json)
// ---------------------------------------------------------------------------

#[derive(Serialize, Deserialize, Default, Clone)]
#[serde(rename_all = "camelCase")]
pub struct BridgeState {
    #[serde(default)]
    pub channel: Option<String>,
    #[serde(default)]
    pub bound_session_id: Option<String>,
    #[serde(default)]
    pub login: Option<LoginRecord>,
}

#[derive(Serialize, Deserialize, Clone)]
#[serde(rename_all = "camelCase")]
pub struct LoginRecord {
    pub pid: u32,
    pub started_at: u64,
    pub expires_at: u64,
    #[serde(default)]
    pub connected: bool,
}

fn home_dir() -> Result<PathBuf, String> {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(PathBuf::from)
        .ok_or_else(|| "无法确定用户目录".to_string())
}

/// Shared with `sztu_code.core.wechat.binding`; keep both in sync.
pub fn bridge_state_path() -> Result<PathBuf, String> {
    Ok(home_dir()?.join(".sztu").join("wechat-bridge.json"))
}

fn openclaw_config_path() -> Result<PathBuf, String> {
    if let Some(explicit) = std::env::var_os("OPENCLAW_CONFIG_PATH") {
        return Ok(PathBuf::from(explicit));
    }
    Ok(home_dir()?.join(".openclaw").join("openclaw.json"))
}

fn openclaw_state_dir() -> Result<PathBuf, String> {
    if let Some(explicit) = std::env::var_os("OPENCLAW_STATE_DIR") {
        return Ok(PathBuf::from(explicit));
    }
    Ok(home_dir()?.join(".openclaw").join("state"))
}

fn load_bridge_state() -> BridgeState {
    bridge_state_path()
        .ok()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

fn save_bridge_state(state: &BridgeState) -> Result<(), String> {
    let path = bridge_state_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let text = serde_json::to_string_pretty(state).map_err(|error| error.to_string())?;
    std::fs::write(path, text).map_err(|error| error.to_string())
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|delta| delta.as_secs())
        .unwrap_or(0)
}

// ---------------------------------------------------------------------------
// OpenClaw config / account index inspection
// ---------------------------------------------------------------------------

#[derive(Debug, Default, PartialEq, Eq)]
pub struct ChannelSnapshot {
    /// The Weixin plugin is installed *and* enabled in `openclaw.json`.
    pub plugin_enabled: bool,
    /// `channels.<channel>.enabled`, defaulting to enabled when absent.
    pub channel_enabled: bool,
    pub default_account: Option<String>,
    pub accounts: Vec<String>,
}

/// Read the channel/plugin view out of an `openclaw.json` payload.
pub fn channel_snapshot(config_json: &str, channel: &str) -> ChannelSnapshot {
    let Ok(root) = serde_json::from_str::<serde_json::Value>(config_json) else {
        return ChannelSnapshot::default();
    };

    let plugin_enabled = root
        .get("plugins")
        .and_then(|plugins| plugins.get("entries"))
        .and_then(|entries| entries.get(channel))
        .and_then(|entry| entry.get("enabled"))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);

    let channel_cfg = root
        .get("channels")
        .and_then(|channels| channels.get(channel));
    let channel_enabled = channel_cfg
        .and_then(|cfg| cfg.get("enabled"))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(true);
    let default_account = channel_cfg
        .and_then(|cfg| cfg.get("defaultAccount"))
        .and_then(serde_json::Value::as_str)
        .map(str::to_string);
    let accounts = channel_cfg
        .and_then(|cfg| cfg.get("accounts"))
        .and_then(serde_json::Value::as_object)
        .map(|map| map.keys().cloned().collect())
        .unwrap_or_default();

    ChannelSnapshot {
        plugin_enabled,
        channel_enabled,
        default_account,
        accounts,
    }
}

/// The plugin writes the account ids registered by QR login into this index.
fn read_account_index() -> Vec<String> {
    let Ok(path) = openclaw_state_dir() else {
        return Vec::new();
    };
    let path = path.join(DEFAULT_CHANNEL).join("accounts.json");
    let Ok(text) = std::fs::read_to_string(path) else {
        return Vec::new();
    };
    let Ok(value) = serde_json::from_str::<serde_json::Value>(&text) else {
        return Vec::new();
    };
    let mut accounts = Vec::new();
    collect_account_ids(&value, &mut accounts);
    accounts.sort();
    accounts.dedup();
    accounts
}

/// OpenClaw versions have used both a string array and an object keyed by
/// account id for this index. Accept the small set of object forms without
/// making the connection state depend on one plugin release.
fn collect_account_ids(value: &serde_json::Value, output: &mut Vec<String>) {
    match value {
        serde_json::Value::String(id) if !id.trim().is_empty() => output.push(id.clone()),
        serde_json::Value::Array(items) => {
            for item in items {
                collect_account_ids(item, output);
            }
        }
        serde_json::Value::Object(map) => {
            for field in ["id", "accountId", "account_id", "account"] {
                if let Some(id) = map.get(field).and_then(serde_json::Value::as_str) {
                    if !id.trim().is_empty() {
                        output.push(id.to_string());
                        return;
                    }
                }
            }
            for field in ["accounts", "items", "data"] {
                if let Some(items) = map.get(field) {
                    collect_account_ids(items, output);
                    return;
                }
            }
            for (key, value) in map {
                if value.is_object() || value.is_array() {
                    if !key.trim().is_empty() {
                        output.push(key.clone());
                    }
                }
            }
        }
        _ => {}
    }
}

fn strip_ansi(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    while let Some(ch) = chars.next() {
        if ch == '\u{1b}' {
            // CSI sequence: ESC [ ... final-byte
            if chars.peek() == Some(&'[') {
                chars.next();
                for next in chars.by_ref() {
                    if ('@'..='~').contains(&next) {
                        break;
                    }
                }
            }
            continue;
        }
        out.push(ch);
    }
    out
}

// ---------------------------------------------------------------------------
// Parsing the login output
// ---------------------------------------------------------------------------

#[derive(Debug, Default, PartialEq, Eq)]
pub struct LoginOutput {
    /// Longest contiguous block-character run: the terminal QR code.
    pub qr: Option<String>,
    /// `https://...` fallback link printed below the QR.
    pub link: Option<String>,
    /// The plugin reported a confirmed scan.
    pub connected: bool,
}

/// Extract the QR block, fallback link and success marker from login output.
pub fn parse_login_output(text: &str) -> LoginOutput {
    let cleaned = strip_ansi(text);
    let mut best_qr: Vec<String> = Vec::new();
    let mut current: Vec<String> = Vec::new();
    let mut link: Option<String> = None;
    let mut connected = false;

    for line in cleaned.lines() {
        let trimmed = line.trim();
        if !trimmed.is_empty() && QR_BLOCK_CHARS.iter().any(|ch| trimmed.contains(*ch)) {
            current.push(line.trim_end().to_string());
            continue;
        }
        if !current.is_empty() {
            if current.len() > best_qr.len() {
                best_qr = std::mem::take(&mut current);
            } else {
                current.clear();
            }
        }
        if link.is_none()
            && (trimmed.starts_with("https://") || trimmed.starts_with("http://"))
            && !trimmed.contains(char::is_whitespace)
        {
            link = Some(trimmed.to_string());
        }
        let lower = trimmed.to_ascii_lowercase();
        if CONNECTED_MARKERS.iter().any(|marker| {
            if marker.is_ascii() {
                lower.contains(marker)
            } else {
                trimmed.contains(marker)
            }
        }) {
            connected = true;
        }
    }
    if current.len() > best_qr.len() {
        best_qr = current;
    }

    LoginOutput {
        qr: (!best_qr.is_empty()).then(|| best_qr.join("\n")),
        link,
        connected,
    }
}

// ---------------------------------------------------------------------------
// Locating a working OpenClaw launcher
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Launcher {
    pub program: PathBuf,
    pub args: Vec<String>,
}

impl Launcher {
    pub fn command(&self) -> StdCommand {
        let mut command = StdCommand::new(&self.program);
        command.args(&self.args);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x0800_0000;
            command.creation_flags(CREATE_NO_WINDOW);
        }
        command
    }
}

fn is_executable_file(path: &Path) -> bool {
    path.is_file()
}

/// A `node` shim without a `.exe` suffix cannot be re-spawned by OpenClaw's
/// launcher, so Windows candidates must keep their extension.
fn is_usable_node(path: &Path) -> bool {
    if !is_executable_file(path) {
        return false;
    }
    #[cfg(windows)]
    {
        return path
            .extension()
            .and_then(|ext| ext.to_str())
            .is_some_and(|ext| ext.eq_ignore_ascii_case("exe"));
    }
    #[cfg(not(windows))]
    {
        true
    }
}

fn node_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("SZTU_OPENCLAW_NODE") {
        candidates.push(PathBuf::from(explicit));
    }
    #[cfg(windows)]
    {
        if let Ok(program_files) = std::env::var("ProgramFiles") {
            candidates.push(PathBuf::from(program_files).join("nodejs").join("node.exe"));
        }
        if let Ok(program_files) = std::env::var("ProgramFiles(x86)") {
            candidates.push(PathBuf::from(program_files).join("nodejs").join("node.exe"));
        }
        if let Some(appdata) = std::env::var_os("APPDATA") {
            let nvm = PathBuf::from(&appdata).join("nvm");
            if let Ok(entries) = std::fs::read_dir(&nvm) {
                let mut versions: Vec<PathBuf> = entries
                    .flatten()
                    .map(|entry| entry.path().join("node.exe"))
                    .filter(|path| path.is_file())
                    .collect();
                versions.sort();
                candidates.extend(versions.into_iter().rev());
            }
        }
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            candidates.push(
                PathBuf::from(local)
                    .join("Volta")
                    .join("bin")
                    .join("node.exe"),
            );
        }
    }
    #[cfg(not(windows))]
    {
        candidates.push(PathBuf::from("/usr/local/bin/node"));
        candidates.push(PathBuf::from("/usr/bin/node"));
        candidates.push(PathBuf::from("/opt/homebrew/bin/node"));
        if let Ok(home) = home_dir() {
            candidates.push(home.join(".local/bin/node"));
            candidates.push(home.join(".volta/bin/node"));
        }
    }
    if let Some(path) = std::env::var_os("PATH") {
        for dir in std::env::split_paths(&path) {
            candidates.push(dir.join(if cfg!(windows) { "node.exe" } else { "node" }));
        }
    }
    candidates
}

fn openclaw_mjs_candidates() -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(explicit) = std::env::var_os("SZTU_OPENCLAW_MJS") {
        candidates.push(PathBuf::from(explicit));
    }
    let relative = Path::new("node_modules")
        .join("openclaw")
        .join("openclaw.mjs");
    #[cfg(windows)]
    {
        if let Some(appdata) = std::env::var_os("APPDATA") {
            candidates.push(PathBuf::from(&appdata).join("npm").join(&relative));
        }
        if let Some(local) = std::env::var_os("LOCALAPPDATA") {
            candidates.push(
                PathBuf::from(&local)
                    .join("pnpm")
                    .join("global")
                    .join("5")
                    .join(&relative),
            );
        }
    }
    if let Ok(home) = home_dir() {
        candidates.push(home.join(".npm-global/lib").join(&relative));
        candidates.push(home.join(".bun/install/global").join(&relative));
    }
    candidates.push(PathBuf::from("/usr/local/lib").join(&relative));
    candidates.push(PathBuf::from("/usr/lib").join(&relative));
    candidates.push(PathBuf::from("/opt/homebrew/lib").join(&relative));
    candidates
}

/// Pick how to invoke OpenClaw, preferring `node.exe openclaw.mjs` because an
/// extensionless `node` shim breaks OpenClaw's internal re-spawn.
pub fn resolve_openclaw() -> Option<Launcher> {
    if let Some(explicit) = std::env::var_os("SZTU_OPENCLAW_BIN") {
        let path = PathBuf::from(explicit);
        if is_executable_file(&path) {
            return Some(Launcher {
                program: path,
                args: Vec::new(),
            });
        }
    }

    let mjs = openclaw_mjs_candidates()
        .into_iter()
        .find(|path| path.is_file());
    let node = node_candidates()
        .into_iter()
        .find(|path| is_usable_node(path));
    if let (Some(node), Some(mjs)) = (node, mjs) {
        return Some(Launcher {
            program: node,
            args: vec![mjs.to_string_lossy().into_owned()],
        });
    }

    None
}

// ---------------------------------------------------------------------------
// Status derivation
// ---------------------------------------------------------------------------

/// Map the observed facts onto the state machine the panel renders.
pub fn resolve_state(
    cli_available: bool,
    snapshot: &ChannelSnapshot,
    account_index: &[String],
    login_active: bool,
) -> &'static str {
    if !cli_available || !snapshot.plugin_enabled {
        return "unavailable";
    }
    if login_active {
        return "pending";
    }
    if snapshot.channel_enabled
        && (!account_index.is_empty()
            || !snapshot.accounts.is_empty()
            || snapshot.default_account.is_some())
    {
        return "connected";
    }
    "disconnected"
}

fn describe_launcher_error() -> Option<String> {
    if resolve_openclaw().is_some() {
        return None;
    }
    Some(
        "未找到可用的 OpenClaw 启动方式：需要 node.exe 与 openclaw.mjs（或设置 SZTU_OPENCLAW_BIN）。"
            .to_string(),
    )
}

// ---------------------------------------------------------------------------
// Login process state
// ---------------------------------------------------------------------------

#[derive(Clone, Default)]
pub struct WeChatLoginProcess {
    child: Arc<StdMutex<Option<Child>>>,
    stdout: Arc<StdMutex<String>>,
    stderr: Arc<StdMutex<String>>,
}

impl WeChatLoginProcess {
    pub fn new() -> Self {
        Self::default()
    }

    fn stop(&self) {
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
        self.clear_buffers();
    }

    fn clear_buffers(&self) {
        if let Ok(mut buffer) = self.stdout.lock() {
            buffer.clear();
        }
        if let Ok(mut buffer) = self.stderr.lock() {
            buffer.clear();
        }
    }

    fn stdout_snapshot(&self) -> String {
        self.stdout
            .lock()
            .map(|buffer| buffer.clone())
            .unwrap_or_default()
    }

    fn output_snapshot(&self) -> String {
        let stdout = self.stdout_snapshot();
        let stderr = self
            .stderr
            .lock()
            .map(|buffer| buffer.clone())
            .unwrap_or_default();
        if stderr.is_empty() {
            stdout
        } else if stdout.is_empty() {
            stderr
        } else {
            format!("{stdout}\n{stderr}")
        }
    }

    fn stderr_tail(&self) -> String {
        let text = self
            .stderr
            .lock()
            .map(|buffer| buffer.clone())
            .unwrap_or_default();
        let lines: Vec<&str> = text
            .lines()
            .filter(|line| !line.trim().is_empty())
            .collect();
        let start = lines.len().saturating_sub(6);
        strip_ansi(&lines[start..].join("\n"))
    }

    fn running(&self) -> bool {
        match self.child.lock() {
            Ok(mut guard) => match guard.as_mut() {
                Some(child) => matches!(child.try_wait(), Ok(None)),
                None => false,
            },
            Err(_) => false,
        }
    }
}

// ---------------------------------------------------------------------------
// Tauri commands
// ---------------------------------------------------------------------------

#[tauri::command]
pub fn wechat_status(state: State<'_, WeChatLoginProcess>) -> WeChatStatus {
    let mut bridge = load_bridge_state();
    let cli_available = resolve_openclaw().is_some();
    let snapshot = std::fs::read_to_string(openclaw_config_path().unwrap_or_default())
        .map(|text| channel_snapshot(&text, DEFAULT_CHANNEL))
        .unwrap_or_default();
    let account_index = read_account_index();

    let output = parse_login_output(&state.output_snapshot());
    let account_ready = !account_index.is_empty()
        || !snapshot.accounts.is_empty()
        || snapshot.default_account.is_some();
    let mut login_active = false;
    if let Some(record) = bridge.login.clone() {
        let expired = record.expires_at <= now_secs();
        match output.connected || account_ready {
            true => bridge.login = None,
            false if expired || !state.running() => bridge.login = None,
            false => login_active = true,
        }
    }
    let _ = save_bridge_state(&bridge);

    let account = snapshot
        .default_account
        .clone()
        .or_else(|| account_index.first().cloned())
        .or_else(|| snapshot.accounts.first().cloned());

    let resolved_state =
        if output.connected && cli_available && snapshot.plugin_enabled && snapshot.channel_enabled
        {
            "connected"
        } else {
            resolve_state(cli_available, &snapshot, &account_index, login_active)
        };

    WeChatStatus {
        state: resolved_state,
        account,
        bound_session_id: bridge.bound_session_id,
        last_error: describe_launcher_error(),
    }
}

#[tauri::command]
pub async fn wechat_login_start(
    state: State<'_, WeChatLoginProcess>,
) -> Result<Option<WeChatLoginTicket>, String> {
    let Some(launcher) = resolve_openclaw() else {
        return Ok(None);
    };

    state.stop();
    let mut command = launcher.command();
    command
        .arg("channels")
        .arg("login")
        .arg("--channel")
        .arg(DEFAULT_CHANNEL)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    let mut child = command
        .spawn()
        .map_err(|error| format!("无法启动 openclaw: {error}"))?;
    let pid = child.id();

    if let Some(stdout) = child.stdout.take() {
        let buffer = Arc::clone(&state.stdout);
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(mut guard) = buffer.lock() {
                    guard.push_str(&line);
                    guard.push('\n');
                }
            }
        });
    }
    if let Some(stderr) = child.stderr.take() {
        let buffer = Arc::clone(&state.stderr);
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                if let Ok(mut guard) = buffer.lock() {
                    guard.push_str(&line);
                    guard.push('\n');
                }
            }
        });
    }

    if let Ok(mut guard) = state.child.lock() {
        *guard = Some(child);
    }

    // Wait for the QR to appear; the process stays alive afterwards so the
    // user can actually scan it.
    let deadline = Instant::now() + QR_WAIT;
    loop {
        let parsed = parse_login_output(&state.output_snapshot());
        if parsed.qr.is_some() || parsed.link.is_some() {
            let qr = parsed
                .qr
                .clone()
                .or_else(|| parsed.link.clone())
                .unwrap_or_default();
            let started = now_secs();
            let expires = started + LOGIN_TTL_SECS;
            let mut bridge = load_bridge_state();
            bridge.channel = Some(DEFAULT_CHANNEL.to_string());
            bridge.login = Some(LoginRecord {
                pid,
                started_at: started,
                expires_at: expires,
                connected: false,
            });
            let _ = save_bridge_state(&bridge);
            return Ok(Some(WeChatLoginTicket {
                qr,
                link: parsed.link,
                expires_at: Some(expires.to_string()),
            }));
        }
        if !state.running() {
            let tail = state.stderr_tail();
            state.stop();
            return Err(if tail.is_empty() {
                "openclaw 未输出二维码就退出了".to_string()
            } else {
                format!("openclaw 未输出二维码就退出了：{tail}")
            });
        }
        if Instant::now() >= deadline {
            state.stop();
            return Err("等待二维码超时，请确认 OpenClaw 与微信插件配置正常".to_string());
        }
        std::thread::sleep(Duration::from_millis(200));
    }
}

#[tauri::command]
pub fn wechat_login_cancel(state: State<'_, WeChatLoginProcess>) -> bool {
    state.stop();
    let mut bridge = load_bridge_state();
    bridge.login = None;
    save_bridge_state(&bridge).is_ok()
}

#[tauri::command]
pub fn wechat_bind_session(session_id: String) -> bool {
    let trimmed = session_id.trim();
    if trimmed.is_empty() {
        return false;
    }
    let mut bridge = load_bridge_state();
    bridge.bound_session_id = Some(trimmed.to_string());
    save_bridge_state(&bridge).is_ok()
}

#[tauri::command]
pub fn wechat_unbind_session() -> bool {
    let mut bridge = load_bridge_state();
    bridge.bound_session_id = None;
    save_bridge_state(&bridge).is_ok()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    const CONFIG: &str = r#"{
        "plugins": { "entries": { "openclaw-weixin": { "enabled": true } } },
        "channels": {
            "openclaw-weixin": {
                "enabled": true,
                "defaultAccount": "acct-a",
                "accounts": { "acct-a": { "token": "x" }, "acct-b": {} }
            }
        }
    }"#;

    #[test]
    fn snapshot_reads_plugin_and_channel_state() {
        let snapshot = channel_snapshot(CONFIG, DEFAULT_CHANNEL);
        assert!(snapshot.plugin_enabled);
        assert!(snapshot.channel_enabled);
        assert_eq!(snapshot.default_account.as_deref(), Some("acct-a"));
        let mut accounts = snapshot.accounts.clone();
        accounts.sort();
        assert_eq!(accounts, vec!["acct-a", "acct-b"]);
    }

    #[test]
    fn snapshot_defaults_to_disabled_plugin_and_enabled_channel() {
        let snapshot = channel_snapshot("{}", DEFAULT_CHANNEL);
        assert!(!snapshot.plugin_enabled);
        assert!(snapshot.channel_enabled);
        assert!(snapshot.accounts.is_empty());
    }

    #[test]
    fn snapshot_tolerates_invalid_json() {
        assert_eq!(
            channel_snapshot("not json", DEFAULT_CHANNEL),
            ChannelSnapshot::default()
        );
    }

    #[test]
    fn snapshot_respects_disabled_channel() {
        let config = r#"{"plugins":{"entries":{"openclaw-weixin":{"enabled":true}}},
            "channels":{"openclaw-weixin":{"enabled":false}}}"#;
        assert!(!channel_snapshot(config, DEFAULT_CHANNEL).channel_enabled);
    }

    #[test]
    fn parse_login_output_extracts_qr_block_and_link() {
        // Trimmed copy of real output from `openclaw channels login`.
        let output = "\u{1b}[33m正在启动...\u{1b}[0m\n\n用手机微信扫描以下二维码，以继续连接：\n\n▄▄▄▄▄▄▄\n█ ▄▄▄ █\n█ █▄▄ █\n▄▄▄▄▄▄▄\n\n若二维码未能显示或无法使用，你可以访问以下链接以继续：\nhttps://liteapp.weixin.qq.com/q/abc?qrcode=1&bot_type=3\n\n正在等待操作...\n";
        let parsed = parse_login_output(output);
        assert_eq!(
            parsed.qr.as_deref(),
            Some("▄▄▄▄▄▄▄\n█ ▄▄▄ █\n█ █▄▄ █\n▄▄▄▄▄▄▄")
        );
        assert_eq!(
            parsed.link.as_deref(),
            Some("https://liteapp.weixin.qq.com/q/abc?qrcode=1&bot_type=3")
        );
        assert!(!parsed.connected);
    }

    #[test]
    fn parse_login_output_keeps_longest_block_run() {
        let output = "█\nnoise\n\n▄▄\n██\n▀▀\n";
        assert_eq!(parse_login_output(output).qr.as_deref(), Some("▄▄\n██\n▀▀"));
    }

    #[test]
    fn parse_login_output_detects_confirmed_scan() {
        let parsed = parse_login_output("正在等待操作...\n登录成功\n");
        assert!(parsed.connected);
        assert!(parsed.qr.is_none());
    }

    #[test]
    fn parse_login_output_detects_english_success_markers() {
        assert!(parse_login_output("scan succeeded\n").connected);
        assert!(parse_login_output("Authenticated with WeChat\n").connected);
    }

    #[test]
    fn resolve_state_covers_every_branch() {
        let connected = ChannelSnapshot {
            plugin_enabled: true,
            channel_enabled: true,
            default_account: None,
            accounts: vec!["acct".into()],
        };
        assert_eq!(resolve_state(false, &connected, &[], false), "unavailable");
        assert_eq!(resolve_state(true, &connected, &[], true), "pending");
        assert_eq!(resolve_state(true, &connected, &[], false), "connected");
        assert_eq!(
            resolve_state(true, &connected, &["acct".into()], false),
            "connected"
        );

        let empty = ChannelSnapshot {
            plugin_enabled: true,
            channel_enabled: true,
            default_account: None,
            accounts: Vec::new(),
        };
        assert_eq!(resolve_state(true, &empty, &[], false), "disconnected");
        assert_eq!(
            resolve_state(true, &ChannelSnapshot::default(), &[], false),
            "unavailable"
        );
    }

    #[test]
    fn resolve_state_ignores_accounts_when_channel_disabled() {
        let disabled = ChannelSnapshot {
            plugin_enabled: true,
            channel_enabled: false,
            default_account: None,
            accounts: vec!["acct".into()],
        };
        assert_eq!(resolve_state(true, &disabled, &[], false), "disconnected");
    }

    #[test]
    fn resolve_state_accepts_default_account_without_index() {
        let snapshot = ChannelSnapshot {
            plugin_enabled: true,
            channel_enabled: true,
            default_account: Some("acct-default".into()),
            accounts: Vec::new(),
        };
        assert_eq!(resolve_state(true, &snapshot, &[], false), "connected");
    }

    #[test]
    fn collect_account_ids_accepts_supported_index_shapes() {
        let value = serde_json::json!({
            "accounts": [{"accountId": "acct-a"}, {"id": "acct-b"}]
        });
        let mut ids = Vec::new();
        collect_account_ids(&value, &mut ids);
        ids.sort();
        assert_eq!(ids, vec!["acct-a", "acct-b"]);

        let value = serde_json::json!({"acct-c": {"token": "x"}});
        let mut ids = Vec::new();
        collect_account_ids(&value, &mut ids);
        assert_eq!(ids, vec!["acct-c"]);
    }

    #[test]
    fn usable_node_requires_exe_suffix_on_windows() {
        let shim = PathBuf::from("C:/Users/test/bin/node");
        #[cfg(windows)]
        assert!(!is_usable_node(&shim));
        #[cfg(not(windows))]
        assert!(!is_usable_node(&shim));
    }
}
