use std::{
    collections::HashMap,
    fs,
    io::{Read, Write},
    path::{Path, PathBuf},
    process::Command as StdCommand,
    process::Stdio,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex as StdMutex, OnceLock,
    },
};

use base64::Engine;
use portable_pty::{CommandBuilder, MasterPty, NativePtySystem, PtySize, PtySystem};
use serde::{Deserialize, Serialize};
use tauri::{
    path::BaseDirectory,
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Listener, Manager, State, WebviewWindow, Window,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{tcp::OwnedWriteHalf, TcpStream},
    process::{Child, Command},
    sync::Mutex,
    time::{sleep, Duration},
};

#[cfg(target_os = "macos")]
mod macos_work_area;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[derive(Clone)]
struct IpcConnection {
    writer: Arc<Mutex<Option<Arc<Mutex<OwnedWriteHalf>>>>>,
    generation: Arc<Mutex<u64>>,
}

impl IpcConnection {
    fn new() -> Self {
        Self {
            writer: Arc::new(Mutex::new(None)),
            generation: Arc::new(Mutex::new(0)),
        }
    }
}

#[derive(Clone)]
struct DaemonProcess {
    child: Arc<Mutex<Option<Child>>>,
}

impl DaemonProcess {
    fn new() -> Self {
        Self {
            child: Arc::new(Mutex::new(None)),
        }
    }
}

#[derive(Serialize)]
struct DaemonStartResult {
    status: String,
    detail: String,
}

#[derive(Serialize)]
struct NativeSettingsResult {
    autostart: bool,
    stay_awake: bool,
    supported: bool,
    theme: String,
    wallpaper: String,
}

/// 桌面端外观设置（主题/壁纸），持久化到 ~/.sztu/desktop-settings.json
#[derive(Serialize, Deserialize)]
struct DesktopAppearance {
    theme: String,
    wallpaper: String,
}

impl Default for DesktopAppearance {
    fn default() -> Self {
        Self {
            theme: "light".into(),
            wallpaper: "none".into(),
        }
    }
}

fn desktop_settings_path() -> Result<PathBuf, String> {
    let home = std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .ok_or_else(|| "无法确定用户目录".to_string())?;
    Ok(PathBuf::from(home)
        .join(".sztu")
        .join("desktop-settings.json"))
}

fn load_appearance() -> DesktopAppearance {
    desktop_settings_path()
        .ok()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

fn save_appearance(appearance: &DesktopAppearance) -> Result<(), String> {
    let path = desktop_settings_path()?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let text = serde_json::to_string_pretty(appearance).map_err(|error| error.to_string())?;
    std::fs::write(path, text).map_err(|error| error.to_string())
}

#[derive(Deserialize)]
struct WorkspaceRecord {
    path: String,
}

struct PtySession {
    master: Box<dyn MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child: Box<dyn portable_pty::Child + Send + Sync>,
}

struct PtySessions {
    sessions: StdMutex<HashMap<String, PtySession>>,
}

impl PtySessions {
    fn new() -> Self {
        Self {
            sessions: StdMutex::new(HashMap::new()),
        }
    }
}

impl Drop for PtySession {
    fn drop(&mut self) {
        let _ = self.child.kill();
    }
}

#[derive(Clone, Serialize)]
struct PtyOutput {
    session_id: String,
    data: Vec<u8>,
}

static STAY_AWAKE: AtomicBool = AtomicBool::new(false);

#[cfg(windows)]
static WAKE_SENDER: OnceLock<mpsc::Sender<bool>> = OnceLock::new();

#[cfg(windows)]
#[link(name = "kernel32")]
extern "system" {
    fn SetThreadExecutionState(es_flags: u32) -> u32;
}

#[cfg(windows)]
fn wake_sender() -> &'static mpsc::Sender<bool> {
    WAKE_SENDER.get_or_init(|| {
        let (sender, receiver) = mpsc::channel::<bool>();
        std::thread::spawn(move || {
            const ES_CONTINUOUS: u32 = 0x8000_0000;
            const ES_SYSTEM_REQUIRED: u32 = 0x0000_0001;
            while let Ok(enabled) = receiver.recv() {
                let flags = if enabled {
                    ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                } else {
                    ES_CONTINUOUS
                };
                unsafe {
                    SetThreadExecutionState(flags);
                }
            }
        });
        sender
    })
}

#[cfg(windows)]
fn autostart_enabled() -> bool {
    std::process::Command::new("reg.exe")
        .args([
            "query",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            "SztuCode",
        ])
        .creation_flags(0x0800_0000)
        .status()
        .is_ok_and(|status| status.success())
}

#[cfg(not(windows))]
fn autostart_enabled() -> bool {
    false
}

#[cfg(windows)]
fn update_autostart(enabled: bool) -> Result<(), String> {
    let mut command = std::process::Command::new("reg.exe");
    command.creation_flags(0x0800_0000);
    if enabled {
        let executable = std::env::current_exe().map_err(|error| error.to_string())?;
        command.args([
            "add",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            "SztuCode",
            "/t",
            "REG_SZ",
            "/d",
            &format!(r#""{}""#, executable.display()),
            "/f",
        ]);
    } else {
        command.args([
            "delete",
            r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
            "/v",
            "SztuCode",
            "/f",
        ]);
    }
    let output = command.output().map_err(|error| error.to_string())?;
    if output.status.success() {
        Ok(())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).trim().to_string())
    }
}

#[cfg(not(windows))]
fn update_autostart(_enabled: bool) -> Result<(), String> {
    Err("autostart is currently supported on Windows only".into())
}

#[tauri::command]
fn native_settings_get() -> NativeSettingsResult {
    let appearance = load_appearance();
    NativeSettingsResult {
        autostart: autostart_enabled(),
        stay_awake: STAY_AWAKE.load(Ordering::Relaxed),
        supported: cfg!(windows),
        theme: appearance.theme,
        wallpaper: appearance.wallpaper,
    }
}

#[tauri::command]
fn native_settings_update(
    autostart: Option<bool>,
    stay_awake: Option<bool>,
    theme: Option<String>,
    wallpaper: Option<String>,
) -> Result<NativeSettingsResult, String> {
    if theme
        .as_deref()
        .is_some_and(|value| !matches!(value, "system" | "light" | "dark"))
    {
        return Err("unsupported desktop theme".into());
    }
    if wallpaper
        .as_deref()
        .is_some_and(|value| !matches!(value, "none" | "mist" | "grid" | "paper" | "custom"))
    {
        return Err("unsupported desktop wallpaper".into());
    }
    if let Some(enabled) = autostart {
        update_autostart(enabled)?;
    }
    if let Some(enabled) = stay_awake {
        #[cfg(windows)]
        wake_sender()
            .send(enabled)
            .map_err(|error| format!("failed to update wake state: {error}"))?;
        #[cfg(not(windows))]
        if enabled {
            return Err("keep-awake is currently supported on Windows only".into());
        }
        STAY_AWAKE.store(enabled, Ordering::Relaxed);
    }
    if theme.is_some() || wallpaper.is_some() {
        let mut appearance = load_appearance();
        if let Some(value) = theme {
            appearance.theme = value;
        }
        if let Some(value) = wallpaper {
            appearance.wallpaper = value;
        }
        save_appearance(&appearance)?;
    }
    Ok(native_settings_get())
}

