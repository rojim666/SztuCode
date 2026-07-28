use std::{path::PathBuf, process::Stdio, sync::Arc};

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
            if child.try_wait().map_err(|error| error.to_string())?.is_none() {
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
        command.args(args).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
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
        if current.as_ref().is_some_and(|active| Arc::ptr_eq(active, &writer)) {
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
        .invoke_handler(tauri::generate_handler![ipc_connect, ipc_send, daemon_start])
        .setup(|app| {
            let window = app.get_webview_window("main").expect("main window exists");
            window.set_focus().expect("focus main window");
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running SztuCode desktop");
}
