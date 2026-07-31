use std::{
    path::PathBuf,
    process::Stdio,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, OnceLock,
    },
};

use serde::Serialize;
use tauri::{Emitter, Manager, State, Window};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{tcp::OwnedWriteHalf, TcpStream},
    process::{Child, Command},
    sync::Mutex,
    time::{sleep, Duration},
};

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
    NativeSettingsResult {
        autostart: autostart_enabled(),
        stay_awake: STAY_AWAKE.load(Ordering::Relaxed),
        supported: cfg!(windows),
    }
}

#[tauri::command]
fn native_settings_update(
    autostart: Option<bool>,
    stay_awake: Option<bool>,
) -> Result<NativeSettingsResult, String> {
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
    Ok(native_settings_get())
}

fn daemon_candidates() -> Vec<(PathBuf, Vec<String>, Option<PathBuf>)> {
    let mut candidates = Vec::new();
    if let Ok(executable) = std::env::var("SZTU_DAEMON_EXECUTABLE") {
        candidates.push((PathBuf::from(executable), Vec::new(), None));
    }
    if let Ok(current) = std::env::current_exe() {
        if let Some(parent) = current.parent() {
            candidates.push((parent.join("sztu-code.exe"), Vec::new(), None));
        }
    }
    let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|desktop| desktop.parent())
        .map(PathBuf::from);
    if let Some(root) = repository {
        let python = root.join(".venv").join("Scripts").join("python.exe");
        if python.exists() {
            candidates.push((
                python,
                vec!["-m".into(), "sztu_code.core".into()],
                Some(root),
            ));
        }
    }
    candidates.push((PathBuf::from("sztu-code"), Vec::new(), None));
    candidates
}

#[tauri::command]
async fn daemon_start(state: State<'_, DaemonProcess>) -> Result<DaemonStartResult, String> {
    if TcpStream::connect(("127.0.0.1", 7437)).await.is_ok() {
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
    for (executable, args, current_dir) in daemon_candidates() {
        if executable.is_absolute() && !executable.exists() {
            continue;
        }
        let mut command = Command::new(&executable);
        command
            .args(args)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        if let Some(directory) = current_dir {
            command.current_dir(directory);
        }
        #[cfg(windows)]
        command.as_std_mut().creation_flags(0x0800_0000);
        match command.spawn() {
            Ok(child) => {
                *state.child.lock().await = Some(child);
                for _ in 0..40 {
                    if TcpStream::connect(("127.0.0.1", 7437)).await.is_ok() {
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
                        errors.push(format!("{} exited during startup", executable.display()));
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

// 连接 Python daemon，并将 NDJSON 消息广播给 React 客户端 SDK。
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

// 主入口：注册受控 IPC 桥与系统目录选择能力。
fn main() {
    tauri::Builder::default()
        .manage(IpcConnection::new())
        .manage(DaemonProcess::new())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            ipc_connect,
            ipc_send,
            daemon_start,
            native_settings_get,
            native_settings_update
        ])
        .setup(|app| {
            let window = app.get_webview_window("main").expect("main window exists");
            window.set_focus().expect("focus main window");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running SztuCode desktop");
}