fn registered_workspace(requested: &str) -> Result<PathBuf, String> {
    let canonical = PathBuf::from(requested)
        .canonicalize()
        .map_err(|error| format!("无法访问当前项目目录：{error}"))?;
    if !canonical.is_dir() {
        return Err("当前项目路径不是目录".into());
    }
    let home = std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .ok_or_else(|| "无法确定用户目录".to_string())?;
    let registry_path = PathBuf::from(home).join(".sztu").join("workspaces.json");
    let registry = std::fs::read_to_string(&registry_path)
        .map_err(|error| format!("无法读取项目登记信息：{error}"))?;
    let records: Vec<WorkspaceRecord> = serde_json::from_str(&registry)
        .map_err(|error| format!("项目登记信息格式无效：{error}"))?;
    let registered = records.into_iter().any(|record| {
        PathBuf::from(record.path)
            .canonicalize()
            .is_ok_and(|path| path == canonical)
    });
    if !registered {
        return Err("仅允许在已登记的当前项目目录中执行命令".into());
    }
    #[cfg(windows)]
    {
        let path = canonical.to_string_lossy();
        if let Some(unc) = path.strip_prefix(r"\\?\UNC\") {
            return Ok(PathBuf::from(format!(r"\\{unc}")));
        }
        if let Some(local) = path.strip_prefix(r"\\?\") {
            return Ok(PathBuf::from(local));
        }
    }
    Ok(canonical)
}

fn pty_size(cols: u16, rows: u16) -> PtySize {
    PtySize {
        rows: rows.clamp(1, 500),
        cols: cols.clamp(1, 500),
        pixel_width: 0,
        pixel_height: 0,
    }
}

#[tauri::command]
fn sandbox_pty_start(
    session_id: String,
    workspace_path: String,
    cols: u16,
    rows: u16,
    window: Window,
    state: State<'_, PtySessions>,
) -> Result<(), String> {
    if session_id.is_empty() || session_id.len() > 128 {
        return Err("Invalid terminal session ID".into());
    }
    let workspace = registered_workspace(&workspace_path)?;
    let mut sessions = state
        .sessions
        .lock()
        .map_err(|_| "Terminal session manager is unavailable".to_string())?;
    if sessions.contains_key(&session_id) {
        return Err("Terminal session already exists".into());
    }

    let pair = NativePtySystem::default()
        .openpty(pty_size(cols, rows))
        .map_err(|error| format!("Unable to create terminal: {error}"))?;
    let mut command = CommandBuilder::new("powershell.exe");
    command.args(["-NoLogo", "-NoProfile"]);
    command.cwd(&workspace);
    let child = pair
        .slave
        .spawn_command(command)
        .map_err(|error| format!("Unable to start PowerShell: {error}"))?;
    drop(pair.slave);
    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|error| format!("Unable to read terminal output: {error}"))?;
    let writer = pair
        .master
        .take_writer()
        .map_err(|error| format!("Unable to open terminal input: {error}"))?;

    let output_session_id = session_id.clone();
    std::thread::spawn(move || {
        let mut buffer = [0_u8; 8192];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => break,
                Ok(length) => {
                    let payload = PtyOutput {
                        session_id: output_session_id.clone(),
                        data: buffer[..length].to_vec(),
                    };
                    if window.emit("sandbox:pty-output", payload).is_err() {
                        break;
                    }
                }
                Err(_) => break,
            }
        }
    });

    sessions.insert(
        session_id,
        PtySession {
            master: pair.master,
            writer,
            child,
        },
    );
    Ok(())
}

#[tauri::command]
fn sandbox_pty_write(
    session_id: String,
    data: String,
    state: State<'_, PtySessions>,
) -> Result<(), String> {
    let mut sessions = state
        .sessions
        .lock()
        .map_err(|_| "Terminal session manager is unavailable".to_string())?;
    let session = sessions
        .get_mut(&session_id)
        .ok_or_else(|| "Terminal session is not running".to_string())?;
    session
        .writer
        .write_all(data.as_bytes())
        .and_then(|_| session.writer.flush())
        .map_err(|error| format!("Unable to write to terminal: {error}"))
}

#[tauri::command]
fn sandbox_pty_resize(
    session_id: String,
    cols: u16,
    rows: u16,
    state: State<'_, PtySessions>,
) -> Result<(), String> {
    let sessions = state
        .sessions
        .lock()
        .map_err(|_| "Terminal session manager is unavailable".to_string())?;
    let session = sessions
        .get(&session_id)
        .ok_or_else(|| "Terminal session is not running".to_string())?;
    session
        .master
        .resize(pty_size(cols, rows))
        .map_err(|error| format!("Unable to resize terminal: {error}"))
}

#[tauri::command]
fn sandbox_pty_close(session_id: String, state: State<'_, PtySessions>) -> Result<(), String> {
    let mut session = state
        .sessions
        .lock()
        .map_err(|_| "Terminal session manager is unavailable".to_string())?
        .remove(&session_id);
    if let Some(session) = session.as_mut() {
        let _ = session.child.kill();
    }
    Ok(())
}

fn daemon_candidates(app: &tauri::AppHandle) -> Vec<(PathBuf, Vec<String>, Option<PathBuf>)> {
    let mut candidates = Vec::new();
    if let Ok(executable) = std::env::var("SZTU_DAEMON_EXECUTABLE") {
        candidates.push((PathBuf::from(executable), Vec::new(), None));
    }
    if let Ok(runtime) = app.path().resolve("resources/runtime/main.js", BaseDirectory::Resource) {
        if runtime.exists() {
            let runtime = child_path(&runtime);
            let bundled_node = runtime
                .parent()
                .map(|directory| directory.join(if cfg!(windows) { "node.exe" } else { "node" }));
            if let Some(node) = bundled_node.filter(|path| path.exists()) {
                candidates.push((
                    node,
                    vec![runtime.to_string_lossy().into_owned()],
                    runtime.parent().map(PathBuf::from),
                ));
            }
            candidates.push((
                PathBuf::from("node"),
                vec![runtime.to_string_lossy().into_owned()],
                runtime.parent().map(PathBuf::from),
            ));
        }
    }
    #[cfg(debug_assertions)]
    {
    let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|desktop| desktop.parent())
        .map(PathBuf::from);
    if let Some(root) = repository {
        let runtime = root
            .join("packages")
            .join("runtime-ts")
            .join("dist")
            .join("main.js");
        if runtime.exists() {
            candidates.push((
                PathBuf::from("node"),
                vec![runtime.to_string_lossy().into_owned()],
                Some(root.clone()),
            ));
        }
    }
    }
    candidates
}

