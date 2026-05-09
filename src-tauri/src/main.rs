// Prevents an extra console window from appearing on Windows in release.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::api::path::resource_dir;
use tauri::{Manager, RunEvent, WindowEvent};

struct BackendState {
    child: Mutex<Option<Child>>,
}

fn pick_backend_port() -> u16 {
    if let Ok(port) = std::env::var("DATAFUSIONX_BACKEND_PORT") {
        if let Ok(parsed) = port.parse::<u16>() {
            return parsed;
        }
    }
    if let Ok(listener) = TcpListener::bind("127.0.0.1:0") {
        if let Ok(addr) = listener.local_addr() {
            return addr.port();
        }
    }
    8765
}

fn locate_backend(handle: &tauri::AppHandle) -> Option<PathBuf> {
    if let Ok(env_path) = std::env::var("DATAFUSIONX_BACKEND_EXE") {
        let p = PathBuf::from(env_path);
        if p.exists() {
            return Some(p);
        }
    }
    if let Some(dir) = handle
        .path_resolver()
        .resolve_resource("../backend-dist/backend.exe")
    {
        if dir.exists() {
            return Some(dir);
        }
    }
    if let Ok(env) = tauri::utils::platform::current_exe() {
        if let Some(parent) = env.parent() {
            let candidate = parent.join("backend").join("backend.exe");
            if candidate.exists() {
                return Some(candidate);
            }
            let alt = parent.join("backend.exe");
            if alt.exists() {
                return Some(alt);
            }
        }
    }
    if let Some(res_dir) = resource_dir(&handle.package_info(), &handle.env()).ok() {
        let candidate = res_dir.join("backend-dist").join("backend.exe");
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

fn spawn_backend(handle: &tauri::AppHandle, port: u16) -> Option<Child> {
    let exe = locate_backend(handle)?;
    let mut cmd = Command::new(exe);
    cmd.env("DATAFUSIONX_BACKEND_PORT", port.to_string())
        .env("DATAFUSIONX_HOST", "127.0.0.1")
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    cmd.spawn().ok()
}

fn wait_backend_ready(port: u16, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if std::net::TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(250));
    }
    false
}

#[tauri::command]
fn backend_url(state: tauri::State<u16>) -> String {
    format!("http://127.0.0.1:{}", *state)
}

fn main() {
    let port = pick_backend_port();

    tauri::Builder::default()
        .manage(port)
        .manage(BackendState { child: Mutex::new(None) })
        .invoke_handler(tauri::generate_handler![backend_url])
        .setup(move |app| {
            let handle = app.handle();
            let child = spawn_backend(&handle, port);
            if let Some(c) = child {
                let state: tauri::State<BackendState> = app.state();
                *state.child.lock().unwrap() = Some(c);
            }
            wait_backend_ready(port, Duration::from_secs(15));
            if let Some(window) = app.get_window("main") {
                let init_script = format!(
                    "window.DATAFUSIONX_API_BASE = 'http://127.0.0.1:{}';",
                    port
                );
                let _ = window.eval(&init_script);
            }
            Ok(())
        })
        .on_window_event(|event| {
            if let WindowEvent::Destroyed = event.event() {
                let app = event.window().app_handle();
                if let Some(state) = app.try_state::<BackendState>() {
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app.try_state::<BackendState>() {
                    if let Ok(mut guard) = state.child.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