fn daemon_log_path() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE")
        .or_else(|| std::env::var_os("HOME"))
        .map(|home| PathBuf::from(home).join(".sztu").join("logs").join("desktop-daemon.log"))
}

fn child_path(path: &PathBuf) -> PathBuf {
    #[cfg(windows)]
    {
        let text = path.to_string_lossy();
        if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
            return PathBuf::from(format!(r"\\{unc}"));
        }
        if let Some(local) = text.strip_prefix(r"\\?\") {
            return PathBuf::from(local);
        }
    }
    path.clone()
}

fn daemon_log_tail(path: &PathBuf) -> String {
    std::fs::read_to_string(path)
        .ok()
        .map(|text| text.lines().rev().take(12).collect::<Vec<_>>().into_iter().rev().collect::<Vec<_>>().join(" | "))
        .unwrap_or_default()
}

#[tauri::command]
async fn daemon_start(app: tauri::AppHandle, state: State<'_, DaemonProcess>) -> Result<DaemonStartResult, String> {
    if TcpStream::connect(("127.0.0.1", 7438)).await.is_ok() {
        return Ok(DaemonStartResult {
            status: "already_running".into(),
            detail: "本地服务已在运行".into(),
        });
    }
    {
        let mut active = state.child.lock().await;
        if let Some(child) = active.as_mut() {
            if child
                .try_wait()
                .map_err(|error| error.to_string())?
                .is_none()
            {
                return Ok(DaemonStartResult {
                    status: "starting".into(),
                    detail: "本地服务正在启动".into(),
                });
            }
        }
        *active = None;
    }

    let mut errors = Vec::new();
    let log_path = daemon_log_path();
    if let Some(path) = log_path.as_ref() {
        if let Some(parent) = path.parent() {
            let _ = std::fs::create_dir_all(parent);
        }
        let _ = std::fs::write(path, "");
    }
    for (executable, args, current_dir) in daemon_candidates(&app) {
        if executable.is_absolute() && !executable.exists() {
            continue;
        }
        let mut command = Command::new(&executable);
        command
            .args(&args)
            .env("SZTU_TS_PORT", "7438")
            .stdin(Stdio::null());
        if let Some(path) = log_path.as_ref() {
            match std::fs::OpenOptions::new().create(true).append(true).open(path) {
                Ok(mut log) => {
                    let _ = writeln!(log, "starting {} {}", executable.display(), args.join(" "));
                    match log.try_clone() {
                        Ok(stdout) => {
                            command.stdout(Stdio::from(stdout)).stderr(Stdio::from(log));
                        }
                        Err(_) => {
                            command.stdout(Stdio::null()).stderr(Stdio::from(log));
                        }
                    }
                }
                Err(_) => {
                    command.stdout(Stdio::null()).stderr(Stdio::null());
                }
            }
        } else {
            command.stdout(Stdio::null()).stderr(Stdio::null());
        }
        if let Some(directory) = current_dir {
            command.current_dir(directory);
        }
        #[cfg(windows)]
        command.as_std_mut().creation_flags(0x0800_0000);
        match command.spawn() {
            Ok(child) => {
                *state.child.lock().await = Some(child);
                for _ in 0..40 {
                    if TcpStream::connect(("127.0.0.1", 7438)).await.is_ok() {
                        return Ok(DaemonStartResult {
                            status: "started".into(),
                            detail: "本地服务已启动".into(),
                        });
                    }
                    let exited = {
                        let mut active = state.child.lock().await;
                        active
                            .as_mut()
                            .and_then(|process| process.try_wait().ok().flatten())
                            .is_some()
                    };
                    if exited {
                        let tail = log_path.as_ref().map(daemon_log_tail).unwrap_or_default();
                        errors.push(format!("{} exited during startup{}", executable.display(), if tail.is_empty() { String::new() } else { format!(": {tail}") }));
                        *state.child.lock().await = None;
                        break;
                    }
                    sleep(Duration::from_millis(125)).await;
                }
                if state.child.lock().await.is_some() {
                    return Ok(DaemonStartResult {
                        status: "starting".into(),
                        detail: "进程已启动，正在等待服务端口".into(),
                    });
                }
            }
            Err(error) => errors.push(format!("{}: {error}", executable.display())),
        }
    }
    Err(format!(
        "未找到可启动的 SztuCode daemon。{}",
        errors.join("；")
    ))
}

// 附件读取结果：图片/二进制走 base64，文本走 UTF-8 内容，超限或不支持在 error 里说明
#[derive(Serialize)]
struct AttachmentData {
    path: String,
    name: String,
    size: u64,
    mime_type: Option<String>,
    is_text: bool,
    text_content: Option<String>,
    data_base64: Option<String>,
    error: Option<String>,
}

const IMAGE_MAX_BYTES: u64 = 5 * 1024 * 1024;
const TEXT_MAX_BYTES: u64 = 1024 * 1024;
const TEXT_READ_LIMIT: usize = 32 * 1024;

// 按扩展名推断常见文件的 MIME 类型；未知类型返回 None
fn guess_mime(path: &PathBuf) -> Option<String> {
    let ext = path.extension()?.to_string_lossy().to_lowercase();
    let mime = match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "bmp" => "image/bmp",
        "svg" => "image/svg+xml",
        "pdf" => "application/pdf",
        "txt" | "md" | "markdown" => "text/plain",
        "csv" => "text/csv",
        "html" | "htm" => "text/html",
        "css" => "text/css",
        "js" | "mjs" | "cjs" => "text/javascript",
        "ts" | "tsx" => "text/typescript",
        "jsx" => "text/jsx",
        "py" => "text/x-python",
        "rs" => "text/x-rust",
        "go" => "text/x-go",
        "java" => "text/x-java",
        "c" | "h" => "text/x-c",
        "cpp" | "cc" | "hpp" => "text/x-c++",
        "sh" | "bash" => "text/x-sh",
        "yaml" | "yml" => "text/yaml",
        "toml" => "text/toml",
        "xml" => "text/xml",
        "sql" => "text/x-sql",
        "json" | "json5" => "application/json",
        _ => return None,
    };
    Some(mime.to_string())
}

fn is_image(mime: &str) -> bool {
    mime.starts_with("image/")
}

// 前 8KB 出现 NUL 字节即视为二进制
fn looks_binary(bytes: &[u8]) -> bool {
    bytes.iter().take(8192).any(|&byte| byte == 0)
}

// 读取单个附件：任何失败都落到 error 字段，不中断整批
fn read_one_attachment(path: &str) -> AttachmentData {
    let pb = PathBuf::from(path);
    let name = pb
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string());
    let failed = |size: u64, mime: Option<String>, error: String| AttachmentData {
        path: path.to_string(),
        name: name.clone(),
        size,
        mime_type: mime,
        is_text: false,
        text_content: None,
        data_base64: None,
        error: Some(error),
    };
    let metadata = match std::fs::metadata(&pb) {
        Ok(meta) => meta,
        Err(error) => return failed(0, None, format!("无法读取文件：{error}")),
    };
    let size = metadata.len();
    let mime = guess_mime(&pb);
    let is_img = mime.as_deref().is_some_and(is_image);
    if is_img && size > IMAGE_MAX_BYTES {
        return failed(size, mime, "图片超过 5MB 限制".into());
    }
    if !is_img && size > TEXT_MAX_BYTES {
        return failed(size, mime, "文件超过 1MB 限制".into());
    }
    let mut data = Vec::new();
    if let Err(error) = std::fs::File::open(&pb).and_then(|mut file| file.read_to_end(&mut data)) {
        return failed(size, mime, format!("读取失败：{error}"));
    }
    if !looks_binary(&data) {
        let text: String = String::from_utf8_lossy(&data).chars().take(TEXT_READ_LIMIT).collect();
        return AttachmentData {
            path: path.to_string(),
            name,
            size,
            mime_type: mime,
            is_text: true,
            text_content: Some(text),
            data_base64: None,
            error: None,
        };
    }
    let encoded = base64::engine::general_purpose::STANDARD.encode(&data);
    AttachmentData {
        path: path.to_string(),
        name,
        size,
        mime_type: mime,
        is_text: false,
        text_content: None,
        data_base64: Some(encoded),
        error: None,
    }
}

// 读取「添加附件」选中的文件内容：图片/二进制返回 base64，文本返回内容，逐文件报告错误
#[tauri::command]
fn read_attachment(paths: Vec<String>) -> Result<Vec<AttachmentData>, String> {
    Ok(paths.iter().map(|path| read_one_attachment(path)).collect())
}

// Connect to the TypeScript daemon and relay NDJSON messages to the frontend SDK.
#[tauri::command]
async fn ipc_connect(
    host: String,
    port: u16,
    window: Window,
    state: State<'_, IpcConnection>,
) -> Result<(), String> {
    let stream = TcpStream::connect((host.as_str(), port))
        .await
        .map_err(|error| format!("无法连接本地服务：{error}"))?;
    let (reader, writer) = stream.into_split();
    let writer = Arc::new(Mutex::new(writer));
    let connection = state.inner().clone();
    let generation = {
        let mut current = connection.generation.lock().await;
        *current += 1;
        *current
    };
    *connection.writer.lock().await = Some(writer);

    tauri::async_runtime::spawn(async move {
        let mut lines = BufReader::new(reader).lines();
        let reason = loop {
            match lines.next_line().await {
                Ok(Some(line)) => {
                    if window.emit("sztu:message", line).is_err() {
                        break "frontend window is no longer available".to_string();
                    }
                }
                Ok(None) => break "daemon closed the connection".to_string(),
                Err(error) => break error.to_string(),
            }
        };
        if *connection.generation.lock().await == generation {
            *connection.writer.lock().await = None;
            let _ = window.emit("sztu:disconnected", reason);
        }
    });
    Ok(())
}

// 通过已建立的单一 TCP 连接发送一条 JSON-RPC NDJSON 帧。
#[tauri::command]
async fn ipc_send(payload: String, state: State<'_, IpcConnection>) -> Result<(), String> {
    let writer = state
        .writer
        .lock()
        .await
        .clone()
        .ok_or_else(|| "本地服务尚未连接".to_string())?;
    let result: Result<(), std::io::Error> = async {
        let mut writer_lock = writer.lock().await;
        writer_lock.write_all(payload.as_bytes()).await?;
        writer_lock.write_all(b"\n").await?;
        writer_lock.flush().await?;
        Ok(())
    }
    .await;
    if let Err(error) = result {
        let mut current = state.writer.lock().await;
        if current
            .as_ref()
            .is_some_and(|active| Arc::ptr_eq(active, &writer))
        {
            *current = None;
        }
        return Err(format!("发送 IPC 请求失败：{error}"));
    }
    Ok(())
}

// macOS：无动画铺满/还原工作区（避开 NSWindow.zoom 与 WKWebView 不同步）
#[tauri::command]
fn macos_toggle_work_area(window: WebviewWindow) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        macos_work_area::toggle_work_area(&window)
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = window;
        Err("macos_toggle_work_area is only available on macOS".into())
    }
}

#[tauri::command]
fn create_persistent_worktree(workspace_path: String, worktree_id: String, label: String) -> Result<serde_json::Value, String> {
    let root = Path::new(&workspace_path);
    if !root.is_dir() { return Err("项目目录不存在".into()); }
    let repository_check = StdCommand::new("git")
        .args(["-C", &workspace_path, "rev-parse", "--verify", "HEAD"])
        .output()
        .map_err(|error| format!("无法执行 Git：{error}"))?;
    if !repository_check.status.success() {
        return Err("当前项目不是有效的 Git 仓库，或仓库还没有任何提交。请先初始化 Git 并至少提交一次。".into());
    }
    let short_id: String = worktree_id.chars().filter(|ch| ch.is_ascii_alphanumeric()).take(12).collect();
    if short_id.is_empty() { return Err("聊天 ID 无效".into()); }
    let project_name = root.file_name().and_then(|name| name.to_str()).unwrap_or("project");
    let worktree_root = root.parent().unwrap_or(root).join(".sztu-worktrees").join(project_name);
    fs::create_dir_all(&worktree_root).map_err(|error| format!("无法创建工作树目录：{error}"))?;
    let safe_label: String = label.chars().filter(|ch| ch.is_ascii_alphanumeric() || *ch == '-').take(24).collect();
    let safe_label = if safe_label.is_empty() { "worktree".to_string() } else { safe_label };
    let target = worktree_root.join(format!("{safe_label}-{short_id}"));
    let branch = format!("sztucode/{safe_label}-{short_id}");
    if target.exists() { return Err(format!("该聊天的永久工作树已存在：{}", target.display())); }
    let output = StdCommand::new("git")
        .args(["-C", &workspace_path, "worktree", "add", "-b", &branch])
        .arg(&target)
        .arg("HEAD")
        .output()
        .map_err(|error| format!("无法执行 Git：{error}"))?;
    if !output.status.success() {
        let detail = String::from_utf8_lossy(&output.stderr).trim().to_string();
        return Err(if detail.is_empty() { "创建永久工作树失败".into() } else { format!("创建永久工作树失败：{detail}") });
    }
    Ok(serde_json::json!({ "path": target.to_string_lossy().to_string(), "branch": branch }))
}

#[cfg(windows)]
fn ide_candidates() -> Vec<(PathBuf, Vec<String>)> {
    let mut candidates = Vec::new();
    if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA") {
        let programs = PathBuf::from(local_app_data).join("Programs");
        candidates.push((programs.join("Microsoft VS Code").join("Code.exe"), Vec::new()));
        candidates.push((programs.join("Cursor").join("Cursor.exe"), Vec::new()));
    }
    if let Some(path) = std::env::var_os("PATH") {
        for directory in std::env::split_paths(&path) {
            for launcher in ["code.cmd", "code.exe", "code", "cursor.cmd", "cursor.exe", "cursor"] {
                let entry = directory.join(launcher);
                if !entry.is_file() {
                    continue;
                }
                for ancestor in entry.ancestors().skip(1).take(5) {
                    for executable in ["Code.exe", "Cursor.exe"] {
                        let candidate = ancestor.join(executable);
                        if candidate.is_file() && !candidates.iter().any(|(path, _)| path == &candidate) {
                            candidates.push((candidate, Vec::new()));
                        }
                    }
                }
            }
        }
    }
    candidates.push((PathBuf::from("code.exe"), Vec::new()));
    candidates.push((PathBuf::from("cursor.exe"), Vec::new()));
    candidates
}

#[cfg(target_os = "macos")]
fn ide_candidates() -> Vec<(PathBuf, Vec<String>)> {
    vec![
        (PathBuf::from("open"), vec!["-a".into(), "Visual Studio Code".into()]),
        (PathBuf::from("open"), vec!["-a".into(), "Cursor".into()]),
        (PathBuf::from("code"), Vec::new()),
        (PathBuf::from("cursor"), Vec::new()),
    ]
}

#[cfg(all(unix, not(target_os = "macos")))]
fn ide_candidates() -> Vec<(PathBuf, Vec<String>)> {
    vec![
        (PathBuf::from("code"), Vec::new()),
        (PathBuf::from("cursor"), Vec::new()),
        (PathBuf::from("codium"), Vec::new()),
    ]
}

#[derive(Deserialize)]
struct WorkspacePathRecord {
    workspace_id: String,
    path: String,
}

fn workspace_path_for_id(workspace_id: &str) -> Option<PathBuf> {
    let data_root = std::env::var_os("SZTU_DATA_DIR")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("USERPROFILE").map(|home| PathBuf::from(home).join(".sztu")))
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".sztu")))?;
    let records = fs::read_to_string(data_root.join("workspaces.json")).ok()?;
    let records = serde_json::from_str::<Vec<WorkspacePathRecord>>(&records).ok()?;
    records
        .into_iter()
        .find(|record| record.workspace_id == workspace_id)
        .map(|record| PathBuf::from(record.path))
}

#[derive(Serialize)]
struct ExternalApp {
    id: String,
    name: String,
    icon: String,
    available: bool,
}

#[tauri::command]
fn list_external_apps() -> Vec<ExternalApp> {
    #[cfg(windows)]
    {
        let local_app_data = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
        let program_files = std::env::var_os("ProgramFiles").map(PathBuf::from);

        let check_path = |p: &Path| p.exists();
        let mut apps = Vec::new();

        // TraeCode CN
        let trae_cn = local_app_data
            .as_ref()
            .map(|d| d.join("Programs").join("Trae CN").join("Trae CN.exe"))
            .filter(|p| check_path(p));
        apps.push(ExternalApp {
            id: "trae-cn".into(),
            name: "TraeCode CN".into(),
            icon: "trae".into(),
            available: trae_cn.is_some(),
        });

        // TraeCode
        let trae = local_app_data
            .as_ref()
            .map(|d| d.join("Programs").join("Trae").join("Trae.exe"))
            .filter(|p| check_path(p));
        apps.push(ExternalApp {
            id: "trae".into(),
            name: "TraeCode".into(),
            icon: "trae".into(),
            available: trae.is_some(),
        });

        // VS Code
        let vscode = local_app_data
            .as_ref()
            .map(|d| d.join("Programs").join("Microsoft VS Code").join("Code.exe"))
            .filter(|p| check_path(p))
            .or_else(|| {
                program_files
                    .as_ref()
                    .map(|d| d.join("Microsoft VS Code").join("Code.exe"))
                    .filter(|p| check_path(p))
            });
        apps.push(ExternalApp {
            id: "vscode".into(),
            name: "Visual Studio Code".into(),
            icon: "vscode".into(),
            available: vscode.is_some(),
        });

        // Cursor
        let cursor = local_app_data
            .as_ref()
            .map(|d| d.join("Programs").join("Cursor").join("Cursor.exe"))
            .filter(|p| check_path(p));
        apps.push(ExternalApp {
            id: "cursor".into(),
            name: "Cursor".into(),
            icon: "cursor".into(),
            available: cursor.is_some(),
        });

        // WebStorm (check common JetBrains paths)
        let webstorm = if let Some(pf) = program_files.as_ref() {
            let jetbrains = pf.join("JetBrains");
            let mut found = None;
            if let Ok(entries) = fs::read_dir(&jetbrains) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().to_lowercase();
                    if name.starts_with("webstorm") {
                        let exe = entry.path().join("bin").join("webstorm64.exe");
                        if exe.exists() {
                            found = Some(exe);
                            break;
                        }
                    }
                }
            }
            found
        } else {
            None
        };
        apps.push(ExternalApp {
            id: "webstorm".into(),
            name: "WebStorm".into(),
            icon: "webstorm".into(),
            available: webstorm.is_some(),
        });

        // File explorer (always available on Windows)
        apps.push(ExternalApp {
            id: "explorer".into(),
            name: "文件资源管理器".into(),
            icon: "folder".into(),
            available: true,
        });

        // Default app
        apps.push(ExternalApp {
            id: "default".into(),
            name: "默认应用".into(),
            icon: "default".into(),
            available: true,
        });

        apps
    }

    #[cfg(target_os = "macos")]
    {
        let check_app = |name: &str| {
            PathBuf::from("/Applications")
                .join(format!("{name}.app"))
                .exists()
        };
        let mut apps = Vec::new();

        apps.push(ExternalApp { id: "trae-cn".into(), name: "TraeCode CN".into(), icon: "trae".into(), available: check_app("Trae CN") });
        apps.push(ExternalApp { id: "trae".into(), name: "TraeCode".into(), icon: "trae".into(), available: check_app("Trae") });
        apps.push(ExternalApp { id: "vscode".into(), name: "Visual Studio Code".into(), icon: "vscode".into(), available: check_app("Visual Studio Code") });
        apps.push(ExternalApp { id: "cursor".into(), name: "Cursor".into(), icon: "cursor".into(), available: check_app("Cursor") });
        apps.push(ExternalApp { id: "webstorm".into(), name: "WebStorm".into(), icon: "webstorm".into(), available: check_app("WebStorm") });
        apps.push(ExternalApp { id: "explorer".into(), name: "访达".into(), icon: "folder".into(), available: true });
        apps.push(ExternalApp { id: "default".into(), name: "默认应用".into(), icon: "default".into(), available: true });

        apps
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let in_path = |cmd: &str| {
            std::env::var_os("PATH").map(|p| {
                std::env::split_paths(&p).any(|dir| dir.join(cmd).is_file())
            }).unwrap_or(false)
        };
        vec![
            ExternalApp { id: "vscode".into(), name: "Visual Studio Code".into(), icon: "vscode".into(), available: in_path("code") },
            ExternalApp { id: "cursor".into(), name: "Cursor".into(), icon: "cursor".into(), available: in_path("cursor") },
            ExternalApp { id: "explorer".into(), name: "文件管理器".into(), icon: "folder".into(), available: true },
            ExternalApp { id: "default".into(), name: "默认应用".into(), icon: "default".into(), available: true },
        ]
    }
}

fn app_command_for_id(app_id: &str, target: &Path) -> Result<StdCommand, String> {
    match app_id {
        "explorer" => {
            #[cfg(windows)]
            {
                let mut cmd = StdCommand::new("explorer.exe");
                if target.is_dir() {
                    cmd.arg(target);
                } else {
                    cmd.arg("/select,");
                    cmd.arg(target);
                }
                return Ok(cmd);
            }
            #[cfg(target_os = "macos")]
            {
                let mut cmd = StdCommand::new("open");
                cmd.arg("-R");
                cmd.arg(target);
                return Ok(cmd);
            }
            #[cfg(all(unix, not(target_os = "macos")))]
            {
                let mut cmd = StdCommand::new("xdg-open");
                cmd.arg(target.parent().unwrap_or(target));
                return Ok(cmd);
            }
        }
        "default" => {
            #[cfg(windows)]
            {
                let mut cmd = StdCommand::new("cmd");
                cmd.args(["/c", "start", ""]);
                cmd.arg(target);
                return Ok(cmd);
            }
            #[cfg(target_os = "macos")]
            {
                let mut cmd = StdCommand::new("open");
                cmd.arg(target);
                return Ok(cmd);
            }
            #[cfg(all(unix, not(target_os = "macos")))]
            {
                let mut cmd = StdCommand::new("xdg-open");
                cmd.arg(target);
                return Ok(cmd);
            }
        }
        other => {
            let (exe, args) = resolve_editor_path(other)?;
            let mut cmd = StdCommand::new(&exe);
            cmd.args(&args);
            cmd.arg(target);
            Ok(cmd)
        }
    }
}

#[cfg(windows)]
fn resolve_editor_path(app_id: &str) -> Result<(PathBuf, Vec<String>), String> {
    let local_app_data = std::env::var_os("LOCALAPPDATA").map(PathBuf::from);
    let program_files = std::env::var_os("ProgramFiles").map(PathBuf::from);

    match app_id {
        "trae-cn" => {
            let p = local_app_data
                .ok_or("缺少 LOCALAPPDATA")?
                .join("Programs").join("Trae CN").join("Trae CN.exe");
            if p.is_file() { Ok((p, Vec::new())) } else { Err("Trae CN 未安装".into()) }
        }
        "trae" => {
            let p = local_app_data
                .ok_or("缺少 LOCALAPPDATA")?
                .join("Programs").join("Trae").join("Trae.exe");
            if p.is_file() { Ok((p, Vec::new())) } else { Err("Trae 未安装".into()) }
        }
        "vscode" => {
            let p = local_app_data
                .as_ref()
                .map(|d| d.join("Programs").join("Microsoft VS Code").join("Code.exe"))
                .filter(|p| p.is_file())
                .or_else(|| program_files.as_ref().map(|d| d.join("Microsoft VS Code").join("Code.exe")).filter(|p| p.is_file()))
                .ok_or("VS Code 未安装")?;
            Ok((p, Vec::new()))
        }
        "cursor" => {
            let p = local_app_data
                .ok_or("缺少 LOCALAPPDATA")?
                .join("Programs").join("Cursor").join("Cursor.exe");
            if p.is_file() { Ok((p, Vec::new())) } else { Err("Cursor 未安装".into()) }
        }
        "webstorm" => {
            let pf = program_files.ok_or("缺少 ProgramFiles")?;
            let jetbrains = pf.join("JetBrains");
            let mut found = None;
            if let Ok(entries) = fs::read_dir(&jetbrains) {
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().to_lowercase();
                    if name.starts_with("webstorm") {
                        let exe = entry.path().join("bin").join("webstorm64.exe");
                        if exe.exists() { found = Some(exe); break; }
                    }
                }
            }
            found.map(|p| (p, Vec::new())).ok_or_else(|| "WebStorm 未安装".into())
        }
        _ => Err(format!("未知应用：{app_id}")),
    }
}

#[cfg(target_os = "macos")]
fn resolve_editor_path(app_id: &str) -> Result<(PathBuf, Vec<String>), String> {
    let (app_name, args) = match app_id {
        "trae-cn" => ("Trae CN", vec!["-a".into(), "Trae CN".into()]),
        "trae" => ("Trae", vec!["-a".into(), "Trae".into()]),
        "vscode" => ("Visual Studio Code", vec!["-a".into(), "Visual Studio Code".into()]),
        "cursor" => ("Cursor", vec!["-a".into(), "Cursor".into()]),
        "webstorm" => ("WebStorm", vec!["-a".into(), "WebStorm".into()]),
        _ => return Err(format!("未知应用：{app_id}")),
    };
    let app_path = PathBuf::from("/Applications").join(format!("{app_name}.app"));
    if app_path.exists() {
        Ok((PathBuf::from("open"), args))
    } else {
        Err(format!("{app_name} 未安装"))
    }
}

#[cfg(all(unix, not(target_os = "macos")))]
fn resolve_editor_path(app_id: &str) -> Result<(PathBuf, Vec<String>), String> {
    let cmd = match app_id {
        "vscode" => "code",
        "cursor" => "cursor",
        _ => return Err(format!("未知应用：{app_id}")),
    };
    Ok((PathBuf::from(cmd), Vec::new()))
}

#[tauri::command]
fn open_path_with_app(path: String, app_id: String) -> Result<(), String> {
    let target = PathBuf::from(&path);
    // allow file to not exist for edge cases, but most apps will handle it
    let mut cmd = app_command_for_id(&app_id, &target)?;
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000);
    cmd.spawn().map_err(|e| format!("启动失败：{e}"))?;
    Ok(())
}

#[tauri::command]
fn open_workspace_in_ide(workspace_path: String, workspace_id: Option<String>) -> Result<(), String> {
    let workspace_id = workspace_id.and_then(|id| {
        let trimmed = id.trim().to_string();
        (!trimmed.is_empty()).then_some(trimmed)
    });
    let workspace = workspace_id
        .as_deref()
        .and_then(workspace_path_for_id)
        .unwrap_or_else(|| PathBuf::from(&workspace_path));
    if !workspace.is_dir() {
        return Err(format!("项目目录不存在：{}", workspace.display()));
    }

    let mut errors = Vec::new();
    for (executable, args) in ide_candidates() {
        if executable.is_absolute() && !executable.is_file() {
            continue;
        }
        let mut command = StdCommand::new(&executable);
        command
            .args(&args)
            .arg(&workspace)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        command.creation_flags(0x0800_0000);
        match command.spawn() {
            Ok(_) => return Ok(()),
            Err(error) => errors.push(format!("{}: {error}", executable.display())),
        }
    }

    let detail = errors.last().map(String::as_str).unwrap_or("未找到可用的 IDE");
    Err(format!("无法启动 VS Code 或 Cursor。请先安装其中一个并确保命令可用。{detail}"))
}

// ── 内置浏览器 webview 控制（JS API 不含 navigate/eval/url，经 Rust 桥接实现）──

#[tauri::command]
fn browser_webview_eval(app: tauri::AppHandle, label: String, code: String) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("webview {label} 不存在"))?;
    webview.eval(&code).map_err(|error| error.to_string())
}

#[tauri::command]
fn browser_webview_url(app: tauri::AppHandle, label: String) -> Result<String, String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("webview {label} 不存在"))?;
    let url = webview.url().map_err(|error| error.to_string())?;
    Ok(url.to_string())
}

#[tauri::command]
fn browser_webview_navigate(
    app: tauri::AppHandle,
    label: String,
    url: String,
) -> Result<(), String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("webview {label} 不存在"))?;
    let parsed: tauri::Url = url
        .parse()
        .map_err(|error| format!("无效的 URL：{error}"))?;
    webview.navigate(parsed).map_err(|error| error.to_string())
}

#[tauri::command]
fn browser_webview_toggle_devtools(
    app: tauri::AppHandle,
    label: String,
) -> Result<bool, String> {
    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("webview {label} 不存在"))?;
    #[cfg(any(debug_assertions, feature = "devtools"))]
    {
        if webview.is_devtools_open() {
            webview.close_devtools();
            Ok(false)
        } else {
            webview.open_devtools();
            Ok(true)
        }
    }
    #[cfg(not(any(debug_assertions, feature = "devtools")))]
    {
        let _ = webview;
        Err("DevTools 仅在开发模式或启用 devtools 特性时可用".into())
    }
}

// ── 元素选择器数据桥（原生 WebMessage 通道）──
// 注入页面通过 chrome.webview.postMessage('__szpk__:<json>') 回传选中元素。
// 该消息同时会到达 Tauri 的 IPC 入口（格式不符被忽略，无副作用），
// 本命令在目标 webview 上额外注册一个 WebView2 WebMessageReceived 监听器，
// 匹配前缀后经 Tauri 事件 sztu:element-picked 广播给主窗口——
// 完全绕开远程页面的 IPC/ACL 限制，不产生导航，不打扰页面路由。

#[cfg(windows)]
#[tauri::command]
fn browser_webview_attach_picker(app: tauri::AppHandle, label: String) -> Result<(), String> {
    use webview2_com::WebMessageReceivedEventHandler;
    use windows::core::PWSTR;

    let webview = app
        .get_webview(&label)
        .ok_or_else(|| format!("webview {label} 不存在"))?;
    let handler_app = app.clone();
    let handler_label = label;
    webview
        .with_webview(move |platform_webview| unsafe {
            let Ok(core) = platform_webview.controller().CoreWebView2() else {
                return;
            };
            let handler = WebMessageReceivedEventHandler::create(Box::new(
                move |_sender, args| {
                    let Some(args) = args else {
                        return Ok(());
                    };
                    let mut message = PWSTR::null();
                    if args.TryGetWebMessageAsString(&mut message).is_ok() {
                        let text = webview2_com::take_pwstr(message);
                        if let Some(payload) = text.strip_prefix("__szpk__:") {
                            let _ = handler_app.emit(
                                "sztu:element-picked",
                                serde_json::json!({
                                    "label": handler_label,
                                    "payload": payload,
                                }),
                            );
                        }
                    }
                    Ok(())
                },
            ));
            let mut token: i64 = 0;
            let _ = core.add_WebMessageReceived(&handler, &mut token);
        })
        .map_err(|error| error.to_string())
}

#[cfg(not(windows))]
#[tauri::command]
fn browser_webview_attach_picker(_app: tauri::AppHandle, _label: String) -> Result<(), String> {
    // 非 Windows 平台没有 WebView2 原生消息桥；前端注入脚本会自动退化为 hash 回传通道
    Err("元素选择器原生数据通道仅在 Windows (WebView2) 上可用".into())
}

// 主入口：注册受控 IPC 桥与系统目录选择能力。
fn main() {
    tauri::Builder::default()
        .manage(IpcConnection::new())
        .manage(DaemonProcess::new())
        .manage(PtySessions::new())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            ipc_connect,
            ipc_send,
            daemon_start,
            native_settings_get,
            native_settings_update,
            sandbox_pty_start,
            sandbox_pty_write,
            sandbox_pty_resize,
            sandbox_pty_close,
            read_attachment,
            create_persistent_worktree,
            list_external_apps,
            open_path_with_app,
            open_workspace_in_ide,
            browser_webview_eval,
            browser_webview_url,
            browser_webview_navigate,
            browser_webview_toggle_devtools,
            browser_webview_attach_picker,
            macos_toggle_work_area
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").expect("main window exists");
            if let Some(icon) = app.default_window_icon() {
                window.set_icon(icon.clone())?;
            }

            // 每次启动时重置窗口大小为默认值并居中，避免记住上次调整的尺寸
            let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize::new(1440.0, 920.0)));
            let _ = window.center();

            let tray_window = window.clone();
            let app_handle = app.handle().clone();
            app.listen("tray://quit", move |_| app_handle.exit(0));
            if let Some(menu_window) = app.get_webview_window("tray-menu") {
                let menu_for_events = menu_window.clone();
                menu_window.on_window_event(move |event| {
                    if let tauri::WindowEvent::Focused(false) = event {
                        let _ = menu_for_events.hide();
                    }
                });
            }
            TrayIconBuilder::new()
                .icon(app.default_window_icon().expect("application icon").clone())
                .tooltip("SztuCode")
                .show_menu_on_left_click(false)
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        if let Some(menu) = tray_window.app_handle().get_webview_window("tray-menu") {
                            let _ = menu.hide();
                        }
                        let _ = tray_window.show();
                        let _ = tray_window.set_focus();
                    } else if let TrayIconEvent::Click {
                        button: MouseButton::Right,
                        button_state: MouseButtonState::Up,
                        position,
                        ..
                    } = event {
                        if let Some(menu) = tray_window.app_handle().get_webview_window("tray-menu") {
                            if menu.is_visible().unwrap_or(false) {
                                let _ = menu.hide();
                                return;
                            }
                            // 以托盘图标右上角为锚点，菜单贴在图标左上侧；
                            // 同时限制在当前屏幕工作区内，避免任务栏/多屏时跑出屏幕。
                            // 托盘事件给出物理像素坐标；窗口配置是逻辑像素，需要按 DPI 换算。
                            let scale = menu.scale_factor().unwrap_or(1.0);
                            let size = tauri::PhysicalSize::new(
                                (300.0 * scale).round() as u32,
                                (338.0 * scale).round() as u32,
                            );
                            let monitor = menu.current_monitor().ok().flatten();
                            let (left, top, right, bottom) = monitor
                                .map(|m| {
                                    let p = m.position(); let s = m.size();
                                    (p.x, p.y, p.x + s.width as i32, p.y + s.height as i32)
                                })
                                .unwrap_or((0, 0, i32::MAX, i32::MAX));
                            let x = ((position.x as i32) - size.width as i32).clamp(left, right - size.width as i32);
                            let y = ((position.y as i32) - size.height as i32 - 4).clamp(top, bottom - size.height as i32);
                            let _ = menu.set_position(tauri::PhysicalPosition::new(x, y));
                            let _ = menu.show();
                            let _ = menu.set_focus();
                        }
                    }
                })
                .build(app)?;

            let close_window = window.clone();
            window.on_window_event(move |event| {
                if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                    api.prevent_close();
                    let _ = close_window.hide();
                }
            });
            #[cfg(target_os = "macos")]
            {
                use window_vibrancy::{apply_vibrancy, NSVisualEffectMaterial};
                // 锁定浅色窗口主题，避免 Sidebar vibrancy 跟随系统深色模式
                let _ = window.set_theme(Some(tauri::Theme::Light));
                // Sidebar 材质更透一些，贴近 Cursor/Codex 浅色毛玻璃
                let _ = apply_vibrancy(&window, NSVisualEffectMaterial::Sidebar, None, None);
                // 拖边缘改大小时逐帧重绘，避免 WKWebView 旧帧缩放造成 8px 边距跳变
                let _ = macos_work_area::disable_live_resize_preserve(&window);
                let window_for_resize = window.clone();
                window.on_window_event(move |event| {
                    if let tauri::WindowEvent::Resized(_) = event {
                        macos_work_area::sync_webview_to_content_view(&window_for_resize);
                    }
                });
            }
            window.set_focus().expect("focus main window");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running SztuCode desktop");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc::{self, Receiver};

    struct TestPty {
        _master: Box<dyn MasterPty + Send>,
        writer: Box<dyn Write + Send>,
        child: Box<dyn portable_pty::Child + Send + Sync>,
        output: Receiver<Vec<u8>>,
    }

    impl TestPty {
        fn start(cwd: &std::path::Path) -> Self {
            let pair = NativePtySystem::default()
                .openpty(pty_size(100, 30))
                .expect("create test PTY");
            let mut command = CommandBuilder::new("powershell.exe");
            command.args(["-NoLogo", "-NoProfile"]);
            command.cwd(cwd);
            let child = pair
                .slave
                .spawn_command(command)
                .expect("start test PowerShell");
            drop(pair.slave);
            let mut reader = pair.master.try_clone_reader().expect("clone PTY reader");
            let writer = pair.master.take_writer().expect("take PTY writer");
            let (sender, output) = mpsc::channel();
            std::thread::spawn(move || {
                let mut buffer = [0_u8; 4096];
                while let Ok(length) = reader.read(&mut buffer) {
                    if length == 0 || sender.send(buffer[..length].to_vec()).is_err() {
                        break;
                    }
                }
            });
            Self {
                _master: pair.master,
                writer,
                child,
                output,
            }
        }

        fn send(&mut self, input: &str) {
            self.writer
                .write_all(input.as_bytes())
                .expect("write PTY input");
            self.writer.flush().expect("flush PTY input");
        }

        fn read_until(&self, marker: &str) -> String {
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
            let mut output = String::new();
            while std::time::Instant::now() < deadline {
                let remaining = deadline.saturating_duration_since(std::time::Instant::now());
                match self.output.recv_timeout(remaining) {
                    Ok(bytes) => {
                        output.push_str(&String::from_utf8_lossy(&bytes));
                        if output.contains(marker) {
                            return output;
                        }
                    }
                    Err(_) => break,
                }
            }
            panic!("PTY output did not contain {marker:?}: {output:?}");
        }
    }

    impl Drop for TestPty {
        fn drop(&mut self) {
            let _ = self.child.kill();
        }
    }

    #[test]
    fn sandbox_rejects_unregistered_workspace() {
        let temporary =
            std::env::temp_dir().join(format!("sztucode-sandbox-test-{}", std::process::id()));
        std::fs::create_dir_all(&temporary).expect("temporary directory");
        let result = registered_workspace(temporary.to_string_lossy().as_ref());
        let _ = std::fs::remove_dir(&temporary);
        assert!(result.is_err());
    }

    #[test]
    fn worktree_rejects_non_git_directory_without_creating_storage() {
        let temporary = std::env::temp_dir().join(format!(
            "sztucode-worktree-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .expect("system time")
                .as_nanos()
        ));
        let project = temporary.join("project");
        std::fs::create_dir_all(&project).expect("temporary project directory");

        let result = create_persistent_worktree(
            project.to_string_lossy().into_owned(),
            "workspace-123".into(),
            "project".into(),
        );

        assert!(result.is_err());
        assert!(!temporary.join(".sztu-worktrees").exists());
        let _ = std::fs::remove_dir_all(&temporary);
    }

    #[test]
    #[cfg(windows)]
    fn pty_sessions_are_interactive_and_independent() {
        let workspace = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("desktop directory")
            .parent()
            .expect("workspace directory")
            .canonicalize()
            .expect("canonical workspace");
        let workspace_text = workspace.to_string_lossy();
        let expected_path = workspace_text
            .strip_prefix(r"\\?\")
            .unwrap_or(workspace_text.as_ref());
        let shell_workspace = PathBuf::from(expected_path);
        let mut first = TestPty::start(&shell_workspace);
        let mut second = TestPty::start(&shell_workspace);

        first.send("\x1b[1;1R");
        second.send("\x1b[1;1R");
        first.send("$terminalValue='one'\r");
        second.send("$terminalValue='two'\r");
        first.send("[Console]::Out.WriteLine(\"PTY_FIRST:$terminalValue\")\r");
        second.send("[Console]::Out.WriteLine(\"PTY_SECOND:$terminalValue\")\r");
        first.send("[Console]::Out.WriteLine(\"PTY_CWD:$((Get-Location).Path)\")\r");

        assert!(first.read_until("PTY_FIRST:one").contains("PTY_FIRST:one"));
        assert!(second
            .read_until("PTY_SECOND:two")
            .contains("PTY_SECOND:two"));
        let expected_cwd = format!("PTY_CWD:{expected_path}");
        let cwd_output = first.read_until(&expected_cwd);
        assert!(cwd_output.contains(&expected_cwd));
    }
}
